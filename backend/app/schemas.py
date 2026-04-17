"""API schemas for itinerary requests and responses."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


TravelStyle = Literal[
    "cultural",
    "adventure",
    "food",
    "relaxation",
    "nature",
    "spiritual",
    "shopping",
    "nightlife",
    "photography",
    "family",
]


class ItineraryRequest(BaseModel):
    """User-facing request. Free-form enough to handle odd constraints."""

    destination: str = Field(..., description="Primary destination, e.g. 'Udaipur' or 'Kerala'")
    duration_days: int = Field(..., ge=1, le=30)
    budget_inr: int = Field(..., ge=0, description="Total budget in INR for the whole trip")
    travelers: int = Field(default=2, ge=1, le=20)
    travel_styles: list[TravelStyle] = Field(default_factory=list)
    special_instructions: Optional[str] = Field(
        default=None,
        description="Free-form constraints, e.g. 'pure veg, 2 seniors, no long drives'",
    )
    start_date: Optional[date] = None


class Activity(BaseModel):
    name: str
    description: str
    duration_minutes: int
    cost_inr: int
    location: str
    tips: Optional[str] = None
    source_urls: list[str] = Field(default_factory=list)


class MealSuggestion(BaseModel):
    meal: Literal["breakfast", "lunch", "dinner", "snack"]
    place: str
    cuisine: str
    cost_inr: int
    notes: Optional[str] = None


class DayPlan(BaseModel):
    day_number: int
    theme: str
    morning: list[Activity] = Field(default_factory=list)
    afternoon: list[Activity] = Field(default_factory=list)
    evening: list[Activity] = Field(default_factory=list)
    meals: list[MealSuggestion] = Field(default_factory=list)
    daily_cost_estimate_inr: int


class Accommodation(BaseModel):
    name: str
    area: str
    type: Literal["hotel", "homestay", "hostel", "resort", "guesthouse", "airbnb"]
    price_per_night_inr: int
    rating: Optional[float] = None
    why: str


class CostBreakdown(BaseModel):
    accommodation_inr: int
    food_inr: int
    activities_inr: int
    transport_inr: int
    miscellaneous_inr: int
    total_inr: int
    fits_budget: bool
    notes: Optional[str] = None


class Itinerary(BaseModel):
    id: Optional[str] = None
    request: ItineraryRequest
    summary: str
    best_time_to_visit: str
    getting_there: str
    local_transportation: str
    days: list[DayPlan]
    accommodation_suggestions: list[Accommodation]
    cost_breakdown: CostBreakdown
    packing_list: list[str]
    local_tips: list[str]
    cautions: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    created_at: Optional[datetime] = None


class ItineraryListItem(BaseModel):
    id: str
    destination: str
    duration_days: int
    summary: str
    created_at: datetime
