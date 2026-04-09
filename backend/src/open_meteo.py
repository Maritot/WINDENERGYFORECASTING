"""Helpers for talking to the Open-Meteo APIs."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
REQUEST_TIMEOUT_SECONDS = 20


class OpenMeteoError(RuntimeError):
    """Raised when Open-Meteo returns an error or malformed payload."""


def _read_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    query = urlencode(params, doseq=True)
    request = Request(
        f"{url}?{query}",
        headers={
            "Accept": "application/json",
            "User-Agent": "wind-energy-forecast/1.0",
        },
    )

    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            payload = response.read().decode("utf-8")
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="ignore").strip()
        raise OpenMeteoError(
            f"Weather provider request failed with status {error.code}."
            + (f" Details: {detail}" if detail else "")
        ) from error
    except URLError as error:
        raise OpenMeteoError(
            "Weather provider is unavailable right now. Please try again shortly."
        ) from error

    try:
        return json.loads(payload)
    except json.JSONDecodeError as error:
        raise OpenMeteoError("Weather provider returned an invalid JSON response.") from error


def search_locations(query: str, count: int = 8) -> list[dict[str, Any]]:
    """Search city or place names via the Open-Meteo geocoding API."""

    cleaned_query = query.strip()
    if len(cleaned_query) < 2:
        return []

    payload = _read_json(
        GEOCODING_URL,
        {
            "name": cleaned_query,
            "count": count,
            "language": "en",
            "format": "json",
        },
    )

    results = []
    for item in payload.get("results", []) or []:
        name = item.get("name")
        latitude = item.get("latitude")
        longitude = item.get("longitude")
        if name is None or latitude is None or longitude is None:
            continue

        results.append(
            {
                "name": str(name),
                "country": item.get("country"),
                "admin1": item.get("admin1"),
                "latitude": float(latitude),
                "longitude": float(longitude),
                "timezone": str(item.get("timezone") or "auto"),
            }
        )

    return results


def fetch_hourly_forecast(
    *,
    latitude: float,
    longitude: float,
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    """Fetch hourly weather aligned with the forecasting model features."""

    payload = _read_json(
        FORECAST_URL,
        {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": [
                "temperature_2m",
                "surface_pressure",
                "wind_speed_10m",
                "wind_direction_10m",
            ],
            "timezone": "auto",
            "wind_speed_unit": "ms",
            "start_date": start_date,
            "end_date": end_date,
        },
    )

    hourly = payload.get("hourly")
    if not isinstance(hourly, dict):
        raise OpenMeteoError("Weather provider did not return hourly forecast data.")

    required_fields = [
        "time",
        "temperature_2m",
        "surface_pressure",
        "wind_speed_10m",
        "wind_direction_10m",
    ]
    missing_fields = [field for field in required_fields if field not in hourly]
    if missing_fields:
        raise OpenMeteoError(
            "Weather provider response is missing hourly fields: "
            + ", ".join(missing_fields)
        )

    lengths = {field: len(hourly[field]) for field in required_fields}
    if len(set(lengths.values())) != 1:
        raise OpenMeteoError("Weather provider returned mismatched hourly array lengths.")

    records: list[dict[str, Any]] = []
    for index, timestamp in enumerate(hourly["time"]):
        row = {
            "timestamp": timestamp,
            "temperature": hourly["temperature_2m"][index],
            "pressure": hourly["surface_pressure"][index],
            "wind_speed": hourly["wind_speed_10m"][index],
            "wind_direction": hourly["wind_direction_10m"][index],
        }

        if any(value is None for value in row.values()):
            raise OpenMeteoError(
                "Weather provider returned incomplete hourly data for the selected range."
            )

        records.append(
            {
                "timestamp": str(row["timestamp"]),
                "temperature": float(row["temperature"]),
                "pressure": float(row["pressure"]),
                "wind_speed": float(row["wind_speed"]),
                "wind_direction": float(row["wind_direction"]),
            }
        )

    return {
        "timezone": payload.get("timezone"),
        "hourly_records": records,
    }
