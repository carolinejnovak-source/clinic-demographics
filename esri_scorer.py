"""
esri_scorer.py — ESRI scaffold (Phase 2 placeholder)
All functions return None until ESRI API key is configured.
"""

ESRI_API_KEY = None  # Set when available


def get_esri_demographics(lat, lng):
    """
    Returns ESRI enrichment demographics for a location.
    Will return: {
        population_45plus: int,
        population_growth_pct: float,
        pct_commercially_insured: float,
        estimated_vascular_demand: float,
    }
    Requires ESRI_API_KEY to be set.
    """
    if not ESRI_API_KEY:
        return None

    # TODO: implement when key available
    # Example endpoint: https://geoenrich.arcgis.com/arcgis/rest/services/World/geoenrichmentserver/GeoEnrichment/enrich
    return None


def get_esri_traffic(lat, lng):
    """
    Returns ESRI traffic data for a location.
    Will return: {
        avg_daily_traffic: int,
    }
    Requires ESRI_API_KEY to be set.
    """
    if not ESRI_API_KEY:
        return None

    # TODO: implement when key available
    return None
