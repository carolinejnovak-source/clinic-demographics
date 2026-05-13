#!/usr/bin/env python3
"""
esri_precache.py — Batch pre-cache ESRI GeoEnrichment data for all VIP clinic sites.
Run quarterly (or manually). Reads lat/lon from phase2_results.json + Google Sheet geocodes.
Saves to esri_cache.json (30-day cache already in esri_scorer, extended here to 90 days).
"""

import sys
import os
import json
import time
import requests

sys.path.insert(0, '/opt/mikala-apps/clinic-demographics')
import esri_scorer

PHASE2_FILE = '/opt/mikala-apps/clinic-demographics/phase2_results.json'
SITES_FILE = '/tmp/vip_sites.json'
LOG_FILE = '/opt/mikala-apps/clinic-demographics/esri_precache.log'

def geocode_address(address):
    """Geocode an address using ESRI geocoding service."""
    try:
        r = requests.get(
            'https://geocode-api.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates',
            params={'SingleLine': address, 'token': esri_scorer.ESRI_API_KEY, 'f': 'json', 'maxLocations': 1},
            headers=esri_scorer.ESRI_HEADERS, timeout=10)
        d = r.json()
        candidates = d.get('candidates', [])
        if candidates:
            loc = candidates[0]['location']
            return loc['y'], loc['x']  # lat, lng
    except Exception as e:
        print(f"  Geocode error: {e}")
    return None, None

def load_sites():
    """Load all sites with coordinates from phase2_results and vip_sites."""
    sites = []
    seen = set()

    # From phase2_results (has lat/lon for 73 sites)
    with open(PHASE2_FILE) as f:
        data = json.load(f)
    for r in data['results']:
        lat = r.get('lat')
        lon = r.get('lon')
        name = r.get('name', '')
        addr = r.get('address', '')
        if lat and lon and name not in seen:
            sites.append({'name': name, 'lat': float(lat), 'lng': float(lon), 'address': addr})
            seen.add(name)
        elif name and addr and name not in seen:
            sites.append({'name': name, 'lat': None, 'lng': None, 'address': addr})
            seen.add(name)

    # From vip_sites.json (Google Sheet geocodes)
    if os.path.exists(SITES_FILE):
        with open(SITES_FILE) as f:
            sheet_data = json.load(f)
        for tab, tab_sites in sheet_data.items():
            for site in tab_sites:
                name = site.get('name', '')
                lat = site.get('lat')
                lng = site.get('lng')
                addr = site.get('address', '')
                if name and name not in seen and lat and lng:
                    sites.append({'name': name, 'lat': float(lat), 'lng': float(lng), 'address': addr})
                    seen.add(name)

    return sites

def run_precache():
    sites = load_sites()
    print(f"Total sites: {len(sites)}")

    has_coords = [s for s in sites if s['lat'] and s['lng']]
    needs_geocode = [s for s in sites if not s['lat'] and s['address']]
    print(f"  With coords: {len(has_coords)}")
    print(f"  Need geocoding: {len(needs_geocode)}")

    results = {'cached': [], 'failed': [], 'geocoded': []}

    # Geocode missing ones
    for site in needs_geocode:
        print(f"  Geocoding: {site['name']} — {site['address']}")
        lat, lng = geocode_address(site['address'])
        if lat and lng:
            site['lat'] = lat
            site['lng'] = lng
            has_coords.append(site)
            results['geocoded'].append(site['name'])
            print(f"    → {lat:.4f}, {lng:.4f}")
        else:
            results['failed'].append({'name': site['name'], 'reason': 'geocode failed'})
            print(f"    → FAILED")
        time.sleep(0.3)

    # Enrich all sites with coords
    print(f"\nEnriching {len(has_coords)} sites...")
    for i, site in enumerate(has_coords):
        name = site['name']
        lat = site['lat']
        lng = site['lng']
        print(f"  [{i+1}/{len(has_coords)}] {name}...", end=' ', flush=True)
        try:
            dem = esri_scorer.get_esri_demographics(lat, lng)
            if dem:
                print(f"OK (pop45={dem.get('population_45plus','?')}, income=${dem.get('median_income','?'):,})" if dem.get('median_income') else f"OK (pop45={dem.get('population_45plus','?')})")
                results['cached'].append(name)
            else:
                print("no data returned")
                results['failed'].append({'name': name, 'reason': 'no data'})
        except Exception as e:
            print(f"ERROR: {e}")
            results['failed'].append({'name': name, 'reason': str(e)})
        time.sleep(0.5)  # be gentle with the API

    # Write log
    log = {
        'run_at': time.strftime('%Y-%m-%d %H:%M:%S UTC'),
        'total_sites': len(sites),
        'cached': len(results['cached']),
        'geocoded': len(results['geocoded']),
        'failed': len(results['failed']),
        'failed_sites': results['failed']
    }
    with open(LOG_FILE, 'w') as f:
        json.dump(log, f, indent=2)

    print(f"\n✅ Done: {len(results['cached'])} cached, {len(results['geocoded'])} geocoded, {len(results['failed'])} failed")
    print(f"Log: {LOG_FILE}")
    return log

if __name__ == '__main__':
    run_precache()
