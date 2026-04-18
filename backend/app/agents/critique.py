"""Post-generation critique + deterministic fixes.

Two kinds of work happen here:

1. **Silent fixes** — things Python can do better than Claude, applied in place:
   - Re-order activities within a day's morning/afternoon/evening bucket by
     physical proximity (nearest-neighbor from the first stop that has coords).
   - Re-compute the cost breakdown sums and stamp `computed_*_inr` fields so
     the UI can show "the model said X, we summed Y".

2. **Issues list** — things only the model can fix (missing meals, wrong
   day count, activities that straddle opposite sides of the city). These
   get returned as a list of human-readable strings for the repair prompt.

The whole module is pure — no I/O, no network. Tests (when they exist) will
live beside it.
"""
from __future__ import annotations

import math
from typing import Iterable

from app.schemas import Activity, DayPlan, Itinerary, ItineraryRequest

# A day whose activities are spread further than this (km, max pairwise)
# earns an issue flag. City-scale heuristic — intentionally generous.
_MAX_DAY_SPREAD_KM = 15.0

# Budget arithmetic tolerance. The model often rounds; anything inside this
# band is fine. Beyond it, we flag.
_BUDGET_TOLERANCE_INR = 500


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance between (lat, lng) pairs in km."""
    lat1, lng1 = math.radians(a[0]), math.radians(a[1])
    lat2, lng2 = math.radians(b[0]), math.radians(b[1])
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def _coords(act: Activity) -> tuple[float, float] | None:
    if act.lat is None or act.lng is None:
        return None
    return (act.lat, act.lng)


def order_by_proximity(activities: list[Activity]) -> list[Activity]:
    """Nearest-neighbor reorder, starting from the first activity that has coords.

    Activities without coords keep their relative order but get appended at
    the end — we can't route them, so we trust the model's placement.
    """
    with_coords = [a for a in activities if _coords(a) is not None]
    without = [a for a in activities if _coords(a) is None]
    if len(with_coords) <= 2:
        return with_coords + without

    ordered: list[Activity] = [with_coords[0]]
    remaining = with_coords[1:]
    while remaining:
        last = _coords(ordered[-1])
        assert last is not None  # only Activities with coords reach here
        remaining.sort(key=lambda a: haversine_km(last, _coords(a)))  # type: ignore[arg-type]
        ordered.append(remaining.pop(0))
    return ordered + without


def day_spread_km(day: DayPlan) -> float:
    """Max pairwise distance between any two activities in a day that have coords."""
    pts = [c for a in _all_activities(day) if (c := _coords(a)) is not None]
    if len(pts) < 2:
        return 0.0
    return max(haversine_km(pts[i], pts[j]) for i in range(len(pts)) for j in range(i + 1, len(pts)))


def _all_activities(day: DayPlan) -> Iterable[Activity]:
    yield from day.morning
    yield from day.afternoon
    yield from day.evening


def _reorder_day(day: DayPlan) -> None:
    day.morning = order_by_proximity(day.morning)
    day.afternoon = order_by_proximity(day.afternoon)
    day.evening = order_by_proximity(day.evening)


def verify_budget(it: Itinerary, request: ItineraryRequest) -> tuple[int, int, int, list[str]]:
    """Recompute the numeric budget breakdown from per-item costs.

    Returns (computed_activities, computed_food, computed_total, issues).
    `issues` is non-empty when the model's totals drift beyond tolerance or
    when the plan overshoots the user's budget but claims `fits_budget=true`.
    """
    travelers = max(request.travelers, 1)
    computed_activities = sum(
        a.cost_inr for day in it.days for a in _all_activities(day)
    ) * travelers
    computed_food = sum(
        m.cost_inr for day in it.days for m in day.meals
    ) * travelers

    cb = it.cost_breakdown
    computed_total = (
        computed_activities
        + computed_food
        + cb.accommodation_inr
        + cb.transport_inr
        + cb.miscellaneous_inr
    )

    issues: list[str] = []
    if abs(cb.activities_inr - computed_activities) > _BUDGET_TOLERANCE_INR:
        issues.append(
            f"cost_breakdown.activities_inr={cb.activities_inr} but per-activity sum × {travelers} travelers "
            f"= {computed_activities}. Reconcile or update per-item costs."
        )
    if abs(cb.food_inr - computed_food) > _BUDGET_TOLERANCE_INR:
        issues.append(
            f"cost_breakdown.food_inr={cb.food_inr} but per-meal sum × {travelers} travelers "
            f"= {computed_food}. Reconcile or update per-meal costs."
        )
    if abs(cb.total_inr - computed_total) > _BUDGET_TOLERANCE_INR:
        issues.append(
            f"cost_breakdown.total_inr={cb.total_inr} but component sum = {computed_total}. "
            f"Adjust the sub-totals or the total so they match."
        )
    if computed_total > request.budget_inr and cb.fits_budget:
        issues.append(
            f"Plan totals ~₹{computed_total} (travelers={travelers}) which exceeds budget ₹{request.budget_inr}, "
            f"but `fits_budget` is true. Either trim the plan or flip the flag and explain."
        )

    return computed_activities, computed_food, computed_total, issues


def critique(it: Itinerary, request: ItineraryRequest) -> list[str]:
    """Run silent fixes in place and return a list of issues for the repair pass.

    An empty list means the draft is good enough to ship without a repair call.
    """
    issues: list[str] = []

    # Day count sanity.
    if len(it.days) != request.duration_days:
        issues.append(
            f"Plan has {len(it.days)} days but request asked for {request.duration_days}. "
            f"Add or remove days to match exactly."
        )
    expected_nums = set(range(1, request.duration_days + 1))
    actual_nums = {d.day_number for d in it.days}
    if expected_nums != actual_nums and len(it.days) == request.duration_days:
        issues.append(
            f"day_number values {sorted(actual_nums)} don't cover 1..{request.duration_days}."
        )

    # Silent fix: reorder activities by proximity within each bucket.
    for day in it.days:
        _reorder_day(day)

    # Geographic coherence — flag days with coords whose spread is too big.
    for day in it.days:
        spread = day_spread_km(day)
        if spread > _MAX_DAY_SPREAD_KM:
            issues.append(
                f"Day {day.day_number}: activities span {spread:.1f}km. "
                f"Either cluster them into one area or split across days."
            )

    # Meal coverage — every day should have at least lunch and dinner.
    for day in it.days:
        meals = {m.meal for m in day.meals}
        missing = {"lunch", "dinner"} - meals
        if missing:
            issues.append(
                f"Day {day.day_number} is missing {', '.join(sorted(missing))}. Add a specific spot."
            )

    # Coordinates coverage — if <40% of activities have coords, ask for more.
    all_acts = [a for day in it.days for a in _all_activities(day)]
    if all_acts:
        with_coords = sum(1 for a in all_acts if _coords(a) is not None)
        if with_coords / len(all_acts) < 0.4:
            issues.append(
                f"Only {with_coords}/{len(all_acts)} activities have lat/lng. "
                f"Add coordinates (decimal degrees) so the route can be validated."
            )

    # Budget verification + stamp computed totals (silent fix on the schema side).
    computed_acts, computed_food, computed_total, budget_issues = verify_budget(it, request)
    it.cost_breakdown.computed_activities_inr = computed_acts
    it.cost_breakdown.computed_food_inr = computed_food
    it.cost_breakdown.computed_total_inr = computed_total
    issues.extend(budget_issues)

    return issues
