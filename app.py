from flask import Flask, render_template, request, jsonify
import requests
import math
import os
import re
import json
import threading

app = Flask(__name__)

CLINICS = [
    {"name": "Astoria, NY", "address": "23-25 31st St Suite 410, Astoria, NY 11105"},
    {"name": "Brighton Beach, NY", "address": "23 Brighton 11th St 7th Floor, Brooklyn, NY 11235"},
    {"name": "Bronx, NY", "address": "2100 Bartow Ave Suite 400, Bronx, NY 10475"},
    {"name": "Downtown Brooklyn, NY", "address": "188 Montague St 10th floor, Brooklyn, NY 11201"},
    {"name": "Financial District, NY", "address": "156 William St Suite 302, New York, NY 10038"},
    {"name": "Forest Hills, NY", "address": "107-30 71st Rd Suite 204, Forest Hills, NY 11375"},
    {"name": "Hartsdale, NY", "address": "280 N Central Ave Suite 450, Hartsdale, NY 10530"},
    {"name": "Jericho, NY", "address": "350 Jericho Tpke Suite 310, Jericho, NY 11753"},
    {"name": "Midtown Manhattan, NY", "address": "290 Madison Ave Floor 2, New York, NY 10017"},
    {"name": "Port Jefferson, NY", "address": "70 N Country Rd #201, Port Jefferson, NY 11777"},
    {"name": "Staten Island, NY", "address": "4236 Hylan Blvd, Staten Island, NY 10312"},
    {"name": "Upper East Side, NY", "address": "1111 Park Ave # 1b, New York, NY 10128"},
    {"name": "West Islip, NY", "address": "500 Montauk Hwy Suite G, West Islip, NY 11795"},
    {"name": "Yonkers, NY", "address": "124 New Main St, Yonkers, NY 10701"},
    {"name": "Clifton, NJ", "address": "1117 US-46 Ste 205, Clifton, NJ 07013"},
    {"name": "Edgewater, NJ", "address": "968 River Rd # 200, Edgewater, NJ 07020"},
    {"name": "Harrison, NJ", "address": "620 Essex St #202, Harrison, NJ 07029"},
    {"name": "Hoboken, NJ", "address": "70 Hudson St Lower Level, Hoboken, NJ 07030"},
    {"name": "Morris County, NJ", "address": "3695 Hill Rd, Parsippany, NJ 07054"},
    {"name": "Morristown, NJ", "address": "310 Madison Ave 3rd floor, Morristown, NJ 07960"},
    {"name": "Paramus, NJ", "address": "140 NJ-17 #269, Paramus, NJ 07652"},
    {"name": "Princeton, NJ", "address": "8 Forrestal Rd S suite 203, Princeton, NJ 08540"},
    {"name": "Scotch Plains, NJ", "address": "2253 South Ave #2, Scotch Plains, NJ 07076"},
    {"name": "West Orange, NJ", "address": "405 Northfield Ave #204, West Orange, NJ 07052"},
    {"name": "Woodbridge, NJ", "address": "517 U.S. Rte 1 #1100, Iselin, NJ 08830"},
    {"name": "Woodland Park, NJ", "address": "1167 McBride Ave Suite 2, Woodland Park, NJ 07424"},
    {"name": "Huntington Beach, CA", "address": "7677 Center Ave #310, Huntington Beach, CA 92647"},
    {"name": "Irvine, CA", "address": "4482 Barranca Pkwy #252, Irvine, CA 92604"},
    {"name": "National City, CA", "address": "22 W 35th St suite 202, National City, CA 91950"},
    {"name": "Newport Beach, CA", "address": "1525 Superior Ave suite 202, Newport Beach, CA 92663"},
    {"name": "Palo Alto, CA", "address": "2248 Park Blvd, Palo Alto, CA 94306"},
    {"name": "Poway, CA", "address": "15708 Pomerado Rd suite n202, Poway, CA 92064"},
    {"name": "San Diego, CA", "address": "5330 Carroll Canyon Rd #140, San Diego, CA 92121"},
    {"name": "San Jose, CA", "address": "1270 S Winchester Blvd # 102, San Jose, CA 95128"},
    {"name": "Temecula, CA", "address": "27290 Madison Ave Suite 102, Temecula, CA 92590"},
    {"name": "Bethesda, MD", "address": "6903 Rockledge Dr Suite 470, Bethesda, MD 20817"},
    {"name": "Bowie, MD", "address": "4201 Northview Dr Suite 104, Bowie, MD 20716"},
    {"name": "Maple Lawn, MD", "address": "11810 W Market Pl Suite 300, Fulton, MD 20759"},
    {"name": "Farmington, CT", "address": "399 Farmington Ave LL2, Farmington, CT 06032"},
    {"name": "Hamden, CT", "address": "2080 Whitney Ave #250, Hamden, CT 06518"},
    {"name": "Stamford, CT", "address": "1266 E Main St Suite 465, Stamford, CT 06902"},
    {"name": "Arlington, TX", "address": "3050 S Center St #110, Arlington, TX 76014"},
    {"name": "Cedar Park, TX", "address": "351 Cypress Creek Road STE 200, Cedar Park, TX 78613"},
    {"name": "Fort Worth, TX", "address": "3455 Locke Ave Suite 300, Fort Worth, TX 76107"},
    {"name": "Kyle, TX", "address": "135 Bunton Creek Rd #300, Kyle, TX 78640"},
]

