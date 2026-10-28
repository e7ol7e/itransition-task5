"""Numerical references and regression checks, independent of Google availability."""
import io
import os
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['OMP_NUM_THREADS'] = '1'
import statistics
import unittest
from datetime import date, timedelta

import numpy as np
from pypdf import PdfReader

from analytics import Settings, analyze, analyze_series, grubbs, parse_csv
from report import build_pdf


def dates(n):
    return [(date(2026, 1, 1) + timedelta(days=i)).isoformat() for i in range(n)]


class StatisticsTests(unittest.TestCase):
    def test_nist_grubbs_reference(self):
        # NIST e-Handbook example: only the 245.57 observation is rejected.
        sample = [199.31,199.53,200.19,200.82,201.92,201.95,202.18,245.57]
        result = grubbs(sample)
        self.assertEqual(list(result), [7])
        self.assertAlmostEqual(result[7]['score'],2.4687,places=3)
        self.assertAlmostEqual(result[7]['critical'],2.1266,places=3)

    def test_sample_statistics_and_quartiles(self):
        values = [1,2,3,4,5,6,7,8]
        result = analyze_series('Mine',values,dates(8),Settings())
        self.assertEqual(result['stats']['mean'],statistics.mean(values))
        self.assertEqual(result['stats']['median'],statistics.median(values))
        self.assertAlmostEqual(result['stats']['std'],statistics.stdev(values))
        self.assertEqual(result['stats']['q1'],2.75)
        self.assertEqual(result['stats']['q3'],6.25)
        self.assertEqual(result['stats']['iqr'],3.5)

    def test_moving_window_does_not_include_tested_value(self):
        result=analyze_series('Mine',[10,10,10,100],dates(4),Settings(moving_window=3,moving_percent=40))
        self.assertEqual(result['moving_average'],[None,None,None,10.])
        self.assertEqual(result['flags']['moving'],[3])
        self.assertEqual(result['anomalies'][-1]['moving_percent'],900.)

    def test_constant_and_zero_output_are_finite(self):
        for value in [0,10]:
            result=analyze_series('Mine',[value]*30,dates(30),Settings())
            self.assertEqual(result['anomalies'],[])
            self.assertEqual(result['stats']['std'],0)
        result=analyze_series('Mine',[0,0,0,1],dates(4),Settings(moving_window=3))
        self.assertEqual(result['flags']['moving'],[3])

    def test_total_is_daily_sum_and_has_its_own_tests(self):
        snapshot={'dates':dates(4),'mines':['A','B'],'values':[[1,9],[2,8],[3,7],[4,6]],'snapshot':'a'*16,'fetched_at':'now'}
        result=analyze(snapshot,Settings())
        self.assertEqual(result['series'][0]['values'],[10]*4)
        self.assertEqual(result['series'][0]['stats']['std'],0)
        self.assertEqual(result['series'][0]['anomalies'],[])

    def test_polynomial_fit_reproduces_known_cubic(self):
        xs=np.linspace(-1,1,30)
        values=100+3*xs+8*xs**2-4*xs**3
        result=analyze_series('Mine',values,dates(30),Settings(trend_degree=3))
        np.testing.assert_allclose(result['trend'],values,atol=1e-10)

    def test_method_selection_and_episode_coverage(self):
        values=[10,10,10,100,110,10,10,10]
        result=analyze_series('Mine',values,dates(8),Settings(methods=['moving'],moving_window=3))
        flattened=[p['index'] for e in result['episodes'] for p in e['points']]
        self.assertEqual(flattened,result['flags']['moving'])
        self.assertTrue(all(p['tests']==['moving'] for p in result['anomalies']))

    def test_invalid_parameters(self):
        for kwargs in [{'moving_window':0},{'grubbs_alpha':0},{'trend_degree':5},{'methods':[]},{'iqr_factor':float('nan')}]:
            with self.assertRaises(ValueError):Settings(**kwargs)


class SourceTests(unittest.TestCase):
    def test_blank_inactive_columns_and_formula_totals(self):
        text='Date,A,,B,Total\n2026-01-01,1,,2,3\n2026-01-02,3,,4,7\n2026-01-03,5,,6,11\n'
        result=parse_csv(text)
        self.assertEqual(result['mines'],['A','B'])
        self.assertEqual(result['values'],[[1,2],[3,4],[5,6]])
        self.assertEqual(result['snapshot'],parse_csv(text)['snapshot'])

    def test_source_failures_are_not_silently_imputed(self):
        for text in [
            'Date,A\n2026-01-01,1\n2026-01-01,2\n2026-01-03,3',
            'Date,A\n2026-01-01,1\n2026-01-03,2\n2026-01-04,3',
            'Date,A\n2026-01-01,1\n2026-01-02,#ERROR!\n2026-01-03,3',
            'Date,A\n2026-01-01,1\n2026-01-02,nan\n2026-01-03,3',
            'Date,A\n2026-01-01,1\n2026-01-02,-1\n2026-01-03,3',
        ]:
            with self.assertRaises(ValueError):parse_csv(text)

    def test_pdf_contains_settings_all_series_and_anomaly_details(self):
        snapshot={'dates':dates(8),'mines':['Reference mine'],'values':[[v] for v in [10,10,10,100,10,10,10,10]],'snapshot':'a'*16,'fetched_at':'2026-01-09T00:00:00Z'}
        result=analyze(snapshot,Settings(moving_window=3))
        pdf=build_pdf(result)
        reader=PdfReader(io.BytesIO(pdf))
        text='\n'.join(p.extract_text() for p in reader.pages)
        self.assertGreaterEqual(len(reader.pages),5)
        for value in ['Reference mine','Anomaly casebook','2026-01-04','100.00','aaaaaaaaaaaaaaaa','two-sided','Median']:
            self.assertIn(value.casefold(),text.casefold())


if __name__=='__main__':unittest.main()
