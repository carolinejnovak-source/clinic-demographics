"""
Google Sheets sync module for VIP Site Analyzer.
Reads columns A-D from all tabs, filters by column D (TRUE), 
categorizes by column C status.
"""
import json, urllib.request, urllib.parse

SHEET_ID = '1zt3zMiqerSDs7NKodnx0Gj6zTGM6yTwNjQXkSDMQuuY'
CONFIG_FILE = '/root/.openclaw/workspace/google_sheets_config.json'
SITES_FILE = '/tmp/vip_sites.json'

STATUS_COLORS = {
    'open': 'blue',
    'pending opening day': 'purple',
    'possible new sites': 'orange',
    'possible expansion': 'orange',
}

SKIP_TABS = {'Template', 'Clinic Comparison - Existing', 'Clinic Comparison Part 2'}

def get_access_token():
    with open(CONFIG_FILE) as f:
        config = json.load(f)
    # Try existing access token first
    try:
        url = f'https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}?fields=spreadsheetId'
        req = urllib.request.Request(url, headers={'Authorization': f'Bearer {config["access_token"]}'})
        urllib.request.urlopen(req)
        return config['access_token']
    except:
        pass
    # Refresh
    data = urllib.parse.urlencode({
        'client_id': config['client_id'],
        'client_secret': config['client_secret'],
        'refresh_token': config['refresh_token'],
        'grant_type': 'refresh_token'
    }).encode()
    req = urllib.request.Request('https://oauth2.googleapis.com/token', data=data, method='POST')
    resp = json.loads(urllib.request.urlopen(req).read())
    access_token = resp['access_token']
    config['access_token'] = access_token
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f)
    return access_token

def get_sheet_tabs(token):
    url = f'https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}?fields=sheets.properties.title'
    req = urllib.request.Request(url, headers={'Authorization': f'Bearer {token}'})
    result = json.loads(urllib.request.urlopen(req).read())
    return [s['properties']['title'] for s in result.get('sheets', [])]

def read_tab(token, tab_name):
    encoded = urllib.parse.quote(f"{tab_name}!A1:D500")
    url = f'https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}/values/{encoded}'
    req = urllib.request.Request(url, headers={'Authorization': f'Bearer {token}'})
    try:
        result = json.loads(urllib.request.urlopen(req).read())
        return result.get('values', [])
    except:
        return []

def sync():
    token = get_access_token()
    tabs = get_sheet_tabs(token)
    territories = {}
    clinics = []

    for tab in tabs:
        if tab in SKIP_TABS or tab.strip() == '':
            continue
        rows = read_tab(token, tab)
        if not rows:
            continue

        # Find header row (has "Status" in col C or similar)
        data_start = 0
        for i, row in enumerate(rows):
            if len(row) >= 4 and str(row[3]).strip().lower() in ('true', 'false', 'need pinned on buxton/vip analyzer map?'):
                data_start = i
                break

        # Skip if this is a header row
        if data_start < len(rows) and len(rows[data_start]) > 3 and str(rows[data_start][3]).strip().lower() == 'need pinned on buxton/vip analyzer map?':
            data_start += 1

        territory_clinics = []
        for row in rows[data_start:]:
            if len(row) < 4:
                continue
            name = str(row[0]).strip() if row[0] else ''
            address = str(row[1]).strip() if len(row) > 1 and row[1] else ''
            status = str(row[2]).strip() if len(row) > 2 and row[2] else ''
            include = str(row[3]).strip().upper() if len(row) > 3 and row[3] else ''

            if include != 'TRUE':
                continue
            if not name or not address:
                continue

            color = STATUS_COLORS.get(status.lower(), 'blue')
            # Clean up tab name (remove trailing spaces/underscores)
            clean_tab = tab.strip().rstrip('_').strip()
            clinic = {
                'name': name,
                'address': address,
                'status': status,
                'color': color,
                'territory': clean_tab,
            }
            territory_clinics.append(clinic)
            clinics.append(clinic)

        if territory_clinics:
            clean_tab = tab.strip().rstrip('_').strip()
            # Merge duplicate territory names
            if clean_tab in territories:
                territories[clean_tab].extend(territory_clinics)
            else:
                territories[clean_tab] = territory_clinics

    data = {'territories': territories, 'clinics': clinics}
    with open(SITES_FILE, 'w') as f:
        json.dump(data, f)
    return len(clinics), list(territories.keys())

if __name__ == '__main__':
    count, tabs = sync()
    print(f'Synced {count} sites across {len(tabs)} territories: {tabs}')
