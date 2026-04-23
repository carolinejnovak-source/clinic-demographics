"""
ring_ads.py — 1AC campaign impressions + clicks within 30-min drive time
Uses area-weighted ZIP-isochrone intersection (Shapely + TIGERweb ZCTA boundaries)
"""
import json, os, sys, time, requests
sys.path.insert(0, "/opt/mikala-apps/clinic-demographics/venv/lib/python3.12/site-packages")
import flexpolyline
from shapely.geometry import shape, Point
from shapely.ops import unary_union
from google.ads.googleads.client import GoogleAdsClient
from collections import defaultdict

GADS_CONFIG = {
    'developer_token': 'WjIXymJXbBG9E0VXgVbHlg',
    'client_id': '453985230410-a23tdpb2f51ehgbfrhe0not2mfu6qb48.apps.googleusercontent.com',
    'client_secret': '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',
    'refresh_token': '1//06fud1b81YyFfCgYIARAAGAYSNwF-L9IrcznV5A6rQJrHwRSvMkefp--7RgQpGxzTiGmUwIXwPFfW9qQYO3IhQKYbY9_tATj6g9s',
    'login_customer_id': '8026139929',
    'use_proto_plus': True,
}
CUSTOMER_ID = '4728374529'
ONE_AC_IDS = ['23461310636','23465856364','23465856469','23461310825','23465856451','23465856235']

HERE_API_KEY = "WYqJdDCGYmTRFQT5zxM_aUNTb8XH0_MwezLgqvRkCbE"
HERE_DEPARTURE = "2026-03-10T10:00:00"

CACHE_DIR = '/opt/mikala-apps/clinic-demographics/ring_ads_cache'
os.makedirs(CACHE_DIR, exist_ok=True)

_mem_cache = {}

def _safe_key(s):
    return s.replace(' ','_').replace('/','_').replace(',','').replace('.','')


# ── 1. 30-min isochrone ──────────────────────────────────────────────────────

def get_30min_isochrone(lat, lon):
    key = f'iso30:{lat:.4f},{lon:.4f}'
    if key in _mem_cache:
        return _mem_cache[key]
    cache_file = os.path.join(CACHE_DIR, f'iso30_{lat:.4f}_{lon:.4f}.json')
    if os.path.exists(cache_file):
        with open(cache_file) as f:
            result = json.load(f)
        _mem_cache[key] = result
        return result
    try:
        url = (
            f"https://isoline.router.hereapi.com/v8/isolines"
            f"?transportMode=car&origin={lat},{lon}"
            f"&range%5Btype%5D=time&range%5Bvalues%5D=1800"
            f"&departureTime={HERE_DEPARTURE}&apikey={HERE_API_KEY}"
        )
        r = requests.get(url, timeout=30)
        if r.status_code == 200:
            data = r.json()
            features = []
            for isoline in data.get('isolines', []):
                for poly in isoline.get('polygons', []):
                    encoded = poly['outer']
                    coords_raw = flexpolyline.decode(encoded)
                    coords = [[lon, lat] for lat, lon in coords_raw]
                    features.append({
                        'type': 'Feature',
                        'geometry': {'type': 'Polygon', 'coordinates': [coords]},
                        'properties': {'contour': 30, 'metric': 'time'}
                    })
            result = {'type': 'FeatureCollection', 'features': features}
            with open(cache_file, 'w') as f:
                json.dump(result, f)
            _mem_cache[key] = result
            return result
    except Exception as e:
        print(f'30-min isochrone error ({lat},{lon}): {e}')
    return None


def _decode_flexible_polyline(encoded):
    """Decode HERE flexible polyline encoding to list of [lon, lat] coords."""
    import math
    # HERE flexible polyline decoder
    result = []
    header_byte = ord(encoded[0])
    precision = header_byte & 0x0F
    factor = 10 ** precision
    idx = 1
    last_lat = 0
    last_lon = 0

    def decode_value(idx):
        result2 = 0
        shift = 0
        while True:
            b = ord(encoded[idx]) - 63
            idx += 1
            result2 |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        val = -(result2 >> 1) if result2 & 1 else result2 >> 1
        return val, idx

    while idx < len(encoded):
        dlat, idx = decode_value(idx)
        dlon, idx = decode_value(idx)
        last_lat += dlat
        last_lon += dlon
        result.append([last_lon / factor, last_lat / factor])

    if result and result[0] != result[-1]:
        result.append(result[0])
    return result


