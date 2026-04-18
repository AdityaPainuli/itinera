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
from typing import Any, AsyncIterator

from anthropic import AsyncAnthropic

from app.agents.critique import critique
from app.agents.prompts import (
    REPAIR_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    build_repair_message,
    build_user_message,
)
from app.config import settings
from app.schemas import Itinerary, ItineraryRequest

# Discrete event kinds the UI reacts to. Keep in sync with the frontend
# ProgressPanel — and remember: these are the whole public contract between
# the agent stream and the client, so don't rename without a coordinated change.
EventKind = str  # "researching" | "search" | "synthesizing" | "validating" |
#                 "repairing" | "done" | "error"

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
        """Non-streaming entrypoint — drains the stream and returns the final itinerary.

        Preserved so the JSON route and any non-SSE caller still work.
        """
        final: Itinerary | None = None
        async for event in self.generate_stream(request):
            kind = event.get("kind")
            if kind == "done":
                final = event["itinerary"]
            elif kind == "error":
                raise ValueError(event.get("message", "agent failed"))
        if final is None:
            raise ValueError("agent stream ended without producing an itinerary")
        return final

    async def generate_stream(
        self, request: ItineraryRequest
    ) -> AsyncIterator[dict[str, Any]]:
        """Run the full pipeline, yielding stage events as each phase progresses.

        Events are dicts with a `kind` key. Shapes:
          - {"kind": "researching"}
          - {"kind": "search", "query": "...", "status": "running"|"done"}
          - {"kind": "synthesizing"}
          - {"kind": "validating", "issues": N}
          - {"kind": "repairing", "issues": N}
          - {"kind": "done", "itinerary": Itinerary}
          - {"kind": "error", "message": "..."}
        """
        try:
            yield {"kind": "researching"}

            draft: Itinerary | None = None
            async for ev in self._draft_stream(request):
                if ev.get("kind") == "draft":
                    draft = ev["itinerary"]
                else:
                    yield ev
            assert draft is not None, "_draft_stream must emit exactly one draft event"

            issues = critique(draft, request)
            yield {"kind": "validating", "issues": len(issues)}

            if not issues:
                draft.quality_checks = ["All automated checks passed."]
                yield {"kind": "done", "itinerary": draft}
                return

            log.info("Draft critique found %d issue(s); running repair pass.", len(issues))
            yield {"kind": "repairing", "issues": len(issues)}
            try:
                repaired = await self._repair(request, draft, issues)
                residual = critique(repaired, request)
                repaired.quality_checks = _summarize_checks(issues, residual)
                yield {"kind": "done", "itinerary": repaired}
            except (ValueError, json.JSONDecodeError) as exc:
                log.warning("Repair pass failed: %s. Falling back to draft.", exc)
                draft.quality_checks = _summarize_checks(issues, issues)
                yield {"kind": "done", "itinerary": draft}
        except Exception as exc:  # noqa: BLE001 — SSE boundary, anything becomes a client event
            log.exception("Agent stream failed")
            yield {"kind": "error", "message": str(exc) or exc.__class__.__name__}

    async def _draft_stream(
        self, request: ItineraryRequest
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream the draft call. Yields `search`/`synthesizing` progress events
        and, at the end, a single `draft` event carrying the parsed `Itinerary`.
        """
        user_msg = build_user_message(
            request_json=request.model_dump_json(indent=2),
            schema_json=_SCHEMA_HINT,
            max_searches=settings.max_web_searches,
        )

        # Accumulate input_json deltas per content-block index so we can emit
        # the search `query` once the tool-use block closes.
        pending_tool_input: dict[int, list[str]] = {}
        search_announced = False
        synthesizing_announced = False

        async with self.client.messages.stream(
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
        ) as stream:
            async for event in stream:
                etype = getattr(event, "type", None)
                if etype == "content_block_start":
                    block = getattr(event, "content_block", None)
                    btype = getattr(block, "type", None)
                    if btype == "server_tool_use" and getattr(block, "name", "") == "web_search":
                        pending_tool_input[event.index] = []
                        if not search_announced:
                            # First search starting — signal the UI so it can
                            # transition out of the generic "researching" state.
                            search_announced = True
                elif etype == "content_block_delta":
                    delta = getattr(event, "delta", None)
                    dtype = getattr(delta, "type", None)
                    if dtype == "input_json_delta" and event.index in pending_tool_input:
                        pending_tool_input[event.index].append(
                            getattr(delta, "partial_json", "") or ""
                        )
                elif etype == "content_block_stop":
                    if event.index in pending_tool_input:
                        raw = "".join(pending_tool_input.pop(event.index))
                        query = _safe_json_get(raw, "query")
                        if query:
                            yield {"kind": "search", "query": query, "status": "done"}
                elif etype == "text":
                    # First text event after tool use means synthesis has started.
                    if not synthesizing_announced:
                        synthesizing_announced = True
                        yield {"kind": "synthesizing"}

            final_message = await stream.get_final_message()

        text = _extract_text(final_message.content)
        data = _parse_itinerary_json(text)
        data["request"] = request.model_dump(mode="json")
        yield {"kind": "draft", "itinerary": Itinerary.model_validate(data)}

    async def _repair(
        self,
        request: ItineraryRequest,
        draft: Itinerary,
        issues: list[str],
    ) -> Itinerary:
        """Second Claude call, no tools — cheap, focused, just fix the issues."""
        draft_payload = draft.model_dump(mode="json")
        # Strip fields the model doesn't need to see or edit:
        #   - computed_* are our post-hoc bookkeeping
        #   - quality_checks is what *we* produce from the critique pass
        #   - request is backend-owned (reattached after parsing), and absent from _SCHEMA_HINT
        cb = draft_payload.get("cost_breakdown", {})
        for k in ("computed_total_inr", "computed_activities_inr", "computed_food_inr"):
            cb.pop(k, None)
        draft_payload.pop("quality_checks", None)
        draft_payload.pop("request", None)

        user_msg = build_repair_message(
            draft_json=json.dumps(draft_payload, indent=2, ensure_ascii=False),
            issues=issues,
            schema_json=_SCHEMA_HINT,
        )

        response = await self.client.messages.create(
            model=settings.anthropic_model,
            max_tokens=settings.max_tokens,
            system=REPAIR_SYSTEM_PROMPT,
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


def _safe_json_get(raw: str, key: str) -> str | None:
    """Parse a potentially-partial JSON string and return `key` if present.

    The streaming API delivers tool input as successive `input_json_delta`
    chunks. The final concatenation should be valid JSON, but we stay
    defensive — if it isn't, we just drop the field rather than crashing
    the whole stream.
    """
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict):
        val = parsed.get(key)
        return val if isinstance(val, str) else None
    return None
