"""Stage 2b: price forecaster - gradient boosting on lag + seasonal features."""
import os
import json
import joblib
import numpy as np
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, mean_absolute_error

from features import load_data, build_price_dataset
from train_suitability import MODELS_DIR

CAT = ["crop_name", "state"]
NUM = ["lag1", "lag2", "lag3", "mom_change", "month_sin", "month_cos", "year_idx"]


def main():
    data = load_data()
    df = build_price_dataset(data)
    df["month_sin"] = np.sin(2 * np.pi * df["month"] / 12)
    df["month_cos"] = np.cos(2 * np.pi * df["month"] / 12)
    df["year_idx"] = df["year"] - df["year"].min()
    X, y = df[CAT + NUM], df["target_next_month"]
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.25,
                                              random_state=42)
    pre = ColumnTransformer([
        ("num", "passthrough", NUM),
        ("cat", OneHotEncoder(handle_unknown="ignore"), CAT)])
    reg = GradientBoostingRegressor(n_estimators=400, learning_rate=0.06,
                                    max_depth=4, random_state=42)
    pipe = Pipeline([("pre", pre), ("reg", reg)])
    pipe.fit(X_tr, y_tr)
    pred = pipe.predict(X_te)
    rmse = float(np.sqrt(mean_squared_error(y_te, pred)))
    mae = mean_absolute_error(y_te, pred)
    print(f"RMSE={rmse:.0f} Rs/quintal  MAE={mae:.0f} Rs/quintal  "
          f"(mean price={y.mean():.0f}, MAE/mean={mae/y.mean():.1%})")
    joblib.dump(pipe, os.path.join(MODELS_DIR, "price.pkl"))
    path = os.path.join(MODELS_DIR, "metadata.json")
    meta = {}
    if os.path.exists(path):
        with open(path) as f:
            meta = json.load(f)
    meta.update({"price_rmse": round(rmse, 2), "price_mae": round(mae, 2),
                 "price_features": CAT + NUM})
    with open(path, "w") as f:
        json.dump(meta, f, indent=2)
    print("saved models/price.pkl")


if __name__ == "__main__":
    main()
