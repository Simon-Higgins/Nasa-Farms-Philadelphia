"""Run with .venv/Scripts/python -m unittest backend.test_contract -v."""
import json
import unittest
from pathlib import Path
from fastapi import HTTPException
from backend.main import app, compare, CompareRequest, county_season_inputs

ROOT = Path(__file__).resolve().parents[1]

class ContractTests(unittest.TestCase):
    def test_sample_exact(self):
        request = CompareRequest.model_validate_json((ROOT / 'examples/fieldshift-request.example.json').read_text())
        actual = compare(request)
        self.assertEqual(actual, json.loads((ROOT / 'examples/fieldshift-response.example.json').read_text()))
        self.assertTrue(actual['baseline']['is_baseline'])
        self.assertFalse(actual['baseline']['meets_crop_family_filter'])
        self.assertEqual([r['rank'] for r in actual['rotations']], [1, 2])

    def test_historical_inputs(self):
        result = county_season_inputs('20001', 2024)
        self.assertEqual(result['county_fips'], '20001')
        self.assertEqual(len(result['crops']), 3)
        corn = result['crops'][0]
        self.assertEqual(corn['margin_proxy_usd_per_acre'], -261.417)
        for crop in result['crops']:
            self.assertEqual(crop['heat']['planting_date'], crop['planting_water']['scenario_planting_date'])
            self.assertEqual(crop['planting_water']['estimate_status'], 'estimated')
            self.assertNotIn('score', crop)
        with self.assertRaises(HTTPException) as caught:
            county_season_inputs('01001', 2024)
        self.assertEqual(caught.exception.status_code, 404)

if __name__ == '__main__':
    unittest.main()

