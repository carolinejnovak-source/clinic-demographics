"""
esri_scorer.py — ESRI GeoEnrichment integration (Phase 3)
Requires Referer header: https://mikala.vipmedicalgroup.ai
"""

import requests
import json
import os
import time

ESRI_API_KEY = "AAPTagA-ZHnVRY4hRFzy2FgF75Q..FP0NbWqz2VKFjHFRjPxVp07xRnR3VoVwH9ObIspuwqvep26gXAzaJr-gEonyzaQQLgizswCZlSv3cmKKi0x893DbCvXSM6DqjuZUTAQ6T5o7fz6qvcmHjm5bVKlCX4mI0_Lgohuu-jZl6k9I-aqLvd3ozj1aLN8lWJvUM6LhXdEbjLf0VUvkar_4SokEB7ZK_mMvUDBO7ytSztGbJ72OSqzzu-fRU5yyPSuS6wGTESMVmW8uSRUNxA..AT1_ykN7S8LI"

ESRI_HEADERS = {'Referer': 'https://mikala.vipmedicalgroup.ai'}
ENRICH_URL = "https://geoenrich.arcgis.com/arcgis/rest/services/World/geoenrichmentserver/GeoEnrichment/enrich"

CACHE_FILE = os.path.join(os.path.dirname(__file__), 'esri_cache.json')
_cache = None

def _load_cache():
    global _cache
    if _cache is None:
        try:
            with open(CACHE_FILE) as f:
                _cache = json.load(f)
        except Exception:
            _cache = {}
    return _cache

def _save_cache():
    try:
        with open(CACHE_FILE, 'w') as f:
            json.dump(_cache, f)
    except Exception:
        pass

def _enrich(lat, lng, data_collections):
    """Call ESRI GeoEnrichment for a point (1-mile default buffer)."""
    global _cache
    cache = _load_cache()
    cache_key = f"{lat:.4f},{lng:.4f}|{'|'.join(data_collections)}"
    if cache_key in cache:
        entry = cache[cache_key]
        if time.time() - entry.get('ts', 0) < 86400 * 30:
            return entry.get('data')

    study_areas = json.dumps([{"geometry": {"x": lng, "y": lat}}])
    try:
        r = requests.post(ENRICH_URL,
            params={'token': ESRI_API_KEY, 'f': 'json'},
            data={'studyAreas': study_areas, 'dataCollections': json.dumps(data_collections), 'f': 'json'},
            headers=ESRI_HEADERS, timeout=20)
        d = r.json()
        if 'error' in d:
            print(f"ESRI enrich error: {d['error']}")
            return None
        results = d.get('results', [])
        if not results:
            return None
        featuresets = results[0].get('value', {}).get('FeatureSet', [])
        if not featuresets:
            return None
        features = featuresets[0].get('features', [])
        if not features:
            return None
        attrs = features[0].get('attributes', {})
        cache[cache_key] = {'data': attrs, 'ts': time.time()}
        _cache = cache
        _save_cache()
        return attrs
    except Exception as e:
        print(f"ESRI enrich exception: {e}")
        return None


def get_esri_demographics(lat, lng):
    """
    Returns ESRI enrichment demographics for a location.
    Fetches Age + KeyUSFacts + PopulationTotals collections.
    """
    age_attrs = _enrich(lat, lng, ['Age'])
    facts_attrs = _enrich(lat, lng, ['KeyUSFacts'])
    pop_attrs = _enrich(lat, lng, ['PopulationTotals'])

    if not age_attrs and not facts_attrs:
        return None

    result = {'source': 'esri'}

    # Population 45+ (MALE45..MALE85 + FEM45..FEM85)
    age_buckets = [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85]
    if age_attrs:
        pop45_m = sum(age_attrs.get(f'MALE{a}', 0) or 0 for a in age_buckets if a >= 45)
        pop45_f = sum(age_attrs.get(f'FEM{a}', 0) or 0 for a in age_buckets if a >= 45)
        pop45 = pop45_m + pop45_f
        if pop45 > 0:
            result['population_45plus'] = pop45

    # Total population + 45% share
    total_pop = 0
    if facts_attrs:
        total_pop = facts_attrs.get('TOTPOP_CY', 0) or 0
        if total_pop > 0:
            result['total_population'] = total_pop
            if 'population_45plus' in result:
                result['pop45_pct'] = round(result['population_45plus'] / total_pop * 100, 1)

    # Median household income
    if facts_attrs:
        inc = facts_attrs.get('MEDHINC_CY', 0) or 0
        if inc > 0:
            result['median_income'] = inc

    # Population growth % (2020→current from PopulationTotals)
    if pop_attrs:
        pop_cy = pop_attrs.get('TOTPOP_CY', 0) or 0
        pop_2020 = pop_attrs.get('TOTPOP10', 0) or 0  # TOTPOP10 = 2010 census; use as baseline
        # POPGRWCYFY = current-to-forecast growth rate
        growth_forecast = pop_attrs.get('POPGRWCYFY', None)
        if growth_forecast is not None:
            result['population_growth_pct'] = round(float(growth_forecast) * 100, 2)
        elif pop_cy > 0 and pop_2020 > 0:
            result['population_growth_pct'] = round((pop_cy - pop_2020) / pop_2020 * 100, 2)

    return result if len(result) > 1 else None


def get_esri_traffic(lat, lng):
    """
    Returns ESRI traffic data. Traffic collection may require additional privileges.
    Returns dict with avg_daily_traffic or None.
    """
    attrs = _enrich(lat, lng, ['Traffic'])
    if not attrs:
        return None
    traffic = 0
    for k, v in attrs.items():
        if ('TRAFFIC' in k.upper() or 'AADT' in k.upper()) and isinstance(v, (int, float)) and v > 0:
            traffic = v
            break
    return {'avg_daily_traffic': int(traffic)} if traffic > 0 else None
