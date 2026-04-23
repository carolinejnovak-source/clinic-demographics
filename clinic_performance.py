"""
Clinic Performance — backend logic
Google Ads geographic click data + Looker leads/bookings
"""
import math
from collections import defaultdict
from google.ads.googleads.client import GoogleAdsClient

GADS_CONFIG = {
    'developer_token': 'WjIXymJXbBG9E0VXgVbHlg',
    'client_id': '453985230410-a23tdpb2f51ehgbfrhe0not2mfu6qb48.apps.googleusercontent.com',
    'client_secret': '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',
    'refresh_token': '1//06fud1b81YyFfCgYIARAAGAYSNwF-L9IrcznV5A6rQJrHwRSvMkefp--7RgQpGxzTiGmUwIXwPFfW9qQYO3IhQKYbY9_tATj6g9s',
    'login_customer_id': '8026139929',
    'use_proto_plus': True,
}
CUSTOMER_ID = '4728374529'

NYC_CLINICS = ['Astoria','Brighton Beach','Bronx','Downtown Brooklyn',
               'Financial District','Forest Hills','Midtown Manhattan',
               'Staten Island','Upper East Side']

NYC_ZIP_COUNTS = {
    'Astoria': 6, 'Brighton Beach': 5, 'Bronx': 14,
    'Downtown Brooklyn': 4, 'Financial District': 5, 'Forest Hills': 4,
    'Midtown Manhattan': 7, 'Staten Island': 12, 'Upper East Side': 4,
}

SHARED_CITIES = {
    'Costa Mesa':      {'Huntington Beach': 0.5, 'Irvine': 0.5},
    'Santa Ana':       {'Huntington Beach': 0.5, 'Irvine': 0.5},
    'Fountain Valley': {'Huntington Beach': 0.5, 'Irvine': 0.5},
    'Tustin':          {'Huntington Beach': 0.5, 'Irvine': 0.5},
    'Chula Vista':     {'San Diego': 0.5, 'National City': 0.5},
    'El Cajon':        {'San Diego': 0.5, 'National City': 0.5},
    'La Mesa':         {'San Diego': 0.5, 'National City': 0.5},
    'Spring Valley':   {'San Diego': 0.5, 'National City': 0.5},
    'La Presa':        {'San Diego': 0.5, 'National City': 0.5},
}

