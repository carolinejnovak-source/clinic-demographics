"""
poi_scorer.py — OSM Points of Interest scoring (Phase 1)
Fetches POI data from Overpass API, caches 30 days, returns counts/decay scores.
"""
import json
import math
import time
import os
import re
import requests
from datetime import datetime, timedelta

CACHE_FILE = '/opt/mikala-apps/clinic-demographics/poi_cache.json'
OVERPASS_URL = 'https://overpass-api.de/api/interpreter'
CACHE_TTL_DAYS = 30

PHARMACY_NAMES = re.compile(r'cvs|walgreens|rite aid|duane reade', re.I)
BIGBOX_NAMES = re.compile(
    r"target|walmart|costco|sam'?s club|bj'?s|kohl'?s|dick'?s|best buy|home depot|lowe'?s|tj maxx|marshalls|homegoods",
    re.I
)
NEGATIVE_NAMES = re.compile(
    r"dollar tree|dollar general|family dollar|ollie'?s|five below|ace cash|rent-?a-?center|aaron'?s|payday",
    re.I
)


def _load_cache():
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE) as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_cache(cache):
    try:
        with open(CACHE_FILE, 'w') as f:
            json.dump(cache, f)
    except Exception as e:
        print(f"poi_cache save error: {e}")


def _cache_key(lat, lng):
    return f"{round(lat, 2)},{round(lng, 2)}"


def _haversine_miles(lat1, lon1, lat2, lon2):
    R = 3958.8
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))


def _overpass_query(query):
    try:
        r = requests.post(OVERPASS_URL, data={'data': query}, timeout=40)
        r.raise_for_status()
        return r.json().get('elements', [])
    except Exception as e:
        print(f"Overpass error: {e}")
        return []


def _dedupe(elements):
    seen = set()
    result = []
    for el in elements:
        lat = el.get('lat') or (el.get('center', {}) or {}).get('lat')
        lon = el.get('lon') or (el.get('center', {}) or {}).get('lon')
        if lat is None or lon is None:
            continue
        key = (round(lat, 4), round(lon, 4))
        if key not in seen:
            seen.add(key)
            el['_lat'] = lat
            el['_lon'] = lon
            result.append(el)
    return result


def _miles_to_deg(miles):
    return miles / 69.0


def _bbox(lat, lng, miles):
    d = _miles_to_deg(miles)
    return f"{lat-d},{lng-d},{lat+d},{lng+d}"


def _fetch_pharmacies(lat, lng):
    bb = _bbox(lat, lng, 1.0)
    q = f"""
[out:json][timeout:30];
(
  node["amenity"="pharmacy"]({bb});
  way["amenity"="pharmacy"]({bb});
  node["shop"="chemist"]({bb});
  way["shop"="chemist"]({bb});
);
out center;
"""
    elements = _overpass_query(q)
    time.sleep(1)
    return _dedupe(elements)


def _fetch_primary_care(lat, lng):
    bb = _bbox(lat, lng, 1.0)
    q = f"""
[out:json][timeout:30];
(
  node["amenity"="doctors"]({bb});
  way["amenity"="doctors"]({bb});
  node["healthcare"="doctor"]({bb});
  way["healthcare"="doctor"]({bb});
);
out center;
"""
    elements = _overpass_query(q)
    time.sleep(1)
    return _dedupe(elements)


def _fetch_bigbox(lat, lng):
    bb = _bbox(lat, lng, 2.0)
    q = f"""
[out:json][timeout:30];
(
  node["shop"="department_store"]({bb});
  way["shop"="department_store"]({bb});
  node["shop"="wholesale"]({bb});
  way["shop"="wholesale"]({bb});
  node["shop"="superstore"]({bb});
  way["shop"="superstore"]({bb});
);
out center;
"""
    elements = _overpass_query(q)
    time.sleep(1)
    return _dedupe(elements)


