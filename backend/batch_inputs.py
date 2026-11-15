"""Single-pass source indexing for nationwide historical preparation."""
from array import array
from collections import defaultdict
import csv
from datetime import date, timedelta
import io
from math import isnan
import zipfile

YEARS = range(2020, 2025)


class BatchInputs:
    def __init__(self, data_dir, counties):
        self.data_dir = data_dir
        self.counties = set(counties)
        self.rows = defaultdict(lambda: defaultdict(list))
        self.shared = {}
        self.weather = {'et': {}, 'rain': {}}
        aliases = {'cdl_with_yields_aggregated_cleaned.csv': 'nasa_data_merged(simon).csv'}
        for name in ('cdl_with_yields_aggregated_cleaned.csv', 'nationwide_county_crop_costs_2015_2026.csv'):
            path = data_dir / name
            if not path.exists():
                path = data_dir / aliases.get(name, name)
            print(f'Indexing {path.name}', flush=True)
            with path.open(encoding='utf-8-sig', newline='') as stream:
                for row in csv.DictReader(stream):
                    if row['county_fips'] in self.counties:
                        self.rows[row['county_fips']][name].append(row)
        for name in ('crop_prices_us_2015_2025.csv', 'crop_characteristics.csv'):
            with (data_dir / name).open(encoding='utf-8-sig', newline='') as stream:
                self.shared[name] = list(csv.DictReader(stream))
        soil_name = 'county_planting_date_smap_and_plant_available_water_2015_2026.csv'
        dates = set()
        print('Indexing planting water', flush=True)
        with (data_dir / soil_name).open(encoding='utf-8-sig', newline='') as stream:
            for row in csv.DictReader(stream):
                county = row['county_fips']
                if (county in self.counties and row['crop'] in ('corn', 'soybeans')
                        and row['planting_scenario'] == 'water_demand_reference'
                        and row['scenario_planting_date'][:4] in {str(y) for y in YEARS}):
                    self.rows[county][soil_name].append(row)
                    dates.add((county, row['crop'], row['scenario_planting_date']))
        for crop, suffix in (('corn', 'corn'), ('soybeans', 'soybean')):
            name = f'county_{suffix}_gdd_planting_dates_2015_2026.csv'
            print(f'Indexing {name}', flush=True)
            with (data_dir / name).open(encoding='utf-8-sig', newline='') as stream:
                for row in csv.DictReader(stream):
                    if (row['county_fips'], crop, row['planting_date']) in dates:
                        self.rows[row['county_fips']][name].append(row)
        print('Indexing daily ET', flush=True)
        with (data_dir / 'county_daily_reference_et_2015_2026.csv').open(encoding='utf-8-sig', newline='') as stream:
            self._weather(stream, 'et', 'eto_mm_day')
        print('Indexing daily precipitation', flush=True)
        with zipfile.ZipFile(data_dir / 'county_daily_gridmet_precipitation_2015_2026.zip') as archive:
            names = [name for name in archive.namelist() if name.endswith('.csv')]
            if len(names) != 1:
                raise ValueError('Expected exactly one precipitation CSV')
            with archive.open(names[0]) as raw, io.TextIOWrapper(raw, encoding='utf-8-sig', newline='') as stream:
                self._weather(stream, 'rain', 'precipitation_mm')

    def _weather(self, stream, kind, column):
        seen = {}
        for row in csv.DictReader(stream):
            county = row['county_fips']
            if county not in self.counties:
                continue
            year = int(row['date'][:4])
            if year not in YEARS:
                continue
            day = (date.fromisoformat(row['date']) - date(year, 1, 1)).days
            key = county, year
            if key not in seen:
                seen[key] = bytearray(366)
                self.weather[kind][key] = array('d', [float('nan')]) * 366
            if seen[key][day]:
                raise ValueError(f'Duplicate daily {kind}: {county}/{row["date"]}')
            seen[key][day] = 1
            try:
                value = float(row[column])
            except (ValueError, TypeError):
                value = float('nan')
            self.weather[kind][key][day] = value

    def for_season(self, county, year):
        weather = []
        for kind in ('et', 'rain'):
            values = self.weather[kind].get((county, year), [])
            weather.append({(date(year, 1, 1) + timedelta(days=i)).isoformat(): value
                            for i, value in enumerate(values) if not isnan(value)})
        return {**self.shared, **self.rows[county]}, tuple(weather)
