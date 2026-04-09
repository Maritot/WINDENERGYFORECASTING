"""FastAPI app for serving wind energy predictions to the Next.js frontend."""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from typing import List

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend.src.forecasting import (
    ForecastConfigurationError,
    ForecastValidationError,
    generate_forecast,
)
from backend.src.open_meteo import OpenMeteoError, search_locations
from backend.src.predict import predict_wind_energy
from backend.src.preprocessing import WindDataPreprocessor


BASE_DIR = Path(__file__).resolve().parent.parent
MODELS_DIR = BASE_DIR / "models"
DATA_DIR = BASE_DIR / "data"
DEFAULT_CORS_ORIGINS = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
)


def _parse_cors_origins() -> list[str]:
    raw_origins = os.getenv("CORS_ORIGINS", "")
    if not raw_origins.strip():
        return list(DEFAULT_CORS_ORIGINS)
    return [origin.strip().rstrip("/") for origin in raw_origins.split(",") if origin.strip()]


app = FastAPI(
    title="Wind Energy Forecast API",
    version="2.0.0",
    description=(
        "Backend service for wind energy forecasting. "
        "This API is designed to be consumed by the Next.js frontend."
    ),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_parse_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class WeatherRecord(BaseModel):
    wind_speed: float
    wind_direction: float
    temperature: float
    pressure: float
    timestamp: str
    power_output: float


class ForecastLocation(BaseModel):
    name: str
    latitude: float
    longitude: float
    timezone: str
    country: str | None = None
    admin1: str | None = None


class ForecastRequest(BaseModel):
    location: ForecastLocation
    start_date: date
    days: int = Field(default=7, ge=7, le=7)


@app.get("/")
def home() -> dict[str, str]:
    """Return basic API metadata for the standalone backend."""

    return {
        "name": app.title,
        "version": app.version,
        "health_endpoint": "/health",
        "model_info_endpoint": "/model-info",
        "demo_window_endpoint": "/demo-window",
        "location_search_endpoint": "/locations/search",
        "forecast_endpoint": "/forecast",
        "prediction_endpoint": "/predict",
        "docs": "/docs",
    }


@app.get("/health")
def health() -> dict:
    """Simple health check endpoint."""

    return {"status": "ok"}


@app.get("/model-info")
def model_info() -> dict:
    """Return basic information about the saved model artifacts."""

    metadata_path = MODELS_DIR / "model_metadata.json"
    comparison_path = MODELS_DIR / "model_comparison.csv"

    response = {
        "model_ready": metadata_path.exists(),
        "comparison_ready": comparison_path.exists(),
    }

    if metadata_path.exists():
        response["metadata"] = json.loads(metadata_path.read_text())

    preprocessor_path = MODELS_DIR / "preprocessor.joblib"
    if preprocessor_path.exists():
        preprocessor = WindDataPreprocessor.load(preprocessor_path)
        response["minimum_history_rows"] = preprocessor.minimum_history_rows
        response["feature_warmup_rows"] = preprocessor.feature_warmup_rows

    if comparison_path.exists():
        comparison = pd.read_csv(comparison_path)
        response["comparison"] = comparison.to_dict(orient="records")

    return response


@app.get("/demo-window")
def demo_window() -> dict:
    """Return a recent-history prediction window from the synthetic dataset if present."""

    data_path = DATA_DIR / "wind_data.csv"
    metadata_path = MODELS_DIR / "model_metadata.json"

    if not data_path.exists():
        raise HTTPException(status_code=404, detail="Synthetic demo dataset was not found.")
    if not metadata_path.exists():
        raise HTTPException(status_code=404, detail="Model metadata was not found.")

    preprocessor_path = MODELS_DIR / "preprocessor.joblib"
    minimum_history_rows = 24
    if preprocessor_path.exists():
        preprocessor = WindDataPreprocessor.load(preprocessor_path)
        minimum_history_rows = preprocessor.minimum_history_rows

    frame = pd.read_csv(data_path)
    window = frame.tail(minimum_history_rows)
    return {
        "minimum_history_rows": minimum_history_rows,
        "records": window[
            [
                "timestamp",
                "wind_speed",
                "wind_direction",
                "temperature",
                "pressure",
                "power_output",
            ]
        ].to_dict(orient="records"),
    }


@app.get("/locations/search")
def location_search(q: str) -> dict:
    """Search for forecast locations using the Open-Meteo geocoding API."""

    try:
        return {"results": search_locations(q)}
    except OpenMeteoError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@app.post("/forecast")
def forecast(request: ForecastRequest) -> dict:
    """Generate a date-based 7-day wind energy forecast."""

    try:
        return generate_forecast(
            location=request.location.model_dump(),
            start_date=request.start_date,
            days=request.days,
        )
    except ForecastValidationError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except ForecastConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except OpenMeteoError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@app.post("/predict")
def predict(records: List[WeatherRecord]) -> dict:
    """Predict wind energy from recent historical observations."""

    try:
        payload = [record.model_dump() for record in records]
        return predict_wind_energy(payload)
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
