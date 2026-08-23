"""
Synthetic data generator for the AI Crop Recommendation System.

ALL DATA HERE IS SYNTHETIC / ILLUSTRATIVE - ranges are loosely based on
realistic Indian agriculture figures but are NOT real government data.
Swap in real sources (Agmarknet, IMD, Soil Health Card) for production.

Outputs 7 CSVs into ../data:
  soil_data.csv, weather_data.csv, crop_master.csv, crop_yield_history.csv,
  market_prices.csv, cost_of_cultivation.csv, farmer_seasons.csv

Consistency guarantee: farmer outcomes are DERIVED from yield x price - cost
(plus noise), so ML models learn a real signal rather than random labels.
"""
import os
import numpy as np
import pandas as pd

rng = np.random.default_rng(42)

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "..", "data")
os.makedirs(DATA_DIR, exist_ok=True)


def save(df: pd.DataFrame, name: str) -> None:
    path = os.path.join(DATA_DIR, name)
    df.to_csv(path, index=False)
    print(f"  wrote {name}: {len(df)} rows")


# ---------------------------------------------------------------- districts
# (state, district, dominant_soil) - 18 districts across 5 states
DISTRICTS = [
    ("Punjab", "Ludhiana", "Alluvial"), ("Punjab", "Bathinda", "Alluvial"),
    ("Punjab", "Amritsar", "Alluvial"), ("Uttar Pradesh", "Meerut", "Alluvial"),
    ("Uttar Pradesh", "Kanpur Nagar", "Alluvial"), ("Uttar Pradesh", "Varanasi", "Alluvial"),
    ("Maharashtra", "Nagpur", "Black"), ("Maharashtra", "Aurangabad", "Black"),
    ("Maharashtra", "Solapur", "Black"), ("Madhya Pradesh", "Indore", "Black"),
    ("Madhya Pradesh", "Bhopal", "Black"), ("Karnataka", "Belagavi", "Red"),
    ("Karnataka", "Mysuru", "Red"), ("Karnataka", "Ballari", "Red"),
    ("Tamil Nadu", "Coimbatore", "Red"), ("West Bengal", "Hooghly", "Alluvial"),
    ("West Bengal", "Bardhaman", "Alluvial"), ("Kerala", "Thrissur", "Laterite"),
]
LOCATIONS = [{"location_id": i + 1, "state": s, "district": d, "soil_type": st}
             for i, (s, d, st) in enumerate(DISTRICTS)]
loc_df = pd.DataFrame(LOCATIONS)

# ---------------------------------------------------------------- soil_data
SOIL_BASE = {  # base N,P,K by soil type (kg/ha), realistic-ish ranges
    "Alluvial": (110, 22, 90), "Black": (95, 18, 80), "Red": (70, 15, 60),
    "Laterite": (55, 12, 45), "Sandy": (35, 10, 30), "Clayey": (100, 20, 85),
    "Loamy": (120, 25, 100),
}
PH_BASE = {"Alluvial": 7.2, "Black": 7.8, "Red": 6.3, "Laterite": 5.4,
           "Sandy": 6.8, "Clayey": 7.5, "Loamy": 6.9}
soil_rows = []
for L in LOCATIONS:
    n0, p0, k0 = SOIL_BASE[L["soil_type"]]
    soil_rows.append({
        "location_id": L["location_id"],
        "N": np.clip(rng.normal(n0, 8), 10, 140),
        "P": np.clip(rng.normal(p0, 3), 5, 60),
        "K": np.clip(rng.normal(k0, 7), 10, 140),
        "ph": np.clip(rng.normal(PH_BASE[L["soil_type"]], 0.25), 4.5, 8.5),
        "organic_carbon": round(float(np.clip(rng.normal(0.55, 0.12), 0.15, 1.2)), 2),
    })
# state/district/soil_type columns required by spec
soil_df = pd.DataFrame(soil_rows).merge(loc_df[["location_id", "state", "district", "soil_type"]], on="location_id")
soil_df = soil_df[["location_id", "state", "district", "soil_type", "N", "P", "K", "ph", "organic_carbon"]]
save(soil_df, "soil_data.csv")

