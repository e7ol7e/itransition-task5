"""HTTP and immutable snapshot/report contracts without network dependencies."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1'
import unittest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
import app
from analytics import parse_csv


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client=TestClient(app.app)
        self.snapshot=parse_csv('Date,Alpha,Beta,Total\n2026-01-01,1,2,3\n2026-01-02,3,4,7\n2026-01-03,5,6,11\n2026-01-04,7,8,15')
        self.snapshot['sheet_url']='https://docs.google.com/spreadsheets/d/test/edit'
        app.snapshots[self.snapshot['snapshot']]=self.snapshot

    def test_health_static_and_source(self):
        self.assertEqual(self.client.get('/healthz').status_code,200)
        self.assertIn('Every mine. Every day.',self.client.get('/').text)
        self.assertEqual(self.client.get('/static/app.js').status_code,200)
        self.assertIn('docs.google.com',self.client.get('/api/source').json()['sheet_url'])

    def test_snapshot_and_settings_are_preserved(self):
        r=self.client.post('/api/analyze',json={'snapshot':self.snapshot['snapshot'],'chart_type':'stacked','trend_degree':3,'moving_window':3})
        self.assertEqual(r.status_code,200)
        data=r.json()
        self.assertEqual(data['series'][0]['values'],[3,7,11,15])
        report=app.results[data['report_id']]
        self.assertEqual(report['settings']['trend_degree'],3)
        self.assertEqual(report['settings']['chart_type'],'stacked')
        self.assertEqual(report['source']['snapshot'],self.snapshot['snapshot'])

    def test_expired_snapshots_and_bad_inputs_are_explicit(self):
        self.assertEqual(self.client.post('/api/analyze',json={'snapshot':'f'*16}).status_code,409)
        self.assertEqual(self.client.post('/api/analyze',json={'moving_window':0}).status_code,422)
        self.assertEqual(self.client.post('/api/analyze',json={'url':'http://localhost/'}).status_code,422)
        self.assertEqual(self.client.get('/api/report/'+'f'*24+'.pdf').status_code,409)

    def test_pdf_content_disposition(self):
        response=self.client.post('/api/analyze',json={'snapshot':self.snapshot['snapshot']})
        handle=response.json()['report_id']
        for inline in [False,True]:
            pdf=self.client.get(f'/api/report/{handle}.pdf?inline={str(inline).lower()}')
            self.assertEqual(pdf.status_code,200)
            self.assertTrue(pdf.content.startswith(b'%PDF'))
            self.assertIn('inline' if inline else 'attachment',pdf.headers['content-disposition'])


if __name__=='__main__':unittest.main()
