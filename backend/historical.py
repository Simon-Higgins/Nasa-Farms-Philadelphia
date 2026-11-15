"""Rank two actual historical seasons without a yield-model dependency."""
import json
from pathlib import Path
from fastapi import HTTPException

CANDIDATES = [('corn', 'corn'), ('corn', 'soybeans'), ('soybeans', 'corn'), ('sorghum', 'soybeans')]
FAMILIES = {'corn': 'grass', 'soybeans': 'legume', 'sorghum': 'grass'}


def compare_historical(request):
    from backend.main import normalized, explain
    if (request.county_fips, request.first_harvest_year) != ('20001', 2024):
        raise HTTPException(404, 'Historical comparison covers Allen County (20001), 2024–2025.')
    if request.baseline_rotation is None:
        raise HTTPException(422, 'Select a baseline_rotation for historical comparison.')
    baseline_crops = tuple(request.baseline_rotation)
    if any(crop not in FAMILIES for crop in baseline_crops):
        raise HTTPException(422, 'Historical crops supported: corn, soybeans, sorghum.')
    snapshots = []
    for year in (2024, 2025):
        path = Path(__file__).resolve().parent / 'data' / f'allen-{year}-analysis.json'
        if not path.exists():
            raise HTTPException(503, f'Prepare historical analysis for {year} first.')
        snapshot = json.loads(path.read_text(encoding='utf-8'))
        if snapshot['county_fips'] != request.county_fips or snapshot['harvest_year'] != year:
            raise HTTPException(503, 'Historical snapshot identity mismatch.')
        snapshots.append(snapshot)
    rows, unranked = [], []
    sequences = list(dict.fromkeys([baseline_crops, *CANDIDATES]))
    for sequence in sequences:
        is_baseline = sequence == baseline_crops
        family_pass = not request.require_crop_family_change or FAMILIES[sequence[0]] != FAMILIES[sequence[1]]
        if not is_baseline and not family_pass:
            continue
        reasons, seasons = [], []
        for index, crop in enumerate(sequence):
            source = next((c for c in snapshots[index]['crops'] if c['crop'] == crop), None)
            season = {'crop': crop, 'harvest_year': 2024 + index}
            if source is None:
                reasons.append(f'missing_crop:{crop}:{2024 + index}')
            else:
                margin = source['margin_proxy_usd_per_acre']
                if margin is None:
                    reasons.append(f'missing_yield:{crop}:{2024 + index}')
                heat = source['heat_assessment']['status']
                if heat != 'passed':
                    reasons.append(f'heat_{heat}:{crop}:{2024 + index}')
                water = source['water_assessment']
                if water['status'] != 'calculated':
                    reasons.append(f"{water['reason']}:{crop}:{2024 + index}")
                season.update(annual_margin_usd_per_acre=margin,
                              yield_basis=source['yield_basis'],
                              heat_status=heat,
                              planting_date=source['planting_water']['scenario_planting_date'])
                if water['status'] == 'calculated':
                    season['rainfed_shortfall_mm'] = water['upper']['rainfed_shortfall_mm']
                    season['rainfed_shortfall_lower_mm'] = water['lower']['rainfed_shortfall_mm']
            seasons.append(season)
        row = {'id': '-'.join(sequence), 'is_baseline': is_baseline,
               'seasons': seasons, 'meets_crop_family_filter': family_pass,
               'score': None, 'score_delta_vs_baseline': None}
        if reasons:
            row.update(reasons=reasons, heat_status='unassessed' if any('missing_crop:' in r for r in reasons) else next((s['heat_status'] for s in seasons if s.get('heat_status') != 'passed'), 'passed'),
                       explanation='Cannot score: ' + '; '.join(reasons))
            unranked.append(row)
        else:
            row.update(annual_margin_usd_per_acre=sum(s['annual_margin_usd_per_acre'] for s in seasons) / 2,
                       rainfed_shortfall_mm=sum(s['rainfed_shortfall_mm'] for s in seasons),
                       rainfed_shortfall_lower_mm=sum(s['rainfed_shortfall_lower_mm'] for s in seasons),
                       heat_status='passed')
            rows.append(row)
    margins = [r['annual_margin_usd_per_acre'] for r in rows]
    waters = [r['rainfed_shortfall_mm'] for r in rows]
    for row in rows:
        m = normalized(row['annual_margin_usd_per_acre'], min(margins), max(margins))
        w = 1 - normalized(row['rainfed_shortfall_mm'], min(waters), max(waters))
        row.update(margin_normalized=m, lower_shortfall_normalized=w,
                   score=round(100 * (request.weights.margin * m + request.weights.lower_rainfed_shortfall * w), 10))
    current = next(r for r in rows + unranked if r['is_baseline'])
    if current['score'] is not None:
        current.update(explanation='Your selected rotation under 2024–2025 historical conditions.', score_delta_vs_baseline=0)
    alternatives = sorted([r for r in rows if not r['is_baseline']], key=lambda r: (-r['score'], r['id']))[:2]
    for rank, row in enumerate(alternatives, 1):
        row['rank'] = rank
        if current['score'] is not None:
            row['score_delta_vs_baseline'] = round(row['score'] - current['score'], 10)
            row['explanation'] = 'Compared with the baseline: ' + explain(row, current)
        else:
            row['explanation'] = 'Baseline has insufficient data; direct comparison unavailable.'
    return {'data_mode': 'historical', 'county_fips': request.county_fips,
            'county_label': snapshots[0]['county_label'], 'scenario_label': '2024–2025 historical county scenarios; not a forecast',
            'baseline': current, 'rotations': alternatives,
            'unranked': [r for r in unranked if not r['is_baseline']],
            'applied_weights': request.weights.model_dump(),
            'applied_filters': {'require_crop_family_change': request.require_crop_family_change},
            'sources': sorted(set(s for snapshot in snapshots for s in snapshot['source_files'])),
            'assumptions': ['Observed county yields, national prices and regional cost proxies; not ML predictions.',
                            'Harvested area assumed equal to planted area; no previous-crop yield or cost adjustment.',
                            'Each year independently initialized from its planting-day SMAP; no inter-year moisture carryover.',
                            'Fixed root depth and zero irrigation; stage calendars are hypothetical, not observed planting dates.',
                            'Scoring uses upper-Kc shortfall consistently; lower-Kc totals are also returned.',
                            'Normalize over complete eligible candidates plus a complete baseline, then return the top two alternatives.',
                            'Candidate library: corn-corn, corn-soybeans, soybeans-corn, sorghum-soybeans, plus selected baseline.']}