# -------------------------------------------------------------- weather_data
MONTHS = list(range(1, 13))
BASE_TEMP = {"North": 24.5, "West": 27.0, "South": 27.5, "East": 26.0}
REGION_OF_STATE = {"Punjab": "North", "Uttar Pradesh": "North",
                   "Maharashtra": "West", "Madhya Pradesh": "West",
                   "Karnataka": "South", "Tamil Nadu": "South",
                   "West Bengal": "East", "Kerala": "South"}
MONSOON_RAIN = {6: 160, 7: 250, 8: 230, 9: 170}
NON_MONSOON_RAIN = {10: 60, 11: 15, 12: 8, 1: 10, 2: 10, 3: 8, 4: 12, 5: 30}

weather_rows = []
for L in LOCATIONS:
    region = REGION_OF_STATE[L["state"]]
    bt = BASE_TEMP[region] + rng.normal(0, 1.0)
    district_rain_mult = rng.uniform(0.75, 1.3)
    for m in MONTHS:
        # seasonal temperature wave (peaks ~May)
        temp = bt + 6.5 * np.cos((m - 5) * np.pi / 6) + rng.normal(0, 0.8)
        base_rain = MONSOON_RAIN[m] if m in MONSOON_RAIN else NON_MONSOON_RAIN[m]
        rain = base_rain * district_rain_mult * rng.uniform(0.8, 1.2)
        hum = np.clip(50 + rain * 0.12 + rng.normal(0, 5), 25, 95)
        weather_rows.append({"location_id": L["location_id"], "month": m,
                             "avg_temp_c": round(temp, 1),
                             "avg_rainfall_mm": round(rain, 1),
                             "avg_humidity_pct": round(hum, 1)})
weather_df = pd.DataFrame(weather_rows)
save(weather_df, "weather_data.csv")

# ---------------------------------------------------------------- crop_master
CROPS = [
    # name, family, ideal soils, ideal temp, ideal annual-rainfall(mm), water req, season
    ("Rice", "Cereal", ["Alluvial", "Clayey", "Loamy"], (20, 36), (900, 2200), "High", "Kharif"),
    ("Wheat", "Cereal", ["Alluvial", "Loamy", "Black"], (10, 25), (400, 900), "Medium", "Rabi"),
    ("Maize", "Cereal", ["Alluvial", "Loamy", "Red", "Black"], (18, 32), (500, 1200), "Medium", "Kharif"),
    ("Barley", "Cereal", ["Alluvial", "Sandy", "Loamy"], (10, 26), (350, 800), "Low", "Rabi"),
    ("Cotton", "Fiber", ["Black", "Alluvial"], (20, 34), (600, 1200), "Medium", "Kharif"),
    ("Jute", "Fiber", ["Alluvial", "Clayey"], (24, 37), (1000, 2000), "High", "Kharif"),
    ("Sugarcane", "Cash Crop", ["Alluvial", "Black", "Loamy", "Clayey"], (20, 35), (900, 2000), "Very High", "Annual"),
    ("Soybean", "Oilseed", ["Black", "Loamy"], (18, 32), (600, 1200), "Medium", "Kharif"),
    ("Groundnut", "Oilseed", ["Sandy", "Red", "Loamy", "Black"], (22, 33), (500, 1100), "Medium", "Kharif"),
    ("Mustard", "Oilseed", ["Alluvial", "Loamy", "Sandy"], (10, 25), (300, 700), "Low", "Rabi"),
    ("Sunflower", "Oilseed", ["Black", "Red", "Loamy", "Alluvial"], (18, 33), (500, 1000), "Medium", "Rabi"),
    ("Chickpea", "Pulse", ["Black", "Red", "Loamy", "Sandy"], (15, 28), (350, 750), "Low", "Rabi"),
    ("Pigeon Pea", "Pulse", ["Black", "Red", "Loamy"], (20, 32), (600, 1100), "Low", "Kharif"),
    ("Tomato", "Vegetable", ["Loamy", "Red", "Alluvial", "Black"], (18, 30), (500, 1000), "Medium", "Rabi"),
    ("Onion", "Vegetable", ["Alluvial", "Loamy", "Black", "Red"], (15, 30), (450, 900), "Medium", "Rabi"),
    ("Potato", "Vegetable", ["Alluvial", "Loamy", "Sandy"], (12, 24), (450, 900), "Medium", "Rabi"),
    ("Banana", "Fruit", ["Alluvial", "Loamy", "Red", "Clayey"], (22, 34), (1000, 2200), "Very High", "Annual"),
    ("Mango", "Fruit", ["Alluvial", "Loamy", "Red", "Laterite"], (22, 36), (700, 1800), "Medium", "Annual"),
    ("Turmeric", "Spice", ["Loamy", "Red", "Clayey", "Alluvial"], (20, 33), (800, 1600), "High", "Kharif"),
    ("Chili", "Spice", ["Black", "Red", "Loamy"], (18, 32), (550, 1100), "Medium", "Kharif"),
]
crop_master = pd.DataFrame(
    CROPS, columns=["crop_name", "crop_family", "ideal_soil_types",
                    "ideal_temp_range", "ideal_rainfall_range",
                    "water_requirement", "season"])