# ── 2. 1AC ZIP-level data (cached daily) ────────────────────────────────────

def get_1ac_zip_data(start_date, end_date):
    """Returns {zip_code_str: {clicks, impressions}} for all 1AC campaigns."""
    cache_key = f'1ac_zip:{start_date}:{end_date}'
    if cache_key in _mem_cache:
        return _mem_cache[cache_key]
    cache_file = os.path.join(CACHE_DIR, f'1ac_zip_{start_date}_{end_date}.json')
    # Use cache if less than 6 hours old
    if os.path.exists(cache_file):
        age = time.time() - os.path.getmtime(cache_file)
        if age < 21600:
            with open(cache_file) as f:
                result = json.load(f)
            _mem_cache[cache_key] = result
            return result

    client = GoogleAdsClient.load_from_dict(GADS_CONFIG)
    service = client.get_service('GoogleAdsService')
    id_list = ','.join(ONE_AC_IDS)
    query = (
        "SELECT campaign.id, segments.geo_target_postal_code, "
        "metrics.impressions, metrics.clicks "
        "FROM geographic_view "
        "WHERE segments.date BETWEEN '" + start_date + "' AND '" + end_date + "' "
        "AND campaign.id IN (" + id_list + ") "
        "AND metrics.impressions > 0 "
        "LIMIT 10000"
    )
    rows = list(service.search(customer_id=CUSTOMER_ID, query=query))

    # Resolve geo resource names -> ZIP codes
    geo_resources = set(str(r.segments.geo_target_postal_code) for r in rows if str(r.segments.geo_target_postal_code))
    geo_to_zip = {}
    sample = list(geo_resources)
    for i in range(0, len(sample), 200):
        chunk = sample[i:i+200]
        rn_str = "', '".join(chunk)
        q2 = ("SELECT geo_target_constant.resource_name, geo_target_constant.name "
              "FROM geo_target_constant "
              "WHERE geo_target_constant.resource_name IN ('" + rn_str + "')")
        try:
            resp = service.search(customer_id=CUSTOMER_ID, query=q2)
            for row in resp:
                g = row.geo_target_constant
                geo_to_zip[g.resource_name] = g.name  # e.g. "10001"
        except Exception as e:
            print(f'Geo resolve error: {e}')

    # Aggregate
    result = defaultdict(lambda: {'clicks': 0, 'impressions': 0})
    for row in rows:
        res = str(row.segments.geo_target_postal_code)
        zipcode = geo_to_zip.get(res)
        if not zipcode:
            continue
        zipcode = zipcode.strip().zfill(5)
        result[zipcode]['clicks'] += row.metrics.clicks
        result[zipcode]['impressions'] += row.metrics.impressions

    result = dict(result)
    with open(cache_file, 'w') as f:
        json.dump(result, f)
    _mem_cache[cache_key] = result
    return result


# ── 3. ZCTA boundaries from TIGERweb ────────────────────────────────────────

