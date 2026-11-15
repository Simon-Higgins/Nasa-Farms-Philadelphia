"""Precompute default economic indicators for the published ML scenarios."""
import argparse
import csv
import json
from hashlib import sha256
from math import isfinite
from pathlib import Path
from statistics import mean

DATA = Path(__file__).resolve().parent / 'data'
CROPS = ('corn', 'soybeans')
ASSUMPTIONS = ('2025 national crop prices and compiled county 2026 regional cost proxies, '
               'held constant across both planning years without inflation adjustment.')


def load_budgets(data_dir):
    with (data_dir / 'crop_prices_us_2015_2025.csv').open(encoding='utf-8-sig', newline='') as stream:
        prices = {row['crop']: float(row['price_usd_per_yield_unit']) for row in csv.DictReader(stream)
                  if row['harvest_year'] == '2025' and row['crop'] in CROPS and row['yield_unit'] == 'bu'}
    if set(prices) != set(CROPS):
        raise ValueError('Both 2025 crop prices in USD/bu are required.')
    budgets = {}
    with (data_dir / 'nationwide_county_crop_costs_2015_2026.csv').open(encoding='utf-8-sig', newline='') as stream:
        for row in csv.DictReader(stream):
            county = row['county_fips']
            if county in budgets:
                raise ValueError(f'Duplicate county budget: {county}')
            budgets[county] = {crop: {'price_usd_per_bu': prices[crop],
                                      'cost_usd_per_acre': float(row[f'{crop}_cost_usd_per_planted_acre_2026'])}
                               for crop in CROPS}
            if any(not isfinite(value) or value < 0 for budget in budgets[county].values() for value in budget.values()):
                raise ValueError(f'Invalid default budget: {county}')
    return budgets


def prepare_county(county, budgets, pairs):
    directory = DATA / 'counties' / county
    bundle = json.loads((directory / 'ml-yields.json').read_text(encoding='utf-8'))
    margins, waters = {}, {}
    for record in bundle['records']:
        crop, year = record['crop'], record['historical_year']
        key = f'{crop}:{year}'
        budget = budgets[crop]
        margins[key] = record['predicted_yield'] * budget['price_usd_per_bu'] - budget['cost_usd_per_acre']
        snapshot = json.loads((directory / f'{year}-analysis.json').read_text(encoding='utf-8'))
        source = next(c for c in snapshot['crops'] if c['crop'] == crop)
        waters[key] = source['water_assessment']['upper']['rainfed_shortfall_mm']
    rotations = {}
    for first in CROPS:
        for second in CROPS:
            annual_margins = [(margins[f'{first}:{a}'] + margins[f'{second}:{b}']) / 2 for a, b in pairs]
            shortfalls = [waters[f'{first}:{a}'] + waters[f'{second}:{b}'] for a, b in pairs]
            rotations[f'{first}-{second}'] = {
                'annual_margin_usd_per_acre': mean(annual_margins),
                'rainfed_shortfall_mm': mean(shortfalls),
                'margin_range_usd_per_acre': [min(annual_margins), max(annual_margins)],
                'shortfall_range_mm': [min(shortfalls), max(shortfalls)]}
    prediction_hash = sha256((directory / 'ml-yields.json').read_text(encoding='utf-8').encode()).hexdigest()
    analysis_hashes = {str(year): sha256((directory / f'{year}-analysis.json').read_text(encoding='utf-8').encode()).hexdigest()
                       for year in {record['historical_year'] for record in bundle['records']}}
    result = {'county_fips': county, 'historical_pairs': pairs, 'budget': budgets,
              'prediction_sha256': prediction_hash, 'analysis_sha256': analysis_hashes,
              'economics_assumptions': ASSUMPTIONS, 'price_year': 2025, 'cost_year': 2026,
              'season_margins': margins, 'rotations': rotations}
    path = directory / 'default-margins.json'
    temporary = path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(result, separators=(',', ':'), allow_nan=False) + '\n', encoding='utf-8')
    temporary.replace(path)


def prepare(data_dir):
    budgets = load_budgets(data_dir)
    catalog = json.loads((DATA / 'planning-counties.json').read_text(encoding='utf-8'))
    for county in catalog['counties']:
        prepare_county(county['county_fips'], budgets[county['county_fips']], county['historical_pairs'])
    print(f'Prepared default margins for {len(catalog["counties"])} counties')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir', type=Path, default=Path(__file__).resolve().parents[2] / 'Data')
    prepare(parser.parse_args().data_dir)
