"use client";

import { useState, useEffect, useRef, useCallback } from "react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type TournamentMode = "build" | "semifinal" | "finale";
type GamePhase = "idle" | "running" | "replaying" | "stopped" | "complete";

interface ChallengeEntry {
  cell_type:   string;
  success:     boolean;
  score_delta: number;
  lives_delta: number;
  streak?:     number;
}

interface ScoreBreakdown {
  base_score:             number;
  life_bonus:             number;
  token_bonus:            number;
  league_final_score:     number;
  perfect_run_bonus:      number;
  challenge_mastery_bonus:number;
  streak_bonus:           number;
  coin_sweep_bonus:       number;
  efficiency_bonus:       number;
  full_clear_bonus:       number;
  bonus_score:            number;
  shadow_final_score:     number;
}

interface GameState {
  grid:               string[][];
  player_pos:         [number, number];
  lives:              number;
  score:              number;
  tokens_used:        number;
  challenges_visited: number;
  has_red_key:        boolean;
  game_over:          boolean;
  game_won:           boolean;
  final_score:        number;
  shadow_score?:      number;
  bonus_score?:       number;
  pending_challenge:  string | null;
  challenge_log:      ChallengeEntry[];
  steps_taken?:       number;
  coins_collected?:   number;
  total_coins?:       number;
  successful_challenges?: number;
  failed_challenges?: number;
  max_challenge_streak?: number;
  total_challenges?:  number;
  red_door_unlocked?: boolean;
  score_breakdown?:   ScoreBreakdown;
  step_history?:      GameState[];
  run_id?:            number;
}

