"""Shared HTTP/direct adapter for the Streamlit dashboard."""
import json
from math import isfinite
import os
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class BackendError(RuntimeError):
    pass


def error_message(detail):
    if isinstance(detail, list):
        return '; '.join(str(item.get('msg', item)) if isinstance(item, dict) else str(item) for item in detail)
    if isinstance(detail, dict):
        return str(detail.get('reason', detail))
    return str(detail)


class FieldShiftClient:
    def __init__(self, mode=None, base_url=None):
        self.mode = mode or os.getenv('FIELDSHIFT_BACKEND_MODE', 'auto')
        self.base_url = (base_url or os.getenv('FIELDSHIFT_API_URL', 'http://127.0.0.1:8000')).rstrip('/')
        if self.mode not in ('auto', 'http', 'direct'):
            raise BackendError('FIELDSHIFT_BACKEND_MODE must be auto, http or direct.')

    def _call(self, path, payload=None):
        if self.mode != 'direct':
            data = json.dumps(payload).encode('utf-8') if payload is not None else None
            request = Request(self.base_url + path, data=data, headers={'Content-Type': 'application/json'})
            try:
                with urlopen(request, timeout=15 if payload is not None else 3) as response:
                    result = json.load(response)
                self.mode = 'http'
                return result
            except HTTPError as error:
                try:
                    detail = json.loads(error.read()).get('detail', error.reason)
                except (ValueError, AttributeError):
                    detail = error.reason
                raise BackendError(f'Comparison service returned {error.code}: {error_message(detail)}') from error
            except (URLError, TimeoutError, OSError) as error:
                if self.mode == 'http':
                    raise BackendError('Cannot reach the comparison service. Check that the backend is running and try again.') from error
                self.mode = 'direct'
            except ValueError as error:
                raise BackendError('The comparison service returned invalid JSON.') from error
        return self._direct(path, payload)

    def _direct(self, path, payload):
        root = str(Path(__file__).resolve().parents[1])
        if root not in sys.path:
            sys.path.insert(0, root)
        try:
            from backend.main import PlanningRequest, capabilities, planning_compare
            if payload is None:
                return capabilities()
            request = PlanningRequest.model_validate(payload)
            return planning_compare(request)
        except ImportError as error:
            raise BackendError('The local backend dependencies are missing. Install backend/requirements.txt.') from error
        except Exception as error:
            # FastAPI and Pydantic errors retain their actionable validation details.
            detail = getattr(error, 'detail', str(error))
            raise BackendError(error_message(detail)) from error

    def capabilities(self):
        result = self._call('/api/v1/capabilities')
        try:
            counties = result['planning']['supported_ml_counties']
            if not counties:
                raise KeyError('No prepared counties')
            for county in counties:
                fips = county['county_fips']
                if (not isinstance(fips, str) or len(fips) != 5 or not fips.isdigit()
                        or not isinstance(county['county_label'], str)
                        or not set(county['crops']) & {'corn', 'soybeans'}):
                    raise KeyError('Incomplete county entry')
        except (KeyError, TypeError) as error:
            raise BackendError('Supported county data is unavailable or incomplete.') from error
        return result

    def compare(self, payload):
        result = self._call('/api/v1/planning/compare', payload)
        try:
            baseline = result['baseline']
            alternatives = result['rotations']
            if not isinstance(baseline, dict) or not isinstance(alternatives, list):
                raise ValueError('Invalid result shape')
            if result['county_fips'] != payload['county_fips']:
                raise ValueError('County mismatch')
            if not isinstance(result['county_label'], str):
                raise ValueError('Missing county label')
            if [season['crop'] for season in baseline['seasons']] != payload['baseline_rotation']:
                raise ValueError('Baseline mismatch')
            for row in [baseline, *alternatives]:
                if len(row['seasons']) != 2:
                    raise ValueError('Missing seasons')
                if [s['harvest_year'] for s in row['seasons']] != [payload['first_harvest_year'], payload['first_harvest_year'] + 1]:
                    raise ValueError('Planning year mismatch')
                for field in ('annual_margin_usd_per_acre', 'rainfed_shortfall_mm', 'score'):
                    value = row.get(field)
                    if value is not None and (type(value) not in (int, float) or not isfinite(value)):
                        raise ValueError('Invalid numeric result')
        except (KeyError, TypeError, ValueError) as error:
            raise BackendError('The comparison response is incomplete or does not match the selected county/year.') from error
        return result


def build_payload(fips, first_harvest, planned_rotation, require_family_change, margin_weight):
    crops = [crop.strip().lower().replace(' ', '_') for crop in planned_rotation.split('->')]
    if len(crops) != 2 or any(crop not in ('corn', 'soybeans') for crop in crops):
        raise BackendError('Select a rotation using corn and soybeans.')
    return {
        'county_fips': str(fips).zfill(5), 'first_harvest_year': int(first_harvest),
        'horizon_years': 2, 'yield_basis': 'ml_prediction', 'baseline_rotation': crops,
        'require_crop_family_change': bool(require_family_change),
        'weights': {'margin': margin_weight / 100, 'lower_rainfed_shortfall': (100 - margin_weight) / 100},
    }
