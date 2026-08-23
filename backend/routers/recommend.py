from fastapi import APIRouter, HTTPException
from backend.schemas import RecommendRequest, RecommendResponse, Recommendation
from backend.inference import get_ranker
from datetime import datetime, timezone

router = APIRouter()


@router.post("/api/recommend", response_model=RecommendResponse)
def recommend(req: RecommendRequest):
    ranker = get_ranker()
    try:
        recs = ranker.recommend(
            soil_type=req.soil_type, state=req.state, district=req.district,
            previous_crop=req.previous_crop,
            previous_outcome=req.previous_outcome,
            previous_profit_amount=req.previous_profit_amount,
            farmer_id=req.farmer_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return RecommendResponse(
        recommendations=[Recommendation(**{k: v for k, v in r.items()
                                           if not k.startswith("_")})
                         for r in recs],
        generated_at=datetime.now(timezone.utc).isoformat())
