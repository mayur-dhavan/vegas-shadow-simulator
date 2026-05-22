# Vegas Shadow Simulator

Vegas Shadow Simulator is a local tournament sandbox for an AWS Bedrock-driven dungeon agent. It combines a Python simulation backend, a FastAPI API layer, SQLite run history, and a Next.js dashboard for running and replaying tournament attempts.

## What It Includes

- Python game engine for the grid, scoring, lives, challenge resolution, and replay state
- Bedrock orchestrator that loops the agent through tool use and challenge handling
- FastAPI backend for run execution, streaming, default map access, and run history
- Next.js 14 UI for launching runs, watching the board state, and inspecting past attempts
- SQLite persistence for tournament runs and challenge outcomes

## Tech Stack

- Backend: Python, FastAPI, boto3, SQLite
- Frontend: Next.js 14, React 18, TypeScript, Tailwind CSS
- AI runtime: AWS Bedrock in `us-east-1`

## Prerequisites

- Python 3.11+
- Node.js 18+
- npm 9+
- AWS credentials configured locally with access to Bedrock Runtime in `us-east-1`

## Quick Start

### 1. Install backend dependencies

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Install frontend dependencies

```powershell
Set-Location .\vegas-ui
npm install
Set-Location ..
```

### 3. Start the FastAPI backend

```powershell
uvicorn api_server:app --host 0.0.0.0 --port 8000 --reload
```

The backend will:

- initialize `tournament_runs.db` on first startup
- expose health and run endpoints on `http://localhost:8000`
- store completed run history in SQLite

### 4. Start the Next.js UI

```powershell
Set-Location .\vegas-ui
npm run dev
```

Open `http://localhost:3000`.

The UI proxies browser requests through Next.js API routes to the local FastAPI backend on `http://localhost:8000`.

## Main Entry Points

- `api_server.py`: FastAPI bridge for the simulator backend
- `orchestrator.py`: Bedrock conversation loop, tool routing, and run orchestration
- `game_engine.py`: core grid state, scoring rules, and movement logic
- `db.py`: SQLite persistence for runs and challenge logs
- `vegas-ui/app/page.tsx`: interactive dashboard for runs, replays, and history

## Project Structure

```text
.
|-- api_server.py
|-- orchestrator.py
|-- game_engine.py
|-- db.py
|-- tools/
|   |-- code_executor.py
|   |-- pathfinder.py
|   `-- webscraper.py
`-- vegas-ui/
    |-- app/
    |   |-- page.tsx
    |   `-- api/
    `-- package.json
```

## Notes

- The backend currently targets `us.amazon.nova-pro-v1:0` in the main orchestrator.
- Historical Bedrock experiments are also present in `boss_simulator.py` and `test_bedrock.py`.
- Local database files, caches, and UI build output are intentionally ignored from version control.