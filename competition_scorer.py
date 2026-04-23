"""
competition_scorer.py — Enhanced competition scoring (Phase 4)
Buxton-methodology decay-weighted competition scores.
"""
import math


def _km_to_miles(km):
    return km * 0.621371


def get_competition_decay_score(lat, lng, competitor_list):
    """
    Takes a list of competitors (each with distance_km field).
    Returns dict with competitor_decay_score, competitor_count_2mi, competitor_count_1mi.
    Lower decay score = better for VIP (less competition).
    Decay: within 0.5mi = 3pts, 0.5-1mi = 2pts, 1-2mi = 1pt
    """
    decay_score = 0
    count_2mi = 0
    count_1mi = 0

    for comp in competitor_list:
        dist_km = comp.get('distance_km')
        if dist_km is None:
            # Try to compute from lat/lng if available
            comp_lat = comp.get('lat')
            comp_lng = comp.get('lng') or comp.get('lon')
            if comp_lat and comp_lng:
                R = 6371
                dlat = math.radians(comp_lat - lat)
                dlon = math.radians(comp_lng - lng)
                a = math.sin(dlat/2)**2 + math.cos(math.radians(lat)) * math.cos(math.radians(comp_lat)) * math.sin(dlon/2)**2
                dist_km = R * 2 * math.asin(math.sqrt(a))
            else:
                continue

        dist_mi = _km_to_miles(dist_km)

        if dist_mi <= 2.0:
            count_2mi += 1
            if dist_mi <= 0.5:
                decay_score += 3
            elif dist_mi <= 1.0:
                decay_score += 2
            else:
                decay_score += 1
            if dist_mi <= 1.0:
                count_1mi += 1

    return {
        'competitor_decay_score': decay_score,
        'competitor_count_2mi': count_2mi,
        'competitor_count_1mi': count_1mi,
    }


def get_patients_per_competitor(ring_pop_25min, competitor_count_25min):
    """
    Returns float: patients per competitor (higher = better).
    ring_pop_25min: total population within ~25 min drive (use 20min as proxy)
    competitor_count_25min: number of competitors within ~25 min
    """
    if not ring_pop_25min or not competitor_count_25min:
        return float('inf') if ring_pop_25min else 0.0
    return round(ring_pop_25min / competitor_count_25min, 1)
