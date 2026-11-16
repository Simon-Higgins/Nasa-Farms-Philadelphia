"""Client and dashboard control-flow regressions without a web server."""
from contextlib import nullcontext
from io import BytesIO
import json
from pathlib import Path
import runpy
import types
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from scripts.fieldshift_client import BackendError, FieldShiftClient, build_payload

ROOT = Path(__file__).resolve().parents[1]


class ClientTests(unittest.TestCase):
    def test_direct_counties_and_comparison(self):
        client = FieldShiftClient(mode='direct')
        self.assertEqual(len(client.capabilities()['planning']['supported_ml_counties']), 595)
        result = client.compare(build_payload('20005', 2026, 'Corn -> Soybeans', True, 35))
        self.assertEqual(result['county_fips'], '20005')
        self.assertEqual(result['baseline']['scenario_count'], 4)
        # With a mixed-family baseline, only the reverse order remains eligible.
        self.assertEqual(len(result['rotations']), 1)

    def test_auto_fallback_only_on_connection_error(self):
        client = FieldShiftClient(mode='auto')
        with patch('scripts.fieldshift_client.urlopen', side_effect=URLError('refused')):
            self.assertTrue(client.capabilities()['planning']['supported_ml_counties'])
        self.assertEqual(client.mode, 'direct')
        error = HTTPError('http://test', 422, 'Invalid request', {}, BytesIO(b'{"detail":"unsupported crop"}'))
        with patch('scripts.fieldshift_client.urlopen', side_effect=error):
            with self.assertRaisesRegex(BackendError, '422.*unsupported crop'):
                FieldShiftClient(mode='auto').compare({})

    def test_http_transport_preserves_the_request(self):
        payload = build_payload('20001', 2027, 'Soybeans -> Corn', False, 80)
        expected = FieldShiftClient(mode='direct').compare(payload)
        with patch('scripts.fieldshift_client.urlopen', return_value=BytesIO(json.dumps(expected).encode())) as send:
            actual = FieldShiftClient(mode='http').compare(payload)
        self.assertEqual(actual, expected)
        request = send.call_args.args[0]
        self.assertEqual(json.loads(request.data), payload)
        self.assertTrue(request.full_url.endswith('/api/v1/planning/compare'))

    def test_invalid_selection_and_http_failure_are_visible(self):
        with self.assertRaises(BackendError):
            build_payload('20001', 2026, 'Oats -> Corn', True, 35)
        with patch('scripts.fieldshift_client.urlopen', side_effect=URLError('refused')):
            with self.assertRaisesRegex(BackendError, 'Cannot reach'):
                FieldShiftClient(mode='http').capabilities()


class StopRendering(BaseException):
    pass


class DashboardHarness(types.ModuleType):
    """Records UI calls to verify session handling; does not emulate a browser."""
    def __init__(self):
        super().__init__('streamlit')
        self.session_state = {}
        self.values = {}
        self.messages = []
        self.submitted = False

    def cache_data(self, **kwargs):
        return lambda function: function

    def columns(self, sizes, **kwargs):
        count = sizes if isinstance(sizes, int) else len(sizes)
        return [self for _ in range(count)]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def selectbox(self, label, options, index=0, **kwargs):
        self.values.setdefault(label, options[index])
        assert self.values[label] in options
        return self.values[label]

    def slider(self, label, value, **kwargs):
        return self.values.get(label, value)

    def checkbox(self, label, value, **kwargs):
        return self.values.get(label, value)

    def form_submit_button(self, *args, **kwargs):
        return self.submitted

    def stop(self):
        raise StopRendering()

    def __getattr__(self, name):
        if name in ('form', 'spinner', 'expander'):
            return lambda *args, **kwargs: nullcontext()
        def record(*args, **kwargs):
            self.messages.append((name, args))
        return record


class DashboardTests(unittest.TestCase):
    def run_dashboard(self, ui):
        ui.messages = []
        with patch.dict('sys.modules', {'streamlit': ui}), patch.dict('os.environ', {'FIELDSHIFT_BACKEND_MODE': 'direct'}):
            try:
                runpy.run_path(str(ROOT / 'scripts/streamlit_frontend.py'))
            except StopRendering:
                pass

    def test_submit_county_changes_and_priority_changes(self):
        ui = DashboardHarness()
        self.run_dashboard(ui)
        self.assertNotIn('api_data', ui.session_state)
        ui.submitted = True
        self.run_dashboard(ui)
        self.assertEqual(ui.session_state['api_data']['county_fips'], '20001')
        ui.values['County'] = 'Atchison County, KS'
        ui.submitted = False
        self.run_dashboard(ui)
        self.assertEqual(ui.session_state['submitted_request']['county_fips'], '20001')
        self.assertTrue(any('Allen County, KS' in str(args) for kind, args in ui.messages if kind == 'caption'))
        ui.submitted = True
        self.run_dashboard(ui)
        self.assertEqual(ui.session_state['api_data']['county_fips'], '20005')
        before = ui.session_state['api_data']['baseline']
        ui.values['Profit priority (%)'] = 100
        self.run_dashboard(ui)
        after = ui.session_state['api_data']['baseline']
        self.assertEqual(ui.session_state['submitted_request']['weights']['margin'], 1.0)
        self.assertEqual(ui.session_state['submitted_request']['weights']['lower_rainfed_shortfall'], 0.0)
        self.assertEqual(before['annual_margin_usd_per_acre'], after['annual_margin_usd_per_acre'])
        self.assertEqual(before['rainfed_shortfall_mm'], after['rainfed_shortfall_mm'])
        self.assertNotEqual(before['score'], after['score'])

    def test_failure_clears_old_results_and_displays_error(self):
        ui = DashboardHarness()
        ui.submitted = True
        self.run_dashboard(ui)
        with patch.object(FieldShiftClient, 'compare', side_effect=BackendError('Service unavailable')):
            self.run_dashboard(ui)
        self.assertIsNone(ui.session_state['api_data'])
        self.assertIn(('error', ('Service unavailable',)), ui.messages)