interface RunSummary {
  id:                 number;
  timestamp:          string;
  mode:               string;
  lives_remaining:    number;
  base_score:         number;
  final_score:        number;
  tokens_used:        number;
  challenges_visited: number;
  game_won:           number;
  game_over:          number;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const MODE_DURATIONS: Record<TournamentMode, number> = {
  build:    10800,
  semifinal:  360,
  finale:      45,
};

const MODE_LABELS: Record<TournamentMode, string> = {
  build:    "Build Mode — 3 Hours",
  semifinal: "Semi-Final — 6 Minutes",
  finale:   "Live Finale — 45 Seconds",
};

const CELL_EMOJI: Record<string, string> = {
  wall:    "⬛", normal:   "⬜", treasure: "💎",
  c7:      "🪙", c8:       "🔴", c30:      "🚪",
  c40:     "🔑", c1:       "💜", c2:       "🧠",
  c4:      "🌐", c3:       "🎭", c5:       "🤔",
  c18:     "🏥",
};

const CELL_BG: Record<string, string> = {
  wall:    "bg-gray-800",
  normal:  "bg-gray-700 hover:bg-gray-600",
  treasure:"bg-yellow-400",
  c7:      "bg-yellow-700",
  c8:      "bg-red-800",
  c30:     "bg-orange-800",
  c40:     "bg-emerald-800",
  c1:      "bg-purple-800",
  c2:      "bg-blue-800",
  c4:      "bg-cyan-800",
  c3:      "bg-violet-800",
  c5:      "bg-sky-800",
  c18:     "bg-teal-800",
};

const CHALLENGE_LABEL: Record<string, string> = {
  c1:  "Violent Violet (Guardrail)",
  c2:  "Code Challenge",
  c3:  "Memory Trial (Memento)",
  c4:  "Web Search (Dark Prophet)",
  c5:  "Simple Question (Bonehead)",
  c18: "Healthcare API",
};

const DEFAULT_MAP: string[][] = [
  ["normal", "c7",    "c7",    "normal", "c7",    "normal", "c40",   "c7",    "normal", "normal" ],
  ["c1",     "wall",  "c7",    "normal", "normal", "normal", "wall",  "normal", "c7",    "normal" ],
  ["normal", "c7",    "c3",    "c7",     "wall",   "normal", "c7",    "normal", "c18",   "normal" ],
  ["c7",     "normal", "wall",  "normal", "c7",    "normal", "normal", "wall",  "normal", "wall"   ],
  ["normal", "c7",    "c5",    "normal", "c8",     "c7",     "normal", "c7",    "c30",   "treasure"],
  ["c7",     "wall",  "normal", "c2",     "normal", "normal", "c8",    "normal", "c7",    "wall"   ],
  ["normal", "c7",    "normal", "wall",   "normal", "c7",     "normal", "c7",    "normal", "c7"     ],
  ["c7",     "normal", "normal", "c7",     "c4",     "normal", "c7",    "normal", "wall",  "normal" ],
  ["normal", "c7",    "c8",    "normal", "c7",     "normal", "normal", "c7",    "normal", "c7"     ],
  ["c7",     "normal", "normal", "c7",     "normal", "wall",   "c7",    "normal", "normal", "normal" ],
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatTime(s: number, mode: TournamentMode): string {
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const p = (n: number) => String(n).padStart(2, "0");
  return mode === "build" ? `${p(h)}:${p(m)}:${p(sec)}` : `${p(m)}:${p(sec)}`;
}

function timerColor(rem: number, total: number) {
  const pct = rem / total;
  if (pct > 0.25) return "text-emerald-400";
  if (pct > 0.10) return "text-yellow-400";
  return "text-red-400 animate-pulse";
}

function lifeBonus(lives: number) { return Math.max(0, lives) * 250; }
function tokenBonus(tokens: number, challenges: number) {
  return Math.max(0, 1000 - Math.floor(tokens / Math.max(challenges, 1)));
}

function cloneMap(map: string[][]): string[][] {
  return map.map((row) => [...row]);
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function StatBox({ label, value, color = "text-white" }: { label: string; value: string | number; color?: string }) {
  return (
    <div className="bg-gray-800 rounded-lg p-3">
      <div className="text-gray-500 text-xs mb-1">{label}</div>
      <div className={`text-2xl font-bold tabular-nums ${color}`}>{value}</div>
    </div>
  );
}

function ChallengeLog({ log }: { log: ChallengeEntry[] }) {
  if (log.length === 0) return (
    <div className="text-gray-600 text-sm italic">No challenges encountered yet.</div>
  );
  return (
    <div className="space-y-1.5">
      {log.map((entry, i) => (
        <div key={i}
          className={`flex items-center justify-between rounded-lg px-3 py-2 text-sm
            ${entry.success ? "bg-emerald-900/40 border border-emerald-700" : "bg-red-900/40 border border-red-800"}`}>
          <div className="flex items-center gap-2">
            <span className="text-base">{CELL_EMOJI[entry.cell_type] ?? "❓"}</span>
            <span className="text-gray-300">{CHALLENGE_LABEL[entry.cell_type] ?? entry.cell_type}</span>
          </div>
          <div className="flex items-center gap-3">
            {entry.score_delta !== 0 && (
              <span className={entry.score_delta > 0 ? "text-yellow-400" : "text-red-400"}>
                {entry.score_delta > 0 ? "+" : ""}{entry.score_delta} pts
              </span>
            )}
            {entry.lives_delta !== 0 && (
              <span className="text-red-400">{entry.lives_delta} ❤️</span>
            )}
            <span className={`font-bold ${entry.success ? "text-emerald-400" : "text-red-400"}`}>
              {entry.success ? "✓ PASS" : "✗ FAIL"}
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}

function RunHistoryTable({ runs, onRefresh }: { runs: RunSummary[]; onRefresh: () => void }) {
  if (runs.length === 0) return (
    <div className="text-gray-600 text-sm italic text-center py-4">
      No runs recorded yet. Run the agent to start tracking!
    </div>
  );
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-gray-500 text-xs uppercase border-b border-gray-700">
            <th className="pb-2 text-left pr-3">Run</th>
            <th className="pb-2 text-left pr-3">Time</th>
            <th className="pb-2 text-left pr-3">Mode</th>
            <th className="pb-2 text-right pr-3">Score</th>
            <th className="pb-2 text-right pr-3">Final</th>
            <th className="pb-2 text-right pr-3">Tokens</th>
            <th className="pb-2 text-right pr-3">Lives</th>
            <th className="pb-2 text-right pr-3">Challenges</th>
            <th className="pb-2 text-center">Result</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((r) => (
            <tr key={r.id} className="border-b border-gray-800 hover:bg-gray-800/50 transition-colors">
              <td className="py-2 pr-3 text-gray-500">#{r.id}</td>
              <td className="py-2 pr-3 text-gray-400 whitespace-nowrap">{r.timestamp.slice(0, 19).replace("T", " ")}</td>
              <td className="py-2 pr-3">
                <span className={`px-1.5 py-0.5 rounded text-xs font-medium
                  ${r.mode === "finale" ? "bg-red-900 text-red-200" :
                    r.mode === "semifinal" ? "bg-orange-900 text-orange-200" :
                    "bg-blue-900 text-blue-200"}`}>
                  {r.mode}
                </span>
              </td>
              <td className="py-2 pr-3 text-right text-yellow-400 tabular-nums">{r.base_score.toLocaleString()}</td>
              <td className="py-2 pr-3 text-right font-bold text-white tabular-nums">{r.final_score.toLocaleString()}</td>
              <td className="py-2 pr-3 text-right text-cyan-400 tabular-nums">{r.tokens_used.toLocaleString()}</td>
              <td className="py-2 pr-3 text-right">
                {"❤️".repeat(Math.max(0, r.lives_remaining))}{"🖤".repeat(Math.max(0, 5 - r.lives_remaining))}
              </td>
              <td className="py-2 pr-3 text-right text-purple-400">{r.challenges_visited}</td>
              <td className="py-2 text-center">
                {r.game_won
                  ? <span className="text-yellow-400 font-bold">🏆 WIN</span>
                  : <span className="text-red-400">💀 LOSS</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <button onClick={onRefresh}
        className="mt-3 text-xs text-gray-500 hover:text-gray-300 transition-colors">
        ↺ Refresh history
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function Home() {
  const [mode, setMode]                     = useState<TournamentMode>("build");
  const [phase, setPhase]                   = useState<GamePhase>("idle");
  const [timeRemaining, setTimeRemaining]   = useState(MODE_DURATIONS.build);
  const [systemPrompt, setSystemPrompt]     = useState(
    "You are an expert dungeon navigator. Always call use_smart_loot with strategy='smart_loot' " +
    "to find the safest path to the treasure. Maximise score, preserve lives."
  );
  const [startPos, setStartPos]             = useState<[number, number]>([0, 0]);
  const [baseMap, setBaseMap]               = useState<string[][]>(cloneMap(DEFAULT_MAP));
  const [gameState, setGameState]           = useState<GameState | null>(null);
  const [gameMap, setGameMap]               = useState<string[][]>(cloneMap(DEFAULT_MAP));
  const [runs, setRuns]                     = useState<RunSummary[]>([]);
  const [errorMsg, setErrorMsg]             = useState("");
  const [activeTab, setActiveTab]           = useState<"stats"|"challenges"|"history">("stats");
  const [replayProgress, setReplayProgress] = useState<{ step: number; total: number } | null>(null);

  const timerRef  = useRef<ReturnType<typeof setInterval> | null>(null);
  const abortRef  = useRef<AbortController | null>(null);
  const replayRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const modeRef  = useRef<TournamentMode>(mode);
  modeRef.current = mode;
  const runAgentRef = useRef<() => void>(() => {});

  const fetchDefaultMap = useCallback(async () => {
    try {
      const res = await fetch("/api/default-map", { cache: "no-store" });
      if (!res.ok) return;
      const data = await res.json();
      const nextMap = Array.isArray(data.game_map) ? data.game_map : DEFAULT_MAP;
      const nextStart = Array.isArray(data.start_pos) ? data.start_pos : [0, 0];
      setBaseMap(cloneMap(nextMap));
      setGameMap(cloneMap(nextMap));
      setStartPos([nextStart[0] ?? 0, nextStart[1] ?? 0]);
    } catch {
      setBaseMap(cloneMap(DEFAULT_MAP));
      setGameMap(cloneMap(DEFAULT_MAP));
      setStartPos([0, 0]);
    }
  }, []);

  // ── Fetch run history ────────────────────────────────────────────
  const fetchRuns = useCallback(async () => {
    try {
      const res = await fetch("/api/runs");
      if (res.ok) setRuns(await res.json());
    } catch { /* backend may not be ready yet */ }
  }, []);

  useEffect(() => {
    fetchDefaultMap();
    fetchRuns();
  }, [fetchDefaultMap, fetchRuns]);

  // ── Timer ────────────────────────────────────────────────────────
  const stopTimer = useCallback(() => {
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
  }, []);

  const startTimer = useCallback(() => {
    stopTimer();
    timerRef.current = setInterval(() => {
      setTimeRemaining((prev) => {
        if (prev <= 1) {
          stopTimer();
          if (modeRef.current === "finale") runAgentRef.current();
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
  }, [stopTimer]);

  useEffect(() => {
    stopTimer();
    setTimeRemaining(MODE_DURATIONS[mode]);
    setPhase("idle");
    setGameState(null);
    setGameMap(cloneMap(baseMap));
    setErrorMsg("");
    abortRef.current?.abort();
    if (mode === "finale") {
      const t = setTimeout(startTimer, 100);
      return () => clearTimeout(t);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, baseMap]);

  // ── Agent run ────────────────────────────────────────────────────
  const handleRunAgent = useCallback(async () => {
    setPhase("running");
    setErrorMsg("");
    setGameState(null);
    const runMap = cloneMap(baseMap);
    setGameMap(runMap);
    abortRef.current = new AbortController();
    if (mode === "semifinal") startTimer();

    try {
      const res = await fetch("/api/run", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ system_prompt: systemPrompt, game_map: runMap, start_pos: startPos, mode }),
        signal:  abortRef.current.signal,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ error: `HTTP ${res.status}` }));
        throw new Error(err.error ?? `HTTP ${res.status}`);
      }
      const data: GameState = await res.json();
      const steps = data.step_history ?? [];
      if (steps.length > 0) {
        setPhase("replaying");
        setReplayProgress({ step: 0, total: steps.length });
        let idx = 0;
        replayRef.current = setInterval(() => {
          const snap = steps[idx];
          setGameMap(snap.grid);
          setGameState(snap);
          setReplayProgress({ step: idx + 1, total: steps.length });
          idx++;
          if (idx >= steps.length) {
            clearInterval(replayRef.current!);
            replayRef.current = null;
            setGameState(data);
            setGameMap(data.grid ?? snap.grid);
            setReplayProgress(null);
            setPhase("complete");
            stopTimer();
            fetchRuns();
          }
        }, 400);
      } else {
        setGameState(data);
        if (data.grid) setGameMap(data.grid);
        setPhase("complete");
        stopTimer();
        fetchRuns();
      }
    } catch (err: unknown) {
      const isAbort = err instanceof Error && err.name === "AbortError";
      if (!isAbort) { setErrorMsg(err instanceof Error ? err.message : String(err)); setPhase("idle"); }
    }
  }, [mode, systemPrompt, baseMap, startPos, startTimer, stopTimer, fetchRuns]);

  runAgentRef.current = handleRunAgent;

  const handleStop  = useCallback(() => {
    abortRef.current?.abort();
    if (replayRef.current) { clearInterval(replayRef.current); replayRef.current = null; }
    stopTimer();
    setPhase("stopped");
    setReplayProgress(null);
  }, [stopTimer]);
  const handleResetBoard = useCallback(() => {
    setGameState(null);
    setGameMap(cloneMap(baseMap));
    setErrorMsg("");
  }, [baseMap]);
  const handleRerun = useCallback(() => {
    setGameState(null);
    setGameMap(cloneMap(baseMap));
    setErrorMsg("");
    handleRunAgent();
  }, [baseMap, handleRunAgent]);

  // ── Derived ──────────────────────────────────────────────────────
  const isRunning    = phase === "running" || phase === "replaying";
  const promptLocked = mode === "finale" && timeRemaining === 0;
  const cols         = gameMap[0]?.length ?? 10;
  const challengeLog = gameState?.challenge_log ?? [];
  const scoreBreakdown = gameState?.score_breakdown;
  const totalCoins = gameState?.total_coins ?? baseMap.flat().filter((cell) => cell === "c7").length;
  const totalChallenges = gameState?.total_challenges ?? baseMap.flat().filter((cell) => ["c1", "c2", "c3", "c4", "c5", "c18"].includes(cell)).length;

  // ── Render ───────────────────────────────────────────────────────
  return (
    <main className="min-h-screen bg-gray-950 p-4 md:p-6 space-y-5">

      {/* ── Header ── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-yellow-400 tracking-wide">⚔️ Vegas Shadow Simulator</h1>
          <p className="text-gray-500 text-xs mt-0.5">AWS AI League 2026 Global Finals — Tournament Engine</p>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-gray-500 text-sm">Mode:</span>
          <select value={mode} onChange={(e) => setMode(e.target.value as TournamentMode)}
            disabled={isRunning}
            className="bg-gray-800 border border-gray-600 text-white rounded-lg px-3 py-1.5
                       text-sm focus:outline-none focus:ring-2 focus:ring-yellow-500 disabled:opacity-50">
            <option value="build">Build Mode (3 Hours)</option>
            <option value="semifinal">Semi-Final (6 Minutes)</option>
            <option value="finale">Live Finale (45 Seconds)</option>
          </select>
        </div>
      </div>

      {/* ── Main two-column layout ── */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">

        {/* LEFT: Timer + Controls + Grid */}
        <div className="space-y-4">

          {/* Timer bar */}
          <div className="bg-gray-900 border border-gray-700 rounded-xl p-4 flex items-center justify-between">
            <div>
              <div className={`text-4xl font-black tabular-nums ${timerColor(timeRemaining, MODE_DURATIONS[mode])}`}>
                {formatTime(timeRemaining, mode)}
              </div>
              <div className="text-gray-500 text-xs mt-1">{MODE_LABELS[mode]}</div>
            </div>
            <div className={`px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider
              ${phase === "idle"      ? "bg-gray-700 text-gray-400" :
                phase === "running"   ? "bg-blue-700 text-blue-100 animate-pulse" :
                phase === "replaying" ? "bg-purple-700 text-purple-100 animate-pulse" :
                phase === "stopped"   ? "bg-orange-700 text-orange-100" :
                                        "bg-emerald-700 text-emerald-100"}`}>
              {phase}
            </div>
          </div>

          {/* Controls */}
          <div className="flex flex-wrap gap-2 items-center">
            {mode !== "finale" && (
              <button onClick={handleRunAgent} disabled={isRunning || phase === "complete"}
                className="px-5 py-2 bg-yellow-600 hover:bg-yellow-500 text-black font-bold
                           rounded-lg disabled:opacity-40 transition-colors text-sm">
                ▶ Run Agent
              </button>
            )}
            <button onClick={handleResetBoard} disabled={isRunning}
              className="px-5 py-2 bg-gray-800 hover:bg-gray-700 text-white font-bold
                         rounded-lg border border-gray-700 disabled:opacity-40 transition-colors text-sm">
              ↺ Reset Board
            </button>
            {mode === "semifinal" && (
              <>
                <button onClick={handleStop} disabled={!isRunning}
                  className="px-5 py-2 bg-red-700 hover:bg-red-600 text-white font-bold
                             rounded-lg disabled:opacity-40 transition-colors text-sm">
                  ■ Stop
                </button>
                <button onClick={handleRerun} disabled={phase !== "stopped" && phase !== "complete"}
                  className="px-5 py-2 bg-blue-700 hover:bg-blue-600 text-white font-bold
                             rounded-lg disabled:opacity-40 transition-colors text-sm">
                  ↺ Rerun
                </button>
              </>
            )}
            {mode === "finale" && (
              <p className="text-sm text-gray-400 italic">
                {timeRemaining > 0
                  ? `⏳ Edit your prompt — ${timeRemaining}s remaining`
                  : "🔒 Prompt locked — agent auto-submitted"}
              </p>
            )}
          </div>

          {errorMsg && (
            <div className="bg-red-900/50 border border-red-700 rounded-lg p-3 text-red-300 text-sm">
              ⚠ {errorMsg}
            </div>
          )}

          {/* 2D Grid */}
          <div className="bg-gray-900 border border-gray-700 rounded-xl p-4">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-gray-400 text-xs font-bold uppercase tracking-wider">Dungeon Map</h2>
              <span className="text-gray-600 text-xs">{gameMap.length}×{cols} champion board</span>
              {phase === "running" && (
                <span className="text-blue-400 text-xs animate-pulse font-semibold">● Agent running…</span>
              )}
              {phase === "replaying" && replayProgress && (
                <span className="text-purple-400 text-xs animate-pulse font-semibold">
                  ▶ Replaying {replayProgress.step}/{replayProgress.total} steps…
                </span>
              )}
            </div>

            {/* Grid */}
            <div className="grid gap-0.5" style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}>
              {gameMap.map((row, r) =>
                row.map((cell, c) => {
                  const isPlayer   = gameState?.player_pos[0] === r && gameState?.player_pos[1] === c;
                  const isChallenge= ["c1","c2","c3","c4","c5","c18"].includes(cell);
                  const bg         = CELL_BG[cell] ?? "bg-gray-700";
                  return (
                    <div key={`${r}-${c}`} title={`[${r},${c}] ${cell}`}
                      className={`${bg} flex items-center justify-center w-8 h-8 sm:w-9 sm:h-9 md:w-10 md:h-10 text-lg md:text-xl rounded
                        transition-all duration-200 relative
                        ${isPlayer ? "ring-2 ring-white scale-110 z-10" : ""}
                        ${isChallenge && !isPlayer ? "ring-1 ring-yellow-500/50" : ""}`}>
                      <span className={isPlayer ? "animate-bounce" : ""}>
                        {isPlayer ? "🧙" : (CELL_EMOJI[cell] ?? "❓")}
                      </span>
                      {/* Challenge indicator dot */}
                      {isChallenge && (
                        <span className="absolute -top-0.5 -right-0.5 w-2 h-2 bg-yellow-400 rounded-full" />
                      )}
                    </div>
                  );
                })
              )}
            </div>

            {/* Legend */}
            <div className="mt-3 flex flex-wrap gap-x-3 gap-y-1 text-xs text-gray-600">
              {Object.entries(CELL_EMOJI).map(([k, v]) => (
                <span key={k}>{v}&thinsp;<span className="text-gray-700">{k}</span></span>
              ))}
              <span>🧙&thinsp;<span className="text-gray-700">player</span></span>
            </div>
          </div>
        </div>

        {/* RIGHT: Prompt + Tabs (Stats / Challenges / History) */}
        <div className="space-y-4">

          {/* System Prompt */}
          <div className="bg-gray-900 border border-gray-700 rounded-xl p-4">
            <div className="flex items-center justify-between mb-2">
              <h2 className="text-gray-400 text-xs font-bold uppercase tracking-wider">System Prompt</h2>
              {promptLocked
                ? <span className="text-red-400 text-xs font-bold">🔒 LOCKED</span>
                : <span className="text-gray-600 text-xs">{systemPrompt.length} chars</span>}
            </div>
            <textarea value={systemPrompt} onChange={(e) => setSystemPrompt(e.target.value)}
              disabled={promptLocked} rows={6}
              className="w-full bg-gray-800 border border-gray-700 text-gray-100 rounded-lg p-3
                         text-sm resize-none font-mono leading-relaxed focus:outline-none
                         focus:ring-2 focus:ring-yellow-500 disabled:opacity-50 disabled:cursor-not-allowed"/>
            <p className="text-gray-600 text-xs mt-1.5">
              {mode === "finale"
                ? "Editable until 00:00, then auto-submitted."
                : "⚠ Avoid 'violence', 'illegal', 'edible flowers' — they trigger the Guardrail on 💜"}
            </p>
          </div>

          {/* Tab bar */}
          <div className="bg-gray-900 border border-gray-700 rounded-xl overflow-hidden">
            <div className="flex border-b border-gray-700">
              {(["stats","challenges","history"] as const).map((tab) => (
                <button key={tab} onClick={() => setActiveTab(tab)}
                  className={`flex-1 py-2 text-xs font-bold uppercase tracking-wider transition-colors
                    ${activeTab === tab
                      ? "bg-gray-800 text-white border-b-2 border-yellow-400"
                      : "text-gray-500 hover:text-gray-300"}`}>
                  {tab === "stats"      ? "📊 Stats"
                  : tab === "challenges" ? `🎯 Challenges ${challengeLog.length > 0 ? `(${challengeLog.length})` : ""}`
                  :                        `📜 History ${runs.length > 0 ? `(${runs.length})` : ""}`}
                </button>
              ))}
            </div>

            <div className="p-4">

              {/* ── Stats tab ── */}
              {activeTab === "stats" && (
                <div className="space-y-3">
                  <div className="grid grid-cols-2 gap-3">
                    <div className="bg-gray-800 rounded-lg p-3 col-span-2">
                      <div className="text-gray-500 text-xs mb-1">Lives</div>
                      <div className="flex items-center gap-1">
                        {Array.from({ length: 5 }).map((_, i) => (
                          <span key={i} className="text-xl">
                            {i < (gameState?.lives ?? 5) ? "❤️" : "🖤"}
                          </span>
                        ))}
                        <span className="ml-2 text-gray-400 text-sm">{gameState?.lives ?? 5} / 5</span>
                      </div>
                    </div>
                    <StatBox label="League Score"   value={(gameState?.final_score ?? 0).toLocaleString()} color="text-yellow-300" />
                    <StatBox label="Shadow Score"   value={(gameState?.shadow_score ?? gameState?.final_score ?? 0).toLocaleString()} color="text-orange-300" />
                    <StatBox label="Tokens Used"    value={(gameState?.tokens_used ?? 0).toLocaleString()} color="text-cyan-400" />
                    <StatBox label="Steps"          value={gameState?.steps_taken ?? 0} color="text-emerald-400" />
                    <StatBox label="Coins"          value={`${gameState?.coins_collected ?? 0}/${totalCoins}`} color="text-yellow-400" />
                    <StatBox label="Challenge Clears" value={`${gameState?.successful_challenges ?? 0}/${totalChallenges}`} color="text-purple-400" />
                    <div className="bg-gray-800 rounded-lg p-3">
                      <div className="text-gray-500 text-xs mb-1">Red Key</div>
                      <div className="text-lg">{gameState?.has_red_key ? "🔑 Collected" : <span className="text-gray-600">Not found</span>}</div>
                    </div>
                    <div className="bg-gray-800 rounded-lg p-3">
                      <div className="text-gray-500 text-xs mb-1">Red Door</div>
                      <div className="text-lg">{gameState?.red_door_unlocked ? "🚪 Unlocked" : <span className="text-gray-600">Still closed</span>}</div>
                    </div>
                  </div>

                  {/* Bonus breakdown */}
                  {gameState && (
                    <div className="bg-gray-800 rounded-lg p-3 space-y-1.5">
                      <div className="text-gray-500 text-xs font-bold uppercase">League Score Breakdown</div>
                      <div className="flex justify-between text-sm"><span className="text-gray-400">Base</span><span className="text-yellow-400">{(scoreBreakdown?.base_score ?? gameState.score).toLocaleString()}</span></div>
                      <div className="flex justify-between text-sm"><span className="text-gray-400">Life bonus (+{Math.max(0,gameState.lives)}×250)</span><span className="text-pink-400">+{(scoreBreakdown?.life_bonus ?? lifeBonus(gameState.lives)).toLocaleString()}</span></div>
                      <div className="flex justify-between text-sm"><span className="text-gray-400">Token bonus</span><span className="text-cyan-400">+{(scoreBreakdown?.token_bonus ?? tokenBonus(gameState.tokens_used, gameState.challenges_visited)).toLocaleString()}</span></div>
                      <div className="border-t border-gray-700 pt-1.5 flex justify-between font-bold"><span className="text-white">Official Final Score</span><span className="text-yellow-300 text-lg">{gameState.final_score.toLocaleString()}</span></div>

                      <div className="pt-3 text-gray-500 text-xs font-bold uppercase border-t border-gray-700">Shadow Bonuses</div>
                      <div className="flex justify-between text-sm"><span className="text-gray-400">Perfect run</span><span className="text-orange-300">+{(scoreBreakdown?.perfect_run_bonus ?? 0).toLocaleString()}</span></div>
                      <div className="flex justify-between text-sm"><span className="text-gray-400">Challenge mastery</span><span className="text-orange-300">+{(scoreBreakdown?.challenge_mastery_bonus ?? 0).toLocaleString()}</span></div>
                      <div className="flex justify-between text-sm"><span className="text-gray-400">Challenge streak</span><span className="text-orange-300">+{(scoreBreakdown?.streak_bonus ?? 0).toLocaleString()}</span></div>
                      <div className="flex justify-between text-sm"><span className="text-gray-400">Coin sweep</span><span className="text-orange-300">+{(scoreBreakdown?.coin_sweep_bonus ?? 0).toLocaleString()}</span></div>
                      <div className="flex justify-between text-sm"><span className="text-gray-400">Efficiency</span><span className="text-orange-300">+{(scoreBreakdown?.efficiency_bonus ?? 0).toLocaleString()}</span></div>
                      <div className="flex justify-between text-sm"><span className="text-gray-400">Full clear</span><span className="text-orange-300">+{(scoreBreakdown?.full_clear_bonus ?? 0).toLocaleString()}</span></div>
                      <div className="border-t border-gray-700 pt-1.5 flex justify-between font-bold"><span className="text-white">Shadow Final Score</span><span className="text-orange-300 text-lg">{(gameState.shadow_score ?? gameState.final_score).toLocaleString()}</span></div>
                    </div>
                  )}
                </div>
              )}

              {/* ── Challenges tab ── */}
              {activeTab === "challenges" && (
                <div className="space-y-3">
                  <div className="flex items-center justify-between mb-2">
                    <span>Challenges encountered this run</span>
                    <span className="text-gray-600">
                      🟡 yellow dots on grid = unvisited challenge cells
                    </span>
                  </div>
                  <ChallengeLog log={challengeLog} />

                  {/* Challenge reference */}
                  <div className="border-t border-gray-700 pt-3 grid grid-cols-3 gap-2 text-xs text-center">
                    {[
                      { cell: "c1",  name: "Guardrail",  pts: 400,  emoji: "💜" },
                      { cell: "c2",  name: "Code",       pts: 600,  emoji: "🧠" },
                      { cell: "c3",  name: "Memory",     pts: 550,  emoji: "🎭" },
                      { cell: "c4",  name: "Web",        pts: 800,  emoji: "🌐" },
                      { cell: "c5",  name: "Simple Q",   pts: 250,  emoji: "🤔" },
                      { cell: "c18", name: "Healthcare", pts: 500,  emoji: "🏥" },
                    ].map(({ cell, name, pts, emoji }) => {
                      const hit  = challengeLog.find(e => e.cell_type === cell);
                      const done = !!hit;
                      return (
                        <div key={cell}
                          className={`rounded-lg p-2 border
                            ${done
                              ? hit?.success ? "border-emerald-700 bg-emerald-900/30" : "border-red-800 bg-red-900/20"
                              : "border-gray-700 bg-gray-800"}`}>
                          <div className="text-xl mb-1">{emoji}</div>
                          <div className="text-gray-300 font-medium">{name}</div>
                          <div className="text-gray-500">+{pts} pts</div>
                          <div className="mt-1 font-bold">
                            {done ? (hit?.success ? "✓ PASS" : "✗ FAIL") : "—"}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* ── History tab ── */}
              {activeTab === "history" && (
                <RunHistoryTable runs={runs} onRefresh={fetchRuns} />
              )}
            </div>
          </div>

          {/* Victory / Game Over banner */}
          {gameState?.game_over && (
            <div className={`rounded-xl border-2 p-5 text-center
              ${gameState.game_won
                ? "border-yellow-400 bg-yellow-900/20"
                : "border-red-600 bg-red-900/20"}`}>
              <div className="text-3xl mb-1">{gameState.game_won ? "🏆 VICTORY!" : "💀 GAME OVER"}</div>
              <div className="text-5xl font-black text-yellow-300 tabular-nums my-2">
                {gameState.final_score.toLocaleString()}
              </div>
              <div className="text-yellow-600 text-xs tracking-widest uppercase">Official Final Score</div>
              <div className="mt-3 text-sm text-orange-300">
                Shadow Score: {(gameState.shadow_score ?? gameState.final_score).toLocaleString()}
              </div>
              <div className="text-gray-600 text-xs">+{(gameState.bonus_score ?? 0).toLocaleString()} simulator-only bonus points</div>
              {gameState.run_id && (
                <div className="text-gray-600 text-xs mt-2">Saved as Run #{gameState.run_id}</div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* ── Scoring reference (full width) ── */}
      <div className="bg-gray-900 border border-gray-700 rounded-xl p-4">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-gray-500 text-xs font-bold uppercase tracking-wider">Scoring Reference</h2>
          <span className="text-gray-600 text-xs">10×10 board • 30 coins + 6 challenges + league and shadow bonuses</span>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-3 text-xs text-center">
          {[
            { emoji:"💎", name:"Treasure",      pts:"+2000",  color:"text-yellow-400", note:"ends game"    },
            { emoji:"🪙", name:"Coin (c7)",     pts:"+250",   color:"text-yellow-400", note:"×30 on map"   },
            { emoji:"🔑", name:"Red Key",       pts:"+50",    color:"text-emerald-400",note:"+ unlocks door"},
            { emoji:"🚪", name:"Red Door",      pts:"+1000",  color:"text-emerald-400",note:"needs key"    },
            { emoji:"🌐", name:"Web (c4)",      pts:"+800",   color:"text-cyan-400",   note:"-1 life fail" },
            { emoji:"🧠", name:"Code (c2)",     pts:"+600",   color:"text-blue-400",   note:"-1 life fail" },
            { emoji:"💜", name:"Guardrail (c1)",pts:"+400",   color:"text-purple-400", note:"-1 life fail" },
            { emoji:"🎭", name:"Memory (c3)",   pts:"+550",   color:"text-violet-400", note:"-1 life fail" },
            { emoji:"🤔", name:"Simple Q (c5)", pts:"+250",   color:"text-sky-400",    note:"-1 life fail" },
            { emoji:"🏥", name:"Healthcare(c18)",pts:"+500",  color:"text-teal-400",   note:"-1 life fail" },
            { emoji:"🔴", name:"Spike (c8)",    pts:"−1 ❤️",  color:"text-red-400",    note:"unavoidable"  },
            { emoji:"❤️", name:"Life bonus",    pts:"+250×",  color:"text-pink-400",   note:"per life left"},
            { emoji:"🧮", name:"Token bonus",   pts:"up to +1000", color:"text-cyan-400", note:"fewer tokens" },
            { emoji:"✨", name:"Perfect run",   pts:"+500",   color:"text-orange-300", note:"shadow bonus" },
            { emoji:"🔥", name:"Streak bonus",  pts:"+150×",  color:"text-orange-300", note:"per chain"     },
            { emoji:"🧹", name:"Coin sweep",    pts:"+750",   color:"text-orange-300", note:"all 30 coins"   },
            { emoji:"🏁", name:"Full clear",    pts:"+1000",  color:"text-orange-300", note:"all 6 challenges"},
            { emoji:"⚡", name:"Efficiency",    pts:"up to +600", color:"text-orange-300", note:"fewer steps" },
          ].map(({ emoji, name, pts, color, note }) => (
            <div key={name} className="bg-gray-800 rounded-lg p-2">
              <div className="text-2xl mb-1">{emoji}</div>
              <div className="text-gray-300 font-medium">{name}</div>
              <div className={`font-bold ${color}`}>{pts}</div>
              <div className="text-gray-600 text-xs">{note}</div>
            </div>
          ))}
        </div>
      </div>
    </main>
  );
}