STATE_FIPS = {
    "AL":"01","AK":"02","AZ":"04","AR":"05","CA":"06","CO":"08","CT":"09",
    "DE":"10","DC":"11","FL":"12","GA":"13","HI":"15","ID":"16","IL":"17",
    "IN":"18","IA":"19","KS":"20","KY":"21","LA":"22","ME":"23","MD":"24",
    "MA":"25","MI":"26","MN":"27","MS":"28","MO":"29","MT":"30","NE":"31",
    "NV":"32","NH":"33","NJ":"34","NM":"35","NY":"36","NC":"37","ND":"38",
    "OH":"39","OK":"40","OR":"41","PA":"42","RI":"44","SC":"45","SD":"46",
    "TN":"47","TX":"48","UT":"49","VT":"50","VA":"51","WA":"53","WV":"54",
    "WI":"55","WY":"56",
}

_cache = {}
_preload_status = {"done": 0, "total": len(CLINICS), "complete": False}


# ── Helpers ──────────────────────────────────────────────────────

def extract_zip(address):
    m = re.search(r'\b(\d{5})\b', address)
    return m.group(1) if m else None

def extract_state(address):
    m = re.search(r',\s*([A-Z]{2})\s+\d{5}', address)
    return m.group(1) if m else None

def geocode_address(address):
    key = f"geo:{address}"
    if key in _cache:
        return _cache[key]
    try:
        r = requests.get(
            "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress",
            params={"address": address, "benchmark": "2020", "format": "json"},
            timeout=10
        )
        matches = r.json().get("result", {}).get("addressMatches", [])
        if matches:
            c = matches[0]["coordinates"]
            result = (float(c["y"]), float(c["x"]))
            _cache[key] = result
            return result
    except Exception as e:
        print(f"Geocode error for {address}: {e}")
    return None

def get_isochrone(lat, lon):
    key = f"iso:{lat:.4f},{lon:.4f}"
    if key in _cache:
        return _cache[key]
    try:
        r = requests.post(
            "https://valhalla1.openstreetmap.de/isochrone",
            json={
                "locations": [{"lat": lat, "lon": lon}],
                "costing": "auto",
                "contours": [{"time": 10}, {"time": 20}],
                "polygons": True,
                "denoise": 0.5,
                "generalize": 150,
            },
            timeout=30
        )
        if r.status_code == 200:
            data = r.json()
            _cache[key] = data
            return data
    except Exception as e:
        print(f"Isochrone error for ({lat},{lon}): {e}")
    return None

def get_county_fips(lat, lon):
    key = f"county:{lat:.4f},{lon:.4f}"
    if key in _cache:
        return _cache[key]
    try:
        r = requests.get(
            "https://geocoding.geo.census.gov/geocoder/geographies/coordinates",
            params={"x": lon, "y": lat,
                    "benchmark": "Public_AR_Current",
                    "vintage": "Current_Current",
                    "layers": "Counties", "format": "json"},
            timeout=10
        )
        counties = r.json().get("result", {}).get("geographies", {}).get("Counties", [])
        if counties:
            c = counties[0]
            result = (c.get("STATE", ""), c.get("COUNTY", ""))
            _cache[key] = result
            return result
    except:
        pass
    return (None, None)

def get_census_acs(state_fips, county_fips):
    key = f"acs:{state_fips},{county_fips}"
    if key in _cache:
        return _cache[key]
    result = {"population": None, "median_income": None, "error": None}
    try:
        r = requests.get(
            "https://api.census.gov/data/2022/acs/acs5",
            params={"get": "B01003_001E,B19013_001E",
                    "for": f"county:{county_fips}",
                    "in": f"state:{state_fips}"},
            timeout=12
        )
        data = r.json()
        if len(data) >= 2:
            d = dict(zip(data[0], data[1]))
            pop = int(d.get("B01003_001E", 0) or 0)
            inc = int(d.get("B19013_001E", 0) or 0)
            result["population"] = pop if pop > 0 else None
            result["median_income"] = inc if inc > 0 else None
    except Exception as e:
        result["error"] = str(e)
    _cache[key] = result
    return result

