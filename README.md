# AI Crop Recommendation System

Helps a farmer decide the most **profitable** crop to sow next season. Given soil
type, location (state + district), the previous crop and its outcome, the system
returns a **ranked Top-3 crop list** with predicted yield, market price, cost of
cultivation, net profit per acre and a plain-language reason.

> **Note:** all soil/weather/market data in this repo is **synthetically
> generated for demo purposes** - it is not real government data. Swap in real
> sources for production (see [Real data sources](#real-data-sources-for-production)).

## Quick start

```bash
pip install -r requirements.txt

python synthetic_data_generator/generate.py   # 1. generate CSVs into data/
python ml/train_suitability.py                # 2. train Stage 1
python ml/train_yield.py                      # 3. train yield model
python ml/train_price.py                      # 4. train price model

run.bat                                       # Windows: start server + open UI
# or manually:
python -m uvicorn backend.main:app --port 8000
```

Then open **http://127.0.0.1:8000** in your browser.
(Opening `frontend/standalone/index.html` directly from disk will NOT work -
the frontend must be served by the backend so it can call `/api/*`.)

## Architecture

```
+----------------------------------------------------------------------+
| 1. DATA LAYER                                                        |
|    synthetic_data_generator/generate.py -> data/*.csv                |
|    (soil, weather, crop_master, yield history, market prices,        |
|     cost of cultivation, farmer seasons)                             |
+----------------------------------------------------------------------+
| 2. FEATURE & TRAINING LAYER                                          |
|    ml/features.py           joins raw tables -> model-ready features |
|    ml/train_suitability.py  Stage 1  (RandomForest, binary suitability|
|                                      scored per candidate crop)      |
|    ml/train_yield.py        Stage 2a (GBR, yield t/acre)             |
|    ml/train_price.py        Stage 2b (GBR on lag/seasonal features)  |
|    ml/rank_profit.py        Stage 2c profit ranking + rotation rule  |
|                             + personalization                        |
|    models/                  *.pkl artifacts + metadata.json          |
+----------------------------------------------------------------------+
| 3. BACKEND / API LAYER (FastAPI)                                     |
|    backend/main.py            app entrypoint, serves frontend at "/" |
|    backend/routers/recommend.py  POST /api/recommend                 |
|    backend/routers/history.py    GET/POST /api/history               |
|    backend/routers/meta.py       GET /api/meta                       |
|    backend/db.py              SQLite via SQLAlchemy (Postgres-ready) |
|    backend/inference.py       loads models once at startup           |
+----------------------------------------------------------------------+
| 4. FRONTEND LAYER                                                    |
|    frontend/standalone/index.html                                    |
|    Single-file React + Tailwind app served by FastAPI (no Node build)|
+----------------------------------------------------------------------+
```

### Request flow

`form submit -> POST /api/recommend -> look up region soil/weather/market
features -> Stage 1 scores all 20 crops for agro-climatic suitability,
shortlists top-8 -> Stage 2 predicts yield + price per candidate ->
profit = yield x price - cost -> rotation rule (same crop family as
previous_crop => profit x 0.85) -> personalization (+/-5% based on the
farmer's own logged profit/loss with that crop) -> sort by adjusted
profit -> Top-3 JSON -> ranked cards in the browser.`

### Design note on Stage 1

A multi-class `crop_name` classifier is unlearnable here because every
candidate crop at one location shares identical location-only features.
Stage 1 is therefore a **binary suitability classifier** evaluated once per
(location x candidate-crop) pair, using crop attributes as features; the
top-k probabilities form the shortlist. This is recorded in
`models/metadata.json`.

## API examples

```bash
curl -X POST http://127.0.0.1:8000/api/recommend ^
  -H "Content-Type: application/json" ^
  -d "{\"farmer_id\":\"F1023\",\"soil_type\":\"Black\",\"state\":\"Maharashtra\",
       \"district\":\"Nagpur\",\"previous_crop\":\"Cotton\",
       \"previous_outcome\":\"loss\",\"previous_profit_amount\":-3200}"

curl http://127.0.0.1:8000/api/history/F1001
curl http://127.0.0.1:8000/api/meta
```

Interactive docs: http://127.0.0.1:8000/docs

## Regenerating data / retraining models

- Data: `python synthetic_data_generator/generate.py` (fixed seed = 42;
  prints row counts, missing values and profit/loss balance ~49%/51%).
- Models: run the three training scripts; each prints accuracy/F1 or RMSE/MAE
  and updates `models/metadata.json`.
- Delete `backend/app.db` to re-seed farmer history from CSV on next startup.

## Project layout

```
crop-recommendation-system/
|-- README.md
|-- requirements.txt
|-- run.bat                     one-click launcher (Windows)
|-- synthetic_data_generator/generate.py
|-- data/                       generated CSVs
|-- ml/                         features + training + ranking pipeline
|-- models/                     trained artifacts + metadata.json
|-- backend/                    FastAPI app (routers, db, inference)
`-- frontend/standalone/        single-file React + Tailwind UI
```

## Real data sources (for production)

- Soil: Soil Health Card Portal (soilhealth.dac.gov.in), ISRO Bhuvan soil API
- Weather: IMD, Open-Meteo, OpenWeatherMap
- Market prices: Agmarknet / data.gov.in mandi price API
- Cost of cultivation / MSP: DES (eands.dacnet.nic.in)
- Baseline soil-to-crop training set: Kaggle "Crop Recommendation Dataset" (ICFA)

Replace the corresponding loaders in `ml/features.py` and the generator with
these feeds; the two-stage pipeline itself stays unchanged.

## Assumptions

- Synthetic yields/prices/costs are internally consistent (costs are derived
  from realistic yield x price with a variable margin factor) so models learn
  real signal rather than noise.
- Kharif harvest month approximated as October, Rabi as April, for price
  forecasting targets.
- Personalization uses only the farmer's own logged seasons; new logs written
  via POST /api/history feed back into future recommendations.
