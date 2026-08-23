"""Stage 1: crop suitability classifier (RandomForest).

Framing note: a multi-class crop_name target is unlearnable here because all
candidate crops at one location share identical location features. We instead
train a BINARY suitability classifier over every (location x candidate crop)
pair, with crop attributes as features. At inference we score each of the 20
crops against the farmer's location and shortlist the top-k by P(suitable).
"""
import os
import json
import joblib
from datetime import datetime, timezone
from sklearn.ensemble import RandomForestClassifier
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score

from features import load_data, build_suitability_dataset

MODELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models")

NUM_FEATURES = ["N", "P", "K", "ph", "organic_carbon", "avg_temp_c",
                "total_rainfall_mm", "avg_humidity_pct", "kharif_rain",
                "kharif_temp", "rabi_rain", "rabi_temp",
                "n_ideal_soils", "temp_mid", "rain_lo", "rain_hi",
                "water_ordinal"]
CAT_FEATURES = ["soil_type", "season"]


def make_pipeline():
    pre = ColumnTransformer([
        ("num", "passthrough", NUM_FEATURES),
        ("cat", OneHotEncoder(handle_unknown="ignore"), CAT_FEATURES)])
    clf = RandomForestClassifier(n_estimators=300, min_samples_leaf=2,
                                 random_state=42)
    return Pipeline([("pre", pre), ("clf", clf)])


def main():
    data = load_data()
    df = build_suitability_dataset(data)
    X = df[NUM_FEATURES + CAT_FEATURES]
    y = df["suitable"]
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.25,
                                              stratify=y, random_state=42)
    pipe = make_pipeline()
    pipe.fit(X_tr, y_tr)
    pred = pipe.predict(X_te)
    prob = pipe.predict_proba(X_te)[:, 1]
    acc = accuracy_score(y_te, pred)
    f1m = f1_score(y_te, pred, average="macro")
    auc = roc_auc_score(y_te, prob)
    print(f"accuracy={acc:.3f}  macro-F1={f1m:.3f}  ROC-AUC={auc:.3f}  "
          f"positive rate={y.mean():.1%}")
    os.makedirs(MODELS_DIR, exist_ok=True)
    joblib.dump(pipe, os.path.join(MODELS_DIR, "suitability.pkl"))
    path = os.path.join(MODELS_DIR, "metadata.json")
    meta = {}
    if os.path.exists(path):
        with open(path) as f:
            meta = json.load(f)
    meta.update({"model": "RandomForestClassifier", "task": "stage1_suitability_binary",
                 "accuracy": round(acc, 4), "macro_f1": round(f1m, 4),
                 "roc_auc": round(auc, 4), "n_samples": len(df),
                 "features": {"numeric": NUM_FEATURES, "categorical": CAT_FEATURES},
                 "trained_at": datetime.now(timezone.utc).isoformat()})
    with open(path, "w") as f:
        json.dump(meta, f, indent=2)
    print("saved models/suitability.pkl")


if __name__ == "__main__":
    main()
