import logging
import re
from datetime import datetime

import dash_bootstrap_components as dbc
import pandas as pd
import plotly
import pytz
from geopy.geocoders import Nominatim
from timezonefinder import TimezoneFinder

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

theme_map = {
    name: getattr(dbc.themes, name) for name in dir(dbc.themes) if name.isupper()
}


def get_theme_name(theme_url):
    for name, url in theme_map.items():
        if url == theme_url:
            return name
    return None


def generate_color_mapping(categories: list[str]) -> dict[str, str]:
    """Generate a color mapping for categories"""
    color_palette = (
        plotly.colors.qualitative.Set1
    )  # Use a predefined Plotly color palette
    color_mapping = {
        category: color_palette[i % len(color_palette)]
        for i, category in enumerate(categories)
    }
    return color_mapping


def extract_timestamp_from_key(key: str) -> pd.Timestamp:
    """Extract timestamp from S3 key"""
    try:
        timestamp_str = key.split("image_")[-1].split(".jpg")[0]
        return pd.to_datetime(timestamp_str, format="%Y-%m-%d_%H:%M:%S")
    except (IndexError, ValueError):
        return datetime.min


def extract_town_from_text(text: str) -> list[str]:
    """Extract capitalized place names (e.g., Philadelphia)"""
    return re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", text)


def get_timezone_and_offset(city_name: str) -> tuple[str | None, float | None]:
    """Get timezone and UTC offset for a given city name"""
    geolocator = Nominatim(user_agent="timezone_finder")
    tf = TimezoneFinder()

    try:
        location = geolocator.geocode(city_name)
        if location:
            timezone_str = tf.timezone_at(lng=location.longitude, lat=location.latitude)
            if timezone_str:
                tz = pytz.timezone(timezone_str)
                now_utc = datetime.utcnow().replace(tzinfo=pytz.utc)
                local_time = now_utc.astimezone(tz)
                offset_hours = local_time.utcoffset().total_seconds() / 3600
                return timezone_str, offset_hours
    except Exception:
        pass

    return None, 0.0


def compare_timezones(query_city: str, reference_city: str = "Warsaw") -> float:
    """Compare timezones of cities extracted from text with a reference city."""
    extracted_cities = extract_town_from_text(query_city)

    for city in extracted_cities:
        tz_text, offset_text = get_timezone_and_offset(city)
        if tz_text:
            tz_ref, offset_ref = get_timezone_and_offset(reference_city)
            if tz_ref:
                diff = offset_text - offset_ref
                return diff
    logger.error("Could not determine time difference.")
    return 0.0
