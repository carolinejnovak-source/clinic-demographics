from flask import Flask, render_template, request, jsonify
import requests
import math
import json
import os
import time
from functools import lru_cache

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

# Simple in-memory cache
_geocache = {}
_census_cache = {}
_cms_cache = {}

RADIUS_MILES = 10

def haversine(lat1, lon1, lat2, lon2):
    """Distance in miles between two lat/lon points."""
    R = 3958.8
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return 2 * R * math.asin(math.sqrt(a))

def geocode_address(address):
    """Return (lat, lon) for an address using Census Geocoder."""
    if address in _geocache:
        return _geocache[address]
    try:
        url = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
        params = {"address": address, "benchmark": "2020", "format": "json"}
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        matches = data.get("result", {}).get("addressMatches", [])
        if matches:
            coords = matches[0]["coordinates"]
            result = (float(coords["y"]), float(coords["x"]))
            _geocache[address] = result
            return result
    except Exception as e:
        print(f"Geocode error: {e}")
    return None

def get_zip_from_address(address):
    """Extract zip code from address string."""
    import re
    match = re.search(r'\b(\d{5})\b', address)
    return match.group(1) if match else None

def get_state_fips(state_abbr):
    STATE_FIPS = {
        "AL": "01", "AK": "02", "AZ": "04", "AR": "05", "CA": "06",
        "CO": "08", "CT": "09", "DE": "10", "FL": "12", "GA": "13",
        "HI": "15", "ID": "16", "IL": "17", "IN": "18", "IA": "19",
        "KS": "20", "KY": "21", "LA": "22", "ME": "23", "MD": "24",
        "MA": "25", "MI": "26", "MN": "27", "MS": "28", "MO": "29",
        "MT": "30", "NE": "31", "NV": "32", "NH": "33", "NJ": "34",
        "NM": "35", "NY": "36", "NC": "37", "ND": "38", "OH": "39",
        "OK": "40", "OR": "41", "PA": "42", "RI": "44", "SC": "45",
        "SD": "46", "TN": "47", "TX": "48", "UT": "49", "VT": "50",
        "VA": "51", "WA": "53", "WV": "54", "WI": "55", "WY": "56",
        "DC": "11",
    }
    return STATE_FIPS.get(state_abbr.upper(), "")

def extract_state(address):
    """Extract state abbreviation from address."""
    import re
    match = re.search(r',\s*([A-Z]{2})\s+\d{5}', address)
    if match:
        return match.group(1)
    # Try last two-letter word before zip
    parts = address.replace(',', ' ').split()
    for i, p in enumerate(parts):
        if len(p) == 2 and p.isupper() and i < len(parts) - 1:
            return p
    return None

