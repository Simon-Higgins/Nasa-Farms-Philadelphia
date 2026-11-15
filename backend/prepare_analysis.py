"""Prepare one county's analysis; optionally supply the daily reference ET CSV."""
import argparse
import csv
import io
import json
import zipfile
from pathlib import Path
from backend.county_inputs import build
from backend.environment import MissingInput, heat_screen, water_balance


def weather_rows(stream, county, value_column, year=2024):
    result = {}
    for row in csv.DictReader(stream):
        if row['county_fips'] == county and row['date'].startswith(str(year)):
            if row['date'] in result:
                raise ValueError('Duplicate county-day weather')
            result[row['date']] = row[value_column]
    return result


def analyze(data_dir, daily_et_path=None, county="20001", year=2024, crop_names=None,
            source_rows=None, daily_weather=None):
    result = build(data_dir, county, year, crop_names=crop_names, source_rows=source_rows)
    et, rain = {}, {}
    if daily_weather is not None:
        et, rain = daily_weather
        result['source_files'] += ['county_daily_reference_et_2015_2026.csv', 'county_daily_gridmet_precipitation_2015_2026.zip']
    elif daily_et_path:
        with daily_et_path.open(encoding='utf-8-sig', newline='') as stream:
            et = weather_rows(stream, result['county_fips'], 'eto_mm_day', year)
        archive = data_dir / 'county_daily_gridmet_precipitation_2015_2026.zip'
        with zipfile.ZipFile(archive) as z:
            names = [n for n in z.namelist() if n.endswith('.csv')]
            if len(names) != 1:
                raise ValueError('Expected exactly one precipitation CSV')
            with z.open(names[0]) as raw, io.TextIOWrapper(raw, encoding='utf-8-sig', newline='') as stream:
                rain = weather_rows(stream, result['county_fips'], 'precipitation_mm', year)
        result['source_files'] += [daily_et_path.name, archive.name]
    result['data_mode'] = 'historical_analysis'
    for crop in result['crops']:
        crop['yield_basis'] = 'observed_county_yield'
        crop['heat_assessment'] = heat_screen(crop['heat'], crop['characteristics'])
        crop['water_assessment'] = {'status': 'unavailable', 'reason': 'missing_daily_reference_et', 'rainfed_shortfall_mm': None}
        if daily_et_path or daily_weather is not None:
            try:
                crop['water_assessment'] = {'status': 'calculated', **{
                    bound: water_balance(crop['planting_water'], crop['characteristics'], et, rain, bound)
                    for bound in ('lower', 'upper')}}
            except MissingInput as error:
                crop['water_assessment']['reason'] = str(error)
    result['limitations'] = [v for v in result['limitations'] if not v.startswith('Rainfed shortfall')]
    result['limitations'] += ['Heat is a reference thermal screen, not verified maturity.',
                              'Water results require daily ET; monthly stage columns are not substituted.',
                              'No additional weather-based yield penalty is applied to historical yields.']
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir', type=Path, default=Path(__file__).resolve().parents[2] / 'Data')
    parser.add_argument('--daily-et', type=Path)
    parser.add_argument('--year', type=int, default=2024)
    parser.add_argument('--output', type=Path, default=None)
    args = parser.parse_args()
    result = analyze(args.data_dir, args.daily_et, year=args.year)
    args.output = args.output or Path(__file__).resolve().parent / "data" / f"allen-{args.year}-analysis.json"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({c['crop']: {'heat': c['heat_assessment']['status'], 'water': c['water_assessment']['status']} for c in result['crops']}))
