"""HTTP routes."""
from __future__ import annotations

import json
from datetime import datetime
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse, StreamingResponse
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import ItineraryAgent
from app.config import settings
from app.database import ItineraryRow, get_session
from app.notifier import notify_limit_reached
from app.rate_limit import QuotaResult, check_and_consume
from app.schemas import Itinerary, ItineraryListItem, ItineraryRequest

router = APIRouter(prefix="/api")
_agent = ItineraryAgent()


async def _enforce_quota(session: AsyncSession) -> QuotaResult:
    """Consume one quota slot or raise 429.

    The slot is consumed *before* generation starts — so a failed generation
    still costs one of the day's requests. That's a deliberate trade-off:
    counting only successes opens the door to a malicious caller burning
    Anthropic credit by triggering repeated failures.
    """
    if settings.daily_request_limit <= 0:
        # Rate limiting disabled.
        return QuotaResult(allowed=True, count=0, limit=0, reset_at=datetime.utcnow(), should_notify=False)

    result = await check_and_consume(session, settings.daily_request_limit)
    if not result.allowed:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Daily request limit reached ({result.count}/{result.limit}). "
                f"Resets at {result.reset_at:%Y-%m-%d %H:%M UTC}."
            ),
            headers={"Retry-After": str(result.retry_after_seconds)},
        )
    if result.should_notify:
        notify_limit_reached(result.count, result.limit, result.reset_at)
    return result


@router.post("/itinerary/generate", response_model=Itinerary)
async def generate_itinerary(
    request: ItineraryRequest,
    session: AsyncSession = Depends(get_session),
) -> Itinerary:
    await _enforce_quota(session)
    try:
        itinerary = await _agent.generate(request)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    await _persist(itinerary, request, session)
    return itinerary


