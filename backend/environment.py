"""Deterministic rainfed screening model; no ML dependency or network access."""
from datetime import date, timedelta
from math import isfinite


class MissingInput(ValueError):
    pass


def number(value, label, minimum=0):
    try:
        value = float(value)
    except (TypeError, ValueError):
        raise MissingInput(f'missing_or_invalid_{label}') from None
    if not isfinite(value) or value < minimum:
        raise MissingInput(f'missing_or_invalid_{label}')
    return value


def crop_coefficient(day, traits, bound):
    lengths = [int(number(traits[f'stage_{stage}_days'], stage, 1))
               for stage in ('initial', 'development', 'midseason', 'late_season')]
    ini, mid, end = [number(traits[f'kc_{stage}_{bound}'], f'kc_{stage}')
                     for stage in ('initial', 'mid', 'end')]
    a, b, c, d = lengths
    if not 0 <= day < sum(lengths):
        raise ValueError('Day outside crop calendar')
    if day < a:
        return ini
    if day < a + b:
        return ini + (mid - ini) * (day - a + 1) / b
    if day < a + b + c:
        return mid
    return mid + (end - mid) * (day - a - b - c + 1) / d


def heat_screen(heat, traits):
    target = number(traits['maturity_reference_gdd_F_days'], 'heat_target', 0.000001)
    status = heat['freeze_status']
    if status == 'threshold_reached':
        available = number(heat['gdd_F_days_before_first_fall_freeze'], 'pre_freeze_gdd')
        return {'status': 'passed' if available >= target else 'failed',
                'available_gdd_F_days': available, 'target_gdd_F_days': target,
                'deadline': heat['first_fall_freeze_proxy_date']}
    if status in ('no_freeze_through_year_end', 'no_freeze_through_last_observation'):
        available = number(heat['gdd_F_days_through_last_observation_if_no_freeze'], 'observed_gdd')
        return {'status': 'passed' if available >= target else ('failed' if status == 'no_freeze_through_year_end' else 'undetermined'),
                'available_gdd_F_days': available, 'target_gdd_F_days': target,
                'observations_through': heat['freeze_observations_through']}
    raise MissingInput('unknown_freeze_status')


def water_balance(soil, traits, daily_et, daily_rain, bound='lower'):
    """Fixed-depth bucket. Planting-day SMAP initializes state; updates start next day.

    Root growth is deliberately not inferred: use a fixed top-meter-limited mature
    root depth, not the 5cm seed-zone estimate. This is an explicit scenario.
    Rain infiltrates up to storage capacity; excess leaves the bucket before ET.
    """
    if bound not in ('lower', 'upper'):
        raise ValueError('Unknown coefficient bound')
    if soil['estimate_status'] != 'estimated':
        raise MissingInput('invalid_planting_water_estimate')
    depth = min(1.0, number(traits['max_effective_root_depth_lower_m'], 'root_depth', .000001))
    capacity = number(soil['available_water_storage_top_1m_mm'], 'capacity') * depth
    initial = number(soil['estimated_available_water_top_1m_mm'], 'initial_water') * depth
    if initial > capacity + 1e-6:
        raise MissingInput('initial_water_exceeds_capacity')
    stored = initial
    start = date.fromisoformat(soil['scenario_planting_date'])
    days = sum(int(number(traits[f'stage_{stage}_days'], stage, 1)) for stage in ('initial', 'development', 'midseason', 'late_season'))
    monthly = {}
    totals = {'demand_mm': 0., 'precipitation_mm': 0., 'excess_mm': 0., 'supplied_mm': 0., 'rainfed_shortfall_mm': 0.}
    for day in range(1, days):
        current = (start + timedelta(days=day)).isoformat()
        if current not in daily_et or current not in daily_rain:
            raise MissingInput(f'missing_daily_weather:{current}')
        demand = number(daily_et[current], 'daily_et') * crop_coefficient(day, traits, bound)
        rain = number(daily_rain[current], 'daily_precipitation')
        excess = max(0., stored + rain - capacity)
        available = min(capacity, stored + rain)
        supplied = min(available, demand)
        stored = available - supplied
        values = dict(demand_mm=demand, precipitation_mm=rain, excess_mm=excess,
                      supplied_mm=supplied, rainfed_shortfall_mm=demand - supplied)
        month = monthly.setdefault(current[:7], {key: 0. for key in totals})
        for key, value in values.items():
            totals[key] += value
            month[key] += value
    return {**totals, 'monthly': monthly, 'initial_storage_mm': initial,
            'final_storage_mm': stored, 'capacity_mm': capacity,
            'fixed_root_depth_m': depth, 'days_updated': days - 1,
            'coefficient_bound': bound,
            'assumptions': ['Zero irrigation.', 'Fixed effective root depth; no seedling root-growth model.',
                            'Uniform soil water with depth; storage capped at top 1m.',
                            'All precipitation enters bucket; excess is lost before daily uptake.',
                            'Planting-day demand and rain excluded because SMAP initializes that day.',
                            'Unmet demand is a bucket deficit, not a crop stress or yield-loss model.']}
