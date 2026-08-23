"""EDA visualizations of the synthetic dataset.

Generates PNG charts into reports/ - these are embedded in README.md so the
data can be understood at a glance. Run:  python ml/visualize_data.py
Requires: matplotlib, seaborn
"""
import os
import sys

import matplotlib
matplotlib.use("Agg")  # headless save
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from features import load_data  # noqa: E402
from features import build_yield_dataset  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
REPORTS = os.path.join(HERE, "..", "reports")
os.makedirs(REPORTS, exist_ok=True)

sns.set_theme(style="whitegrid", palette="viridis")


def save(fig, name):
    path = os.path.join(REPORTS, name)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    print(f"  wrote reports/{name}")


def main():
    data = load_data()

    # 1. profit/loss balance + outcomes by crop family --------------------
    fs = data["farmer_seasons"]
    master = data["crop_master"]
    fs2 = fs.merge(master[["crop_name", "crop_family"]],
                   left_on="next_crop_sown", right_on="crop_name", how="left")
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    counts = fs["outcome"].value_counts()
    axes[0].pie(counts.values, labels=counts.index, autopct="%1.1f%%",
                colors=["#66c2a5", "#fc8d62"], startangle=90,
                wedgeprops={"edgecolor": "white"})
    axes[0].set_title("Farmer season outcome balance")
    order = (fs2.groupby("crop_family")["outcome"]
             .apply(lambda s: (s == "profit").mean())
             .sort_values())
    sns.barplot(x=order.index, y=order.values, ax=axes[1], hue=order.index,
                legend=False)
    axes[1].set_ylabel("share of seasons ending in profit")
    axes[1].tick_params(axis="x", rotation=45)
    axes[1].set_title("Profit rate by crop family")
    save(fig, "01_outcomes.png")

    # 2. yield distribution per crop --------------------------------------
    yld = build_yield_dataset(data)
    med = yld.groupby("crop_name")["yield_ton_per_acre"].median()
    top_crops = med.sort_values(ascending=False).head(10).index.tolist()
    sub = yld[yld["crop_name"].isin(top_crops)]
    fig, ax = plt.subplots(figsize=(11, 5))
    sns.boxplot(data=sub, x="crop_name", y="yield_ton_per_acre",
                hue="crop_name", legend=False, ax=ax)
    ax.set_yscale("log")
    ax.set_title("Yield distribution - top 10 crops by median yield (log scale)")
    ax.tick_params(axis="x", rotation=40)
    save(fig, "02_yield_distribution.png")

    # 3. monthly climate normals for selected districts -------------------
    wx = data["weather_data"].merge(
        data["soil_data"][["location_id", "district"]], on="location_id")
    pick = ["Ludhiana", "Nagpur", "Belagavi", "Thrissur"]
    sub = wx[wx["district"].isin(pick)]
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
    sns.lineplot(data=sub, x="month", y="avg_rainfall_mm", hue="district",
                 marker="o", ax=axes[0])
    axes[0].set_title("Monthly rainfall (monsoon visible Jun-Sep)")
    axes[0].set_xticks(range(1, 13))
    sns.lineplot(data=sub, x="month", y="avg_temp_c", hue="district",
                 marker="o", ax=axes[1])
    axes[1].set_title("Monthly average temperature")
    axes[1].set_xticks(range(1, 13))
    save(fig, "03_climate_normals.png")

    # 4. market price trends ----------------------------------------------
    mp = data["market_prices"]
    focus = ["Cotton", "Soybean", "Onion", "Tomato"]
    sub = mp[(mp["state"] == "Maharashtra") & (mp["crop_name"].isin(focus))]
    sub = sub.assign(date=pd.to_datetime(
        dict(year=sub["year"], month=sub["month"], day=1)))
    fig, ax = plt.subplots(figsize=(11, 4.5))
    sns.lineplot(data=sub, x="date", y="modal_price_rs_per_quintal",
                 hue="crop_name", marker="o", ax=ax)
    ax.set_title("Modal mandi price trends - Maharashtra (synthetic)")
    ax.set_ylabel("Rs per quintal")
    save(fig, "04_price_trends.png")

    # 5. economics: revenue potential vs cost of cultivation --------------
    cost = data["cost_of_cultivation"]
    q = {"Rice": 27, "Wheat": 29, "Maize": 31, "Barley": 24, "Cotton": 9,
         "Jute": 21, "Sugarcane": 1350, "Soybean": 15, "Groundnut": 17,
         "Mustard": 14, "Sunflower": 13, "Chickpea": 11, "Pigeon Pea": 8}
    c = cost[cost["crop_name"].isin(q)].copy()
    p22 = mp[mp["year"] == 2022].groupby("crop_name")[
        "modal_price_rs_per_quintal"].mean()
    c = c[c["state"] == "Maharashtra"]
    c["expected_revenue"] = c["crop_name"].map(q) * c["crop_name"].map(p22)
    c = c.sort_values("expected_revenue", ascending=False)
    fig, ax = plt.subplots(figsize=(11, 5))
    x = np.arange(len(c))
    ax.bar(x - 0.2, c["expected_revenue"], width=0.4,
           label="expected revenue Rs/acre", color="#66c2a5")
    ax.bar(x + 0.2, c["total_cost_rs_per_acre"], width=0.4,
           label="total cost Rs/acre", color="#fc8d62")
    ax.set_xticks(x)
    ax.set_xticklabels(c["crop_name"], rotation=45, ha="right")
    ax.set_title("Expected revenue vs cost of cultivation - Maharashtra")
    ax.legend()
    save(fig, "05_economics.png")

    # 6. correlation heatmap of soil / climate vs yield -------------------
    num = yld[["N", "P", "K", "ph", "organic_carbon", "avg_temp_c",
               "total_rainfall_mm", "area_acre", "yield_ton_per_acre"]]
    corr = num.corr()
    fig, ax = plt.subplots(figsize=(8, 6.5))
    sns.heatmap(corr, annot=True, fmt=".2f", cmap="crest", ax=ax,
                square=True, cbar_kws={"shrink": 0.8})
    ax.set_title("Feature correlations (soil, climate, yield)")
    save(fig, "06_correlations.png")

    print("\nAll charts saved to reports/. Embed them in README or open directly.")


if __name__ == "__main__":
    main()
