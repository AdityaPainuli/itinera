"""Itinerary generation agent.

Uses Anthropic's `web_search_20250305` server-side tool so Claude does the web
research for us, then falls into structured synthesis in one turn.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from anthropic import AsyncAnthropic

from app.agents.prompts import SYSTEM_PROMPT, build_user_message
from app.config import settings
from app.schemas import Itinerary, ItineraryRequest

log = logging.getLogger(__name__)

_JSON_BLOCK_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)

# Abbreviated schema — the model sees the Pydantic shape below.
_SCHEMA_HINT = """{
  "summary": "string — 2-3 sentence overview with the chosen route",
  "best_time_to_visit": "string",
  "getting_there": "string — flights/trains/roads with approx cost",
  "local_transportation": "string — taxis, autos, bus, rental scooter, etc.",
  "days": [
    {
      "day_number": 1,
      "theme": "string",
      "morning": [ {"name": "...", "description": "...", "duration_minutes": 120,
                    "cost_inr": 500, "location": "...", "tips": "...", "source_urls": ["..."]} ],
      "afternoon": [ ...same shape... ],
      "evening": [ ...same shape... ],
      "meals": [ {"meal": "lunch", "place": "...", "cuisine": "...", "cost_inr": 400, "notes": "..."} ],
      "daily_cost_estimate_inr": 0
    }
  ],
  "accommodation_suggestions": [
    {"name": "...", "area": "...", "type": "hotel|homestay|hostel|resort|guesthouse|airbnb",
     "price_per_night_inr": 0, "rating": 4.3, "why": "..."}
  ],
  "cost_breakdown": {
    "accommodation_inr": 0, "food_inr": 0, "activities_inr": 0,
    "transport_inr": 0, "miscellaneous_inr": 0, "total_inr": 0,
    "fits_budget": true, "notes": "optional"
  },
  "packing_list": ["..."],
  "local_tips": ["..."],
  "cautions": ["..."],
  "sources": ["https://..."]
}"""


class ItineraryAgent:
    def __init__(self, client: AsyncAnthropic | None = None):
        self.client = client or AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def generate(self, request: ItineraryRequest) -> Itinerary:
        user_msg = build_user_message(
            request_json=request.model_dump_json(indent=2),
            schema_json=_SCHEMA_HINT,
            max_searches=settings.max_web_searches,
        )

        response = await self.client.messages.create(
            model=settings.anthropic_model,
            max_tokens=settings.max_tokens,
            system=SYSTEM_PROMPT,
            tools=[
                {
                    "type": "web_search_20250305",
                    "name": "web_search",
                    "max_uses": settings.max_web_searches,
                }
            ],
            messages=[{"role": "user", "content": user_msg}],
        )

        text = _extract_text(response.content)
        data = _parse_itinerary_json(text)

        # Attach the original request so the stored record is self-contained.
        data["request"] = request.model_dump(mode="json")
        return Itinerary.model_validate(data)


def _extract_text(content_blocks: list[Any]) -> str:
    parts: list[str] = []
    for block in content_blocks:
        block_type = getattr(block, "type", None)
        if block_type == "text":
            parts.append(getattr(block, "text", "") or "")
    return "\n".join(parts)


def _parse_itinerary_json(text: str) -> dict[str, Any]:
    """Pull the JSON object out of a fenced code block, fall back to raw text."""
    match = _JSON_BLOCK_RE.search(text)
    raw = match.group(1) if match else text.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        log.error("Failed to parse itinerary JSON. Raw text:\n%s", text)
        raise ValueError(f"Agent did not return valid JSON: {exc}") from exc
