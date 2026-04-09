"""Date-based weather-driven wind energy forecasting."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from backend.src.open_meteo import OpenMeteoError, fetch_hourly_forecast
from backend.src.predict import _load_prediction_runtime, _predict_with_runtime
from backend.src.preprocessing import REQUIRED_COLUMNS


BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"
MODELS_DIR = BACKEND_DIR / "models"
SEED_HISTORY_PATH = DATA_DIR / "wind_data.csv"
FORECAST_DAYS = 7
OPEN_METEO_MAX_FORECAST_DAYS = 16


class ForecastValidationError(ValueError):
    """Raised when a forecast request is invalid."""


class ForecastConfigurationError(RuntimeError):
    """Raised when local model or seed-history files are unavailable."""


def _validate_request_window(start_date: date, days: int) -> date:
    if days != FORECAST_DAYS:
        raise ForecastValidationError("Only 7-day forecasting is supported in this experience.")

    today = date.today()
    max_start_date = today + timedelta(days=OPEN_METEO_MAX_FORECAST_DAYS - days)

    if start_date < today or start_date > max_start_date:
        raise ForecastValidationError(
            "Forecast date is outside the supported Open-Meteo range. "
            f"Choose a date between {today.isoformat()} and {max_start_date.isoformat()}."
        )

    return start_date + timedelta(days=days - 1)


def _load_seed_history(minimum_history_rows: int) -> list[dict[str, Any]]:
    if not SEED_HISTORY_PATH.exists():
        raise ForecastConfigurationError(
            "Seed history was not found in backend/data/wind_data.csv."
        )

    frame = pd.read_csv(SEED_HISTORY_PATH)
    missing_columns = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing_columns:
        raise ForecastConfigurationError(
            "Seed history is missing required columns: " + ", ".join(missing_columns)
        )

    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce")
    frame = frame.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)

    if len(frame) < minimum_history_rows:
        raise ForecastConfigurationError(
            "Seed history does not contain enough rows for recursive forecasting."
        )

    seed = frame.tail(minimum_history_rows).copy()
    seed["timestamp"] = seed["timestamp"].dt.strftime("%Y-%m-%dT%H:%M")
    return seed[REQUIRED_COLUMNS].to_dict(orient="records")


def _aggregate_daily(hourly_rows: list[dict[str, Any]], selected_date: str) -> list[dict[str, Any]]:
    frame = pd.DataFrame(hourly_rows)
    if frame.empty:
        raise ForecastValidationError("No hourly forecast rows were produced for the selected period.")

    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce")
    frame = frame.dropna(subset=["timestamp"]).copy()
    frame["date"] = frame["timestamp"].dt.strftime("%Y-%m-%d")

    daily_rows: list[dict[str, Any]] = []
    for day, group in frame.groupby("date", sort=True):
        peak_index = group["predicted_power"].idxmax()
        peak_row = frame.loc[peak_index]
        daily_rows.append(
            {
                "date": day,
                "total_energy": round(float(group["predicted_power"].sum()), 2),
                "average_power": round(float(group["predicted_power"].mean()), 2),
                "peak_power": round(float(group["predicted_power"].max()), 2),
                "peak_time": peak_row["timestamp"].strftime("%Y-%m-%dT%H:%M"),
                "is_selected": day == selected_date,
            }
        )

    return daily_rows


def generate_forecast(
    *,
    location: dict[str, Any],
    start_date: date,
    days: int = FORECAST_DAYS,
) -> dict[str, Any]:
    """Forecast wind energy for the selected day and the following 6 days."""

    end_date = _validate_request_window(start_date, days)
    runtime = _load_prediction_runtime(MODELS_DIR)
    seed_history = _load_seed_history(runtime["preprocessor"].minimum_history_rows)
    weather_payload = fetch_hourly_forecast(
        latitude=float(location["latitude"]),
        longitude=float(location["longitude"]),
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
    )

    history = [dict(record) for record in seed_history]
    last_power_output = float(history[-1]["power_output"])
    hourly_predictions: list[dict[str, Any]] = []

    for weather_row in weather_payload["hourly_records"]:
        future_row = {
            "timestamp": weather_row["timestamp"],
            "wind_speed": weather_row["wind_speed"],
            "wind_direction": weather_row["wind_direction"],
            "temperature": weather_row["temperature"],
            "pressure": weather_row["pressure"],
            "power_output": last_power_output,
        }
        history.append(future_row)

        prediction_payload = _predict_with_runtime(history, runtime)
        predicted_power = float(prediction_payload["prediction"])
        history[-1]["power_output"] = predicted_power
        last_power_output = predicted_power

        hourly_predictions.append(
            {
                "timestamp": weather_row["timestamp"],
                "wind_speed": round(float(weather_row["wind_speed"]), 3),
                "wind_direction": round(float(weather_row["wind_direction"]), 3),
                "temperature": round(float(weather_row["temperature"]), 3),
                "pressure": round(float(weather_row["pressure"]), 3),
                "predicted_power": round(predicted_power, 2),
            }
        )

    daily_forecast = _aggregate_daily(hourly_predictions, start_date.isoformat())
    if len(daily_forecast) != days:
        raise OpenMeteoError(
            "Weather provider did not return a complete 7-day local-time forecast window."
        )

    selected_day_hourly = [
        row for row in hourly_predictions if row["timestamp"].startswith(start_date.isoformat())
    ]
    if not selected_day_hourly:
        raise OpenMeteoError("Selected day was not present in the returned hourly forecast data.")

    return {
        "location": {
            "name": location["name"],
            "country": location.get("country"),
            "admin1": location.get("admin1"),
            "latitude": float(location["latitude"]),
            "longitude": float(location["longitude"]),
            "timezone": weather_payload.get("timezone") or location.get("timezone"),
        },
        "selected_date": start_date.isoformat(),
        "days": days,
        "model_name": runtime["model_name"],
        "daily_forecast": daily_forecast,
        "selected_day_hourly": selected_day_hourly,
    }
