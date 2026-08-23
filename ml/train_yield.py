"""Stage 2a: yield regressor - gradient boosting with crop one-hot."""
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

from features import load_data, build_yield_dataset
from train_suitability import MODELS_DIR

CAT = ["crop_name", "soil_type", "season", "water_requirement"]
NUM = ["N", "P", "K", "ph", "organic_carbon", "avg_temp_c", "total_rainfall_mm",
       "kharif_rain", "rabi_rain", "area_acre", "year_idx"]


def main():
    data = load_data()
    df = build_yield_dataset(data)
    X, y = df[CAT + NUM], df["yield_ton_per_acre"]
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.25,
                                              random_state=42)
    pre = ColumnTransformer([
        ("num", "passthrough", NUM),
        ("cat", OneHotEncoder(handle_unknown="ignore"), CAT)])
    reg = GradientBoostingRegressor(n_estimators=500, learning_rate=0.05,
                                    max_depth=4, random_state=42)
    pipe = Pipeline([("pre", pre), ("reg", reg)])
    pipe.fit(X_tr, y_tr)
    pred = pipe.predict(X_te)
    rmse = float(np.sqrt(mean_squared_error(y_te, pred)))
    mae = mean_absolute_error(y_te, pred)
    print(f"RMSE={rmse:.3f} t/acre  MAE={mae:.3f} t/acre  "
          f"(mean yield={y.mean():.2f}, MAE/mean={mae/y.mean():.1%})")
    joblib.dump(pipe, os.path.join(MODELS_DIR, "yield.pkl"))
    path = os.path.join(MODELS_DIR, "metadata.json")
    meta = {}
    if os.path.exists(path):
        with open(path) as f:
            meta = json.load(f)
    meta.update({"yield_rmse": round(rmse, 4), "yield_mae": round(mae, 4),
                 "yield_features": CAT + NUM})
    with open(path, "w") as f:
        json.dump(meta, f, indent=2)
    print("saved models/yield.pkl")


if __name__ == "__main__":
    main()
