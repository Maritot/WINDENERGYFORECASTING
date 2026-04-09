"""Prediction helpers for wind energy forecasting."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

import joblib
import pandas as pd

from backend.src.preprocessing import WindDataPreprocessor


BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_MODELS_DIR = BACKEND_DIR / "models"


def _load_artifacts(models_dir: str | Path = DEFAULT_MODELS_DIR) -> Dict[str, Any]:
    models_path = Path(models_dir)
    metadata = json.loads((models_path / "model_metadata.json").read_text())
    preprocessor = WindDataPreprocessor.load(models_path / "preprocessor.joblib")
    return {"metadata": metadata, "preprocessor": preprocessor}


def _load_keras():
    """Import TensorFlow/Keras only when a TF-backed model is actually needed."""

    try:
        from tensorflow import keras  # type: ignore
    except Exception as error:  # pragma: no cover - runtime environment dependent
        raise ImportError(
            "TensorFlow is not available to load the requested neural network model."
        ) from error
    return keras


def _load_prediction_runtime(models_dir: str | Path = DEFAULT_MODELS_DIR) -> Dict[str, Any]:
    """Load the saved preprocessor and best model once for repeated predictions."""

    artifacts = _load_artifacts(models_dir)
    metadata = artifacts["metadata"]
    preprocessor = artifacts["preprocessor"]
    best_model = metadata["best_model"]
    models_path = Path(models_dir)

    if best_model == "random_forest":
        model = joblib.load(models_path / "random_forest.joblib")
    elif best_model == "dense_nn":
        keras = _load_keras()
        model = keras.models.load_model(models_path / "dense_nn.keras")
    elif best_model == "lstm":
        keras = _load_keras()
        model = keras.models.load_model(models_path / "lstm.keras")
    else:
        raise ValueError(f"Unsupported model name in metadata: {best_model}")

    return {
        "metadata": metadata,
        "preprocessor": preprocessor,
        "model_name": best_model,
        "model": model,
    }


def _predict_with_runtime(
    new_data: pd.DataFrame | List[dict], runtime: Dict[str, Any]
) -> Dict[str, Any]:
    """Predict from an already-loaded preprocessor and model runtime."""

    metadata = runtime["metadata"]
    preprocessor = runtime["preprocessor"]
    best_model = runtime["model_name"]
    model = runtime["model"]
    latest_row, latest_sequence = preprocessor.transform_recent_history(new_data)

    if best_model == "random_forest":
        prediction = float(model.predict(latest_row)[0])
    elif best_model == "dense_nn":
        prediction = float(model.predict(latest_row, verbose=0).flatten()[0])
    elif best_model == "lstm":
        prediction = float(model.predict(latest_sequence, verbose=0).flatten()[0])
    else:
        raise ValueError(f"Unsupported model name in metadata: {best_model}")

    return {
        "model_name": best_model,
        "prediction": prediction,
        "lookback_window": metadata["lookback_window"],
        "minimum_history_rows": preprocessor.minimum_history_rows,
        "feature_count": len(preprocessor.feature_columns),
    }


def predict_wind_energy(
    new_data: pd.DataFrame | List[dict], models_dir: str | Path = DEFAULT_MODELS_DIR
) -> Dict[str, Any]:
    """Predict wind power output from recent historical rows."""

    runtime = _load_prediction_runtime(models_dir)
    return _predict_with_runtime(new_data, runtime)


def _load_input_records(input_path: str | Path) -> List[dict]:
    path = Path(input_path)
    if path.suffix.lower() == ".json":
        return json.loads(path.read_text())
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path).to_dict(orient="records")
    raise ValueError("Input file must be a .json or .csv file.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Predict wind energy from recent history.")
    parser.add_argument("--input", required=True, help="Path to a JSON or CSV file with recent rows.")
    parser.add_argument(
        "--models-dir",
        default=str(DEFAULT_MODELS_DIR),
        help="Directory containing saved artifacts.",
    )
    args = parser.parse_args()

    prediction = predict_wind_energy(_load_input_records(args.input), args.models_dir)
    print(json.dumps(prediction, indent=2))


if __name__ == "__main__":
    main()
