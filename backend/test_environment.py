import unittest
from backend.environment import MissingInput, crop_coefficient, heat_screen, water_balance
from backend.main import county_season_analysis

TRAITS = {'stage_initial_days': '1', 'stage_development_days': '1', 'stage_midseason_days': '1', 'stage_late_season_days': '1',
          'kc_initial_lower': '.3', 'kc_mid_lower': '1.2', 'kc_end_lower': '.5',
          'max_effective_root_depth_lower_m': '1', 'maturity_reference_gdd_F_days': '2700'}
SOIL = {'estimate_status': 'estimated', 'available_water_storage_top_1m_mm': '10',
        'estimated_available_water_top_1m_mm': '8', 'scenario_planting_date': '2024-04-01'}

class EnvironmentTests(unittest.TestCase):
    def test_stage_curve_endpoints(self):
        self.assertEqual([crop_coefficient(i, TRAITS, 'lower') for i in range(4)], [.3, 1.2, 1.2, .5])

    def test_bucket_mass_balance_and_planting_day_excluded(self):
        et = {f'2024-04-0{i}': 10 for i in range(2, 5)}
        rain = dict.fromkeys(et, 0)
        rain['2024-04-03'] = 30
        result = water_balance(SOIL, TRAITS, et, rain)
        self.assertAlmostEqual(result['initial_storage_mm'] + result['precipitation_mm'], result['final_storage_mm'] + result['supplied_mm'] + result['excess_mm'])
        self.assertAlmostEqual(result['demand_mm'], result['supplied_mm'] + result['rainfed_shortfall_mm'])
        self.assertEqual(result['days_updated'], 3)
        self.assertGreater(result['rainfed_shortfall_mm'], 0)
        self.assertGreater(result['excess_mm'], 0)

    def test_missing_and_invalid_inputs_not_zero(self):
        with self.assertRaises(MissingInput):
            water_balance(SOIL, TRAITS, {}, {})
        with self.assertRaises(MissingInput):
            water_balance({**SOIL, 'estimate_status': 'before_SMAP_record'}, TRAITS, {}, {})
        with self.assertRaises(MissingInput):
            crop_coefficient(0, {**TRAITS, 'kc_initial_lower': 'nan'}, 'lower')

    def test_partial_heat_record_is_not_failure(self):
        heat = {'freeze_status': 'no_freeze_through_last_observation', 'gdd_F_days_through_last_observation_if_no_freeze': '2000', 'freeze_observations_through': '2026-11-13'}
        self.assertEqual(heat_screen(heat, TRAITS)['status'], 'undetermined')
        heat['gdd_F_days_through_last_observation_if_no_freeze'] = '2800'
        self.assertEqual(heat_screen(heat, TRAITS)['status'], 'passed')

    def test_real_analysis_is_explicit(self):
        result = county_season_analysis('20001', 2024)
        self.assertEqual(len(result['crops']), 3)
        for crop in result['crops']:
            self.assertEqual(crop['yield_basis'], 'observed_county_yield')
            self.assertEqual(crop['heat_assessment']['status'], 'passed')
            assessment = crop['water_assessment']
            self.assertEqual(assessment['status'], 'calculated')
            for bound in ('lower', 'upper'):
                water = assessment[bound]
                self.assertGreater(water['days_updated'], 100)
                self.assertGreaterEqual(water['rainfed_shortfall_mm'], 0)
                self.assertAlmostEqual(water['demand_mm'], water['supplied_mm'] + water['rainfed_shortfall_mm'])
                self.assertAlmostEqual(water['initial_storage_mm'] + water['precipitation_mm'], water['final_storage_mm'] + water['supplied_mm'] + water['excess_mm'])
                self.assertAlmostEqual(sum(m['rainfed_shortfall_mm'] for m in water['monthly'].values()), water['rainfed_shortfall_mm'])
            self.assertGreaterEqual(assessment['upper']['rainfed_shortfall_mm'] + 1e-8, assessment['lower']['rainfed_shortfall_mm'])
