"""
patient_heatmap.py — Patient origin ZIP heatmap data
Fetches from Looker, caches, geocodes ZIPs to lat/lon for Leaflet.heat
"""
import os, json, re, time, requests
from collections import defaultdict

CACHE_FILE = os.path.join(os.path.dirname(__file__), 'patient_zips_cache.json')
CACHE_TTL = 86400 * 7  # 7 days

LOOKER_BASE = 'https://vipmedicalgroup.cloud.looker.com'
LOOKER_CLIENT_ID = '5JCDdKynFKxfJVwr5Ph3'
LOOKER_CLIENT_SECRET = 'pqBBrB6ffNTSDvDGjD6HZssw'

_zip_centroid_cache = {}
_nomi = None

def _get_nomi():
    global _nomi
    if _nomi is None:
        import pgeocode
        _nomi = pgeocode.Nominatim('us')
    return _nomi

def _zip_to_latlon(zipcode):
    if zipcode in _zip_centroid_cache:
        return _zip_centroid_cache[zipcode]
    try:
        row = _get_nomi().query_postal_code(zipcode)
        if row is not None and not hasattr(row['latitude'], '__len__'):
            lat, lon = float(row['latitude']), float(row['longitude'])
            if lat and lon and not (lat != lat):  # nan check
                _zip_centroid_cache[zipcode] = (lat, lon)
                return (lat, lon)
    except:
        pass
    _zip_centroid_cache[zipcode] = None
    return None


# ── Clinic alias/consolidation map ──────────────────────────────────────────
# Maps Looker location keys → canonical clinic name
# Multiple keys can map to the same canonical name; their patient counts merge
CLINIC_ALIASES = {
    'Morris County':          'Morristown',
    'Clinic-West Orange':     'West Orange',
    'ASC-West Orange':        'West Orange',
    'West Orange Northfield': 'West Orange',
    'Clinic-Woodland':        'Woodland Park',
    'ASC-Woodland':           'Woodland Park',
    'Old Bethesda':           'Bethesda',
    'ASC-Bethesda':           'Bethesda',
    'Old Maple Lawn':         'Maple Lawn',
    # Brooklyn-Williamsburg is its own standalone clinic
    'ASC-Midtown':            'Upper East Side',
    'Central Park':           'Dallas - Arlington',
    # ASC-NYCAS — TBD (leaving standalone)
    'ASC-Princeton':          'Princeton',
    'New Woodbridge':         'Woodbridge',
    'North-Jericho':          'Jericho',
    'North-Roslyn':           'Jericho',
    'South-Lindenhurst':      'W Islip',
    'Kyle':                   'Austin - Kyle',
    'Arlington':              'Dallas - Arlington',
    'Fort Worth':             'Dallas - Fort Worth',
    'Houston-Richmond':       'Houston',
    'Houston-River Oaks':     'Houston',
    'ASC-Golden Triangle':    'Temecula',
}

def _apply_aliases(raw_data):
    """Merge aliased clinic keys into their canonical names."""
    from collections import defaultdict
    merged = defaultdict(lambda: defaultdict(int))
    for key, zips in raw_data.items():
        canonical = CLINIC_ALIASES.get(key, key)
        for zipcode, count in zips.items():
            merged[canonical][zipcode] += count
    return {k: dict(v) for k, v in merged.items()}

def _fetch_from_looker():
    """Pull patient ZIP data from Looker, return {clinic_key: {zip: count}}"""
    r = requests.post(f'{LOOKER_BASE}/api/4.0/login',
        data={'client_id': LOOKER_CLIENT_ID, 'client_secret': LOOKER_CLIENT_SECRET}, timeout=30)
    token = r.json()['access_token']
    headers = {'Authorization': f'Bearer {token}'}
    body = {
        'model': 'snow_prd_analytics_db',
        'view': 'fct_dim_patients_phi_exclude',
        'fields': [
            'fct_dim_patients_phi_exclude.patient_location',
            'fct_dim_patients_phi_exclude.patient_postal_code',
            'fct_dim_patients_phi_exclude.count',
        ],
        'filters': {'fct_dim_patients_phi_exclude.patient_postal_code': '-NULL,-""'},
        'limit': 50000
    }
    resp = requests.post(f'{LOOKER_BASE}/api/4.0/queries/run/json',
        headers=headers, json=body, timeout=120)
    data = resp.json()
    clinic_zips = defaultdict(lambda: defaultdict(int))
    for row in data:
        loc = row.get('fct_dim_patients_phi_exclude.patient_location') or ''
        zipcode = str(row.get('fct_dim_patients_phi_exclude.patient_postal_code') or '').strip()[:5]
        count = int(row.get('fct_dim_patients_phi_exclude.count') or 0)
        m = re.match(r'\(([^)]+)\)', loc)
        if m and zipcode and len(zipcode) == 5 and zipcode.isdigit():
            clinic_zips[m.group(1)][zipcode] += count
    return {k: dict(v) for k, v in clinic_zips.items()}

def _load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            d = json.load(open(CACHE_FILE))
            if time.time() - d.get('_ts', 0) < CACHE_TTL:
                return _apply_aliases(d.get('data', {}))
        except:
            pass
    return None

def _save_cache(data):
    json.dump({'_ts': time.time(), 'data': data}, open(CACHE_FILE, 'w'))

def get_all_clinic_zips(force_refresh=False):
    if not force_refresh:
        cached = _load_cache()
        if cached:
            return cached
    data = _fetch_from_looker()
    _save_cache(data)
    return data

# Fuzzy match Looker clinic key → site name
def _normalize(s):
    return re.sub(r'[^a-z0-9]', '', s.lower())

def find_clinic_key(site_name, clinic_zips):
    """Match a site name to the best Looker clinic key"""
    norm_site = _normalize(site_name)
    # Direct match
    for key in clinic_zips:
        if _normalize(key) == norm_site:
            return key
    # Contains match
    for key in clinic_zips:
        nk = _normalize(key)
        if nk in norm_site or norm_site in nk:
            return key
    # Word overlap
    site_words = set(norm_site)
    best, best_score = None, 0
    for key in clinic_zips:
        score = sum(1 for c in _normalize(key) if c in site_words)
        if score > best_score:
            best_score = score
            best = key
    return best if best_score > 3 else None

def get_heatmap_points(site_name):
    """Return [[lat, lon, weight], ...] for a given site name"""
    clinic_zips = get_all_clinic_zips()
    key = find_clinic_key(site_name, clinic_zips)
    if not key:
        return None, 0
    zips = clinic_zips[key]
    points = []
    total = 0
    max_count = max(zips.values()) if zips else 1
    for zipcode, count in sorted(zips.items(), key=lambda x: -x[1]):
        latlon = _zip_to_latlon(zipcode)
        if latlon:
            weight = round(count / max_count, 3)
            points.append([latlon[0], latlon[1], weight])
            total += count
    return points, total
