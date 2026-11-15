import json
from pathlib import Path
from statistics import mean
import unittest
from unittest.mock import patch
from fastapi import HTTPException
from backend.main import PlanningRequest, planning_compare, capabilities, county_season_analysis


class PlanningTests(unittest.TestCase):
    def test_every_advertised_ml_county_runs_with_matching_inputs(self):
        counties = capabilities()['planning']['supported_ml_counties']
        self.assertTrue(counties)
        for county in counties:
            with self.subTest(county=county['county_fips']):
                request = self.request()
                request.county_fips = county['county_fips']
                request.yield_basis = 'ml_prediction'
                result = planning_compare(request)
                analysis = county_season_analysis(request.county_fips, county['historical_pairs'][0][0])
                self.assertEqual(analysis['county_fips'], request.county_fips)
                self.assertEqual(result['county_label'], county['county_label'])
                self.assertEqual(result['historical_pairs'], county['historical_pairs'])
                self.assertEqual(len(result['rotations']), 2)
                default_request = request.model_copy(update={'budgets_by_year': None, 'economics_assumptions': None})
                cached = planning_compare(default_request)
                self.assertEqual(cached['margin_calculation'], 'precomputed_default')
                custom_request = PlanningRequest.model_validate({
                    **default_request.model_dump(), 'budgets_by_year': cached['budgets_by_year'],
                    'economics_assumptions': cached['economics_assumptions']})
                recalculated = planning_compare(custom_request)
                for cached_row, custom_row in zip([cached['baseline'], *cached['rotations']],
                                                  [recalculated['baseline'], *recalculated['rotations']]):
                    self.assertEqual(cached_row['id'], custom_row['id'])
                    self.assertAlmostEqual(cached_row['annual_margin_usd_per_acre'], custom_row['annual_margin_usd_per_acre'])
                    self.assertAlmostEqual(cached_row['score'], custom_row['score'])
                for row in [result['baseline'], *result['rotations']]:
                    for scenario in row['scenarios']:
                        for season in scenario['seasons']:
                            record = season['prediction_provenance']
                            self.assertEqual(record['county_fips'], request.county_fips)
                            self.assertEqual(record['crop'], season['crop'])
                            self.assertEqual(record['historical_year'], season['historical_year'])
        request.county_fips = '99999'
        with self.assertRaises(HTTPException) as error:
            planning_compare(request)
        self.assertEqual(error.exception.status_code, 404)

    def test_real_ml_scenarios_and_no_observed_fallback(self):
        request = self.request()
        request.yield_basis = 'ml_prediction'
        result = planning_compare(request)
        self.assertEqual(result['historical_pairs'], [[2022, 2023], [2023, 2024]])
        self.assertEqual(len(result['excluded_pairs']), 2)
        for pair in result['excluded_pairs']:
            self.assertIn('missing_prediction:soybeans:2021', pair['reasons'])
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

    def test_default_margin_cache_invalidation(self):
        request = self.request().model_copy(update={
            'yield_basis': 'ml_prediction', 'budgets_by_year': None, 'economics_assumptions': None})
        original = json.loads

        def changed_cache(text, **kwargs):
            result = original(text, **kwargs)
            if isinstance(result, dict) and 'prediction_sha256' in result:
                result['prediction_sha256'] = 'outdated'
            return result

        with patch('backend.planning.json.loads', side_effect=changed_cache):
            with self.assertRaises(HTTPException) as error:
                planning_compare(request)
        self.assertEqual(error.exception.status_code, 503)

    def test_all_four_pairs_and_unchanged_daily_calculation(self):
        request = self.request()
        request.yield_basis = 'ml_prediction'
        request.county_fips = '20005'
        result = planning_compare(request)
        self.assertEqual(result['historical_pairs'], [[2020, 2021], [2021, 2022], [2022, 2023], [2023, 2024]])
        self.assertEqual(result['baseline']['scenario_count'], 4)
        self.assertEqual(result['baseline']['annual_margin_usd_per_acre'], mean(
            scenario['annual_margin_usd_per_acre'] for scenario in result['baseline']['scenarios']))
        # The indexed source path must reproduce the existing daily engine.
        data = Path(__file__).parent / 'data'
        legacy = json.loads((data / 'allen-2022-analysis.json').read_text())
        indexed = json.loads((data / 'counties/20001/2022-analysis.json').read_text())
        for crop in ('corn', 'soybeans'):
            old = next(row for row in legacy['crops'] if row['crop'] == crop)
            new = next(row for row in indexed['crops'] if row['crop'] == crop)
            self.assertEqual(old['water_assessment'], new['water_assessment'])

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
