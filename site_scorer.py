"""
site_scorer.py — Composite VIP Site Scorer
Combines OSM POI, competition decay, and demographic data into a 0-150 score.
Based on Buxton methodology, adapted for VIP Medical Group.
"""
import json
import os
import math
import statistics

from esri_scorer import get_esri_demographics, get_esri_traffic
from poi_scorer import get_poi_scores
from competition_scorer import get_competition_decay_score, get_patients_per_competitor

PHASE2_FILE = '/opt/mikala-apps/clinic-demographics/phase2_results.json'
NORMS_FILE = '/opt/mikala-apps/clinic-demographics/score_norms.json'

# Weights (must sum to 1.0)

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

CENSUS_API_KEY = "39d91e3ea57b794ee42f0e60b4548835eb21293b"

def get_census_demographics(lat, lng, zip_code=None):
    """
    Fetch Census-based patient value variables:
    - population_45plus (total pop 45+ within ~5 mile radius ZIP)
    - population_growth_pct (ACS 2023 vs ACS 2019 comparison)
    Returns dict or None on failure.
    """
    import requests, json, os, time
    
    cache_file = os.path.join(os.path.dirname(__file__), "census_phase2_cache.json")
    cache_key = f"{round(lat,3)},{round(lng,3)}"
    
    # Load cache
    try:
        with open(cache_file) as f:
            cache = json.load(f)
    except:
        cache = {}
    
    if cache_key in cache and time.time() - cache[cache_key].get("ts", 0) < 30*24*3600:
        return cache[cache_key]["data"]
    
    result = {"population_45plus": None, "population_growth_pct": None}
    
    if not zip_code:
        # Reverse geocode to ZIP using Census geocoder
        try:
            r = requests.get(
                "https://geocoding.geo.census.gov/geocoder/geographies/coordinates",
                params={"x": lng, "y": lat, "benchmark": "Public_AR_Current", "vintage": "Current_Current", "format": "json"},
                timeout=10
            )
            geos = r.json().get("result", {}).get("geographies", {})
            zips = geos.get("2020 ZIP Code Tabulation Areas", [])
            if zips:
                zip_code = zips[0].get("GEOID", "")[:5]
        except Exception as e:
            print(f"Census reverse geocode error: {e}")
    
    if zip_code:
        # Population 45+ from B01001 table
        # B01001_016E through B01001_025E = Male 45-85+
        # B01001_040E through B01001_049E = Female 45-85+
        male_45 = "+".join([f"B01001_0{str(i).zfill(3)}E" for i in range(16, 26)])
        female_45 = "+".join([f"B01001_0{str(i).zfill(3)}E" for i in range(40, 50)])
        vars_45 = male_45 + "," + female_45.replace("+", ",")
        
        try:
            r = requests.get(
                "https://api.census.gov/data/2023/acs/acs5",
                params={
                    "get": ",".join([f"B01001_0{str(i).zfill(3)}E" for i in list(range(16,26)) + list(range(40,50))]),
                    "for": f"zip code tabulation area:{zip_code}",
                    "key": CENSUS_API_KEY
                },
                timeout=15
            )
            data = r.json()
            if len(data) > 1:
                row = data[1]
                # Sum up all the age variables (indices 0-19 are the 20 age vars)
                total_45plus = sum(int(v or 0) for v in row[:20])
                result["population_45plus"] = total_45plus
        except Exception as e:
            print(f"Census pop45+ error: {e}")
        
        # Population growth: compare ACS 2023 vs 2019 total population
        try:
            r_now = requests.get(
                "https://api.census.gov/data/2023/acs/acs5",
                params={"get": "B01003_001E", "for": f"zip code tabulation area:{zip_code}", "key": CENSUS_API_KEY},
                timeout=10
            )
            r_past = requests.get(
                "https://api.census.gov/data/2019/acs/acs5",
                params={"get": "B01003_001E", "for": f"zip code tabulation area:{zip_code}", "key": CENSUS_API_KEY},
                timeout=10
            )
            now_data = r_now.json()
            past_data = r_past.json()
            if len(now_data) > 1 and len(past_data) > 1:
                pop_now = int(now_data[1][0] or 0)
                pop_past = int(past_data[1][0] or 0)
                if pop_past > 0:
                    result["population_growth_pct"] = round((pop_now - pop_past) / pop_past * 100, 2)
        except Exception as e:
            print(f"Census growth error: {e}")
    
    # Cache
    cache[cache_key] = {"ts": time.time(), "data": result}
    try:
        with open(cache_file, "w") as f:
            json.dump(cache, f)
    except:
        pass
    
    return result


