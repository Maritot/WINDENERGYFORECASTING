"""Training script for wind energy forecasting models."""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Dict

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from backend.src.models import build_dense_nn, build_lstm_model, build_regression_model
from backend.src.preprocessing import WindDataPreprocessor

try:
    import tensorflow as tf
    from tensorflow import keras
except Exception:  # pragma: no cover - handled dynamically for optional TF support
    tf = None
    keras = None


BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_MODELS_DIR = BACKEND_DIR / "models"


def set_seed(seed: int = 42) -> None:
    """Set random seeds for reproducible experiments."""

    random.seed(seed)
    np.random.seed(seed)
    if tf is not None:
        tf.random.set_seed(seed)


def compute_metrics(y_true, y_pred) -> Dict[str, float]:
    """Return MAE, RMSE, and R2 for a prediction task."""

    return {
        "MAE": float(mean_absolute_error(y_true, y_pred)),
        "RMSE": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "R2": float(r2_score(y_true, y_pred)),
    }


def run_training_pipeline(
    data_path: str | Path, models_dir: str | Path = DEFAULT_MODELS_DIR
) -> pd.DataFrame:
    """Train all models, save artifacts, and return comparison metrics."""

    set_seed()
    models_path = Path(models_dir)
    models_path.mkdir(parents=True, exist_ok=True)

    preprocessor = WindDataPreprocessor()
    datasets = preprocessor.prepare_datasets(data_path)
    tabular = datasets["tabular"]
    sequence = datasets["sequence"]

    tensorflow_available = tf is not None and keras is not None

    if tensorflow_available and (len(sequence["X_train"]) == 0 or len(sequence["X_validation"]) == 0):
        raise ValueError(
            "Dataset is too small for LSTM training after preprocessing. "
            "Please provide more historical rows."
        )

    histories: Dict[str, Dict[str, list]] = {}
    rows = []

    random_forest = build_regression_model()
    random_forest.fit(tabular["X_train"], tabular["y_train"])
    rf_validation_predictions = random_forest.predict(tabular["X_validation"])
    rf_test_predictions = random_forest.predict(tabular["X_test"])
    rf_validation_metrics = compute_metrics(tabular["y_validation"], rf_validation_predictions)
    rf_test_metrics = compute_metrics(tabular["y_test"], rf_test_predictions)
    rows.append(
        {
            "model": "random_forest",
            "validation_MAE": rf_validation_metrics["MAE"],
            "validation_RMSE": rf_validation_metrics["RMSE"],
            "validation_R2": rf_validation_metrics["R2"],
            "test_MAE": rf_test_metrics["MAE"],
            "test_RMSE": rf_test_metrics["RMSE"],
            "test_R2": rf_test_metrics["R2"],
        }
    )
    joblib.dump(random_forest, models_path / "random_forest.joblib")

    if tensorflow_available:
        try:
            early_stopping = keras.callbacks.EarlyStopping(
                monitor="val_loss",
                patience=10,
                restore_best_weights=True,
            )

            dense_nn = build_dense_nn(tabular["X_train"].shape[1])
            dense_history = dense_nn.fit(
                tabular["X_train"],
                tabular["y_train"],
                validation_data=(tabular["X_validation"], tabular["y_validation"]),
                epochs=100,
                batch_size=32,
                callbacks=[early_stopping],
                verbose=0,
            )
            dense_validation_predictions = dense_nn.predict(tabular["X_validation"], verbose=0).flatten()
            dense_test_predictions = dense_nn.predict(tabular["X_test"], verbose=0).flatten()
            dense_validation_metrics = compute_metrics(tabular["y_validation"], dense_validation_predictions)
            dense_test_metrics = compute_metrics(tabular["y_test"], dense_test_predictions)
            rows.append(
                {
                    "model": "dense_nn",
                    "validation_MAE": dense_validation_metrics["MAE"],
                    "validation_RMSE": dense_validation_metrics["RMSE"],
                    "validation_R2": dense_validation_metrics["R2"],
                    "test_MAE": dense_test_metrics["MAE"],
                    "test_RMSE": dense_test_metrics["RMSE"],
                    "test_R2": dense_test_metrics["R2"],
                }
            )
            histories["dense_nn"] = {
                key: [float(value) for value in values] for key, values in dense_history.history.items()
            }
            dense_nn.save(models_path / "dense_nn.keras")

            lstm = build_lstm_model(sequence["X_train"].shape[1], sequence["X_train"].shape[2])
            lstm_history = lstm.fit(
                sequence["X_train"],
                sequence["y_train"],
                validation_data=(sequence["X_validation"], sequence["y_validation"]),
                epochs=100,
                batch_size=32,
                callbacks=[early_stopping],
                verbose=0,
            )
            lstm_validation_predictions = lstm.predict(sequence["X_validation"], verbose=0).flatten()
            lstm_test_predictions = lstm.predict(sequence["X_test"], verbose=0).flatten()
            lstm_validation_metrics = compute_metrics(sequence["y_validation"], lstm_validation_predictions)
            lstm_test_metrics = compute_metrics(sequence["y_test"], lstm_test_predictions)
            rows.append(
                {
                    "model": "lstm",
                    "validation_MAE": lstm_validation_metrics["MAE"],
                    "validation_RMSE": lstm_validation_metrics["RMSE"],
                    "validation_R2": lstm_validation_metrics["R2"],
                    "test_MAE": lstm_test_metrics["MAE"],
                    "test_RMSE": lstm_test_metrics["RMSE"],
                    "test_R2": lstm_test_metrics["R2"],
                }
            )
            histories["lstm"] = {
                key: [float(value) for value in values] for key, values in lstm_history.history.items()
            }
            lstm.save(models_path / "lstm.keras")
        except Exception as error:
            tensorflow_available = False
            print(
                "TensorFlow models could not be trained in this environment. "
                f"Continuing with random_forest only. Details: {error}"
            )
    else:
        print(
            "TensorFlow is unavailable in this environment. "
            "Skipping dense_nn and lstm training; using random_forest only."
        )

    results = pd.DataFrame(rows).sort_values("validation_RMSE").reset_index(drop=True)
    best_model = results.iloc[0]["model"]

    results.to_csv(models_path / "model_comparison.csv", index=False)
    (models_path / "training_histories.json").write_text(json.dumps(histories, indent=2))
    preprocessor.save(models_path / "preprocessor.joblib")

    metadata = {
        "best_model": best_model,
        "lookback_window": preprocessor.config.lookback_window,
        "feature_warmup_rows": preprocessor.feature_warmup_rows,
        "minimum_history_rows": preprocessor.minimum_history_rows,
        "feature_columns": preprocessor.feature_columns,
        "tensorflow_available": tensorflow_available,
        "required_columns": [
            "wind_speed",
            "wind_direction",
            "temperature",
            "pressure",
            "timestamp",
            "power_output",
        ],
    }
    (models_path / "model_metadata.json").write_text(json.dumps(metadata, indent=2))

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Train wind energy forecasting models.")
    parser.add_argument("--data", required=True, help="Path to the CSV dataset.")
    parser.add_argument(
        "--models-dir",
        default=str(DEFAULT_MODELS_DIR),
        help="Directory where artifacts will be saved.",
    )
    args = parser.parse_args()

    results = run_training_pipeline(args.data, args.models_dir)
    print("\nTraining complete. Validation-ranked model comparison:")
    print(results.to_string(index=False))


if __name__ == "__main__":
    main()
