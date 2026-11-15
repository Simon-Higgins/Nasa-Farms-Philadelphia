"""Aggregate complete historical weather pairs before normalizing scores."""
import json
from hashlib import sha256
from math import isclose, isfinite
from pathlib import Path
from statistics import mean

from fastapi import HTTPException
from backend.main import CropBudget, normalized, explain
from backend.coverage import planning_counties


def compare_planning(request):
    use_ml = request.yield_basis == 'ml_prediction'
    prepared = next((county for county in planning_counties()
                     if county['county_fips'] == request.county_fips), None)
    if (use_ml and prepared is None) or (not use_ml and request.county_fips != '20001'):
        raise HTTPException(404, 'County/yield basis unavailable. Check /api/v1/capabilities for prepared ML counties.')
    crops = ('corn', 'soybeans')
    if any(crop not in crops for crop in request.baseline_rotation):
        raise HTTPException(422, 'Planning crops currently supported: corn, soybeans.')
    planning_years = [request.first_harvest_year, request.first_harvest_year + 1]
    default_margins = None
    if request.budgets_by_year is None:
        if not use_ml:
            raise HTTPException(422, 'Observed-yield planning requires explicit budgets.')
        path = Path(__file__).resolve().parent / 'data' / 'counties' / request.county_fips / 'default-margins.json'
        if not path.exists():
            raise HTTPException(503, 'Prepare default margins with python -m backend.prepare_margins.')
        default_margins = json.loads(path.read_text(encoding='utf-8'))
        if default_margins['county_fips'] != request.county_fips:
            raise HTTPException(503, 'Default margin cache county mismatch.')
        if request.economics_assumptions is not None:
            raise HTTPException(422, 'Supply custom budgets with custom economics assumptions, or omit both for defaults.')
        budget = {crop: CropBudget.model_validate(value) for crop, value in default_margins['budget'].items()}
        request = request.model_copy(update={
            'budgets_by_year': {str(year): budget for year in planning_years},
            'economics_assumptions': default_margins['economics_assumptions']})
    elif request.economics_assumptions is None:
        raise HTTPException(422, 'Describe the supplied custom budget assumptions.')
    if set(request.budgets_by_year) != {str(year) for year in planning_years}:
        raise HTTPException(422, 'Supply budgets for exactly the two planning years.')
    for budgets in request.budgets_by_year.values():
        if set(budgets) != set(crops):
            raise HTTPException(422, 'Each planning year needs corn and soybean budgets.')
    snapshots = {}
    snapshot_hashes = {}
    first_years = (2020, 2021, 2022, 2023) if use_ml else (2023, 2024)
    data_dir = Path(__file__).resolve().parent / 'data'
    county_dir = data_dir / 'counties' / request.county_fips
    use_county_cache = use_ml and (county_dir / 'ml-yields.json').exists()
    if use_ml and not use_county_cache and request.county_fips != '20001':
        raise HTTPException(503, 'Prepared county ML cache is missing. Rebuild county preparation.')
    for year in range(first_years[0], first_years[-1] + 2):
        path = county_dir / f'{year}-analysis.json' if use_county_cache else data_dir / f'allen-{year}-analysis.json'
        if not path.exists():
            if use_ml:
                snapshots[year] = {}
                continue
            raise HTTPException(503, f'Prepare county {request.county_fips}, {year} environmental analysis.')
        text = path.read_text(encoding='utf-8')
        snapshot = json.loads(text)
        snapshot_hashes[str(year)] = sha256(text.encode()).hexdigest()
        if snapshot['county_fips'] != request.county_fips or snapshot['harvest_year'] != year:
            raise HTTPException(503, 'Planning snapshot identity mismatch.')
        snapshots[year] = {row['crop']: row for row in snapshot['crops']}

    predictions = {}
    model_metadata = None
    if use_ml:
        path = county_dir / 'ml-yields.json' if use_county_cache else data_dir / 'allen-ml-yields.json'
        if not path.exists():
            raise HTTPException(503, 'Prepared ML yield slice unavailable.')
        text = path.read_text(encoding='utf-8')
        bundle = json.loads(text)
        if default_margins is not None and (
                default_margins['prediction_sha256'] != sha256(text.encode()).hexdigest()
                or any(snapshot_hashes.get(year) != digest for year, digest in default_margins['analysis_sha256'].items())):
            raise HTTPException(503, 'Default margin sources changed. Rebuild margins.')
        if bundle['yield_unit'] != 'bu/acre':
            raise HTTPException(503, 'ML yield units do not match planning budgets.')
        model_metadata = {key: value for key, value in bundle.items() if key != 'records'}
        for record in bundle['records']:
            crop, year = record['crop'], record['historical_year']
            if record['county_fips'] != request.county_fips:
                raise HTTPException(503, 'ML prediction county mismatch.')
            key = (crop, year)
            if key in predictions:
                raise HTTPException(503, 'Duplicate ML prediction key.')
            value = record['predicted_yield']
            if value is not None and (not isinstance(value, (int, float)) or not isfinite(value) or value < 0):
                raise HTTPException(503, 'Invalid ML prediction value.')
            source = snapshots.get(year, {}).get(crop)
            if source is None or source['yield_bu_per_harvested_acre'] is None or not isclose(
                    record['observed_yield'], source['yield_bu_per_harvested_acre'], abs_tol=1e-6):
                raise HTTPException(503, 'Observed-yield crosscheck failed for ML source units/identity.')
            predictions[key] = record

    # Use one common scenario set across the baseline and every alternative.
    # Requiring all candidate crops prevents availability from favoring a plan.
    pairs, excluded = [], []
    for first_year in first_years:
        reasons = []
        for year in (first_year, first_year + 1):
            for crop in crops:
                if use_ml and predictions.get((crop, year), {}).get('predicted_yield') is None:
                    reasons.append(f'missing_prediction:{crop}:{year}')
                row = snapshots.get(year, {}).get(crop)
                if row is None:
                    reasons.append(f'missing_crop:{crop}:{year}')
                elif (row['yield_bu_per_harvested_acre'] is None
                      or row['heat_assessment']['status'] != 'passed'
                      or row['water_assessment']['status'] != 'calculated'):
                    reasons.append(f'incomplete_season:{crop}:{year}')
        if reasons:
            if use_ml:
                prepared_exclusion = next((entry for entry in prepared.get('excluded_pairs', [])
                                           if entry['historical_years'] == [first_year, first_year + 1]), None)
                if prepared_exclusion is not None:
                    reasons = prepared_exclusion['reasons']
            excluded.append({'historical_years': [first_year, first_year + 1], 'reasons': reasons})
        else:
            pairs.append((first_year, first_year + 1))
    if not pairs:
        raise HTTPException(422, {'reason': 'No common complete historical pairs.', 'excluded': excluded})
    if default_margins is not None and default_margins['historical_pairs'] != [list(pair) for pair in pairs]:
        raise HTTPException(503, 'Default margins have outdated historical pairs. Rebuild margins.')

    rows = []
    baseline = tuple(request.baseline_rotation)
    for sequence in [(a, b) for a in crops for b in crops]:
        is_baseline = sequence == baseline
        family_pass = not request.require_crop_family_change or sequence[0] != sequence[1]
        if not is_baseline and not family_pass:
            continue
        scenarios = []
        for pair in pairs:
            seasons = []
            for index, crop in enumerate(sequence):
                source = snapshots[pair[index]][crop]
                budget = request.budgets_by_year[str(planning_years[index])][crop]
                prediction = predictions.get((crop, pair[index]))
                crop_yield = prediction['predicted_yield'] if use_ml else source['yield_bu_per_harvested_acre']
                seasons.append({
                    'crop': crop, 'harvest_year': planning_years[index],
                    'historical_year': pair[index], 'yield_basis': request.yield_basis,
                    'prediction_provenance': prediction if use_ml else None,
                    'yield_bu_per_harvested_acre': crop_yield,
                    'annual_margin_usd_per_acre': (default_margins['season_margins'][f'{crop}:{pair[index]}']
                        if default_margins is not None else crop_yield * budget.price_usd_per_bu - budget.cost_usd_per_acre),
                    'rainfed_shortfall_mm': source['water_assessment']['upper']['rainfed_shortfall_mm'],
                })
            scenarios.append({
                'historical_years': list(pair), 'seasons': seasons,
                'annual_margin_usd_per_acre': mean(s['annual_margin_usd_per_acre'] for s in seasons),
                'rainfed_shortfall_mm': sum(s['rainfed_shortfall_mm'] for s in seasons),
            })
        if default_margins is not None:
            summary = default_margins['rotations']['-'.join(sequence)]
        else:
            margins = [s['annual_margin_usd_per_acre'] for s in scenarios]
            waters = [s['rainfed_shortfall_mm'] for s in scenarios]
            summary = {'annual_margin_usd_per_acre': mean(margins), 'rainfed_shortfall_mm': mean(waters),
                       'margin_range_usd_per_acre': [min(margins), max(margins)],
                       'shortfall_range_mm': [min(waters), max(waters)]}
        rows.append({
            'id': '-'.join(sequence), 'is_baseline': is_baseline,
            'seasons': [{'crop': crop, 'harvest_year': year} for crop, year in zip(sequence, planning_years)],
            'meets_crop_family_filter': family_pass, 'heat_status': 'passed',
            **summary,
            'scenario_count': len(scenarios), 'scenarios': scenarios,
        })
    margins = [row['annual_margin_usd_per_acre'] for row in rows]
    waters = [row['rainfed_shortfall_mm'] for row in rows]
    for row in rows:
        margin = normalized(row['annual_margin_usd_per_acre'], min(margins), max(margins))
        water = 1 - normalized(row['rainfed_shortfall_mm'], min(waters), max(waters))
        row['score'] = round(100 * (request.weights.margin * margin + request.weights.lower_rainfed_shortfall * water), 10)
    current = next(row for row in rows if row['is_baseline'])
    current.update(score_delta_vs_baseline=0, explanation='Your plan evaluated across historical weather pairs using the returned planning budget assumptions.')
    alternatives = sorted((row for row in rows if not row['is_baseline']), key=lambda row: (-row['score'], row['id']))[:2]
    for rank, row in enumerate(alternatives, 1):
        row.update(rank=rank, score_delta_vs_baseline=round(row['score'] - current['score'], 10),
                   explanation='Across historical scenarios: ' + explain(row, current))
    return {
        'data_mode': 'planning_scenarios', 'county_fips': request.county_fips,
        'county_label': prepared['county_label'] if use_ml else 'Allen County, KS', 'planning_years': planning_years,
        'scenario_label': 'Equal-weight historical weather pairs with supplied planning budgets',
        'baseline': current, 'rotations': alternatives, 'unranked': [],
        'historical_pairs': [list(pair) for pair in pairs], 'excluded_pairs': excluded,
        'applied_weights': request.weights.model_dump(),
        'applied_filters': {'require_crop_family_change': request.require_crop_family_change},
        'budgets_by_year': {year: {crop: budget.model_dump() for crop, budget in budgets.items()}
                            for year, budgets in request.budgets_by_year.items()},
        'economics_assumptions': request.economics_assumptions,
        'margin_calculation': 'precomputed_default' if default_margins is not None else 'custom_budget',
        'yield_basis': request.yield_basis, 'model_metadata': model_metadata,
        'assumptions': [
            ('Random forest estimates on historical inputs; export training membership and evaluation split are unconfirmed.'
             if use_ml else 'Historical observed county yields are used.'),
            'Average scenario outcomes before score normalization; scenarios have equal weights.',
            'Overlapping historical pairs are dependent; reported ranges are scenario ranges.',
            'Water uses fixed root depth, zero irrigation and independent planting-day initialization each season.',
            'Upper-Kc daily shortfall is prepared separately for each historical crop-year.',
            'Supplied budgets assume harvested area equals planted area.',
            'No previous-crop yield adjustment or causal rotation effect is modeled.',
        ],
    }