def _fetch_negative(lat, lng):
    bb = _bbox(lat, lng, 1.0)
    q = f"""
[out:json][timeout:30];
(
  node["shop"="pawnbroker"]({bb});
  way["shop"="pawnbroker"]({bb});
);
out center;
"""
    elements = _overpass_query(q)
    time.sleep(1)
    return _dedupe(elements)


def get_poi_scores(lat, lng):
    """
    Returns dict with pharmacy_score, pharmacy_count, primary_care_count,
    bigbox_count, negative_cotenant_count.
    """
    cache = _load_cache()
    key = _cache_key(lat, lng)
    now = datetime.utcnow()

    if key in cache:
        entry = cache[key]
        cached_at = datetime.fromisoformat(entry.get('cached_at', '2000-01-01'))
        if now - cached_at < timedelta(days=CACHE_TTL_DAYS):
            return entry['data']

    # Fetch from Overpass
    result = {
        'pharmacy_score': 0,
        'pharmacy_count': 0,
        'primary_care_count': 0,
        'bigbox_count': 0,
        'negative_cotenant_count': 0,
    }

    try:
        # Pharmacies
        pharmacies = _fetch_pharmacies(lat, lng)
        pharm_score = 0
        pharm_count = 0
        for el in pharmacies:
            name = (el.get('tags') or {}).get('name', '')
            is_pharm = (
                (el.get('tags') or {}).get('amenity') == 'pharmacy'
                or (el.get('tags') or {}).get('shop') == 'chemist'
                or PHARMACY_NAMES.search(name)
            )
            if not is_pharm:
                continue
            dist = _haversine_miles(lat, lng, el['_lat'], el['_lon'])
            if dist <= 1.0:
                pharm_count += 1
                if dist <= 0.5:
                    pharm_score += 2
                else:
                    pharm_score += 1
        result['pharmacy_score'] = pharm_score
        result['pharmacy_count'] = pharm_count

        # Primary care
        pc_elements = _fetch_primary_care(lat, lng)
        pc_count = 0
        for el in pc_elements:
            tags = el.get('tags') or {}
            speciality = tags.get('speciality', tags.get('healthcare:speciality', ''))
            is_pc = (
                tags.get('amenity') == 'doctors'
                or tags.get('healthcare') == 'doctor'
            )
            # Filter by speciality if present
            if speciality and not re.search(r'family|general|internal|primary', speciality, re.I):
                continue
            if is_pc:
                dist = _haversine_miles(lat, lng, el['_lat'], el['_lon'])
                if dist <= 1.0:
                    pc_count += 1
        result['primary_care_count'] = pc_count

        # Big box
        bigbox_elements = _fetch_bigbox(lat, lng)
        bb_count = 0
        for el in bigbox_elements:
            name = (el.get('tags') or {}). get('name', '')
            if not BIGBOX_NAMES.search(name):
                # Also count if shop=department_store/wholesale regardless of name
                tags = el.get('tags') or {}
                if tags.get('shop') not in ('department_store', 'wholesale', 'superstore'):
                    continue
            dist = _haversine_miles(lat, lng, el['_lat'], el['_lon'])
            if dist <= 2.0:
                bb_count += 1
        result['bigbox_count'] = bb_count

        # Negative co-tenants
        neg_elements = _fetch_negative(lat, lng)
        neg_count = 0
        for el in neg_elements:
            name = (el.get('tags') or {}).get('name', '')
            is_neg = (
                (el.get('tags') or {}).get('shop') == 'pawnbroker'
                or NEGATIVE_NAMES.search(name)
            )
            if is_neg:
                dist = _haversine_miles(lat, lng, el['_lat'], el['_lon'])
                if dist <= 1.0:
                    neg_count += 1
        result['negative_cotenant_count'] = neg_count

    except Exception as e:
        print(f"POI scoring error: {e}")

    cache[key] = {'data': result, 'cached_at': now.isoformat()}
    _save_cache(cache)
    return result
