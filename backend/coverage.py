"""Published, fully prepared ML planning counties."""
import json
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parent / 'data'


@lru_cache(maxsize=1)
def _read_counties(version):
    # The file version invalidates this cache after an atomic catalog rebuild.
    return json.loads((DATA / 'planning-counties.json').read_text(encoding='utf-8'))['counties']


def planning_counties():
    path = DATA / 'planning-counties.json'
    if not path.exists():
        return [{'county_fips': '20001', 'county_label': 'Allen County, KS',
                 'crops': ['corn', 'soybeans'], 'historical_pairs': [[2022, 2023], [2023, 2024]]}]
    stat = path.stat()
    return _read_counties((stat.st_mtime_ns, stat.st_size))
