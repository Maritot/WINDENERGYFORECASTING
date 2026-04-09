"""Generate a realistic synthetic wind energy forecasting dataset."""

from __future__ import annotations

import zipfile
from pathlib import Path

import numpy as np
import pandas as pd


def generate_synthetic_wind_dataset(
    output_csv: str | Path = "data/wind_data.csv",
    output_zip: str | Path = "wind_dataset.zip",
    num_rows: int = 5000,
    seed: int = 42,
) -> pd.DataFrame:
    """Create a reproducible synthetic dataset for wind energy forecasting."""

    rng = np.random.default_rng(seed)
    timestamps = pd.date_range(start="2025-01-01", periods=num_rows, freq="h")

    hours = timestamps.hour.to_numpy()
    days = timestamps.day.to_numpy()
    months = timestamps.month.to_numpy()
    day_of_year = timestamps.dayofyear.to_numpy()

    seasonal_temperature = 5.0 * np.sin(2 * np.pi * day_of_year / 365.25 - 0.8)
    diurnal_temperature = 3.0 * np.sin(2 * np.pi * hours / 24 - 1.0)
    temperature_noise = rng.normal(0, 1.2, size=num_rows)
    temperature = np.clip(24 + seasonal_temperature + diurnal_temperature + temperature_noise, 15, 35)

    pressure_base = 1010 + 4.5 * np.cos(2 * np.pi * day_of_year / 365.25)
    pressure = np.clip(pressure_base + rng.normal(0, 3.0, size=num_rows), 990, 1030)

    seasonal_wind = 1.8 + 1.2 * np.sin(2 * np.pi * day_of_year / 365.25 + 0.6)
    diurnal_wind = 0.9 * np.sin(2 * np.pi * (hours - 5) / 24)
    wind_speed = np.zeros(num_rows, dtype=float)
    wind_speed[0] = np.clip(6 + seasonal_wind[0] + diurnal_wind[0] + rng.normal(0, 1.3), 0, 15)

    for index in range(1, num_rows):
        persistent_component = 0.72 * wind_speed[index - 1]
        weather_component = 1.6 + seasonal_wind[index] + diurnal_wind[index]
        noise_component = rng.normal(0, 1.15)
        wind_speed[index] = np.clip(
            0.45 * persistent_component + 0.55 * weather_component + noise_component,
            0,
            15,
        )

    wind_direction = np.zeros(num_rows, dtype=int)
    wind_direction[0] = int(rng.integers(0, 361))
    for index in range(1, num_rows):
        direction_shift = rng.normal(0, 18)
        seasonal_shift = 6 * np.sin(2 * np.pi * day_of_year[index] / 365.25)
        wind_direction[index] = int((wind_direction[index - 1] + direction_shift + seasonal_shift) % 361)

    cut_in_speed = 3.0
    rated_speed = 12.0
    max_capacity = 2500.0
    effective_speed = np.clip((wind_speed - cut_in_speed) / (rated_speed - cut_in_speed), 0, 1)
    cubic_power_curve = max_capacity * np.power(effective_speed, 3)
    wake_loss = 1 - 0.04 * np.sin(np.deg2rad(wind_direction))
    air_density_adjustment = 1 + 0.0025 * (pressure - 1010) - 0.003 * (temperature - 24)
    noise = rng.normal(0, 55, size=num_rows)
    power_output = np.clip(cubic_power_curve * wake_loss * air_density_adjustment + noise, 0, max_capacity)

    dataset = pd.DataFrame(
        {
            "timestamp": timestamps,
            "wind_speed": np.round(wind_speed, 3),
            "wind_direction": wind_direction,
            "temperature": np.round(temperature, 3),
            "pressure": np.round(pressure, 3),
            "power_output": np.round(power_output, 3),
            "hour": hours,
            "day": days,
            "month": months,
        }
    )

    csv_path = Path(output_csv)
    zip_path = Path(output_zip)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    dataset.to_csv(csv_path, index=False)

    with zipfile.ZipFile(zip_path, mode="w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.write(csv_path, arcname=csv_path.name)

    return dataset


if __name__ == "__main__":
    generate_synthetic_wind_dataset()
    print("Synthetic wind dataset saved to data/wind_data.csv and wind_dataset.zip")
