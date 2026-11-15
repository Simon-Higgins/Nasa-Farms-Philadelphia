import copy
import json
import unittest
from pathlib import Path
from fastapi import HTTPException
from backend.main import CompareRequest, compare, county_season_analysis

ROOT = Path(__file__).resolve().parents[1]

class HistoricalTests(unittest.TestCase):
    def request(self, **updates):
        value = json.loads((ROOT/'examples/fieldshift-request.historical.json').read_text())
        value.update(updates)
        return CompareRequest.model_validate(value)

    def test_actual_aggregation_and_top_two(self):
        result = compare(self.request())
        self.assertEqual(result, json.loads((ROOT/'examples/fieldshift-response.historical.json').read_text()))
        self.assertEqual(len(result['rotations']), 2)
        baseline = result['baseline']
        self.assertFalse(baseline['meets_crop_family_filter'])
        self.assertIsNotNone(baseline['score'])
        for row in [baseline, *result['rotations']]:
            self.assertEqual([s['harvest_year'] for s in row['seasons']], [2024, 2025])
            expected_margin, expected_water = 0, 0
            for season in row['seasons']:
                source = next(c for c in county_season_analysis('20001',season['harvest_year'])['crops'] if c['crop']==season['crop'])
                expected_margin += source['margin_proxy_usd_per_acre']/2
                expected_water += source['water_assessment']['upper']['rainfed_shortfall_mm']
            self.assertAlmostEqual(row['annual_margin_usd_per_acre'], expected_margin)
            self.assertAlmostEqual(row['rainfed_shortfall_mm'], expected_water)
        self.assertEqual(result['rotations'][0]['id'],'sorghum-soybeans')

    def test_missing_baseline_yield_not_zero(self):
        result = compare(self.request(baseline_rotation=['corn','sorghum']))
        self.assertIsNone(result['baseline']['score'])
        self.assertIn('missing_yield:sorghum:2025',result['baseline']['reasons'])
        self.assertEqual(len(result['rotations']),2)
        self.assertTrue(all(r['score_delta_vs_baseline'] is None for r in result['rotations']))

    def test_validation_and_filter(self):
        for updates, status in [({'baseline_rotation':None},422),({'baseline_rotation':['rice','corn']},422),({'first_harvest_year':2025},404)]:
            with self.assertRaises(HTTPException) as caught:
                compare(self.request(**updates))
            self.assertEqual(caught.exception.status_code,status)
        result=compare(self.request(baseline_rotation=['corn','soybeans']))
        self.assertNotIn('corn-corn',[r['id'] for r in result['rotations']])
        for row in result['rotations']:
            self.assertGreaterEqual(row['score'],0)
            self.assertLessEqual(row['score'],100)

    def test_deterministic_ties(self):
        from backend.main import normalized
        self.assertEqual(normalized(10,10,10),.5)
        self.assertEqual(compare(self.request()),compare(self.request()))
