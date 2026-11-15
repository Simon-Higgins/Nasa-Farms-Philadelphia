import tempfile
from pathlib import Path
import unittest

from backend.predictions import load_crop_csv, PredictionStore
from backend.main import capabilities, CompareRequest, compare


class PredictionTests(unittest.TestCase):
    def load(self, text, **updates):
        options = dict(crop='corn', fips_column='fips', prediction_column='yield 2026',
                       harvest_year=2026, scenario_id='county-expected-2026',
                       yield_unit='bu/acre', model_version='test-only',
                       weather_assumptions='Synthetic fixture, not a real model output')
        options.update(updates)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'corn.csv'
            path.write_text(text, encoding='utf-8-sig')
            return load_crop_csv(path, **options)

    def test_explicit_prediction_and_scenario_lookup(self):
        rows = self.load('fips,yield,yield 2026\n1001,999,125.5\n')
        store = PredictionStore(rows)
        prediction = store.get('01001', 'corn', 2026, 'county-expected-2026')
        self.assertEqual(prediction.predicted_yield, 125.5)
        self.assertEqual(prediction.yield_basis, 'ml_prediction')
        self.assertEqual(prediction.source_row, 2)
        self.assertIsNone(store.get('01001', 'corn', 2027, 'county-expected-2026'))
        self.assertIsNone(store.get('01001', 'corn', 2026, 'different-weather'))

    def test_duplicate_county_year_requires_explicit_row_selection(self):
        text = 'fips,year,yield 2026\n20001,2023,100\n20001,2024,110\n'
        with self.assertRaisesRegex(ValueError, 'Duplicate prediction'):
            self.load(text)
        rows = self.load(text, row_filters={'year': '2024'})
        self.assertEqual(rows[0].predicted_yield, 110)
        with self.assertRaises(ValueError):
            PredictionStore(rows + rows)

    def test_blank_is_missing_zero_is_valid_invalid_is_rejected(self):
        rows = self.load('fips,yield 2026\n20001,\n1001,0\n')
        self.assertIsNone(rows[0].predicted_yield)
        self.assertEqual(rows[1].predicted_yield, 0)
        for value in ('nan', 'inf', '-1', 'unknown'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.load(f'fips,yield 2026\n20001,{value}\n')

    def test_rejects_unconfirmed_or_malformed_handoff(self):
        for text, options in [
            ('fips,yield\n20001,100\n', {}),
            ('fips,yield 2026\n20001,100\n', {'yield_unit': 'kg/ha'}),
            ('fips,yield 2026\n20001,100\n', {'weather_assumptions': ''}),
            ('fips,yield 2026\n20001.0,100\n', {}),
            ('fips,yield 2026\n20000,100\n', {}),
            ('fips,yield 2026\n20001,100,extra\n', {}),
            ('fips,yield 2026\n20001,100\n', {'row_filters': {'fips': '01001'}}),
        ]:
            with self.subTest(text=text, options=options), self.assertRaises(ValueError):
                self.load(text, **options)

    def test_simon_county_year_format_preserves_all_seasons(self):
        # Representative values from the supplied corn file, not test metrics.
        text = ('county_fips,year,yield,predicted_yield\n'
                '20001,2023,96.7,100.05800000000004\n'
                '20001,2024,127.9,123.08399999999983\n')
        options = dict(fips_column='county_fips', prediction_column='predicted_yield',
                       harvest_year=None, year_column='year', scenario_id='historical-model-estimates')
        store = PredictionStore(self.load(text, **options))
        for year, expected in [(2023, 100.058), (2024, 123.084)]:
            self.assertAlmostEqual(store.get('20001', 'corn', year,
                                            'historical-model-estimates').predicted_yield, expected)
        self.assertIsNone(store.get('20001', 'corn', 2026, 'historical-model-estimates'))
        with self.assertRaisesRegex(ValueError, 'Duplicate prediction'):
            self.load(text + '20001,2024,127.9,123.084\n', **options)
        for bad_year in ('', '2024.0', 'invalid', '1800'):
            with self.subTest(year=bad_year), self.assertRaises(ValueError):
                self.load('county_fips,year,predicted_yield\n20001,' + bad_year + ',100\n', **options)
        with self.assertRaisesRegex(ValueError, 'not both'):
            self.load(text, year_column='year')

    def test_advertised_scenarios_are_usable(self):
        value = capabilities()
        self.assertTrue(value['ml_predictions']['ranking_enabled'])
        for scenario in value['scenarios']:
            result = compare(CompareRequest(
                data_mode=scenario['data_mode'], county_fips=scenario['county_fips'],
                first_harvest_year=scenario['first_harvest_year'], horizon_years=2,
                baseline_rotation=['corn', 'corn'], require_crop_family_change=True,
                weights={'margin': 0.35, 'lower_rainfed_shortfall': 0.65}))
            self.assertIsNotNone(result['baseline']['score'])
            self.assertEqual(len(result['rotations']), 2)
