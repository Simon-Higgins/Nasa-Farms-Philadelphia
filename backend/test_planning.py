import json
from pathlib import Path
from statistics import mean
import unittest
from unittest.mock import patch
from fastapi import HTTPException
from backend.main import PlanningRequest, planning_compare


class PlanningTests(unittest.TestCase):
    def test_real_ml_scenarios_and_no_observed_fallback(self):
        request = self.request()
        request.yield_basis = 'ml_prediction'
        result = planning_compare(request)
        self.assertEqual(result['historical_pairs'], [[2022, 2023], [2023, 2024]])
        expected_corn_yield = (74.964 + 100.058 + 100.058 + 123.084) / 4
        self.assertAlmostEqual(result['baseline']['annual_margin_usd_per_acre'], expected_corn_yield * 4 - 700)
        self.assertEqual(len(result['rotations']), 2)
        for row in [result['baseline'], *result['rotations']]:
            for scenario in row['scenarios']:
                for season in scenario['seasons']:
                    self.assertEqual(season['yield_basis'], 'ml_prediction')
                    self.assertEqual(season['historical_year'], season['prediction_provenance']['historical_year'])
        original = json.loads

        def missing_predictions(text, **kwargs):
            value = original(text, **kwargs)
            if isinstance(value, dict) and 'records' in value:
                value['records'] = []
            return value

        with patch('backend.planning.json.loads', side_effect=missing_predictions):
            with self.assertRaises(HTTPException) as error:
                planning_compare(request)
        self.assertEqual(error.exception.status_code, 422)

    def request(self):
        return PlanningRequest(
            county_fips='20001', first_harvest_year=2026,
            baseline_rotation=['corn', 'corn'], require_crop_family_change=True,
            weights={'margin': 0.35, 'lower_rainfed_shortfall': 0.65},
            budgets_by_year={str(year): {
                'corn': {'price_usd_per_bu': 4.0, 'cost_usd_per_acre': 700.0},
                'soybeans': {'price_usd_per_bu': 10.0, 'cost_usd_per_acre': 500.0},
            } for year in (2026, 2027)},
            economics_assumptions='Synthetic test budgets')

    def test_aggregation_and_common_pairs(self):
        result = planning_compare(self.request())
        self.assertEqual(result['historical_pairs'], [[2023, 2024], [2024, 2025]])
        self.assertEqual(len(result['rotations']), 2)
        self.assertFalse(result['baseline']['meets_crop_family_filter'])
        data_dir = Path(__file__).parent / 'data'
        for row in [result['baseline'], *result['rotations']]:
            self.assertEqual(row['scenario_count'], 2)
            self.assertEqual(row['annual_margin_usd_per_acre'], mean(s['annual_margin_usd_per_acre'] for s in row['scenarios']))
            for scenario in row['scenarios']:
                self.assertEqual([s['harvest_year'] for s in scenario['seasons']], [2026, 2027])
                for season in scenario['seasons']:
                    snapshot = json.loads((data_dir / f"allen-{season['historical_year']}-analysis.json").read_text())
                    source = next(c for c in snapshot['crops'] if c['crop'] == season['crop'])
                    price, cost = (4, 700) if season['crop'] == 'corn' else (10, 500)
                    self.assertAlmostEqual(season['annual_margin_usd_per_acre'], source['yield_bu_per_harvested_acre'] * price - cost)
                    self.assertEqual(season['rainfed_shortfall_mm'], source['water_assessment']['upper']['rainfed_shortfall_mm'])

    def test_year_specific_budgets_and_validation(self):
        request = self.request()
        before = planning_compare(request)
        request.budgets_by_year['2027']['corn'].cost_usd_per_acre += 100
        after = planning_compare(request)
        self.assertAlmostEqual(before['baseline']['annual_margin_usd_per_acre'] - after['baseline']['annual_margin_usd_per_acre'], 50)
        request.budgets_by_year.pop('2027')
        with self.assertRaises(HTTPException) as error:
            planning_compare(request)
        self.assertEqual(error.exception.status_code, 422)
