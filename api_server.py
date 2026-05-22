"""
api_server.py — FastAPI bridge between the Next.js UI and the Python backend.

Start:  uvicorn api_server:app --host 0.0.0.0 --port 8000 --reload
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
import json

from game_engine import DEFAULT_MAP
from orchestrator import TournamentOrchestrator
import db as database


@asynccontextmanager
async def lifespan(app: FastAPI):
    database.init_db()
    yield


app = FastAPI(
    title="Vegas Shadow Simulator API",
    description="AWS AI League tournament backend — Bedrock + GameEngine + SQLite",
    version="1.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ------------------------------------------------------------------
# Request model
# ------------------------------------------------------------------

class RunRequest(BaseModel):
    system_prompt: str
    game_map:      Optional[list] = None
    start_pos:     Optional[list] = None
    mode:          Optional[str]  = "build"


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@app.get("/health")
def health() -> dict:
    return {"status": "ok", "model": "us.amazon.nova-pro-v1:0"}


@app.get("/default-map")
def get_default_map() -> dict:
    return {"game_map": DEFAULT_MAP, "start_pos": [0, 0]}


@app.post("/run")
def run_agent(request: RunRequest) -> dict:
    """
    Synchronous tournament run. Saves the result to SQLite and returns
    the final game state (including challenge_log) as JSON.
    """
    game_map  = request.game_map  or DEFAULT_MAP
    start_pos = request.start_pos or [0, 0]
    mode      = request.mode      or "build"

    try:
        orch  = TournamentOrchestrator()
        state = orch.run(
            system_prompt=request.system_prompt,
            game_map=game_map,
            start_pos=start_pos,
        )
        # Persist to SQLite
        run_id = database.save_run(state, mode, request.system_prompt)
        state["run_id"] = run_id
        return state
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/run/stream")
def run_agent_stream(request: RunRequest) -> StreamingResponse:
    """Streaming run — yields newline-delimited JSON state updates."""
    game_map  = request.game_map  or DEFAULT_MAP
    start_pos = request.start_pos or [0, 0]
    mode      = request.mode      or "build"

    def generate():
        try:
            orch       = TournamentOrchestrator()
            last_state = None
            for state in orch.run_step(request.system_prompt, game_map, start_pos):
                last_state = state
                yield json.dumps(state) + "\n"
            # Save final state to DB after stream ends
            if last_state:
                run_id = database.save_run(last_state, mode, request.system_prompt)
                last_state["run_id"] = run_id
                yield json.dumps({"event": "saved", "run_id": run_id}) + "\n"
        except Exception as exc:
            yield json.dumps({"error": str(exc)}) + "\n"

    return StreamingResponse(generate(), media_type="application/x-ndjson")


# ------------------------------------------------------------------
# Run history endpoints
# ------------------------------------------------------------------

@app.get("/runs")
def list_runs(limit: int = 30) -> list:
    """Return the most recent runs, newest first."""
    return database.get_runs(limit=limit)


@app.get("/runs/{run_id}")
def get_run(run_id: int) -> dict:
    """Return a single run with its challenge log embedded."""
    run = database.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return run
