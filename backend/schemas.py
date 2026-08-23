"""Pydantic request/response models."""
from typing import Optional, List
from pydantic import BaseModel, Field


class RecommendRequest(BaseModel):
    farmer_id: str = Field(..., examples=["F1023"])
    soil_type: str
    state: str
    district: str
    previous_crop: str
    previous_outcome: str = Field("profit", pattern="^(profit|loss)$")
    previous_profit_amount: Optional[float] = None


class Recommendation(BaseModel):
    rank: int
    crop_name: str
    predicted_yield_ton_per_acre: float
    predicted_price_rs_per_quintal: float
    cost_of_cultivation_rs_per_acre: float
    predicted_profit_rs_per_acre: float
    reason: str


class RecommendResponse(BaseModel):
    recommendations: List[Recommendation]
    generated_at: str


class SeasonLogIn(BaseModel):
    farmer_id: str
    farmer_name: Optional[str] = None
    location_id: Optional[int] = None
    season: str = Field("Kharif", pattern="^(Kharif|Rabi|Annual)$")
    year: int
    soil_type: str
    previous_crop: str = ""
    outcome: str = Field(..., pattern="^(profit|loss)$")
    profit_amount_rs_per_acre: Optional[float] = None
    next_crop_sown: str


class SeasonLogOut(SeasonLogIn):
    id: int

    class Config:
        from_attributes = True