save(crop_master, "crop_master.csv")

# --------------------------------------------------------- crop_yield_history
# baseline yields expressed as realistic quintals/acre, converted to ton/acre.
# (synthetic/illustrative - loosely based on typical Indian averages)
Q_PER_ACRE = {"Rice": 27, "Wheat": 29, "Maize": 31, "Barley": 24,
              "Cotton": 9, "Jute": 21, "Sugarcane": 1350,
              "Soybean": 15, "Groundnut": 17, "Mustard": 14,
              "Sunflower": 13, "Chickpea": 11, "Pigeon Pea": 8,
              "Tomato": 190, "Onion": 160, "Potato": 170,
              "Banana": 330, "Mango": 55, "Turmeric": 48, "Chili": 14}
YIELD_BASE = {c: q / 100.0 for c, q in Q_PER_ACRE.items()}


def crop_fits_location(crop_row, soil_type, avg_temp, avg_annual_rain):
    """Deterministic suitability check used both here and for consistency."""
    if isinstance(crop_row["ideal_soil_types"], str):
        soils = eval(crop_row["ideal_soil_types"])
    else:
        soils = list(crop_row["ideal_soil_types"])
    t_lo, t_hi = crop_row["ideal_temp_range"]
    r_lo, r_hi = crop_row["ideal_rainfall_range"]
    return (soil_type in soils and t_lo - 3 <= avg_temp <= t_hi + 3
            and r_lo * 0.8 <= avg_annual_rain <= r_hi * 1.25)


avg_by_loc = weather_df.groupby("location_id").agg(
    avg_temp=("avg_temp_c", "mean"), avg_rain=("avg_rainfall_mm", "sum")).reset_index()
loc_ctx = loc_df.merge(avg_by_loc, on="location_id")

yield_rows = []
for _, ctx in loc_ctx.iterrows():
    for crop_name, family, soils, trange, rrange, water, season in CROPS:
        crow = {"crop_name": crop_name, "crop_family": family,
                "ideal_soil_types": list(soils), "ideal_temp_range": trange,
                "ideal_rainfall_range": rrange,
                "water_requirement": water, "season": season}
        fits = crop_fits_location(crow, ctx["soil_type"], ctx["avg_temp"], ctx["avg_rain"])
        # even non-ideal combos appear sometimes (marginal cultivation) at low freq/prob
        p_include = 0.92 if fits else 0.06
        if rng.random() > p_include:
            continue
        base = YIELD_BASE[crop_name]
        fit_mult = 1.0 if fits else 0.55
        loc_skill = rng.uniform(0.85, 1.15)  # persistent district effect
        area = float(np.clip(rng.uniform(40, 400) if fits else rng.uniform(10, 60), 5, None))
        for year in range(2019, 2024):
            trend = 1.0 + 0.02 * (year - 2019)          # mild tech improvement
            y = (base * fit_mult * loc_skill * trend *
                 rng.uniform(0.88, 1.12))               # weather noise
            season_lbl = season if season != "Annual" else ("Kharif" if year % 2 else "Rabi")
            yield_rows.append({"location_id": int(ctx["location_id"]),
                               "crop_name": crop_name,
                               "season": season_lbl, "year": year,
                               "area_acre": round(area, 1),
                               "yield_ton_per_acre": round(y, 3)})