WEIGHTS = {
    'area_draw': 0.35,
    'patient_value': 0.18,
    'competition': 0.22,
    'location_chars': 0.13,
    'thresholds': 0.12,
}

# Sub-weights within area draw
AREA_DRAW_W = {
    'pharmacy_score': 0.25,
    'primary_care_count': 0.20,
    'bigbox_count': 0.15,
    'negative_cotenant_penalty': 0.25,  # negated
    'traffic': 0.15,
}

GRADE_THRESHOLDS = [
    (120, 'Excellent'),
    (100, 'Good'),
    (85, 'Average'),
    (70, 'Below Average'),
    (0, 'Poor'),
]


def _load_phase2():
    try:
        with open(PHASE2_FILE) as f:
            data = json.load(f)
        return data.get('results', [])
    except Exception as e:
        print(f"phase2 load error: {e}")
        return []


def _compute_norms(records):
    """Compute normalization stats (median, stdev) for each variable from network data."""
    fields = ['pop_10min', 'pop_20min', 'female_35plus_10min', 'female_35plus_20min',
              'median_income_zip', 'insured_pct']
    norms = {}
    for field in fields:
        vals = [r.get(field) for r in records if r.get(field) is not None]
        if vals:
            norms[field] = {
                'median': statistics.median(vals),
                'mean': statistics.mean(vals),
                'stdev': statistics.stdev(vals) if len(vals) > 1 else 1,
                'min': min(vals),
                'max': max(vals),
                'p25': sorted(vals)[len(vals)//4],
                'p75': sorted(vals)[3*len(vals)//4],
            }
    return norms


def _load_or_compute_norms():
    if os.path.exists(NORMS_FILE):
        try:
            with open(NORMS_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    records = _load_phase2()
    if not records:
        return {}
    norms = _compute_norms(records)
    try:
        with open(NORMS_FILE, 'w') as f:
            json.dump(norms, f, indent=2)
    except Exception as e:
        print(f"norms save error: {e}")
    return norms


def _percentile_score(value, norm, higher_is_better=True):
    """
    Map a raw value to 0-150 scale using network norms.
    100 = network median. Scale linearly between min/max.
    """
    if value is None:
        return 75  # neutral if missing
    med = norm.get('median', 0)
    stdev = norm.get('stdev', 1) or 1
    # Z-score relative to median
    z = (value - med) / stdev
    if not higher_is_better:
        z = -z
    # Map z-score to 0-150: z=0 → 100, z=±2 → 150/50
    score = 100 + z * 25
    return max(0, min(150, score))


def _simple_percentile(value, reference_values, higher_is_better=True):
    """Percentile rank value against reference list, scaled to 0-150."""
    if value is None or not reference_values:
        return 75
    sorted_vals = sorted(reference_values)
    n = len(sorted_vals)
    rank = sum(1 for v in sorted_vals if v <= value) / n  # 0-1
    if not higher_is_better:
        rank = 1 - rank
    return max(0, min(150, rank * 150))


def compute_site_score(lat, lng, address, demo_data=None, ring_pop_data=None, isochrone_data=None):
    """
    Compute composite VIP site score.

    Args:
        lat, lng: coordinates
        address: string address
        demo_data: dict from /demographics endpoint (optional)
        ring_pop_data: dict from /ring-pop endpoint (optional)
        isochrone_data: GeoJSON isochrone (optional)

    Returns:
        dict with total_score, area_draw_score, patient_value_score,
        competition_score, components, grade
    """
    demo_data = demo_data or {}
    ring_pop_data = ring_pop_data or {}
    norms = _load_or_compute_norms()
    phase2 = _load_phase2()

    # ── 1. Gather raw data ────────────────────────────────────────
    components = {}

    # POI scores
    poi = get_poi_scores(lat, lng)
    components.update(poi)

    # Demographics from passed data or defaults
    pop_10 = ring_pop_data.get('pop_10min') or demo_data.get('pop_10min')
    pop_20 = ring_pop_data.get('pop_20min') or demo_data.get('pop_20min')
    female_35_10 = ring_pop_data.get('female_35plus_10min') or demo_data.get('female_35plus_10min')
    female_35_20 = ring_pop_data.get('female_35plus_20min') or demo_data.get('female_35plus_20min')
    insured_pct = demo_data.get('insured_pct')
    median_income = demo_data.get('median_income_zip') or demo_data.get('median_income')

    components['pop_10min'] = pop_10
    components['pop_20min'] = pop_20
    components['female_35plus_10min'] = female_35_10
    components['female_35plus_20min'] = female_35_20
    components['insured_pct'] = insured_pct
    components['median_income'] = median_income

    # Competition
    competitors = demo_data.get('competitors', [])
    comp_scores = get_competition_decay_score(lat, lng, competitors)
    components.update(comp_scores)

    # Patients per competitor (use pop_20 as proxy for 25-min ring)
    ppc = get_patients_per_competitor(pop_20, comp_scores['competitor_count_2mi'])
    components['patients_per_competitor'] = ppc if ppc != float('inf') else (pop_20 or 0)

    # Phase 3: ESRI GeoEnrichment — population 45+, income, growth, traffic
    esri_dem = get_esri_demographics(lat, lng)
    if esri_dem:
        pop_45plus = esri_dem.get('population_45plus')
        pop_growth_pct = esri_dem.get('population_growth_pct')
        # Override median income with ESRI (more accurate than Census ZIP-level)
        if esri_dem.get('median_income'):
            demo_data['median_income'] = esri_dem['median_income']
    else:
        # Fallback to Census
        zip_code = demo_data.get('zip_code') or demo_data.get('zip')
        census_p2 = get_census_demographics(lat, lng, zip_code)
        pop_45plus = census_p2.get('population_45plus') if census_p2 else None
        pop_growth_pct = census_p2.get('population_growth_pct') if census_p2 else None
    components['population_45plus'] = pop_45plus
    components['population_growth_pct'] = pop_growth_pct

    # Traffic from ESRI (may be None if Traffic collection not available)
    esri_traffic = get_esri_traffic(lat, lng)
    components['avg_daily_traffic'] = esri_traffic.get('avg_daily_traffic') if esri_traffic else None

    # Location characteristics (greenfield defaults)
    components['days_per_week'] = 5
    components['months_per_year'] = 12

    # ── 2. Score each dimension ───────────────────────────────────

    # Reference value lists from phase2 for percentile ranking
    p2_pop20 = [r['pop_20min'] for r in phase2 if r.get('pop_20min')]
    p2_f35_10 = [r['female_35plus_10min'] for r in phase2 if r.get('female_35plus_10min')]
    p2_income = [r['median_income_zip'] for r in phase2 if r.get('median_income_zip')]
    p2_insured = [r['insured_pct'] for r in phase2 if r.get('insured_pct')]

    # ── Area Draw (35%) ────────────────────────────────────────────
    # pharmacy_score: raw pharmacy decay points (higher=better)
    pharmacy_ref = list(range(0, 15))  # 0-14 pts possible
    pharm_pct = _simple_percentile(poi['pharmacy_score'], pharmacy_ref, higher_is_better=True)

    # primary_care_count: more = better (foot traffic driver)
    pc_ref = list(range(0, 20))
    pc_pct = _simple_percentile(poi['primary_care_count'], pc_ref, higher_is_better=True)

    # bigbox_count: more = better
    bb_ref = list(range(0, 15))
    bb_pct = _simple_percentile(poi['bigbox_count'], bb_ref, higher_is_better=True)

    # negative_cotenant: more = worse
    neg_ref = list(range(0, 10))
    neg_pct = _simple_percentile(poi['negative_cotenant_count'], neg_ref, higher_is_better=False)

    # Traffic: use ESRI if available, else neutral
    avg_traffic = components.get('avg_daily_traffic')
    if avg_traffic and avg_traffic > 0:
        # Score: <5k=30, 5-15k=50, 15-30k=70, 30-60k=85, 60-100k=95, 100k+=100
        if avg_traffic >= 100000: traffic_pct = 100
        elif avg_traffic >= 60000: traffic_pct = 95
        elif avg_traffic >= 30000: traffic_pct = 85
        elif avg_traffic >= 15000: traffic_pct = 70
        elif avg_traffic >= 5000: traffic_pct = 50
        else: traffic_pct = 30
    else:
        traffic_pct = 75  # neutral until data available

    area_draw_raw = (
        pharm_pct * AREA_DRAW_W['pharmacy_score'] +
        pc_pct * AREA_DRAW_W['primary_care_count'] +
        bb_pct * AREA_DRAW_W['bigbox_count'] +
        neg_pct * AREA_DRAW_W['negative_cotenant_penalty'] +
        traffic_pct * AREA_DRAW_W['traffic']
    )
    area_draw_score = max(0, min(150, area_draw_raw))

    # ── Patient Value (18%) ───────────────────────────────────────
    # female_35plus as proxy for 45+ vascular patient pool
    f35_pct = _simple_percentile(female_35_10, p2_f35_10, higher_is_better=True)
    # insured_pct
    insured_pct_score = _simple_percentile(insured_pct, p2_insured, higher_is_better=True)
    # income (proxy for commercial insurance)
    income_pct = _simple_percentile(median_income, p2_income, higher_is_better=True)
    # population growth (placeholder 0 until ESRI → neutral)
    growth_pct = 75

    # Population 45+ (Buxton-aligned, better than female 35+ alone)
    p2_pop45 = [r.get('population_45plus') for r in phase2 if r.get('population_45plus')]
    pop45_pct = _simple_percentile(pop_45plus, p2_pop45, higher_is_better=True) if (pop_45plus and p2_pop45) else f35_pct

    # Population growth score
    if pop_growth_pct is not None:
        growth_pct = 100 + (pop_growth_pct * 5)  # each 1% growth = +5 pts
        growth_pct = max(0, min(150, growth_pct))
    else:
        growth_pct = 75  # neutral until data available

    patient_value_score = max(0, min(150,
        pop45_pct * 0.35 +
        insured_pct_score * 0.30 +
        income_pct * 0.15 +
        growth_pct * 0.20
    ))

    # ── Competition (22%) ─────────────────────────────────────────
    # competitor_decay_score: lower = better
    # Normalize against 0-20 range
    comp_decay_ref = list(range(0, 25))
    comp_decay_pct = _simple_percentile(comp_scores['competitor_decay_score'], comp_decay_ref, higher_is_better=False)

    # patients_per_competitor: higher = better (big number = blue ocean)
    ppc_val = components['patients_per_competitor']
    ppc_ref = p2_pop20 if p2_pop20 else [50000]  # rough ref
    ppc_pct = _simple_percentile(ppc_val, ppc_ref, higher_is_better=True)

    competition_score = max(0, min(150,
        comp_decay_pct * 0.50 +
        ppc_pct * 0.50
    ))

    # ── Location Characteristics (13%) ───────────────────────────
    # Greenfield default: 5 days/wk, 12 months — score as neutral (100)
    location_score = 100.0

    # ── Thresholds / Binary Bumps (12%) ──────────────────────────
    threshold_score = 100.0
    bumps = 0
    # Bump up if pop_20 > 100k
    if pop_20 and pop_20 > 100000:
        bumps += 10
    # Bump up if insured_pct > 80
    if insured_pct and insured_pct > 80:
        bumps += 10
    # Bump down if negative co-tenants >= 3
    if poi['negative_cotenant_count'] >= 3:
        bumps -= 15
    # Bump up if pharmacy anchor present (score >= 2)
    if poi['pharmacy_score'] >= 2:
        bumps += 5
    # Bump up if big box present
    if poi['bigbox_count'] >= 1:
        bumps += 5
    threshold_score = max(0, min(150, 100 + bumps))

    # ── Composite Score ───────────────────────────────────────────
    total_score = (
        area_draw_score * WEIGHTS['area_draw'] +
        patient_value_score * WEIGHTS['patient_value'] +
        competition_score * WEIGHTS['competition'] +
        location_score * WEIGHTS['location_chars'] +
        threshold_score * WEIGHTS['thresholds']
    )
    total_score = max(0, min(150, round(total_score, 1)))

    # Grade
    grade = 'Poor'
    for threshold, label in GRADE_THRESHOLDS:
        if total_score >= threshold:
            grade = label
            break

    return {
        'total_score': total_score,
        'area_draw_score': round(area_draw_score, 1),
        'patient_value_score': round(patient_value_score, 1),
        'competition_score': round(competition_score, 1),
        'location_score': round(location_score, 1),
        'threshold_score': round(threshold_score, 1),
        'grade': grade,
        'components': components,
    }
