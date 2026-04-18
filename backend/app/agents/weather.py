"""Weather enrichment via Open-Meteo (free, no API key).

Runs as a post-processor *after* the draft is generated. For each day in the
itinerary, we look up a forecast at the day's centroid (median activity
coordinate) and attach it. Critique can then flag outdoor-heavy days that
fall on rainy forecasts, so the repair pass knows to reshuffle.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from statistics import median
from typing import Iterable

import httpx

from app.schemas import Activity, DayPlan, Itinerary, ItineraryRequest, WeatherForecast

log = logging.getLogger(__name__)

_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# Open-Meteo WMO weather codes → short human label + outdoor-friendliness.
# Source: https://open-meteo.com/en/docs (the `weather_code` section).
_WMO: dict[int, tuple[str, bool]] = {
    0: ("Clear sky", True),
    1: ("Mainly clear", True),
    2: ("Partly cloudy", True),
    3: ("Overcast", True),
    45: ("Fog", True),
    48: ("Rime fog", True),
    51: ("Light drizzle", True),
    53: ("Drizzle", True),
    55: ("Heavy drizzle", False),
    56: ("Freezing drizzle", False),
    57: ("Freezing drizzle", False),
    61: ("Light rain", True),
    63: ("Rain", False),
    65: ("Heavy rain", False),
    66: ("Freezing rain", False),
    67: ("Freezing rain", False),
    71: ("Light snow", True),
    73: ("Snow", False),
    75: ("Heavy snow", False),
    77: ("Snow grains", True),
    80: ("Light showers", True),
    81: ("Rain showers", False),
    82: ("Violent showers", False),
    85: ("Snow showers", False),
    86: ("Heavy snow showers", False),
    95: ("Thunderstorm", False),
    96: ("Thunderstorm w/ hail", False),
    99: ("Heavy thunderstorm", False),
}


def _day_centroid(day: DayPlan) -> tuple[float, float] | None:
    """Return the median (lat, lng) of activities in a day, or None if none are located."""
    coords = [
        (a.lat, a.lng)
        for a in _all_activities(day)
        if a.lat is not None and a.lng is not None
    ]
    if not coords:
        return None
    return (median(c[0] for c in coords), median(c[1] for c in coords))


def _all_activities(day: DayPlan) -> Iterable[Activity]:
    yield from day.morning
    yield from day.afternoon
    yield from day.evening


async def enrich_with_weather(it: Itinerary, request: ItineraryRequest) -> list[str]:
    """Attach `weather` to each DayPlan. Returns new critique issues.

    Silently no-ops if the request has no `start_date`, or if the forecast
    window is too far in the future for Open-Meteo (>16 days out).
    """
    if request.start_date is None:
        return []

    # Open-Meteo's free forecast endpoint covers today..+16 days. If the trip
    # starts outside that window we'd be asking for climatology, not a forecast.
    today = date.today()
    if request.start_date > today + timedelta(days=16):
        log.info("Trip starts beyond forecast window; skipping weather enrichment.")
        return []
    if request.start_date + timedelta(days=request.duration_days - 1) < today:
        return []  # trip fully in the past — nothing to fetch

    # Group by centroid so we don't fire N identical requests for same-city days.
    centroids: dict[tuple[int, int], tuple[float, float]] = {}
    day_keys: list[tuple[int, int] | None] = []
    for d in it.days:
        c = _day_centroid(d)
        if c is None:
            day_keys.append(None)
            continue
        key = (round(c[0], 2), round(c[1], 2))  # ~1km granularity
        centroids.setdefault(key, c)
        day_keys.append(key)

    if not centroids:
        return []

    # Fetch all unique centroids concurrently.
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            responses: dict[tuple[int, int], dict] = {}
            for key, (lat, lng) in centroids.items():
                resp = await client.get(
                    _FORECAST_URL,
                    params={
                        "latitude": lat,
                        "longitude": lng,
                        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum",
                        "start_date": str(request.start_date),
                        "end_date": str(
                            request.start_date + timedelta(days=request.duration_days - 1)
                        ),
                        "timezone": "auto",
                    },
                )
                resp.raise_for_status()
                responses[key] = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("Weather lookup failed: %s. Continuing without forecast.", exc)
        return []

    issues: list[str] = []
    for day, key in zip(it.days, day_keys):
        if key is None:
            continue
        payload = responses.get(key)
        if not payload or "daily" not in payload:
            continue

        target = request.start_date + timedelta(days=day.day_number - 1)
        daily = payload["daily"]
        try:
            idx = daily["time"].index(str(target))
        except (ValueError, KeyError):
            continue

        code = int(daily["weather_code"][idx])
        condition, outdoor_ok = _WMO.get(code, (f"Code {code}", True))
        day.weather = WeatherForecast(
            date=target,
            condition=condition,
            temp_c_high=float(daily["temperature_2m_max"][idx]),
            temp_c_low=float(daily["temperature_2m_min"][idx]),
            precipitation_mm=float(daily["precipitation_sum"][idx]),
            is_outdoor_friendly=outdoor_ok,
        )

        if not outdoor_ok and _has_outdoor_leaning_activities(day):
            issues.append(
                f"Day {day.day_number} ({target}) forecast is '{condition}' "
                f"({day.weather.precipitation_mm:.0f}mm rain). The plan has outdoor-heavy "
                f"stops — consider swapping to indoor alternatives for this day, or "
                f"trading days with one that has better weather."
            )

    return issues


# Keyword heuristic for "this activity is outdoor-leaning". Intentionally
# simple — the cost of a false positive is just an extra repair suggestion,
# which Claude can ignore if it decides the plan is still fine.
_OUTDOOR_KEYWORDS = (
    "beach", "trek", "hike", "hiking", "walk", "park", "garden", "boat", "cruise",
    "safari", "outdoor", "viewpoint", "sunset", "market", "street", "fort", "lake",
    "waterfall", "bike", "cycle", "kayak", "snorkel", "dive", "rafting", "picnic",
)


def _has_outdoor_leaning_activities(day: DayPlan) -> bool:
    for a in _all_activities(day):
        blob = f"{a.name} {a.description} {a.location}".lower()
        if any(k in blob for k in _OUTDOOR_KEYWORDS):
            return True
    return False