_DIRECT_MAPPINGS = {
    'Harrison':       ['Harrison','Elizabeth','Linden','Union','Kenilworth','Roselle','Roselle Park','Hillside','City of Orange','East Orange','Glen Ridge','Verona'],
    'Woodland Park':  ['Woodland Park','Wayne'],
    'Hoboken':        ['Hoboken','Weehawken Township'],
    'West Orange':    ['West Orange','Livingston','Bloomfield','Nutley','Irvington','Montclair','South Orange Village','Maplewood','Berkeley Heights','Summit','Springfield','Cranford','Westfield','Scotch Plains','Clark','New Providence','Millburn','Essex Fells','North Caldwell','Roseland','Cedar Grove'],
    'Princeton':      ['Princeton','Hamilton Township','East Windsor','Lawrence Township','Ewing Township','Pennington','Hopewell','Plainsboro Township'],
    'Woodbridge':     ['Woodbridge Township','Edison','Carteret','Rahway','Perth Amboy','Metuchen','South Amboy','Sayreville','Old Bridge','South River','Piscataway'],
    'Edgewater':      ['Edgewater','Fort Lee','North Bergen','Palisades Park','Ridgefield','Ridgefield Park','Leonia','Cliffside Park'],
    'Clifton':        ['Clifton','Passaic','Garfield','Elmwood Park','East Rutherford','Rutherford','Lyndhurst','Kearny','Belleville','North Arlington','Carlstadt'],
    'Paramus':        ['Paramus','Hackensack','Teaneck','Bergenfield','Fair Lawn','Glen Rock','Ridgewood','Saddle Brook','Hawthorne','Totowa','River Edge','Oradell','New Milford','Dumont','River Vale','Montvale','Park Ridge','Hillsdale','Haworth','Emerson','Allendale','Ramsey','Upper Saddle River','Wyckoff','Midland Park','Chestnut Ridge','Pearl River','West Nyack'],
    'Morristown':     ['Morristown','Denville','Boonton','Parsippany-Troy Hills','Florham Park','Madison','Chatham Township','Bernardsville','Bernards','Montville','Kinnelon','Boonton Township','Mountain Lakes','Harding Township'],
    'Hartsdale':      ['White Plains','Scarsdale','New Rochelle','Mamaroneck','Larchmont','Dobbs Ferry','Briarcliff Manor','Chappaqua','Mount Kisco','Pleasantville','Valhalla','Elmsford','Armonk','Croton-on-Hudson','Sleepy Hollow','Thornwood','Ossining','Ardsley','Rye','Rye Brook','Pelham Manor','Montebello','Bardonia'],
    'Yonkers':        ['Yonkers','Mount Vernon'],
    'Jericho':        ['North Hills','Valley Stream','Rockville Centre','Mineola','East Meadow','Garden City','Manhasset','Plainview','Hicksville','Westbury','Jericho','Great Neck','Roslyn Heights','Syosset','Woodbury','Bethpage','Levittown','Massapequa','Massapequa Park','Farmingdale','Old Bethpage','Carle Place'],
    'West Islip':     ['West Islip','Bay Shore','Babylon','Amityville','Copiague','Lindenhurst','North Babylon','West Babylon','Deer Park','East Islip','Islip','Islip Terrace','Central Islip','Brentwood','Brightwaters'],
    'Port Jefferson': ['Holbrook','Centereach','Stony Brook','Farmingville','Bohemia','Shirley','Manorville','Middle Island','Medford','Selden','Coram','Mount Sinai','Miller Place','Sound Beach','Rocky Point','Ridge'],
    'Kyle':           ['Kyle','San Marcos','Lockhart','Wimberley','Driftwood','Uhland','Manchaca','Creedmoor'],
    'Fort Worth':     ['Fort Worth','Saginaw','Richland Hills','Forest Hill'],
    'Cedar Park':     ['Cedar Park','Round Rock','Leander','Georgetown','Jollyville','Sunset Valley','Lakeway','Wells Branch'],
    'Arlington':      ['Arlington','Grand Prairie','Dallas'],
    'Maple Lawn':     ['Columbia','Ellicott City','Fulton','Clarksville','Glenwood','Jessup','Millersville','West Friendship','Russett'],
    'Bowie':          ['Bowie','Glen Burnie','Hanover','Linthicum Heights','Pasadena','Fort Meade','Severn','Severna Park','Odenton','Crofton','Crownsville','Arnold','Cape Saint Claire','Riviera Beach','Herald Harbor','Annapolis','Davidsonville','West Laurel','Mitchellville','Glenarden'],
    'Bethesda':       ['Bethesda','Rockville','Silver Spring','North Bethesda','Chevy Chase','Catonsville','Aspen Hill','Colesville','Laurel','Washington','McLean'],
    'Stamford':       ['Stamford','Greenwich','Norwalk','Darien','New Canaan','Westport'],
    'Hamden':         ['Hamden','New Haven','North Haven','Shelton','Milford','Derby','Ansonia','West Haven','Meriden','Cheshire','Wallingford'],
    'Farmington':     ['Farmington','Hartford','New Britain','West Hartford','Avon','Newington','Plainville','Wethersfield','Stratford','Waterbury'],
    'San Jose':       ['San Jose','Sunnyvale','Mountain View','Milpitas','Fremont','Hayward','Union City','Newark'],
    'Temecula':       ['Temecula','Murrieta','Menifee','Riverside','Moreno Valley','Hemet','Norco','Corona','Wildomar','Lake Elsinore','San Jacinto','Perris','Beaumont','Banning'],
    'Palo Alto':      ['Palo Alto','Redwood City','Menlo Park','San Mateo','San Carlos','Belmont','Burlingame','Foster City','East Palo Alto','Woodside','Los Altos','Los Altos Hills','Stanford','Hillsborough','Emerald Hills'],
    'Huntington Beach': ['Huntington Beach','Westminster','Garden Grove','Stanton','Orange','Anaheim','Villa Park','Yorba Linda','North Tustin','Rossmoor'],
    'Irvine':         ['Irvine','Lake Forest','Laguna Hills','Laguna Niguel','Laguna Woods','Laguna Beach','Mission Viejo','Rancho Santa Margarita','San Juan Capistrano','Dana Point','San Clemente','Coto de Caza'],
    'Newport Beach':  ['Newport Beach'],
    'San Diego':      ['San Diego','Carlsbad','Encinitas','Oceanside','Santee','Lemon Grove','Solana Beach','Del Mar','Rancho Santa Fe','San Marcos','Vista','Bonita','Lakeside','Bonsall'],
    'National City':  ['National City'],
}

