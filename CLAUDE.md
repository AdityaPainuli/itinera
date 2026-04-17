# CLAUDE.md

Guidance for Claude Code when working in this repo.

## What this is

Itinera is an AI travel itinerary generator. A user submits a destination + budget + constraints; a single Claude API call with server-side `web_search` returns a structured JSON itinerary which gets persisted to SQLite and rendered in a Next.js UI.

## Architecture at a glance

```
User → Next.js form → FastAPI POST /api/itinerary/generate
  → ItineraryAgent.generate()
    → Anthropic API call (model + web_search tool enabled)
    → Claude does 1–6 web searches, then emits a ```json block
  → parse + validate against Pydantic Itinerary schema
  → persist to SQLite (ItineraryRow.payload is the full JSON)
  → return to frontend for rendering
```

**Single source of truth for the itinerary shape:** `backend/app/schemas.py`. Frontend mirrors it in `frontend/src/lib/types.ts`. When you change the shape, update **both**, plus the `_SCHEMA_HINT` string in `backend/app/agents/itinerary_agent.py` (the model sees this hint).

## Key files and what lives where

| File | Purpose | When to touch |
|---|---|---|
| `backend/app/agents/prompts.py` | System + user prompts | Iterating on output quality |
| `backend/app/agents/itinerary_agent.py` | Anthropic SDK call, tool config, JSON extraction | Changing model, tool params, adding tools |
| `backend/app/schemas.py` | Pydantic itinerary schema | Adding/removing fields on the itinerary |
| `backend/app/api/routes.py` | HTTP endpoints + markdown renderer | New endpoints, export formats |
| `backend/app/database.py` | SQLAlchemy models, engine, session | Schema migrations, swapping DB |
| `backend/app/config.py` | Env-driven settings | New env vars |
| `frontend/src/lib/types.ts` | TS mirror of backend schema | **Always** update alongside `schemas.py` |
| `frontend/src/lib/api.ts` | fetch client | New endpoints |
| `frontend/src/app/page.tsx` | Orchestration (state, handlers) | Page-level behavior |
| `frontend/src/components/*` | Form / Display / History | UI changes |

## Dev workflow

```bash
# Backend
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm run dev
```

Run both. Frontend hits the backend directly — no proxy layer.

## Extending the agent

The agent is deliberately lean: one call, one tool, one JSON output. Common extensions:

1. **Add a second tool** (e.g. custom flight lookup). Add to the `tools=[...]` list in `itinerary_agent.py`. Claude will call it interleaved with web searches.
2. **Stream progress back to the UI.** Switch `messages.create` → `messages.stream`, parse `content_block_start` events for `server_tool_use` blocks (those are the searches), forward them over SSE. Frontend opens an `EventSource` instead of awaiting `fetch`.
3. **Tighter output contracts.** Instead of asking for a JSON code block, use a proper response-format constraint. Consider prompt-engineered retries on JSON parse failure (`_parse_itinerary_json` currently raises on first failure).
4. **Tune cost.** Drop `anthropic_model` to `claude-sonnet-4-5` in `.env` — usually fine for this task. Reduce `MAX_WEB_SEARCHES` to 3-4.

## Testing

No tests yet. When you add them:
- Backend: `pytest` with `httpx.AsyncClient` against the FastAPI app. Mock the Anthropic client at the `ItineraryAgent` boundary.
- Frontend: skip unit tests, add a Playwright happy-path smoke test instead.

## Common gotchas

- **Pydantic schema drift.** If generation fails with `ValidationError`, the model produced JSON that doesn't match `Itinerary`. Usually because `_SCHEMA_HINT` in `itinerary_agent.py` drifted from `schemas.py`. Keep them in sync.
- **Web search results empty.** Check `ANTHROPIC_API_KEY` has web-search access. Verify the model string supports the `web_search_20250305` tool.
- **Long generation times.** Expect 30–90s because Claude is doing real web research. Don't add a tight request timeout in any proxy/load balancer.
- **CORS.** Frontend origin is hardcoded in `config.py` as `http://localhost:3000`. Add yours to `cors_origins` in prod.

## Design decisions worth preserving

- **Single-turn agent.** No orchestration framework. Claude's tool-use loop handles the search → synthesize cadence natively. Adding LangGraph/CrewAI here would be pure cost.
- **JSON payload stored whole in SQLite.** Itineraries are read-whole, never queried by field. Column indexes on destination + created_at are sufficient. Don't normalize unless a real query pattern demands it.
- **Schema hint in prompt, not tool schema.** Anthropic's `tools` param is for tools. We want structured *final output*, so we ask for a fenced JSON block. Simple, works, easy to debug.

## Conventions

- Python: type hints everywhere, `from __future__ import annotations` in modules with forward refs, Pydantic for all boundary data.
- TS: strict mode, no `any`, mirror backend types by hand (don't auto-generate — the schemas are small and hand-writing keeps TS idiomatic).
- Prompts live in `prompts.py`, never inline. Makes iteration visible in git history.
