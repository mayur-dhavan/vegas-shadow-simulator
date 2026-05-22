"""
db.py — SQLite persistence for tournament run history and challenge outcomes.
Database file: tournament_runs.db (created in the project root on first run).
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "tournament_runs.db"


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")   # safe for concurrent reads
    con.execute("PRAGMA foreign_keys=ON")
    return con


def init_db() -> None:
    """Create tables if they don't exist. Safe to call on every startup."""
    with _connect() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS runs (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp           TEXT    NOT NULL,
                mode                TEXT    NOT NULL DEFAULT 'build',
                system_prompt       TEXT,
                lives_remaining     INTEGER NOT NULL DEFAULT 0,
                base_score          INTEGER NOT NULL DEFAULT 0,
                final_score         INTEGER NOT NULL DEFAULT 0,
                tokens_used         INTEGER NOT NULL DEFAULT 0,
                challenges_visited  INTEGER NOT NULL DEFAULT 0,
                game_won            INTEGER NOT NULL DEFAULT 0,
                game_over           INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS challenges (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id      INTEGER NOT NULL,
                seq         INTEGER NOT NULL,
                cell_type   TEXT    NOT NULL,
                success     INTEGER NOT NULL,
                score_delta INTEGER NOT NULL DEFAULT 0,
                lives_delta INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
            );
        """)


def save_run(state: dict, mode: str, system_prompt: str) -> int:
    """
    Persist a completed run and its challenge log.
    Returns the new run ID.
    """
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    challenge_log = state.get("challenge_log", [])

    with _connect() as con:
        cur = con.execute(
            """
            INSERT INTO runs
                (timestamp, mode, system_prompt, lives_remaining, base_score,
                 final_score, tokens_used, challenges_visited, game_won, game_over)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ts, mode, system_prompt[:2000],  # cap prompt length in DB
                state.get("lives", 0),
                state.get("score", 0),
                state.get("final_score", 0),
                state.get("tokens_used", 0),
                state.get("challenges_visited", 0),
                int(state.get("game_won", False)),
                int(state.get("game_over", False)),
            ),
        )
        run_id = cur.lastrowid

        for seq, ch in enumerate(challenge_log):
            con.execute(
                """
                INSERT INTO challenges (run_id, seq, cell_type, success, score_delta, lives_delta)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (run_id, seq, ch.get("cell_type", "?"),
                 int(ch.get("success", False)),
                 ch.get("score_delta", 0),
                 ch.get("lives_delta", 0)),
            )

    return run_id


def get_runs(limit: int = 30) -> list[dict]:
    """Return recent runs newest-first, without challenge detail."""
    with _connect() as con:
        rows = con.execute(
            "SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_run_challenges(run_id: int) -> list[dict]:
    """Return all challenge rows for a specific run in order."""
    with _connect() as con:
        rows = con.execute(
            "SELECT * FROM challenges WHERE run_id = ? ORDER BY seq",
            (run_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_run(run_id: int) -> dict | None:
    """Return a single run row with its challenges embedded."""
    with _connect() as con:
        row = con.execute(
            "SELECT * FROM runs WHERE id = ?", (run_id,)
        ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["challenges"] = get_run_challenges(run_id)
        return result