yield_df = pd.DataFrame(yield_rows)
save(yield_df, "crop_yield_history.csv")

# --------------------------------------------------------------- market_prices
PRICE_BASE = {"Rice": 2100, "Wheat": 2150, "Maize": 1950, "Barley": 1750,
              "Cotton": 6400, "Jute": 4800, "Sugarcane": 320, "Soybean": 4300,
              "Groundnut": 5600, "Mustard": 5200, "Sunflower": 5800,
              "Chickpea": 5100, "Pigeon Pea": 6500, "Tomato": 1400,
              "Onion": 1500, "Potato": 1300, "Banana": 2600, "Mango": 4200,
              "Turmeric": 8500, "Chili": 9500}
price_rows = []
for year in range(2021, 2024):
    for crop_name, *_ in CROPS:
        level = PRICE_BASE[crop_name]
        yearly_growth = 1.04 + rng.uniform(-0.01, 0.03)   # mild YoY inflation
        level *= yearly_growth ** (year - 2021)
        for m in MONTHS:
            seasonal = 1.0 + 0.08 * np.sin((m - 10) * np.pi / 6)  # harvest glut dips price
            modal = level * seasonal * rng.uniform(0.94, 1.06)
            lo = modal * rng.uniform(0.82, 0.92)
            hi = modal * rng.uniform(1.08, 1.20)
            price_rows.append({"crop_name": crop_name, "state": "", "month": m,
                               "year": year,
                               "min_price_rs_per_quintal": round(lo, 0),
                               "max_price_rs_per_quintal": round(hi, 0),
                               "modal_price_rs_per_quintal": round(modal, 0)})
prices = pd.DataFrame(price_rows)
# prices vary modestly by state (transport/market access)
states = sorted({l["state"] for l in LOCATIONS})
st_m = {s: rng.uniform(0.94, 1.07) for s in states}
prices_out = []
for _, row in prices.iterrows():
    for st in states:
        m = st_m[st]
        prices_out.append({**row, "state": st,
                           "min_price_rs_per_quintal": round(row["min_price_rs_per_quintal"] * m, 0),
                           "max_price_rs_per_quintal": round(row["max_price_rs_per_quintal"] * m, 0),
                           "modal_price_rs_per_quintal": round(row["modal_price_rs_per_quintal"] * m, 0)})
market_prices_df = pd.DataFrame(prices_out)[
    ["crop_name", "state", "month", "year", "min_price_rs_per_quintal",
     "max_price_rs_per_quintal", "modal_price_rs_per_quintal"]]
save(market_prices_df, "market_prices.csv")

# ------------------------------------------------------- cost_of_cultivation
# Costs are DERIVED from realistic yield x price with a variable margin factor
# so that profit/loss outcomes are internally consistent (some crop-state pairs
# are structurally unprofitable, like in reality).
MARGIN_FACTOR = {c: rng.uniform(0.92, 1.38) for c, *_ in CROPS}
cost_rows = []
for crop_name, *_ in CROPS:
    # expected revenue at baseline yield x 2022 modal price
    p22 = market_prices_df[(market_prices_df["crop_name"] == crop_name) &
                           (market_prices_df["year"] == 2022)]["modal_price_rs_per_quintal"].mean()
    target_cost = Q_PER_ACRE[crop_name] * p22 / MARGIN_FACTOR[crop_name]
    for st in states:
        st_adj = st_m[st]
        total = target_cost * rng.uniform(0.93, 1.07)
        op = total / (1 + rng.uniform(0.18, 0.30))
        fixed = total - op
        cost_rows.append({"crop_name": crop_name, "state": st,
                          "operational_cost_rs_per_acre": round(op * st_adj, 0),
                          "fixed_cost_rs_per_acre": round(fixed * st_adj, 0),
                          "total_cost_rs_per_acre": round(total * st_adj, 0)})
