"""Prepare complete consecutive scenarios from 2020-2024 in one source pass."""
import argparse
import csv
from dataclasses import asdict
import json
from math import isclose
from pathlib import Path
from backend.batch_inputs import BatchInputs, YEARS
from backend.predictions import load_crop_csv
from backend.prepare_analysis import analyze
from backend.prepare_margins import load_budgets, prepare_county

CROPS = ('corn', 'soybeans')
DATA = Path(__file__).resolve().parent / 'data'
PAIRS = [(year, year + 1) for year in range(2020, 2024)]


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(value, separators=(',', ':'), allow_nan=False) + '\n', encoding='utf-8')
    temporary.replace(path)


def prepare(data_dir, predictions_dir, counties=None):
    budgets = load_budgets(data_dir)
    predictions, observed = {}, {}
    for crop in CROPS:
        path = predictions_dir / f'{crop}_with_predictions.csv'
        records = load_crop_csv(path, crop=crop, fips_column='county_fips',
                               prediction_column='predicted_yield', year_column='year',
                               scenario_id='historical-export', yield_unit='bu/acre',
                               model_version='random-forest-export-version-unspecified',
                               weather_assumptions='Historical NASA POWER and county crop-share delta features')
        predictions[crop] = {(r.county_fips, r.harvest_year): r for r in records}
        with path.open(encoding='utf-8-sig', newline='') as stream:
            for row in csv.DictReader(stream):
                observed[row['county_fips'].zfill(5), crop, int(row['year'])] = float(row['yield'])
    requested = list(dict.fromkeys(counties)) if counties else sorted({c for c, y in predictions['corn']})
    available = {}
    for county in requested:
        available[county] = {year for year in YEARS if all(
            predictions[crop].get((county, year)) is not None
            and predictions[crop][county, year].predicted_yield is not None for crop in CROPS)}
    candidates = [c for c in requested if any(set(pair) <= available[c] for pair in PAIRS)]
    print(f'{len(candidates)} counties have at least one complete prediction pair', flush=True)
    inputs = BatchInputs(data_dir, candidates)
    catalog = {'candidate_pairs': [list(pair) for pair in PAIRS], 'counties': [], 'excluded': []}
    for county in requested:
        snapshots, normalized, failures = {}, [], {}
        for year in sorted(available[county]) if county in candidates else []:
            try:
                rows, weather = inputs.for_season(county, year)
                snapshot = analyze(data_dir, county=county, year=year, crop_names=CROPS,
                                   source_rows=rows, daily_weather=weather)
                season_records = []
                for source in snapshot['crops']:
                    crop = source['crop']
                    prediction = predictions[crop][county, year]
                    if source['heat_assessment']['status'] != 'passed':
                        raise ValueError(f'heat_{source["heat_assessment"]["status"]}:{crop}:{year}')
                    if source['water_assessment']['status'] != 'calculated':
                        raise ValueError(f'water_unavailable:{crop}:{year}:{source["water_assessment"]["reason"]}')
                    actual = source['yield_bu_per_harvested_acre']
                    if actual is None or not isclose(observed[county, crop, year], actual, abs_tol=1e-6):
                        raise ValueError(f'Observed-yield unit/identity crosscheck failed:{crop}:{year}')
                    record = asdict(prediction)
                    record.update(historical_year=year, observed_yield=actual)
                    season_records.append(record)
                snapshots[year] = snapshot
                normalized.extend(season_records)
            except (ValueError, KeyError) as error:
                failures[year] = str(error)
        pairs, excluded = [], []
        for pair in PAIRS:
            reasons = []
            for year in pair:
                for crop in CROPS:
                    prediction = predictions[crop].get((county, year))
                    if prediction is None or prediction.predicted_yield is None:
                        reasons.append(f'missing_prediction:{crop}:{year}')
                if year in failures:
                    reasons.append(failures[year])
            if reasons:
                excluded.append({'historical_years': list(pair), 'reasons': reasons})
            elif all(year in snapshots for year in pair):
                pairs.append(list(pair))
        if not pairs:
            catalog['excluded'].append({'county_fips': county, 'excluded_pairs': excluded})
            continue
        directory = DATA / 'counties' / county
        for year, snapshot in snapshots.items():
            save(directory / f'{year}-analysis.json', snapshot)
        save(directory / 'ml-yields.json', {
            'yield_unit': 'bu/acre', 'model_family': 'random_forest', 'model_version': None,
            'evaluation_split': 'Current training source uses a random holdout; exported training membership is unavailable',
            'unit_basis': 'Observed export yields matched compiled bu/harvested-acre columns for each included row',
            'records': normalized})
        label = next(iter(snapshots.values()))['county_label']
        prepare_county(county, budgets[county], pairs)
        catalog['counties'].append({'county_fips': county, 'county_label': label, 'crops': list(CROPS),
                                    'historical_pairs': pairs, 'scenario_count': len(pairs), 'excluded_pairs': excluded})
        print(f'Ready {county}: {len(pairs)} pairs', flush=True)
    save(DATA / 'planning-counties.json', catalog)
    print(f'Published {len(catalog["counties"])} counties; excluded {len(catalog["excluded"])}', flush=True)
    return catalog


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir', type=Path, default=Path(__file__).resolve().parents[2] / 'Data')
    parser.add_argument('--predictions-dir', type=Path, default=Path('training_files'))
    parser.add_argument('--counties', nargs='+', help='Omit to prepare every county with a complete prediction pair')
    args = parser.parse_args()
    prepare(args.data_dir, args.predictions_dir, args.counties)