@router.post("/itinerary/generate/stream")
async def generate_itinerary_stream(
    request: ItineraryRequest,
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    """Server-Sent Events stream of agent progress.

    Each event is encoded as a single SSE `data:` line carrying a JSON object.
    The final event has `kind: "done"` with the full itinerary (including id
    and created_at after persistence); errors arrive as `kind: "error"`.
    """
    # Enforce the quota *before* opening the SSE stream so the client sees
    # a clean 429 with Retry-After, not a stream that errors mid-flight.
    await _enforce_quota(session)
    return StreamingResponse(
        _sse(_agent_events(request, session)),
        media_type="text/event-stream",
        headers={
            # Disable proxy buffering so events reach the browser promptly.
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


async def _agent_events(
    request: ItineraryRequest, session: AsyncSession
) -> AsyncIterator[dict]:
    """Forward agent events to the client, and on `done` persist + re-emit with id."""
    async for event in _agent.generate_stream(request):
        kind = event.get("kind")
        if kind == "done":
            itinerary = event["itinerary"]
            try:
                await _persist(itinerary, request, session)
            except Exception as exc:  # noqa: BLE001
                yield {"kind": "error", "message": f"failed to save: {exc}"}
                return
            yield {"kind": "done", "itinerary": itinerary.model_dump(mode="json")}
        else:
            yield event


async def _sse(events: AsyncIterator[dict]) -> AsyncIterator[bytes]:
    async for event in events:
        yield f"data: {json.dumps(event, default=str)}\n\n".encode("utf-8")


async def _persist(
    itinerary: Itinerary, request: ItineraryRequest, session: AsyncSession
) -> None:
    row = ItineraryRow(
        destination=request.destination,
        duration_days=request.duration_days,
        summary=itinerary.summary,
        payload=itinerary.model_dump(mode="json"),
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    itinerary.id = row.id
    itinerary.created_at = row.created_at


@router.get("/itinerary", response_model=list[ItineraryListItem])
async def list_itineraries(
    session: AsyncSession = Depends(get_session),
    limit: int = 50,
) -> list[ItineraryListItem]:
    stmt = select(ItineraryRow).order_by(desc(ItineraryRow.created_at)).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return [
        ItineraryListItem(
            id=r.id,
            destination=r.destination,
            duration_days=r.duration_days,
            summary=r.summary,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.get("/itinerary/{itinerary_id}", response_model=Itinerary)
async def get_itinerary(
    itinerary_id: str,
    session: AsyncSession = Depends(get_session),
) -> Itinerary:
    row = await session.get(ItineraryRow, itinerary_id)
    if not row:
        raise HTTPException(status_code=404, detail="Itinerary not found")
    itinerary = Itinerary.model_validate(row.payload)
    itinerary.id = row.id
    itinerary.created_at = row.created_at
    return itinerary


@router.get("/itinerary/{itinerary_id}/markdown", response_class=PlainTextResponse)
async def get_itinerary_markdown(
    itinerary_id: str,
    session: AsyncSession = Depends(get_session),
) -> str:
    row = await session.get(ItineraryRow, itinerary_id)
    if not row:
        raise HTTPException(status_code=404, detail="Itinerary not found")
    itinerary = Itinerary.model_validate(row.payload)
    return _to_markdown(itinerary, created_at=row.created_at)


@router.delete("/itinerary/{itinerary_id}")
async def delete_itinerary(
    itinerary_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    row = await session.get(ItineraryRow, itinerary_id)
    if not row:
        raise HTTPException(status_code=404, detail="Itinerary not found")
    await session.delete(row)
    await session.commit()
    return {"status": "deleted", "id": itinerary_id}


def _to_markdown(it: Itinerary, created_at: datetime | None = None) -> str:
    """Render itinerary as markdown. Kept here so it stays in sync with the schema."""
    lines: list[str] = []
    req = it.request
    lines.append(f"# {req.destination} — {req.duration_days} days")
    if created_at:
        lines.append(f"*Generated {created_at:%Y-%m-%d %H:%M UTC}*")
    lines.append("")
    lines.append(f"**Travelers:** {req.travelers}  •  **Budget:** ₹{req.budget_inr:,}")
    if req.travel_styles:
        lines.append(f"**Styles:** {', '.join(req.travel_styles)}")
    if req.special_instructions:
        lines.append(f"**Special instructions:** {req.special_instructions}")
    lines.append("")
    lines.append(f"## Overview\n{it.summary}\n")
    lines.append(f"**Best time to visit:** {it.best_time_to_visit}\n")
    lines.append(f"**Getting there:** {it.getting_there}\n")
    lines.append(f"**Local transportation:** {it.local_transportation}\n")

    lines.append("## Day-by-day\n")
    for day in it.days:
        lines.append(f"### Day {day.day_number} — {day.theme}")
        header_bits = [f"*Estimated cost: ₹{day.daily_cost_estimate_inr:,}*"]
        if day.base_area:
            header_bits.append(f"*Area: {day.base_area}*")
        if day.route_notes:
            header_bits.append(f"*{day.route_notes}*")
        lines.append(" · ".join(header_bits) + "\n")
        for bucket_name, bucket in (("Morning", day.morning), ("Afternoon", day.afternoon), ("Evening", day.evening)):
            if not bucket:
                continue
            lines.append(f"**{bucket_name}**")
            for act in bucket:
                loc = act.location
                if act.neighborhood:
                    loc = f"{loc} ({act.neighborhood})"
                lines.append(
                    f"- **{act.name}** ({act.duration_minutes} min, ₹{act.cost_inr:,}) — "
                    f"{loc}. {act.description}"
                )
                if act.tips:
                    lines.append(f"  *Tip: {act.tips}*")
            lines.append("")
        if day.meals:
            lines.append("**Meals**")
            for m in day.meals:
                extra = f" — {m.notes}" if m.notes else ""
                lines.append(f"- {m.meal.title()} at **{m.place}** ({m.cuisine}, ₹{m.cost_inr:,}){extra}")
            lines.append("")

    lines.append("## Where to stay\n")
    for a in it.accommodation_suggestions:
        rating = f" • ⭐ {a.rating}" if a.rating else ""
        lines.append(
            f"- **{a.name}** ({a.type}, {a.area}) — ₹{a.price_per_night_inr:,}/night{rating}. {a.why}"
        )

    cb = it.cost_breakdown
    lines.append("\n## Cost breakdown\n")
    lines.append(f"| Category | Amount (INR) |\n|---|---:|")
    lines.append(f"| Accommodation | ₹{cb.accommodation_inr:,} |")
    lines.append(f"| Food | ₹{cb.food_inr:,} |")
    lines.append(f"| Activities | ₹{cb.activities_inr:,} |")
    lines.append(f"| Transport | ₹{cb.transport_inr:,} |")
    lines.append(f"| Miscellaneous | ₹{cb.miscellaneous_inr:,} |")
    lines.append(f"| **Total** | **₹{cb.total_inr:,}** |")
    lines.append(f"\n{'✓ Fits budget' if cb.fits_budget else '⚠ Exceeds budget'}")
    if cb.computed_total_inr is not None and cb.computed_total_inr != cb.total_inr:
        lines.append(
            f"\n> Verified sum from per-item costs: ₹{cb.computed_total_inr:,} "
            f"(model reported ₹{cb.total_inr:,})"
        )
    if cb.notes:
        lines.append(f"\n> {cb.notes}")

    if it.quality_checks:
        lines.append("\n## Quality checks\n")
        for c in it.quality_checks:
            lines.append(f"- {c}")

    if it.packing_list:
        lines.append("\n## Packing list\n")
        for p in it.packing_list:
            lines.append(f"- {p}")

    if it.local_tips:
        lines.append("\n## Local tips\n")
        for t in it.local_tips:
            lines.append(f"- {t}")

    if it.cautions:
        lines.append("\n## Cautions\n")
        for c in it.cautions:
            lines.append(f"- {c}")

    if it.sources:
        lines.append("\n## Sources\n")
        for s in it.sources:
            lines.append(f"- {s}")

    return "\n".join(lines)
