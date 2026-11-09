"""Stage 2c: profit ranking - combines Stage 1 shortlist with yield, price,
cost predictions, the crop-rotation rule, and farmer personalization."""
import os
import sys
import joblib
import numpy as np
import pandas as pd
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from features import load_data, _location_context  # noqa: E402

try:
    from backend.config import settings
    MODELS_DIR = str(settings.MODEL_DIR)
except Exception:
    MODELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models")

ROTATION_PENALTY = 0.85      # multiply profit when repeating a crop family
PERSONALIZATION_BONUS = 0.05 # +/-5% for crops this farmer profited/lost before
TOP_K_SHORTLIST = 8


class Ranker:
    def __init__(self, model_dir=None, data_dir=None):
        self.model_dir = str(model_dir or MODELS_DIR)
        self.data = load_data(data_dir=data_dir)
        self.ctx = _location_context(self.data)
        self.master = self.data["crop_master"]
        self.suitability = joblib.load(os.path.join(self.model_dir, "suitability.pkl"))
        self.yield_model = joblib.load(os.path.join(self.model_dir, "yield.pkl"))
        self.price_model = joblib.load(os.path.join(self.model_dir, "price.pkl"))

    def _location_row(self, district):
        row = self.ctx[self.ctx["district"] == district]
        if row.empty:
            raise ValueError(f"unknown district: {district}")
        return row.iloc[0]

    def _harvest_month_year(self):
        """Next upcoming harvest window from 'today'."""
        now = datetime.now()
        if now.month <= 10:
            return 10, now.year          # Kharif harvest ~ Oct
        return 4, now.year + 1           # Rabi harvest ~ Apr

    def _price_lags(self, crop_name, state, month, year):
        mp = self.data["market_prices"]
        s = mp[(mp["crop_name"] == crop_name) & (mp["state"] == state)]
        hist = s.sort_values(["year", "month"])
        series = list(hist["modal_price_rs_per_quintal"])
        lags = [series[-1], series[-2], series[-3]] if len(series) >= 3 \
            else [s["modal_price_rs_per_quintal"].mean()] * 3
        mom = lags[0] / max(lags[1], 1) - 1
        return {"crop_name": crop_name, "state": state,
                "lag1": lags[0], "lag2": lags[1], "lag3": lags[2],
                "mom_change": mom,
                "month_sin": np.sin(2 * np.pi * month / 12),
                "month_cos": np.cos(2 * np.pi * month / 12),
                "year_idx": year - int(mp["year"].min())}

    @staticmethod
    def _reason(crop, suit_p, rain_ok, rotation_penalized, price_trend, pers):
        bits = []
        bits.append(f"{int(round(suit_p * 100))}% agro-climatic match")
        if rain_ok:
            bits.append("season rainfall is favorable")
        if not rotation_penalized:
            bits.append("rotates away from last season's crop family")
        else:
            bits.append("repeats last season's family (yield-risk penalty applied)")
        if price_trend >= 0.005:
            bits.append("market price trending up")
        elif price_trend <= -0.005:
            bits.append("market price trending down")
        if pers > 0:
            bits.append("you previously profited from this crop")
        elif pers < 0:
            bits.append("you previously lost money on this crop")
        return "; ".join(bits).capitalize() + "."

    def recommend(self, soil_type, state, district, previous_crop,
                  previous_outcome="profit", previous_profit_amount=None,
                  farmer_id=None, top_n=3):
        L = self._location_row(district)
        prev_family = self.master.loc[self.master["crop_name"] == previous_crop,
                                      "crop_family"]
        prev_family = prev_family.iat[0] if len(prev_family) else None

        # ---- Stage 1: score all 20 crops, keep top-k shortlist
        from train_suitability import NUM_FEATURES, CAT_FEATURES
        rows = []
        for _, c in self.master.iterrows():
            water_ordinal = {"Low": 0, "Medium": 1, "High": 2, "Very High": 3}[c["water_requirement"]]
            rows.append({**{f: L[f] for f in NUM_FEATURES if f in L.index},
                         "n_ideal_soils": len(c["ideal_soil_types"]),
                         "temp_mid": (c["ideal_temp_range"][0] + c["ideal_temp_range"][1]) / 2,
                         "rain_lo": c["ideal_rainfall_range"][0],
                         "rain_hi": c["ideal_rainfall_range"][1],
                         "water_ordinal": water_ordinal,
                         "soil_type": L["soil_type"], "season": c["season"],
                         "crop_name": c["crop_name"]})
        cand = pd.DataFrame(rows)
        prob = self.suitability.predict_proba(cand[NUM_FEATURES + CAT_FEATURES])[:, 1]
        cand["suit_prob"] = prob
        shortlist = cand.nlargest(TOP_K_SHORTLIST, "suit_prob")

        # ---- personalization signal from farmer's own logged history
        pers_bonus = {}
        fs = self.data["farmer_seasons"]
        if farmer_id:
            mine = fs[fs["farmer_id"] == str(farmer_id)]
            for _, r in mine.iterrows():
                sign = PERSONALIZATION_BONUS if r["outcome"] == "profit" else -PERSONALIZATION_BONUS
                pers_bonus[r["next_crop_sown"]] = pers_bonus.get(r["next_crop_sown"], 0) + sign

        month, year = self._harvest_month_year()
        results = []
        for _, c in shortlist.iterrows():
            crop = c["crop_name"]
            # ---- Stage 2a: yield
            yfeat = {f: c[f] for f in ["N", "P", "K", "ph", "organic_carbon",
                                       "avg_temp_c", "total_rainfall_mm",
                                       "kharif_rain", "rabi_rain"]}
            from train_yield import CAT as YCAT, NUM as YNUM
            yrow = {**yfeat, "area_acre": 50.0, "year_idx": 7,
                    "crop_name": crop, "soil_type": L["soil_type"],
                    "season": c["season"], "water_requirement":
                    self.master.loc[self.master["crop_name"] == crop,
                                    "water_requirement"].iat[0]}
            pred_yield = float(self.yield_model.predict(pd.DataFrame([yrow])[YNUM + YCAT])[0])
            pred_yield = max(pred_yield, 0.01)

            # ---- Stage 2b: price at upcoming harvest month
            prow = self._price_lags(crop, state, month, year)
            from train_price import CAT as PCAT, NUM as PNUM
            pred_price = float(self.price_model.predict(pd.DataFrame([prow])[PNUM + PCAT])[0])

            # ---- cost lookup (fallback: state mean -> crop mean)
            cost_tbl = self.data["cost_of_cultivation"]
            cc = cost_tbl[(cost_tbl["crop_name"] == crop) &
                          (cost_tbl["state"] == state)]["total_cost_rs_per_acre"]
            cost = float(cc.iat[0]) if len(cc) else float(
                cost_tbl[cost_tbl["crop_name"] == crop]["total_cost_rs_per_acre"].mean())

            # ---- profit + rotation rule + personalization
            raw_profit = pred_yield * 100 * pred_price - cost
            rotation_penalized = prev_family is not None and \
                self.master.loc[self.master["crop_name"] == crop, "crop_family"].iat[0] == prev_family
            adj = raw_profit * (ROTATION_PENALTY if rotation_penalized else 1.0)
            pb = pers_bonus.get(crop, 0.0)
            adj *= (1 + pb)
            # prior-season loss on the SAME family adds caution beyond rotation penalty
            if previous_outcome == "loss" and rotation_penalized:
                adj *= 0.95

            trend = prow["mom_change"]
            results.append({
                "crop_name": crop,
                "suitability_probability": round(float(c["suit_prob"]), 3),
                "predicted_yield_ton_per_acre": round(pred_yield, 3),
                "predicted_price_rs_per_quintal": round(pred_price, 0),
                "cost_of_cultivation_rs_per_acre": round(cost, 0),
                "raw_profit_rs_per_acre": round(raw_profit, 0),
                "rotation_penalized": bool(rotation_penalized),
                "personalization_adjustment": round(pb, 3),
                "adjusted_profit_rs_per_acre": round(adj, 0),
                "rain_ok": bool(L["total_rainfall_mm"] >= 400),
                "price_trend": float(trend),
            })

        results.sort(key=lambda r: r["adjusted_profit_rs_per_acre"], reverse=True)
        out = []
        for i, r in enumerate(results[:top_n], start=1):
            out.append({
                "rank": i,
                "crop_name": r["crop_name"],
                "predicted_yield_ton_per_acre": r["predicted_yield_ton_per_acre"],
                "predicted_price_rs_per_quintal": r["predicted_price_rs_per_quintal"],
                "cost_of_cultivation_rs_per_acre": r["cost_of_cultivation_rs_per_acre"],
                "predicted_profit_rs_per_acre": r["adjusted_profit_rs_per_acre"],
                "reason": self._reason(r["crop_name"], r["suitability_probability"],
                                       r["rain_ok"], r["rotation_penalized"],
                                       r["price_trend"], r["personalization_adjustment"]),
                "_debug": {k: v for k, v in r.items() if k not in ("reason",)}})
        return out


if __name__ == "__main__":
    rk = Ranker()
    samples = [
        {"farmer_id": "F1023", "soil_type": "Black", "state": "Maharashtra",
         "district": "Nagpur", "previous_crop": "Cotton", "previous_outcome": "loss"},
        {"soil_type": "Alluvial", "state": "Punjab", "district": "Ludhiana",
         "previous_crop": "Rice", "previous_outcome": "profit"},
        {"soil_type": "Red", "state": "Karnataka", "district": "Belagavi",
         "previous_crop": "Groundnut", "previous_outcome": "profit"},
    ]
    for s in samples:
        print(f"\n=== {s.get('district')} | prev={s['previous_crop']} "
              f"({s['previous_outcome']}) ===")
        recs = rk.recommend(**s)
        for r in recs:
            print(f"  #{r['rank']} {r['crop_name']:12s} profit=Rs "
                  f"{r['predicted_profit_rs_per_acre']:>9,.0f}  "
                  f"y={r['predicted_yield_ton_per_acre']:.2f}t  "
                  f"p=Rs {r['predicted_price_rs_per_quintal']:.0f}/q  "
                  f"cost=Rs {r['cost_of_cultivation_rs_per_acre']:,.0f}")
            print(f"      {r['reason']}")
