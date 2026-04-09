"""Evaluation helpers and plotting utilities."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from backend.src.predict import _load_artifacts
from backend.src.train import run_training_pipeline

try:
    from tensorflow import keras
except Exception:  # pragma: no cover - handled dynamically
    keras = None


BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_MODELS_DIR = BACKEND_DIR / "models"
DEFAULT_PLOTS_DIR = BACKEND_DIR / "plots"


def compute_regression_metrics(y_true, y_pred) -> Dict[str, float]:
    """Return standard regression metrics."""

    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

    return {
        "MAE": float(mean_absolute_error(y_true, y_pred)),
        "RMSE": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "R2": float(r2_score(y_true, y_pred)),
    }


def plot_actual_vs_predicted(y_true, y_pred, title: str, output_path: str | Path) -> None:
    """Save an actual-vs-predicted scatter plot."""

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    plt.figure(figsize=(8, 5))
    plt.scatter(y_true, y_pred, alpha=0.6)
    min_value = min(min(y_true), min(y_pred))
    max_value = max(max(y_true), max(y_pred))
    plt.plot([min_value, max_value], [min_value, max_value], linestyle="--", color="red")
    plt.xlabel("Actual Power Output")
    plt.ylabel("Predicted Power Output")
    plt.title(title)
    plt.tight_layout()
    plt.savefig(output)
    plt.close()


def plot_training_history(history: Dict[str, list], title: str, output_path: str | Path) -> None:
    """Save training and validation loss curves."""

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    plt.figure(figsize=(8, 5))
    plt.plot(history.get("loss", []), label="Training Loss")
    plt.plot(history.get("val_loss", []), label="Validation Loss")
    plt.xlabel("Epoch")
    plt.ylabel("MSE Loss")
    plt.title(title)
    plt.legend()
    plt.tight_layout()
    plt.savefig(output)
    plt.close()


def evaluate_saved_models(
    data_path: str | Path,
    models_dir: str | Path = DEFAULT_MODELS_DIR,
    plots_dir: str | Path = DEFAULT_PLOTS_DIR,
) -> pd.DataFrame:
    """Load saved artifacts, evaluate all models, and write plots."""

    artifacts = _load_artifacts(models_dir)
    preprocessor = artifacts["preprocessor"]
    datasets = preprocessor.prepare_datasets(data_path)

    tabular = datasets["tabular"]
    sequence = datasets["sequence"]
    model_predictions = {}

    random_forest = joblib.load(Path(models_dir) / "random_forest.joblib")
    model_predictions["random_forest"] = (
        tabular["y_test"],
        random_forest.predict(tabular["X_test"]),
    )

    if keras is not None and (Path(models_dir) / "dense_nn.keras").exists():
        dense_model = keras.models.load_model(Path(models_dir) / "dense_nn.keras")
        model_predictions["dense_nn"] = (
            tabular["y_test"],
            dense_model.predict(tabular["X_test"], verbose=0).flatten(),
        )

    if (
        keras is not None
        and (Path(models_dir) / "lstm.keras").exists()
        and len(sequence["X_test"]) > 0
    ):
        lstm_model = keras.models.load_model(Path(models_dir) / "lstm.keras")
        model_predictions["lstm"] = (
            sequence["y_test"],
            lstm_model.predict(sequence["X_test"], verbose=0).flatten(),
        )

    rows = []
    for model_name, (y_true, y_pred) in model_predictions.items():
        metrics = compute_regression_metrics(y_true, y_pred)
        rows.append({"model": model_name, **metrics})
        plot_actual_vs_predicted(
            y_true,
            y_pred,
            f"Actual vs Predicted - {model_name}",
            Path(plots_dir) / f"{model_name}_actual_vs_predicted.png",
        )

    histories_path = Path(models_dir) / "training_histories.json"
    if histories_path.exists():
        histories = json.loads(histories_path.read_text())
        for model_name in ("dense_nn", "lstm"):
            if model_name in histories:
                plot_training_history(
                    histories[model_name],
                    f"Training vs Validation Loss - {model_name}",
                    Path(plots_dir) / f"{model_name}_loss.png",
                )

    results = pd.DataFrame(rows).sort_values("RMSE").reset_index(drop=True)
    results.to_csv(Path(models_dir) / "model_comparison.csv", index=False)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate saved wind forecasting models.")
    parser.add_argument("--data", required=True, help="Path to the CSV dataset.")
    parser.add_argument(
        "--models-dir",
        default=str(DEFAULT_MODELS_DIR),
        help="Directory containing saved models.",
    )
    parser.add_argument(
        "--plots-dir",
        default=str(DEFAULT_PLOTS_DIR),
        help="Directory to save plots.",
    )
    args = parser.parse_args()

    models_path = Path(args.models_dir)
    required_artifacts = [
        models_path / "preprocessor.joblib",
        models_path / "random_forest.joblib",
        models_path / "dense_nn.keras",
        models_path / "lstm.keras",
    ]

    if not all(path.exists() for path in required_artifacts):
        print("Saved artifacts were not found. Training models first.")
        run_training_pipeline(args.data, args.models_dir)

    results = evaluate_saved_models(args.data, args.models_dir, args.plots_dir)
    print("\nModel performance on the test split:")
    print(results.to_string(index=False))


if __name__ == "__main__":
    main()