def get_census_data(lat, lon, state_abbr):
    """Get ACS data for counties within 10-mile radius."""
    cache_key = f"{lat:.4f},{lon:.4f}"
    if cache_key in _census_cache:
        return _census_cache[cache_key]

    result = {
        "population_density": None,
        "median_income": None,
        "insured_pct": None,
        "error": None
    }

    try:
        state_fips = get_state_fips(state_abbr)
        if not state_fips:
            result["error"] = "Could not determine state"
            return result

        # Get all counties in the state with their geo info
        # We'll query ACS for the county containing the address plus neighbors
        # First, use Census geocoder to get the tract/county FIPS
        geo_url = "https://geocoding.geo.census.gov/geocoder/geographies/coordinates"
        geo_params = {
            "x": lon, "y": lat,
            "benchmark": "Public_AR_Current",
            "vintage": "Current_Current",
            "layers": "Counties",
            "format": "json"
        }
        geo_r = requests.get(geo_url, params=geo_params, timeout=10)
        geo_data = geo_r.json()

        counties_in_geo = geo_data.get("result", {}).get("geographies", {}).get("Counties", [])
        if not counties_in_geo:
            result["error"] = "Could not determine county"
            return result

        primary_county = counties_in_geo[0]
        county_fips = primary_county.get("COUNTY", "")

        # Query ACS for this county + adjacent (use state-level query with county filter)
        # Variables: total pop, median income, insured counts
        acs_url = "https://api.census.gov/data/2022/acs/acs5"
        variables = "B01003_001E,B19013_001E,B27001_001E,B27001_005E,B27001_008E,B27001_011E,B27001_014E,B27001_017E,B27001_020E,B27001_023E,B27001_026E,B27001_029E,B01003_001E"

        # Get area in sq miles for the county (approximate using ACS geographic data)
        params = {
            "get": f"{variables},NAME",
            "for": f"county:{county_fips}",
            "in": f"state:{state_fips}",
        }
        acs_r = requests.get(acs_url, params=params, timeout=15)
        acs_data = acs_r.json()

        if len(acs_data) < 2:
            result["error"] = "No ACS data returned"
            return result

        headers = acs_data[0]
        row = acs_data[1]
        data_dict = dict(zip(headers, row))

        total_pop = int(data_dict.get("B01003_001E", 0) or 0)
        median_income = int(data_dict.get("B19013_001E", 0) or 0)

        # Count insured (with any health insurance) vs total for insurance table
        # B27001: Health Insurance Coverage Status by Sex by Age
        # _005, _008, _011, _014, _017, _020, _023, _026, _029 are "with insurance" age buckets for male
        insured_vars = ["B27001_005E","B27001_008E","B27001_011E","B27001_014E",
                        "B27001_017E","B27001_020E","B27001_023E","B27001_026E","B27001_029E"]
        total_insured = sum(int(data_dict.get(v, 0) or 0) for v in insured_vars)
        total_universe = int(data_dict.get("B27001_001E", 1) or 1)
        # Double for female (approximate symmetry)
        insured_pct = min(100, round((total_insured * 2 / total_universe) * 100, 1)) if total_universe > 0 else None

        # Population density: approximate using 10-mile radius circle (314.16 sq mi)
        # County area can vary widely; use a rough density from total pop / circle area
        density = round(total_pop / (math.pi * RADIUS_MILES ** 2), 1)

        result["population_density"] = density
        result["median_income"] = median_income if median_income > 0 else None
        result["insured_pct"] = insured_pct

    except Exception as e:
        result["error"] = str(e)

    _census_cache[cache_key] = result
    return result

def get_cms_data(zipcode):
    """Get CPT 36475 procedure volume for zip codes near the clinic."""
    if zipcode in _cms_cache:
        return _cms_cache[zipcode]

    result = {"cpt36475_volume": None, "error": None}
    try:
        # CMS Medicare Provider Utilization by Provider and Service
        # Dataset: Medicare Physician & Other Practitioners
        url = "https://data.cms.gov/data-api/v1/dataset/9767cb68-8ea9-4f0b-8179-9431abc89f11/data"
        params = {
            "filter[Rndrng_Prvdr_Zip5]": zipcode,
            "filter[HCPCS_Cd]": "36475",
            "size": 200,
            "offset": 0
        }
        r = requests.get(url, params=params, timeout=15)
        data = r.json()

        if isinstance(data, list):
            total = sum(int(row.get("Tot_Srvcs", 0) or 0) for row in data)
            result["cpt36475_volume"] = total
        else:
            result["cpt36475_volume"] = 0

    except Exception as e:
        result["error"] = str(e)

    _cms_cache[zipcode] = result
    return result


@app.route("/")
def index():
    return render_template("index.html", clinics=CLINICS)


@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.get_json()
    address = data.get("address", "").strip()
    if not address:
        return jsonify({"error": "No address provided"}), 400

    # Geocode
    coords = geocode_address(address)
    if not coords:
        return jsonify({"error": f"Could not geocode address: {address}"}), 400

    lat, lon = coords
    state = extract_state(address)
    zipcode = get_zip_from_address(address)

    # Census data
    census = get_census_data(lat, lon, state or "NY")

    # CMS data
    cms = {"cpt36475_volume": None, "error": None}
    if zipcode:
        cms = get_cms_data(zipcode)

    return jsonify({
        "address": address,
        "lat": lat,
        "lon": lon,
        "zip": zipcode,
        "population_density": census.get("population_density"),
        "median_income": census.get("median_income"),
        "insured_pct": census.get("insured_pct"),
        "census_error": census.get("error"),
        "cpt36475_volume": cms.get("cpt36475_volume"),
        "cms_error": cms.get("error"),
        "fair_health_url": f"https://fairhealthconsumer.org/",
        "fair_health_note": "Search CPT 36475 for ZIP code " + (zipcode or "N/A"),
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
