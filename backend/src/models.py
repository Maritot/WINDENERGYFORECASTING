"""Model builders for wind energy forecasting."""

from __future__ import annotations

from sklearn.ensemble import RandomForestRegressor

try:
    from tensorflow import keras
    from tensorflow.keras import layers
except Exception:  # pragma: no cover - handled at runtime for optional TF support
    keras = None
    layers = None


def build_regression_model(random_state: int = 42) -> RandomForestRegressor:
    """Return the default classical regression baseline."""

    return RandomForestRegressor(
        n_estimators=300,
        max_depth=14,
        min_samples_split=4,
        min_samples_leaf=2,
        random_state=random_state,
        n_jobs=1,
    )


def build_dense_nn(input_dim: int) -> keras.Model:
    """Build a feed-forward neural network for regression."""

    if keras is None or layers is None:
        raise ImportError("TensorFlow is not available in this environment.")

    model = keras.Sequential(
        [
            layers.Input(shape=(input_dim,)),
            layers.Dense(128, activation="relu"),
            layers.Dropout(0.2),
            layers.Dense(64, activation="relu"),
            layers.Dropout(0.2),
            layers.Dense(32, activation="relu"),
            layers.Dense(1, activation="linear"),
        ]
    )
    model.compile(optimizer=keras.optimizers.Adam(learning_rate=1e-3), loss="mse", metrics=["mae"])
    return model


def build_lstm_model(sequence_length: int, feature_dim: int) -> keras.Model:
    """Build an LSTM model for time-series regression."""

    if keras is None or layers is None:
        raise ImportError("TensorFlow is not available in this environment.")

    model = keras.Sequential(
        [
            layers.Input(shape=(sequence_length, feature_dim)),
            layers.LSTM(64, return_sequences=True),
            layers.Dropout(0.2),
            layers.LSTM(32),
            layers.Dense(32, activation="relu"),
            layers.Dense(1, activation="linear"),
        ]
    )
    model.compile(optimizer=keras.optimizers.Adam(learning_rate=1e-3), loss="mse", metrics=["mae"])
    return model
