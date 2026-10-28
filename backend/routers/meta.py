from fastapi import APIRouter
import pandas as pd
from backend.config import settings
from backend.inference import get_ranker

router = APIRouter()


@router.get("/api/farmers")
def farmers():
    """All known farmers with names - powers the name autocomplete."""
    path = settings.DATA_DIR / "farmers.csv"
    df = pd.read_csv(path)
    return df.to_dict(orient="records")


@router.get("/api/meta")
def meta():
    ranker = get_ranker()
    locs = ranker.data["soil_data"][["state", "district", "soil_type"]]
    states = {}
    for _, r in locs.iterrows():
        states.setdefault(r["state"], []).append(
            {"district": r["district"], "soil_type": r["soil_type"]})
    master = ranker.data["crop_master"]
    crops = [{"crop_name": r["crop_name"], "crop_family": r["crop_family"],
              "season": r["season"]} for _, r in master.iterrows()]
    return {"soil_types": sorted(locs["soil_type"].unique().tolist()),
            "states": states, "crops": crops}
