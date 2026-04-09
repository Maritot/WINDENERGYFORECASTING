"""Data loading and preprocessing utilities for wind energy forecasting."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import sys
from typing import Dict, Iterable, List, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler


REQUIRED_COLUMNS = [
    "wind_speed",
    "wind_direction",
    "temperature",
    "pressure",
    "timestamp",
    "power_output",
]


@dataclass
class WindPreprocessorConfig:
    """Configuration for feature engineering and splitting."""

    lags: List[int] = field(default_factory=lambda: [1, 2, 3])
    rolling_windows: List[int] = field(default_factory=lambda: [3, 6])
    lookback_window: int = 24
    train_ratio: float = 0.70
    validation_ratio: float = 0.15
    test_ratio: float = 0.15


class WindDataPreprocessor:
    """Prepare wind forecasting data for tabular and sequence models."""

    def __init__(self, config: WindPreprocessorConfig | None = None) -> None:
        self.config = config or WindPreprocessorConfig()
        self.scaler = StandardScaler()
        self.feature_columns: List[str] = []

    def save(self, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)

    @staticmethod
    def load(path: str | Path) -> "WindDataPreprocessor":
        return joblib.load(path)

    @property
    def feature_warmup_rows(self) -> int:
        """Rows consumed before engineered lag and rolling features become usable."""

        max_lag = max(self.config.lags, default=0)
        max_window = max(self.config.rolling_windows, default=0)
        return max(max_lag, max_window)

    @property
    def minimum_history_rows(self) -> int:
        """Minimum recent-history rows required for inference."""

        return self.config.lookback_window + self.feature_warmup_rows

    def load_dataset(self, csv_path: str | Path) -> pd.DataFrame:
        data = pd.read_csv(csv_path)
        self._validate_columns(data.columns)
        data["timestamp"] = pd.to_datetime(data["timestamp"], errors="coerce")

        if data["timestamp"].isna().any():
            raise ValueError(
                "Some timestamp values could not be parsed. Please use a valid datetime format."
            )

        data = data.sort_values("timestamp").reset_index(drop=True)
        data = self._handle_missing_values(data)
        data = self._remove_outliers(data)
        return data

    def prepare_datasets(self, csv_path: str | Path) -> Dict[str, Dict[str, np.ndarray]]:
        raw_data = self.load_dataset(csv_path)
        featured_data = self._engineer_features(raw_data)
        split_frames = self._split_dataframe(featured_data)

        self.feature_columns = [column for column in featured_data.columns if column != "power_output"]
        train_frame = split_frames["train"]
        validation_frame = split_frames["validation"]
        test_frame = split_frames["test"]

        x_train = train_frame[self.feature_columns].to_numpy(dtype=np.float32)
        x_validation = validation_frame[self.feature_columns].to_numpy(dtype=np.float32)
        x_test = test_frame[self.feature_columns].to_numpy(dtype=np.float32)

        y_train = train_frame["power_output"].to_numpy(dtype=np.float32)
        y_validation = validation_frame["power_output"].to_numpy(dtype=np.float32)
        y_test = test_frame["power_output"].to_numpy(dtype=np.float32)

        x_train_scaled = self.scaler.fit_transform(x_train)
        x_validation_scaled = self.scaler.transform(x_validation)
        x_test_scaled = self.scaler.transform(x_test)

        sequence_train = self._make_sequences(x_train_scaled, y_train)
        sequence_validation = self._make_sequences(x_validation_scaled, y_validation)
        sequence_test = self._make_sequences(x_test_scaled, y_test)

        return {
            "tabular": {
                "X_train": x_train_scaled,
                "X_validation": x_validation_scaled,
                "X_test": x_test_scaled,
                "y_train": y_train,
                "y_validation": y_validation,
                "y_test": y_test,
            },
            "sequence": {
                "X_train": sequence_train[0],
                "X_validation": sequence_validation[0],
                "X_test": sequence_test[0],
                "y_train": sequence_train[1],
                "y_validation": sequence_validation[1],
                "y_test": sequence_test[1],
            },
            "frames": split_frames,
        }

    def transform_recent_history(
        self, new_data: pd.DataFrame | List[dict]
    ) -> Tuple[np.ndarray, np.ndarray]:
        frame = pd.DataFrame(new_data).copy()

        missing_columns = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
        if missing_columns:
            raise ValueError(
                "Recent history is missing required columns: " + ", ".join(missing_columns)
            )

        frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce")
        if frame["timestamp"].isna().any():
            raise ValueError("All timestamps in new_data must be valid datetimes.")

        frame = frame.sort_values("timestamp").reset_index(drop=True)
        frame = self._handle_missing_values(frame)
        if len(frame) < self.minimum_history_rows:
            raise ValueError(
                f"At least {self.minimum_history_rows} recent rows are required for prediction. "
                f"This includes {self.feature_warmup_rows} warm-up rows for lag and rolling features."
            )

        frame = self._engineer_features(frame, drop_na=False)

        frame = frame.dropna().reset_index(drop=True)
        if len(frame) < self.config.lookback_window:
            raise ValueError(
                "Not enough usable rows remain after feature engineering. "
                f"Provide at least {self.minimum_history_rows} chronological rows including prior "
                "power_output values."
            )

        features = frame[self.feature_columns].to_numpy(dtype=np.float32)
        features_scaled = self.scaler.transform(features)
        latest_row = features_scaled[-1].reshape(1, -1)
        latest_sequence = features_scaled[-self.config.lookback_window :].reshape(
            1, self.config.lookback_window, -1
        )
        return latest_row, latest_sequence

    def _validate_columns(self, columns: Iterable[str]) -> None:
        missing_columns = [column for column in REQUIRED_COLUMNS if column not in columns]
        if missing_columns:
            raise ValueError(
                "CSV is missing required columns: " + ", ".join(missing_columns)
            )

    def _handle_missing_values(self, frame: pd.DataFrame) -> pd.DataFrame:
        cleaned = frame.copy()
        numeric_columns = cleaned.select_dtypes(include=[np.number]).columns
        for column in numeric_columns:
            cleaned[column] = cleaned[column].fillna(cleaned[column].median())
        return cleaned.dropna(subset=["timestamp"]).reset_index(drop=True)

    def _remove_outliers(self, frame: pd.DataFrame) -> pd.DataFrame:
        cleaned = frame.copy()
        columns_to_check = ["wind_speed", "temperature", "pressure", "power_output"]
        mask = pd.Series(True, index=cleaned.index)
        for column in columns_to_check:
            q1 = cleaned[column].quantile(0.25)
            q3 = cleaned[column].quantile(0.75)
            iqr = q3 - q1
            if iqr == 0:
                continue
            lower_bound = q1 - 1.5 * iqr
            upper_bound = q3 + 1.5 * iqr
            mask &= cleaned[column].between(lower_bound, upper_bound)
        return cleaned.loc[mask].reset_index(drop=True)

    def _engineer_features(self, frame: pd.DataFrame, drop_na: bool = True) -> pd.DataFrame:
        featured = frame.copy()

        featured["hour"] = featured["timestamp"].dt.hour
        featured["day"] = featured["timestamp"].dt.day
        featured["month"] = featured["timestamp"].dt.month
        featured["dayofweek"] = featured["timestamp"].dt.dayofweek

        direction_radians = np.deg2rad(featured["wind_direction"])
        featured["wind_direction_sin"] = np.sin(direction_radians)
        featured["wind_direction_cos"] = np.cos(direction_radians)

        lag_sources = ["wind_speed", "temperature", "pressure", "power_output"]
        for column in lag_sources:
            for lag in self.config.lags:
                featured[f"{column}_lag_{lag}"] = featured[column].shift(lag)

        rolling_sources = ["wind_speed", "power_output"]
        for column in rolling_sources:
            for window in self.config.rolling_windows:
                featured[f"{column}_rolling_mean_{window}"] = (
                    featured[column].shift(1).rolling(window=window).mean()
                )

        featured = featured.drop(columns=["timestamp", "wind_direction"])
        if drop_na:
            featured = featured.dropna().reset_index(drop=True)
        return featured

    def _split_dataframe(self, frame: pd.DataFrame) -> Dict[str, pd.DataFrame]:
        total_rows = len(frame)
        train_end = int(total_rows * self.config.train_ratio)
        validation_end = train_end + int(total_rows * self.config.validation_ratio)

        train_frame = frame.iloc[:train_end].reset_index(drop=True)
        validation_frame = frame.iloc[train_end:validation_end].reset_index(drop=True)
        test_frame = frame.iloc[validation_end:].reset_index(drop=True)

        if min(len(train_frame), len(validation_frame), len(test_frame)) == 0:
            raise ValueError(
                "Dataset is too small after preprocessing. Please provide more rows."
            )

        return {
            "train": train_frame,
            "validation": validation_frame,
            "test": test_frame,
        }

    def _make_sequences(
        self, features: np.ndarray, target: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray]:
        lookback = self.config.lookback_window
        if len(features) <= lookback:
            return (
                np.empty((0, lookback, features.shape[1]), dtype=np.float32),
                np.empty((0,), dtype=np.float32),
            )

        sequences: List[np.ndarray] = []
        labels: List[float] = []
        for index in range(lookback, len(features)):
            sequences.append(features[index - lookback : index])
            labels.append(target[index])

        return np.asarray(sequences, dtype=np.float32), np.asarray(labels, dtype=np.float32)


sys.modules.setdefault("src.preprocessing", sys.modules[__name__])