cost_df = pd.DataFrame(cost_rows)
cost_df["msp_rs_per_quintal"] = cost_df["crop_name"].map({
    "Rice": 2183, "Wheat": 2275, "Maize": 2090, "Barley": 1850,
    "Cotton": 6620, "Soybean": 4890, "Groundnut": 6780, "Mustard": 5650,
    "Sunflower": 7150, "Chickpea": 5440, "Pigeon Pea": 7550, "Sugarcane": 315})
save(cost_df, "cost_of_cultivation.csv")

# ------------------------------------------------------------- farmer_seasons
# Outcomes are DERIVED: true_profit = yield * price - cost (+ noise).
FIRST_NAMES = ["Ramesh", "Suresh", "Ganesh", "Mahesh", "Dinesh", "Rajesh", "Mukesh",
               "Anita", "Sunita", "Kavita", "Geeta", "Seema", "Rekha", "Meena",
               "Arjun", "Vikram", "Sanjay", "Vijay", "Ajay", "Sunil", "Anil",
               "Lakshmi", "Parvati", "Kamala", "Radha", "Shanti", "Devi", "Gauri",
               "Prakash", "Ashok", "Manoj", "Pankaj", "Rakesh", "Bhavani",
               "Nandini", "Priya", "Divya", "Kiran", "Harish", "Gopal"]
LAST_NAMES = ["Patil", "Deshmukh", "Reddy", "Naidu", "Singh", "Yadav", "Sharma",
              "Kumar", "Gowda", "Naik", "Patel", "Chauhan", "Rathod", "Jadhav",
              "Kulkarni", "Pawar", "Meena", "Verma", "Mishra", "Iyer", "Nair"]
