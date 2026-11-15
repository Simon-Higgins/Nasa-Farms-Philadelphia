"""Validated yield handoff, independent of ranking and weather analysis.

Column names and scenario metadata are explicit: never infer a forecast from
an observed `yield` column or reuse one forecast for another harvest year.
"""
import csv
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
import re


@dataclass(frozen=True)
class YieldPrediction:
    county_fips: str
    crop: str
    harvest_year: int
    scenario_id: str
    predicted_yield: float | None
    yield_unit: str
    model_version: str
    weather_assumptions: str
    source_file: str
    source_row: int
    yield_basis: str = 'ml_prediction'


class PredictionStore:
    def __init__(self, predictions):
        self._predictions = {}
        for prediction in predictions:
            key = (prediction.county_fips, prediction.crop,
                   prediction.harvest_year, prediction.scenario_id)
            if key in self._predictions:
                raise ValueError(f'Duplicate prediction key: {key}')
            self._predictions[key] = prediction

    def get(self, county_fips, crop, harvest_year, scenario_id):
        """Absent or blank predictions remain unavailable, never zero/fallback."""
        return self._predictions.get((county_fips, crop, harvest_year, scenario_id))


def load_crop_csv(path, *, crop, fips_column, prediction_column,
                  harvest_year=None, scenario_id, yield_unit, model_version,
                  weather_assumptions, row_filters=None, year_column=None):
    """Read one crop's wide CSV using the exact confirmed prediction column.

    Use year_column for one prediction per county/year, or harvest_year for a
    fixed forecast year. These options are mutually exclusive. row_filters can
    select feature rows when importing a fixed-year prediction column.
    A blank prediction is None; malformed, negative or nonfinite values fail.
    """
    if crop not in ('corn', 'oats', 'soybeans'):
        raise ValueError('Prediction crops supported: corn, oats, soybeans.')
    if year_column is not None and (not isinstance(year_column, str) or not year_column.strip()):
        raise ValueError('year_column must be a nonempty column name.')
    if year_column is not None and harvest_year is not None:
        raise ValueError('Specify year_column or harvest_year, not both.')
    if year_column is None and (type(harvest_year) is not int or not 1900 <= harvest_year <= 2200):
        raise ValueError('harvest_year must be an explicit integer year.')
    if yield_unit != 'bu/acre':
        raise ValueError('Confirm/convert yield units to bu/acre before import.')
    if any(not isinstance(v, str) or not v.strip() for v in
           (scenario_id, model_version, weather_assumptions, fips_column, prediction_column)):
        raise ValueError('Column names, scenario, model and weather metadata are required.')
    filters = row_filters or {}
    predictions = []
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        columns = reader.fieldnames or []
        if len(columns) != len(set(columns)):
            raise ValueError('Duplicate CSV column names.')
        required = {fips_column, prediction_column, *filters}
        if year_column is not None:
            required.add(year_column)
        if not required.issubset(columns):
            raise ValueError(f'Missing CSV columns: {sorted(required - set(columns))}')
        for row_number, row in enumerate(reader, 2):
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f'CSV row {row_number}: malformed field count.')
            if any(row[key].strip() != str(value) for key, value in filters.items()):
                continue
            prediction_year = harvest_year
            if year_column is not None:
                raw_year = row[year_column].strip()
                if not re.fullmatch(r'[0-9]{4}', raw_year) or not 1900 <= int(raw_year) <= 2200:
                    raise ValueError(f'CSV row {row_number}: invalid prediction year.')
                prediction_year = int(raw_year)
            raw_fips = row[fips_column].strip()
            if not re.fullmatch(r'[0-9]{1,5}', raw_fips):
                raise ValueError(f'CSV row {row_number}: invalid county FIPS.')
            fips = raw_fips.zfill(5)
            if fips[:2] == '00' or fips[2:] == '000':
                raise ValueError(f'CSV row {row_number}: expected a county FIPS.')
            raw_yield = row[prediction_column].strip()
            try:
                value = float(raw_yield) if raw_yield else None
            except ValueError as error:
                raise ValueError(f'CSV row {row_number}: invalid predicted yield.') from error
            if value is not None and (not isfinite(value) or value < 0):
                raise ValueError(f'CSV row {row_number}: yield must be finite and nonnegative.')
            predictions.append(YieldPrediction(
                fips, crop, prediction_year, scenario_id, value, yield_unit,
                model_version, weather_assumptions, Path(path).name, row_number))
    if not predictions:
        raise ValueError('No prediction rows matched the configured selection.')
    # Validate uniqueness before handing any records to the caller.
    PredictionStore(predictions)
    return predictions