def get_zcta_boundaries_in_bbox(min_lon, min_lat, max_lon, max_lat):
    """Fetch ZCTA (ZIP) boundary polygons from TIGERweb for a bounding box."""
    cache_key = f'zcta:{min_lon:.3f},{min_lat:.3f},{max_lon:.3f},{max_lat:.3f}'
    if cache_key in _mem_cache:
        return _mem_cache[cache_key]
    cache_file = os.path.join(CACHE_DIR, f'zcta_{min_lon:.3f}_{min_lat:.3f}_{max_lon:.3f}_{max_lat:.3f}.json')
    if os.path.exists(cache_file):
        age = time.time() - os.path.getmtime(cache_file)
        if age < 86400 * 7:
            with open(cache_file) as f:
                result = json.load(f)
            _mem_cache[cache_key] = result
            return result

    url = 'https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/tigerWMS_ACS2022/MapServer/0/query'
    # Fetch in pages (max 1000 per request)
    result = {}
    offset = 0
    while True:
        params = {
            'geometry': f'{min_lon},{min_lat},{max_lon},{max_lat}',
            'geometryType': 'esriGeometryEnvelope',
            'inSR': '4326',
            'spatialRel': 'esriSpatialRelIntersects',
            'outFields': 'ZCTA5,GEOID',
            'outSR': '4326',
            'f': 'json',
            'returnGeometry': 'true',
            'resultOffset': offset,
            'resultRecordCount': 500,
        }
        try:
            r = requests.get(url, params=params, timeout=45)
            data = r.json()
        except Exception as e:
            print(f'TIGERweb ZCTA error: {e}')
            break
        feats = data.get('features', [])
        if not feats:
            break
        for feat in feats:
            attrs = feat.get('attributes', {})
            zipcode = str(attrs.get('ZCTA5') or attrs.get('GEOID') or '').strip().zfill(5)
            if not zipcode or zipcode == '00000':
                continue
            geom_data = feat.get('geometry')
            if not geom_data:
                continue
            try:
                # ArcGIS JSON rings format -> GeoJSON
                rings = geom_data.get('rings', [])
                if not rings:
                    continue
                # Convert to GeoJSON polygon
                geojson_geom = {'type': 'Polygon', 'coordinates': [[[pt[0],pt[1]] for pt in ring] for ring in rings]}
                geom = shape(geojson_geom)
                if not geom.is_valid:
                    geom = geom.buffer(0)
                result[zipcode] = geom.__geo_interface__
            except Exception:
                pass
        if not data.get('exceededTransferLimit', False):
            break
        offset += len(feats)
    with open(cache_file, 'w') as f:
        json.dump(result, f)
    _mem_cache[cache_key] = result
    return result


# ── 4. Main: compute ring-ads for an address ────────────────────────────────

def compute_ring_ads(lat, lon, start_date, end_date):
    """
    Returns {clicks, impressions, zip_count, coverage_note} 
    for 1AC campaigns within 30-min drive time of (lat, lon).
    Area-weighted by isochrone-ZCTA intersection.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    # Fetch 30-min isochrone and 1AC ZIP data in parallel
    iso = None
    zip_data = None

    def _fetch_iso():
        return get_30min_isochrone(lat, lon)

    def _fetch_zip():
        return get_1ac_zip_data(start_date, end_date)

    with ThreadPoolExecutor(max_workers=2) as ex:
        f_iso = ex.submit(_fetch_iso)
        f_zip = ex.submit(_fetch_zip)
        iso = f_iso.result()
        zip_data = f_zip.result()

    if not iso or not iso.get('features'):
        return {'error': 'Could not fetch 30-min isochrone'}

    # Build isochrone polygon
    try:
        iso_polys = [shape(f['geometry']) for f in iso['features'] if f.get('geometry')]
        iso_shape = unary_union(iso_polys)
        if not iso_shape.is_valid:
            iso_shape = iso_shape.buffer(0)
    except Exception as e:
        return {'error': f'Isochrone polygon error: {e}'}

    if not zip_data:
        return {'clicks': 0, 'impressions': 0, 'zip_count': 0, 'coverage_note': 'No 1AC data for date range'}

    # Bounding box of isochrone
    b = iso_shape.bounds
    min_lon, min_lat, max_lon, max_lat = b[0]-0.05, b[1]-0.05, b[2]+0.05, b[3]+0.05

    # Get ZCTA boundaries
    zcta_geoms = get_zcta_boundaries_in_bbox(min_lon, min_lat, max_lon, max_lat)

    total_clicks = 0.0
    total_impressions = 0.0
    matched_zips = 0
    partial_zips = 0

    for zipcode, geom_dict in zcta_geoms.items():
        if zipcode not in zip_data:
            continue
        try:
            zip_shape = shape(geom_dict)
            if not zip_shape.is_valid:
                zip_shape = zip_shape.buffer(0)
            intersection = iso_shape.intersection(zip_shape)
            if intersection.is_empty:
                continue
            zip_area = zip_shape.area
            if zip_area == 0:
                continue
            frac = min(intersection.area / zip_area, 1.0)
            if frac < 0.01:
                continue
            d = zip_data[zipcode]
            total_clicks += d['clicks'] * frac
            total_impressions += d['impressions'] * frac
            matched_zips += 1
            if frac < 0.95:
                partial_zips += 1
        except Exception:
            pass

    return {
        'clicks': round(total_clicks),
        'impressions': round(total_impressions),
        'zip_count': matched_zips,
        'partial_zips': partial_zips,
        'coverage_note': f'{matched_zips} ZIPs ({partial_zips} partial)',
    }
