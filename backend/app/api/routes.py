"""HTTP routes."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import ItineraryAgent
from app.database import ItineraryRow, get_session
from app.schemas import Itinerary, ItineraryListItem, ItineraryRequest

router = APIRouter(prefix="/api")
_agent = ItineraryAgent()


@router.post("/itinerary/generate", response_model=Itinerary)
async def generate_itinerary(
    request: ItineraryRequest,
    session: AsyncSession = Depends(get_session),
) -> Itinerary:
    try:
        itinerary = await _agent.generate(request)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

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
    return itinerary


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
        lines.append(f"*Estimated cost: ₹{day.daily_cost_estimate_inr:,}*\n")
        for bucket_name, bucket in (("Morning", day.morning), ("Afternoon", day.afternoon), ("Evening", day.evening)):
            if not bucket:
                continue
            lines.append(f"**{bucket_name}**")
            for act in bucket:
                lines.append(
                    f"- **{act.name}** ({act.duration_minutes} min, ₹{act.cost_inr:,}) — "
                    f"{act.location}. {act.description}"
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
    if cb.notes:
        lines.append(f"\n> {cb.notes}")

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