CITY_TO_CLINIC = {}
for _clinic, _cities in _DIRECT_MAPPINGS.items():
    for _city in _cities:
        CITY_TO_CLINIC[_city.lower()] = _clinic

_geo_cache = {}

def _gads_client():
    return GoogleAdsClient.load_from_dict(GADS_CONFIG)

def _resolve_geo_names(client, geo_resource_names):
    missing = [r for r in geo_resource_names if r not in _geo_cache]
    if not missing:
        return
    # Use GoogleAdsService to look up geo constants
    service = client.get_service('GoogleAdsService')
    ids = []
    for r in missing:
        try:
            ids.append(r.split('/')[-1])
        except Exception:
            pass
    if not ids:
        return
    id_str = ','.join(ids)
    rn_str = "', '".join(missing)
    query = "SELECT geo_target_constant.resource_name, geo_target_constant.name FROM geo_target_constant WHERE geo_target_constant.resource_name IN ('" + rn_str + "')"
    try:
        resp = service.search(customer_id=CUSTOMER_ID, query=query)
        for row in resp:
            g = row.geo_target_constant
            _geo_cache[g.resource_name] = g.name
    except Exception:
        for r in missing:
            _geo_cache[r] = r.split('/')[-1] if '/' in r else r

def get_geo_clicks(start_date, end_date, campaign_ids=None):
    client = _gads_client()
    service = client.get_service('GoogleAdsService')
    campaign_filter = f"AND campaign.id IN ({','.join(str(c) for c in campaign_ids)})" if campaign_ids else ""
    query = f"""
        SELECT segments.geo_target_city, metrics.impressions, metrics.clicks, metrics.cost_micros
        FROM geographic_view
        WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
            AND metrics.clicks > 0 {campaign_filter}
        LIMIT 5000
    """
    try:
        rows = list(service.search(customer_id=CUSTOMER_ID, query=query))
    except Exception as e:
        return {}, str(e)

    geo_resources = set(str(row.segments.geo_target_city) for row in rows if str(row.segments.geo_target_city))
    _resolve_geo_names(client, list(geo_resources))

    city_data = defaultdict(lambda: {'clicks': 0, 'impressions': 0, 'cost': 0.0})
    for row in rows:
        city_res = str(row.segments.geo_target_city)
        city_name = _geo_cache.get(city_res, city_res.split('/')[-1] if '/' in city_res else city_res)
        city_data[city_name]['clicks'] += row.metrics.clicks
        city_data[city_name]['impressions'] += row.metrics.impressions
        city_data[city_name]['cost'] += row.metrics.cost_micros / 1e6
    return dict(city_data), None

def map_cities_to_clinics(city_data):
    clinic_data = defaultdict(lambda: {'clicks': 0.0, 'impressions': 0.0, 'cost': 0.0})
    nyc_total_zips = sum(NYC_ZIP_COUNTS.values())
    for city, data in city_data.items():
        city_lower = city.lower().strip()
        if city_lower in ('new york', 'new york city', 'nyc'):
            for nyc_clinic, zc in NYC_ZIP_COUNTS.items():
                f = zc / nyc_total_zips
                clinic_data[nyc_clinic]['clicks'] += data['clicks'] * f
                clinic_data[nyc_clinic]['impressions'] += data['impressions'] * f
                clinic_data[nyc_clinic]['cost'] += data['cost'] * f
        elif city in SHARED_CITIES:
            for cl, f in SHARED_CITIES[city].items():
                clinic_data[cl]['clicks'] += data['clicks'] * f
                clinic_data[cl]['impressions'] += data['impressions'] * f
                clinic_data[cl]['cost'] += data['cost'] * f
        else:
            cl = CITY_TO_CLINIC.get(city_lower)
            if cl:
                clinic_data[cl]['clicks'] += data['clicks']
                clinic_data[cl]['impressions'] += data['impressions']
                clinic_data[cl]['cost'] += data['cost']
    return {k: {'clicks': round(v['clicks']), 'impressions': round(v['impressions']), 'cost': round(v['cost'], 2)} for k, v in clinic_data.items()}

