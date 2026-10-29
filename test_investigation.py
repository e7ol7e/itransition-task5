"""Reconciliation, detector evidence and immutable investigation contracts."""
import csv
import io
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from pypdf import PdfReader

import app
from analytics import Settings, analyze, grubbs, parse_csv
from investigation import inspect_day, parse_audit
from report import build_pdf


def fixture(*, weak=False, overlap=False):
    rows = [['kind', 'date_or_id'] + [f'actual_{i}' for i in range(1, 13)] +
            [f'no_event_{i}' for i in range(1, 13)] + [f'events_{i}' for i in range(1, 13)]]
    for i in range(1, 7):
        rows.append(['event', f'E{i}', f'Event {i}', '2026-01-06' if i == 1 or overlap and i == 2 else '2027-01-01',
                     '1', '1.01' if weak and i == 1 else '2' if i == 1 or overlap and i == 2 else '1', '0.5', '1'])
    rows.append(['mines', '', 'Alpha', 'Beta'] + [''] * 10)
    for index in range(10):
        injected = index == 5
        value = (101 if weak else 400 if overlap else 200) if injected else 100
        ids = ('E1|E2' if overlap else 'E1') if injected else ''
        rows.append(['observation', f'2026-01-{index+1:02d}', str(value), '100'] + [''] * 10 +
                    ['100', '100'] + [''] * 10 + [ids, ''] + [''] * 10)
    return rows


def export(rows):
    text = io.StringIO()
    csv.writer(text).writerows(rows)
    return text.getvalue()


def snapshot(**options):
    return parse_audit(export(fixture(**options)), parse_csv)


class InvestigationTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = snapshot()
        self.result = analyze(self.snapshot, Settings(moving_window=3))

    def test_data_and_audit_have_separate_content_identifiers(self):
        raw = parse_csv('Date,Alpha,Beta\n' + '\n'.join(f'{day},{row[0]},{row[1]}' for day, row in zip(self.snapshot['dates'], self.snapshot['values'])))
        self.assertEqual(self.snapshot['data_snapshot'], raw['snapshot'])
        self.assertNotEqual(self.snapshot['snapshot'], raw['snapshot'])
        rows = fixture(); rows[1][2] = 'Renamed event'
        changed = parse_audit(export(rows), parse_csv)
        self.assertEqual(changed['data_snapshot'], raw['snapshot'])
        self.assertNotEqual(changed['snapshot'], self.snapshot['snapshot'])

    def test_rejects_inconsistent_observed_output_and_labels(self):
        mutations = [(13, 2, '201'), (13, 26, ''), (13, 26, 'E1|E1'), (13, 26, 'E9'),
                     (13, 14, 'nan'), (8, 26, 'E1'), (1, 7, '2'), (1, 5, 'inf')]
        for row, column, value in mutations:
            with self.subTest(value=value, column=column):
                rows = fixture(); rows[row][column] = value
                with self.assertRaises(ValueError): parse_audit(export(rows), parse_csv)

    def test_material_labels_and_union_hits(self):
        total = self.result['series'][0]
        self.assertEqual(total['validation']['material_days'], 1)
        self.assertEqual(total['validation']['union']['material_hits'], 1)
        self.assertEqual(total['validation']['events'][0]['status'], 'Detected')
        self.assertEqual(total['validation']['events'][1]['status'], 'Neutral multiplier')
        self.assertEqual(total['validation']['days'][5]['counterfactual'], 200)
        self.assertEqual(total['validation']['days'][5]['delta'], 100)
        self.assertEqual(self.result['series'][2]['validation']['material_days'], 0)
        self.assertIsNone(self.result['series'][2]['validation']['union']['coverage_percent'])

    def test_reserved_network_name_is_rejected(self):
        rows = fixture(); rows[7][2] = 'Total'
        with self.assertRaisesRegex(ValueError, 'reserved'):
            parse_audit(export(rows), parse_csv)

    def test_weak_effect_and_overlapping_events_are_not_double_counted(self):
        weak = analyze(snapshot(weak=True), Settings())['series'][0]['validation']
        self.assertEqual(weak['material_days'], 0)
        self.assertEqual(weak['events'][0]['status'], 'No material days')
        overlapping = analyze(snapshot(overlap=True), Settings())['series'][0]['validation']
        self.assertEqual(overlapping['material_days'], 1)
        self.assertEqual(overlapping['days'][5]['events'], ['E1', 'E2'])
        self.assertEqual(overlapping['days'][5]['delta'], 300)

    def test_contributions_reconcile_in_warmup_and_complete_window(self):
        for day in ['2026-01-01', '2026-01-06']:
            evidence = inspect_day(self.result, 'Total', day)
            self.assertAlmostEqual(sum(row['actual'] for row in evidence['contributions']), evidence['value'])
            self.assertAlmostEqual(sum(row['baseline'] for row in evidence['contributions']), evidence['baseline'])
            self.assertAlmostEqual(sum(row['delta'] for row in evidence['contributions']), evidence['value']-evidence['baseline'])
        self.assertFalse(inspect_day(self.result, 'Alpha', '2026-01-01')['tests'][2]['eligible'])
        self.assertEqual(inspect_day(self.result, 'Alpha', '2026-01-06')['tests'][2]['flagged'], True)

    def test_disabled_methods_keep_evidence_but_leave_union(self):
        result = analyze(self.snapshot, Settings(methods=['grubbs'], grubbs_alpha=.001))
        series = result['series'][0]
        for row in series['comparison']['methods']:
            if row['method'] != 'grubbs': self.assertEqual(row['exclusive'], 0)
        evidence = inspect_day(result, 'Total', '2026-01-06')
        self.assertTrue(evidence['tests'][0]['flagged'])
        self.assertFalse(evidence['tests'][0]['enabled'])
        self.assertEqual(series['comparison']['union_count'], len(series['anomalies']))

    def test_grubbs_trace_records_rejection_and_stopping_candidate(self):
        values = [10, 11, 12, 10, 11, 12, 10, 11, 12, 100]
        trace = []
        original = grubbs(values, iterations=3)
        traced = grubbs(values, iterations=3, trace=trace)
        self.assertEqual(original, traced)
        self.assertEqual(trace[0]['candidate_index'], 9)
        self.assertTrue(trace[0]['rejected'])
        self.assertFalse(trace[1]['rejected'])
        evidence = inspect_day(self.result, 'Alpha', '2026-01-01')['tests'][3]
        self.assertIn('is not that candidate', evidence['calculation'])

    def test_constant_and_zero_baseline_evidence(self):
        raw = parse_csv('Date,A\n2026-01-01,0\n2026-01-02,0\n2026-01-03,0\n2026-01-04,5')
        result = analyze(raw, Settings(moving_window=3))
        evidence = inspect_day(result, 'A', '2026-01-04')
        self.assertTrue(evidence['tests'][2]['flagged'])
        self.assertIn('undefined', evidence['tests'][2]['calculation'])
        self.assertFalse(result['series'][0]['validation']['available'])

    def test_pdf_has_validation_and_network_evidence(self):
        pdf = build_pdf(self.result)
        text = '\n'.join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages)
        for value in ['Simulator', 'Material hits', 'Event 1', 'Grubbs pass evidence', 'Network deviation contributions', '0.01']:
            self.assertIn(value.lower(), text.lower())

    def test_inspector_uses_report_handle_without_refetching(self):
        app.snapshots[self.snapshot['snapshot']] = self.snapshot
        client = TestClient(app.app)
        data = client.post('/api/analyze', json={'snapshot':self.snapshot['snapshot']}).json()
        with patch.object(app, 'fetch_source', side_effect=AssertionError('must not refetch')):
            response = client.get('/api/inspect/'+data['report_id'], params={'series':'Total','date':'2026-01-06'})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['snapshot'], data['source']['snapshot'])
            self.assertEqual(response.headers['cache-control'], 'no-store')
        self.assertEqual(client.get('/api/inspect/'+data['report_id'], params={'series':'missing','date':'2026-01-06'}).status_code, 422)
        self.assertEqual(client.get('/api/inspect/'+'f'*24, params={'series':'Total','date':'2026-01-06'}).status_code, 409)


if __name__ == '__main__': unittest.main()
