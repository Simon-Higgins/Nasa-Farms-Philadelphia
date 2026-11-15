"""Build an auditable single-season input slice from the team's local CSVs."""
import argparse
import csv
import json
import math
from pathlib import Path

CROPS = {'corn': 'corn_grain', 'soybeans': 'soybeans', 'sorghum': 'sorghum_grain'}
GDD = {'corn': 'corn', 'soybeans': 'soybean', 'sorghum': 'grain_sorghum'}


def build(data_dir, county='20001', year=2024):
    sources = []

    def read(name, predicate):
        path = data_dir / name
        if not path.exists():
            path = data_dir / Path(name).name
        if name == 'cdl_with_yields_aggregated_cleaned.csv' and not path.exists():
            path = data_dir / 'nasa_data_merged(simon).csv'
        sources.append(path.name)
        with path.open(encoding='utf-8-sig', newline='') as stream:
            return [row for row in csv.DictReader(stream) if predicate(row)]

    def one(rows, label):
        if len(rows) != 1:
            raise ValueError(f'{label}: expected one row, found {len(rows)}')
        return rows[0]

    def number(value):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError('Non-finite input')
        return result

    yields = one(read('cdl_with_yields_aggregated_cleaned.csv', lambda r: r['county_fips'] == county), 'yields')
    costs = one(read('cost/nationwide_county_crop_costs_2015_2026.csv', lambda r: r['county_fips'] == county), 'costs')
    prices = read('share/crop_prices_us_2015_2025.csv', lambda r: r['harvest_year'] == str(year))
    soils = read('share/county_planting_date_smap_and_plant_available_water_2015_2026.csv', lambda r: r['county_fips'] == county and r['scenario_planting_date'].startswith(str(year)) and r['planting_scenario'] == 'water_demand_reference')
    characteristics = read('share/crop_characteristics.csv', lambda r: r['crop'] in CROPS)
    crops = []
    for crop, yield_name in CROPS.items():
        soil = one([r for r in soils if r['crop'] == crop], crop + ' soil')
        heat = one(read(f'share/county_{GDD[crop]}_gdd_planting_dates_2015_2026.csv', lambda r: r['county_fips'] == county and r['year'] == str(year) and r['planting_date'] == soil['scenario_planting_date']), crop + ' heat')
        price = one([r for r in prices if r['crop'] == crop], crop + ' price')
        if price['yield_unit'] != 'bu':
            raise ValueError('Price/yield unit mismatch')
        raw_yield = yields.get(f'{yield_name}_yield_measured_in_bu_acre_{year}')
        crop_yield = number(raw_yield) if raw_yield not in (None, '') else None
        cost = number(costs[f'{crop}_cost_usd_per_planted_acre_{year}'])
        revenue = crop_yield * number(price['price_usd_per_yield_unit']) if crop_yield is not None else None
        crops.append({'crop': crop, 'yield_bu_per_harvested_acre': crop_yield,
                      'price_usd_per_bu': number(price['price_usd_per_yield_unit']),
                      'cost_usd_per_planted_acre': cost,
                      'cost_geography': costs[f'{crop}_cost_source_{year}'],
                      'revenue_proxy_usd_per_acre': round(revenue, 4) if revenue is not None else None,
                      'margin_proxy_usd_per_acre': round(revenue - cost, 4) if revenue is not None else None,
                      'price_source': price, 'planting_water': soil, 'heat': heat,
                      'characteristics': one([r for r in characteristics if r['crop'] == crop], crop + ' characteristics')})
    return {'data_mode': 'historical_inputs', 'county_fips': county,
            'county_label': f"{costs['ers_county_name']}, {costs['state_abbr']}",
            'harvest_year': year, 'crops': crops, 'source_files': sources,
            'cost_source_url': costs['cost_data_url'],
            'limitations': [
                'Single historical season; not a two-year rotation forecast.',
                'County yields and soil moisture are area summaries, not field observations.',
                'Prices are national; costs are regional proxies, not county farm accounts.',
                'Margin proxy assumes harvested acres equal planted acres; excludes rotation effects.',
                'Rainfed shortfall is not yet calculated. Heat inputs are screening proxies, not verified maturity.',
                'Stage water-use columns are alternative stages; do not sum them together.'
            ]}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir', type=Path, default=Path(__file__).resolve().parents[2] / 'Data')
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parent / 'data' / 'allen-2024.json')
    args = parser.parse_args()
    result = build(args.data_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(f"Saved {result['county_label']} / {result['harvest_year']}: {len(result['crops'])} crops")