FARMER_NAMES = {}
loc_lookup = loc_df.set_index("location_id")
n_farmers = 240
farmer_seasons_rows = []
fid = 1000
for f_idx in range(n_farmers):
    fid += rng.integers(1, 4)
    farmer_name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
    FARMER_NAMES[f"F{fid}"] = farmer_name
    L = LOCATIONS[rng.integers(0, len(LOCATIONS))]
    ctx = loc_ctx[loc_ctx["location_id"] == L["location_id"]].iloc[0]
    suitable_crops = []
    for crop_name, family, soils, trange, rrange, water, season in CROPS:
        crow = {"crop_name": crop_name, "ideal_soil_types": list(soils),
                "ideal_temp_range": trange, "ideal_rainfall_range": rrange}
        if crop_fits_location(crow, ctx["soil_type"], ctx["avg_temp"], ctx["avg_rain"]):
            suitable_crops.append((crop_name, family))
    if not suitable_crops:
        continue
    n_seasons = int(rng.integers(2, 5))
    prev_crop = None
    prev_family = None
    start_year = int(rng.integers(2019, 2021))
    for s in range(n_seasons):
        year = start_year + s
        season_lbl = "Kharif"
        # choose next crop, biased against same family as previous (rotation behavior)
        cands = [c for c in suitable_crops if not prev_family or c[1] != prev_family]
        pool = cands if (cands and rng.random() < 0.8) else suitable_crops
        crop_name, family = pool[rng.integers(0, len(pool))]
        # yield: pull from history for this location/crop/year
        hy = yield_df[(yield_df["location_id"] == L["location_id"]) &
                      (yield_df["crop_name"] == crop_name) &
                      (yield_df["year"].between(year - 1, year + 1))]
        if len(hy):
            y = float(hy.sample(random_state=int(rng.integers(1e9)))["yield_ton_per_acre"].iloc[0])
            y *= rng.uniform(0.9, 1.1)  # individual farmer skill
        else:
            y = YIELD_BASE[crop_name] * rng.uniform(0.7, 1.0)
        # price: modal for that state/crop/month (harvest month approximation)
        pm = market_prices_df[(market_prices_df["crop_name"] == crop_name) &
                              (market_prices_df["state"] == L["state"]) &
                              (market_prices_df["year"] == min(max(year, 2021), 2023))]
        month_map = {"Kharif": 10, "Rabi": 4}
        if len(pm):
            prow = pm[pm["month"] == month_map[season_lbl]]
            price = float(prow["modal_price_rs_per_quintal"].iloc[0]) if len(prow) \
                else float(pm.sample(random_state=int(rng.integers(1e9)))["modal_price_rs_per_quintal"].iloc[0])
        else:
            price = PRICE_BASE[crop_name] * rng.uniform(0.9, 1.05)
        crow_cost = cost_df[(cost_df["crop_name"] == crop_name) & (cost_df["state"] == L["state"])]
        cost = float(crow_cost["total_cost_rs_per_acre"].iloc[0]) if len(crow_cost) \
            else float(cost_df[cost_df["crop_name"] == crop_name]["total_cost_rs_per_acre"].mean())
        quintals = y * 100  # ton -> quintal
        # adverse events (pest/drought/market glut) hit ~30% of seasons
        shock = rng.uniform(0.5, 0.9) if rng.random() < 0.30 else 1.0
        true_profit = quintals * price * shock - cost
        observed = true_profit * rng.uniform(0.95, 1.05)  # reporting noise
        outcome = "profit" if observed > 0 else "loss"
        farmer_seasons_rows.append({
            "farmer_id": f"F{fid}", "farmer_name": FARMER_NAMES[f"F{fid}"],
            "location_id": int(L["location_id"]),
            "season": season_lbl, "year": year,
            "soil_type": ctx["soil_type"],
            "previous_crop": prev_crop if prev_crop else "",
            "outcome": outcome,
            "profit_amount_rs_per_acre": round(observed, 0) if outcome == "profit" else "",
            "next_crop_sown": crop_name})
        prev_crop, prev_family = crop_name, family

farmer_seasons_df = pd.DataFrame(farmer_seasons_rows).sort_values(["farmer_id", "year"])
save(farmer_seasons_df, "farmer_seasons.csv")

farmers_df = pd.DataFrame(
    sorted(FARMER_NAMES.items()), columns=["farmer_id", "farmer_name"])
save(farmers_df, "farmers.csv")

# ------------------------------------------------------------ quality summary
print("\n=== DATA QUALITY SUMMARY ===")
frames = {"soil_data": soil_df, "weather_data": weather_df, "crop_master": crop_master,
          "crop_yield_history": yield_df, "market_prices": market_prices_df,
          "cost_of_cultivation": cost_df, "farmer_seasons": farmer_seasons_df}
for name, df in frames.items():
    miss = int(df.isna().sum().sum())
    print(f"{name:24s} rows={len(df):7d} cols={len(df.columns):2d} missing={miss}")
bal = farmer_seasons_df["outcome"].value_counts(normalize=True)
print(f"\nprofit/loss balance: profit={bal.get('profit', 0):.1%} loss={bal.get('loss', 0):.1%}")
print(f"farmers={farmer_seasons_df['farmer_id'].nunique()}, "
      f"districts={len(loc_df)}, crops={len(crop_master)}")
# msp is nullable by design; everything else must be complete
bad = {name: int(df.isna().sum().sum()) for name, df in frames.items()
       if name != "cost_of_cultivation" and int(df.isna().sum().sum()) > 0}
assert not bad, f"unexpected NaNs: {bad}"
msp_missing = cost_df["msp_rs_per_quintal"].isna().mean()
print(f"\nMSP present for {1 - msp_missing:.0%} of crop-state rows (nullable by design)")
print("OK: all CSVs generated with consistent, derived signals.")