def get_sahie(state_fips, county_fips):
    key = f"sahie:{state_fips},{county_fips}"
    if key in _cache:
        return _cache[key]
    result = {"insured_pct": None, "error": None}
    try:
        r = requests.get(
            "https://api.census.gov/data/timeseries/healthins/sahie",
            params={"get": "PCTIC_PT",
                    "for": f"county:{county_fips}",
                    "in": f"state:{state_fips}",
                    "time": "2022"},
            timeout=12
        )
        data = r.json()
        if len(data) >= 2:
            d = dict(zip(data[0], data[1]))
            pct = float(d.get("PCTIC_PT", 0) or 0)
            result["insured_pct"] = round(pct, 1) if pct > 0 else None
    except Exception as e:
        result["error"] = str(e)
    _cache[key] = result
    return result

def get_cms(zipcode):
    key = f"cms:{zipcode}"
    if key in _cache:
        return _cache[key]
    result = {"cpt36475_volume": None, "error": None}
    try:
        r = requests.get(
            "https://data.cms.gov/data-api/v1/dataset/9767cb68-8ea9-4f0b-8179-9431abc89f11/data",
            params={"filter[Rndrng_Prvdr_Zip5]": zipcode,
                    "filter[HCPCS_Cd]": "36475", "size": 500},
            timeout=15
        )
        data = r.json()
        if isinstance(data, list):
            result["cpt36475_volume"] = sum(int(row.get("Tot_Srvcs", 0) or 0) for row in data)
        else:
            result["cpt36475_volume"] = 0
    except Exception as e:
        result["error"] = str(e)
    _cache[key] = result
    return result


# ── Background preloader ─────────────────────────────────────────

def _preload_worker():
    """Geocode all clinics + fetch their isochrones in background threads."""
    from concurrent.futures import ThreadPoolExecutor
    def load_one(clinic):
        try:
            coords = geocode_address(clinic["address"])
            if coords:
                get_isochrone(coords[0], coords[1])
        except:
            pass
        _preload_status["done"] += 1

    with ThreadPoolExecutor(max_workers=5) as ex:
        ex.map(load_one, CLINICS)

    _preload_status["complete"] = True
    print(f"Preload complete: {_preload_status['done']}/{_preload_status['total']} clinics cached")

threading.Thread(target=_preload_worker, daemon=True).start()


# ── Routes ───────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html",
                           clinics=CLINICS,
                           clinics_json=json.dumps(CLINICS))

@app.route("/preload-status")
def preload_status():
    return jsonify(_preload_status)

@app.route("/clinic-coords")
def clinic_coords():
    """Return geocoded coordinates + cached isochrones for all clinics.
    Called once on page load so the map populates immediately."""
    results = []
    for clinic in CLINICS:
        coords = geocode_address(clinic["address"])
        if not coords:
            continue
        lat, lon = coords
        iso_key = f"iso:{lat:.4f},{lon:.4f}"
        results.append({
            "name": clinic["name"],
            "address": clinic["address"],
            "lat": lat,
            "lon": lon,
            "isochrone": _cache.get(iso_key),  # None if not yet cached
        })
    return jsonify(results)

@app.route("/isochrone", methods=["POST"])
def isochrone_endpoint():
    """Fetch isochrone for a single address (used for custom locations)."""
    data = request.get_json()
    address = (data.get("address") or "").strip()
    name = data.get("name", address)
    if not address:
        return jsonify({"error": "No address"}), 400
    coords = geocode_address(address)
    if not coords:
        return jsonify({"error": f"Could not geocode: {address}"})
    lat, lon = coords
    iso = get_isochrone(lat, lon)
    return jsonify({"name": name, "address": address, "lat": lat, "lon": lon, "isochrone": iso})

@app.route("/demographics", methods=["POST"])
def demographics():
    """Fetch census + CMS data for a single address (separate from isochrone)."""
    data = request.get_json()
    address = (data.get("address") or "").strip()
    if not address:
        return jsonify({"error": "No address"}), 400
    coords = geocode_address(address)
    if not coords:
        return jsonify({"error": f"Could not geocode: {address}"})
    lat, lon = coords
    zipcode = extract_zip(address)
    state_fips, county_fips = get_county_fips(lat, lon)
    acs = get_census_acs(state_fips, county_fips) if state_fips else {}
    sahie = get_sahie(state_fips, county_fips) if state_fips else {}
    cms = get_cms(zipcode) if zipcode else {}
    density = None
    if acs.get("population"):
        density = round(acs["population"] / (math.pi * 10 ** 2), 1)
    return jsonify({
        "lat": lat, "lon": lon, "zip": zipcode,
        "population_density": density,
        "median_income": acs.get("median_income"),
        "insured_pct": sahie.get("insured_pct"),
        "cpt36475_volume": cms.get("cpt36475_volume"),
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