def get_campaigns_list(start_date, end_date):
    client = _gads_client()
    service = client.get_service('GoogleAdsService')
    query = f"""
        SELECT campaign.id, campaign.name, metrics.impressions, metrics.clicks, metrics.cost_micros
        FROM campaign
        WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
            AND metrics.impressions > 0 AND campaign.status = ENABLED
        ORDER BY metrics.cost_micros DESC LIMIT 200
    """
    try:
        rows = list(service.search(customer_id=CUSTOMER_ID, query=query))
        return [{'id': str(r.campaign.id), 'name': r.campaign.name,
                 'impressions': r.metrics.impressions, 'clicks': r.metrics.clicks,
                 'cost': round(r.metrics.cost_micros/1e6,2)} for r in rows], None
    except Exception as e:
        return [], str(e)

def pearson_r(xs, ys):
    pairs = [(x,y) for x,y in zip(xs,ys) if x>0 and y>0]
    n = len(pairs)
    if n < 3: return None
    sx,sy = sum(p[0] for p in pairs), sum(p[1] for p in pairs)
    sxy = sum(p[0]*p[1] for p in pairs)
    sx2 = sum(p[0]**2 for p in pairs)
    sy2 = sum(p[1]**2 for p in pairs)
    d = math.sqrt((n*sx2 - sx**2) * (n*sy2 - sy**2))
    return round((n*sxy - sx*sy)/d, 3) if d else None

def get_clinic_performance(start_date, end_date, campaign_ids=None, looker_data=None):
    city_data, err = get_geo_clicks(start_date, end_date, campaign_ids)
    if err:
        return None, err
    ads = map_cities_to_clinics(city_data)
    all_clinics = set(ads.keys()) | set((looker_data or {}).keys())
    clinics = []
    for clinic in sorted(all_clinics):
        a = ads.get(clinic, {'clicks':0,'impressions':0,'cost':0.0})
        l = (looker_data or {}).get(clinic, {'leads':0,'booked':0,'fulfilled':0})
        clicks, booked, leads = a['clicks'], l.get('booked',0), l.get('leads',0)
        clinics.append({
            'clinic': clinic,
            'adImpressions': a['impressions'], 'adClicks': clicks, 'adSpend': a['cost'],
            'leads': leads, 'booked': booked, 'fulfilled': l.get('fulfilled',0),
            'bookedPer100Clicks': round(booked/clicks*100,2) if clicks>0 else None,
            'bookedPer100Leads': round(booked/leads*100,2) if leads>0 else None,
        })
    clinics.sort(key=lambda x: x['bookedPer100Clicks'] or -1, reverse=True)
    tc = sum(c['adClicks'] for c in clinics)
    tl = sum(c['leads'] for c in clinics)
    tb = sum(c['booked'] for c in clinics)
    return {
        'success': True, 'clinics': clinics,
        'summary': {
            'clinicsWithData': sum(1 for c in clinics if c['adClicks']>0 or c['booked']>0),
            'totalClicks': tc, 'totalLeads': tl, 'totalBooked': tb,
            'totalFulfilled': sum(c['fulfilled'] for c in clinics),
            'avgBookedPer100Clicks': str(round(tb/tc*100,2)) if tc>0 else None,
            'avgBookedPer100Leads': str(round(tb/tl*100,2)) if tl>0 else None,
        },
        'correlation': {
            'clicks_vs_booked': str(pearson_r([c['adClicks'] for c in clinics],[c['booked'] for c in clinics])),
            'leads_vs_booked': str(pearson_r([c['leads'] for c in clinics],[c['booked'] for c in clinics])),
        }
    }, None
