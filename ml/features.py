"""Join raw CSV tables into model-ready feature sets."""
import os
import numpy as np
import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")


def load_data():
    data = {}
    for name in ["soil_data", "weather_data", "crop_master", "crop_yield_history",
                 "market_prices", "cost_of_cultivation", "farmer_seasons"]:
        path = os.path.join(DATA_DIR, f"{name}.csv")
        df = pd.read_csv(path)
        if "ideal_soil_types" in df.columns:
            df["ideal_soil_types"] = df["ideal_soil_types"].apply(eval)
        if "ideal_temp_range" in df.columns:
            df["ideal_temp_range"] = df["ideal_temp_range"].apply(eval)
        if "ideal_rainfall_range" in df.columns:
            df["ideal_rainfall_range"] = df["ideal_rainfall_range"].apply(eval)
        data[name] = df
    return data


def _location_context(data):
    """Per-location: soil + seasonal climate aggregates."""
    soil = data["soil_data"]
    wx = data["weather_data"]
    annual = wx.groupby("location_id").agg(
        avg_temp_c=("avg_temp_c", "mean"),
        avg_rainfall_mm=("avg_rainfall_mm", "mean"),
        total_rainfall_mm=("avg_rainfall_mm", "sum"),
        avg_humidity_pct=("avg_humidity_pct", "mean")).reset_index()
    # season-month aggregates (Kharif ~ Jun-Oct, Rabi ~ Nov-Mar)
    kharif = wx[wx["month"].between(6, 10)].groupby("location_id").agg(
        kharif_rain=("avg_rainfall_mm", "sum"), kharif_temp=("avg_temp_c", "mean")).reset_index()
    rabi = wx[~wx["month"].between(6, 10)].groupby("location_id").agg(
        rabi_rain=("avg_rainfall_mm", "sum"), rabi_temp=("avg_temp_c", "mean")).reset_index()
    ctx = soil.merge(annual, on="location_id").merge(kharif, on="location_id") \
              .merge(rabi, on="location_id")
    return ctx


def _is_suitable(soil_type, avg_temp_c, total_rain_mm, soils, t_range, r_range):
    """Mirrors the generator's deterministic suitability rule (with tolerances)."""
    t_lo, t_hi = t_range
    r_lo, r_hi = r_range
    return (soil_type in soils and t_lo - 3 <= avg_temp_c <= t_hi + 3
            and r_lo * 0.8 <= total_rain_mm <= r_hi * 1.25)


def build_suitability_dataset(data):
    """One row per (location x ALL candidate crops); label = suitable 1/0.
    Includes crop attributes so the model learns the location<->crop match."""
    ctx = _location_context(data)
    master = data["crop_master"]
    rows = []
    for _, L in ctx.iterrows():
        for _, c in master.iterrows():
            suit = _is_suitable(L["soil_type"], L["avg_temp_c"], L["total_rainfall_mm"],
                                c["ideal_soil_types"], c["ideal_temp_range"],
                                c["ideal_rainfall_range"])
            rows.append({
                "location_id": int(L["location_id"]),
                "soil_type": L["soil_type"], "season": c["season"],
                "N": L["N"], "P": L["P"], "K": L["K"], "ph": L["ph"],
                "organic_carbon": L["organic_carbon"],
                "avg_temp_c": L["avg_temp_c"],
                "total_rainfall_mm": L["total_rainfall_mm"],
                "avg_humidity_pct": L["avg_humidity_pct"],
                "kharif_rain": L["kharif_rain"], "kharif_temp": L["kharif_temp"],
                "rabi_rain": L["rabi_rain"], "rabi_temp": L["rabi_temp"],
                # crop attributes
                "n_ideal_soils": len(c["ideal_soil_types"]),
                "temp_mid": (c["ideal_temp_range"][0] + c["ideal_temp_range"][1]) / 2,
                "rain_lo": c["ideal_rainfall_range"][0],
                "rain_hi": c["ideal_rainfall_range"][1],
                "water_ordinal": {"Low": 0, "Medium": 1, "High": 2, "Very High": 3}[c["water_requirement"]],
                "soil_in_ideal": int(L["soil_type"] in c["ideal_soil_types"]),
                "temp_within_ideal": int(c["ideal_temp_range"][0] - 3 <= L["avg_temp_c"] <= c["ideal_temp_range"][1] + 3),
                "rain_within_ideal": int(c["ideal_rainfall_range"][0] * 0.8 <= L["total_rainfall_mm"] <= c["ideal_rainfall_range"][1] * 1.25),
                "crop_name": c["crop_name"],
                "suitable": int(suit)})
    return pd.DataFrame(rows)


def build_yield_dataset(data):
    """Yield regression rows: history joined to location context."""
    ctx = _location_context(data)
    hist = data["crop_yield_history"]
    df = hist.merge(ctx, on="location_id").merge(
        data["crop_master"][["crop_name", "water_requirement"]], on="crop_name")
    df["year_idx"] = df["year"] - df["year"].min()
    return df


def build_price_dataset(data):
    """Lag-feature rows: predict next month's modal price from previous 3 months."""
    mp = data["market_prices"].sort_values(["crop_name", "state", "year", "month"])
    g = mp.groupby(["crop_name", "state"])
    mp["lag1"] = g["modal_price_rs_per_quintal"].shift(1)
    mp["lag2"] = g["modal_price_rs_per_quintal"].shift(2)
    mp["lag3"] = g["modal_price_rs_per_quintal"].shift(3)
    mp["target_next_month"] = g["modal_price_rs_per_quintal"].shift(-1)
    mp = mp.dropna(subset=["lag1", "lag2", "lag3", "target_next_month"])
    mp["mom_change"] = mp["lag1"] / mp["lag2"] - 1
    return mp


if __name__ == "__main__":
    data = load_data()
    suit = build_suitability_dataset(data)
    yld = build_yield_dataset(data)
    prc = build_price_dataset(data)
    print(f"suitability dataset: {suit.shape}, "
          f"positive rate={suit['suitable'].mean():.1%}")
    print(f"yield dataset:       {yld.shape}")
    print(f"price dataset:       {prc.shape}")
    print("\nsample suitability rows:")
    cols = ["location_id", "crop_name", "soil_type", "N", "K", "ph",
            "total_rainfall_mm", "season", "suitable"]
    print(suit[cols].head(5).to_string(index=False))
