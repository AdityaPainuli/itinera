"""Itinerary generation agent.

Three-phase pipeline:

  1. **Draft** — one Claude call with server-side `web_search` enabled.
     Claude researches and emits a fenced JSON block matching `_SCHEMA_HINT`.
  2. **Critique** — pure-Python pass in `critique.py`. Silently reorders
     activities by proximity, stamps verified budget sums, and returns a
     list of issues that need the model to fix.
  3. **Repair** — if critique found issues, a second Claude call (no tools)
     is given the draft + the issues and asked to return a corrected JSON.
     The Python critique runs again on the repaired draft so the UI-visible
     `quality_checks` reflects the *final* state.

Each phase is independently skippable: if the draft is clean, repair never
runs; if repair fails, we fall back to the draft.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from anthropic import AsyncAnthropic

from app.agents.critique import critique
from app.agents.prompts import SYSTEM_PROMPT, build_repair_message, build_user_message
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
      "base_area": "neighborhood/area this day is anchored in",
      "morning": [ {"name": "...", "description": "...", "duration_minutes": 120,
                    "cost_inr": 500, "location": "full address or landmark",
                    "neighborhood": "Fort Kochi", "lat": 9.9658, "lng": 76.2421,
                    "tips": "...", "source_urls": ["..."]} ],
      "afternoon": [ ...same shape... ],
      "evening": [ ...same shape... ],
      "meals": [ {"meal": "lunch", "place": "...", "cuisine": "...", "cost_inr": 400, "notes": "..."} ],
      "daily_cost_estimate_inr": 0,
      "route_notes": "one-line note on the day's geography, e.g. 'All stops within 3km in Fort Kochi'"
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
        draft = await self._draft(request)

        issues = critique(draft, request)

        if issues:
            log.info("Draft critique found %d issue(s); running repair pass.", len(issues))
            try:
                repaired = await self._repair(request, draft, issues)
                residual = critique(repaired, request)
                repaired.quality_checks = _summarize_checks(issues, residual)
                return repaired
            except (ValueError, json.JSONDecodeError) as exc:
                # Repair failed — ship the draft with the original issues annotated
                # rather than 500-ing the user. The UI surfaces the list.
                log.warning("Repair pass failed: %s. Falling back to draft.", exc)
                draft.quality_checks = _summarize_checks(issues, issues)
                return draft

        draft.quality_checks = ["All automated checks passed."]
        return draft

    async def _draft(self, request: ItineraryRequest) -> Itinerary:
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
        data["request"] = request.model_dump(mode="json")
        return Itinerary.model_validate(data)

    async def _repair(
        self,
        request: ItineraryRequest,
        draft: Itinerary,
        issues: list[str],
    ) -> Itinerary:
        """Second Claude call, no tools — cheap, focused, just fix the issues."""
        draft_payload = draft.model_dump(mode="json")
        # Strip computed_* — those are our bookkeeping, not the model's.
        cb = draft_payload.get("cost_breakdown", {})
        for k in ("computed_total_inr", "computed_activities_inr", "computed_food_inr"):
            cb.pop(k, None)
        draft_payload.pop("quality_checks", None)

        user_msg = build_repair_message(
            draft_json=json.dumps(draft_payload, indent=2, ensure_ascii=False),
            issues=issues,
            schema_json=_SCHEMA_HINT,
        )

        response = await self.client.messages.create(
            model=settings.anthropic_model,
            max_tokens=settings.max_tokens,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )

        text = _extract_text(response.content)
        data = _parse_itinerary_json(text)
        data["request"] = request.model_dump(mode="json")
        return Itinerary.model_validate(data)


def _summarize_checks(original: list[str], residual: list[str]) -> list[str]:
    """Produce a UI-friendly quality_checks list.

    - If repair cleared everything: one 'auto-fixed N issue(s)' line.
    - If some issues remain: the residual list, annotated.
    """
    if not residual:
        return [f"Auto-fixed {len(original)} issue(s) during critique pass."]
    return [f"Unresolved after repair: {i}" for i in residual]


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
