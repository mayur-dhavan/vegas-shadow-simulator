"""
game_engine.py — AWS AI League Vegas Shadow Simulator
Tracks 2D grid state, applies point/life logic, and records token economics.
"""

DIRECTION_DELTAS = {
    "up":    (-1,  0),
    "down":  ( 1,  0),
    "left":  ( 0, -1),
    "right": ( 0,  1),
}

MAX_LIVES = 5
CHALLENGE_CELLS  = {"c1", "c2", "c3", "c4", "c5", "c18"}
CHALLENGE_POINTS = {"c1": 400, "c2": 600, "c3": 550, "c4": 800, "c5": 250, "c18": 500}
SHADOW_BONUS_RULES = {
    "perfect_run_bonus": 500,
    "challenge_mastery_per_success": 100,
    "streak_bonus_per_chain": 150,
    "coin_sweep_bonus": 750,
    "efficiency_max_bonus": 600,
    "efficiency_step_penalty": 6,
    "full_clear_bonus": 1000,
}

# 10×10 tournament map. Player starts [0,0], treasure at [4,9].
# 30 coin cells (c7) × 250 = 7,500 pts from coins alone.
# All 6 challenge types are present, along with the red key / red door flow.
# The treasure is only reachable through the red door at [4,8].
DEFAULT_MAP = [
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
]   # Total: 30 c7 coins, 6 challenges, 3 spikes, 10 walls


class GameEngine:
    """
    Maintains all mutable game state for a single tournament run.

    The grid is mutated in place as the agent moves:
    - Collected coins / keys become "normal".
    - Unlocked red doors become "normal".
    Challenge cells (c1/c2/c4) are cleared only after resolve_challenge() is called,
    so a crash during challenge resolution leaves the cell intact for a retry.
    """

    def __init__(self, game_map=None, start_pos=None):
        # Deep copy so that the caller's original map is never mutated,
        # which would otherwise break the Semi-Final "Rerun" flow.
        source = game_map if game_map is not None else DEFAULT_MAP
        self.grid = [row[:] for row in source]
        self.rows = len(self.grid)
        self.cols = len(self.grid[0]) if self.rows else 0

        self.player_pos = list(start_pos) if start_pos is not None else [0, 0]

        self.lives              = MAX_LIVES
        self.score              = 0
        self.tokens_used        = 0
        self.challenges_visited = 0
        self.has_red_key        = False
        self.game_over          = False
        self.game_won           = False
        self.steps_taken        = 0
        self.coins_collected    = 0
        self.successful_challenges = 0
        self.failed_challenges     = 0
        self.challenge_streak      = 0
        self.max_challenge_streak  = 0
        self.unlocked_red_doors    = 0
        self.initial_coin_count    = sum(cell == "c7" for row in self.grid for cell in row)
        self.initial_challenge_count = sum(cell in CHALLENGE_CELLS for row in self.grid for cell in row)
        self._pending_challenge = None  # Set when standing on c1/c2/c4
        self.challenge_log: list = []   # Records each challenge outcome for DB + UI

    # ------------------------------------------------------------------
    # Public movement API
    # ------------------------------------------------------------------

    def step(self, direction: str) -> dict:
        """
        Attempt to move one cell in `direction`.

        Returns a result dict with keys:
            moved         (bool)
            reason        (str)   — populated when moved=False
            cell          (str)   — cell type entered
            effect        (str)   — "normal"|"damage"|"death"|"win"|"challenge"
            score_delta   (int)
            lives_delta   (int)
            pending_challenge (str|None)
        """
        if self.game_over:
            return {"moved": False, "reason": "game_over",
                    "cell": "", "effect": "game_over",
                    "score_delta": 0, "lives_delta": 0,
                    "pending_challenge": None}

        dr, dc = DIRECTION_DELTAS.get(direction, (0, 0))
        nr, nc = self.player_pos[0] + dr, self.player_pos[1] + dc

        if not (0 <= nr < self.rows and 0 <= nc < self.cols):
            return {"moved": False, "reason": "out_of_bounds",
                    "cell": "", "effect": "blocked",
                    "score_delta": 0, "lives_delta": 0,
                    "pending_challenge": None}

        if self.grid[nr][nc] == "wall":
            return {"moved": False, "reason": "wall",
                    "cell": "wall", "effect": "blocked",
                    "score_delta": 0, "lives_delta": 0,
                    "pending_challenge": None}

        self.player_pos = [nr, nc]
        self.steps_taken += 1
        result = self._apply_cell_effect(self.grid[nr][nc], nr, nc)

        # Dead check — happens AFTER applying the effect so lives_delta is
        # already reflected in result before we set game_over.
        if self.lives <= 0:
            self.game_over = True
            result["effect"] = "death"

        result["moved"] = True
        result["reason"] = ""
        return result

    # ------------------------------------------------------------------
    # Challenge resolution (called by orchestrator after c1/c2/c4 step)
    # ------------------------------------------------------------------

    def resolve_challenge(self, cell_type: str, success: bool) -> dict:
        """
        Apply the outcome of a challenge.
        Marks the current cell as 'normal' so it isn't re-triggered.
        """
        r, c = self.player_pos

        if success:
            points = CHALLENGE_POINTS.get(cell_type, 0)
            self.score += points
            self.successful_challenges += 1
            self.challenge_streak += 1
            self.max_challenge_streak = max(self.max_challenge_streak, self.challenge_streak)
            result = {"success": True, "score_delta": points, "lives_delta": 0}
        else:
            self.lives -= 1
            self.failed_challenges += 1
            self.challenge_streak = 0
            if self.lives <= 0:
                self.game_over = True
            result = {"success": False, "score_delta": 0, "lives_delta": -1}

        # Clear the cell regardless of outcome so re-entry is harmless.
        self.grid[r][c] = "normal"
        self._pending_challenge = None

        # Record in challenge log for DB persistence and UI display.
        self.challenge_log.append({
            "cell_type":   cell_type,
            "success":     success,
            "score_delta": result["score_delta"],
            "lives_delta": result["lives_delta"],
            "streak":      self.challenge_streak,
        })
        return result

    # ------------------------------------------------------------------
    # Token tracking
    # ------------------------------------------------------------------

    def record_tokens(self, input_tokens: int, output_tokens: int) -> None:
        """Record token usage from a single Bedrock converse() call."""
        self.tokens_used += input_tokens + output_tokens

    # ------------------------------------------------------------------
    # Score computation
    # ------------------------------------------------------------------

    @property
    def league_score_breakdown(self) -> dict:
        """
        Official competition score.

        Life Bonus  = lives × 250
        Token Bonus = max(0,  1000 − (tokens_used // challenges_visited))
                      (0 challenges → full 1000 bonus)
        """
        life_bonus  = max(0, self.lives) * 250
        token_bonus = max(0, 1000 - (self.tokens_used // max(self.challenges_visited, 1)))
        final_score = self.score + life_bonus + token_bonus
        return {
            "base_score": self.score,
            "life_bonus": life_bonus,
            "token_bonus": token_bonus,
            "final_score": final_score,
        }

    @property
    def shadow_score_breakdown(self) -> dict:
        """Simulator-only bonus score layered on top of league scoring."""
        perfect_run_bonus = (
            SHADOW_BONUS_RULES["perfect_run_bonus"]
            if self.game_won and self.lives == MAX_LIVES
            else 0
        )
        challenge_mastery_bonus = (
            self.successful_challenges * SHADOW_BONUS_RULES["challenge_mastery_per_success"]
        )
        streak_bonus = max(0, self.max_challenge_streak - 1) * SHADOW_BONUS_RULES["streak_bonus_per_chain"]
        coin_sweep_bonus = (
            SHADOW_BONUS_RULES["coin_sweep_bonus"]
            if self.initial_coin_count > 0 and self.coins_collected == self.initial_coin_count
            else 0
        )
        efficiency_bonus = max(
            0,
            SHADOW_BONUS_RULES["efficiency_max_bonus"]
            - (self.steps_taken * SHADOW_BONUS_RULES["efficiency_step_penalty"]),
        )
        full_clear_bonus = (
            SHADOW_BONUS_RULES["full_clear_bonus"]
            if self.game_won
            and self.initial_challenge_count > 0
            and self.successful_challenges == self.initial_challenge_count
            else 0
        )

        bonus_score = (
            perfect_run_bonus
            + challenge_mastery_bonus
            + streak_bonus
            + coin_sweep_bonus
            + efficiency_bonus
            + full_clear_bonus
        )
        return {
            "perfect_run_bonus": perfect_run_bonus,
            "challenge_mastery_bonus": challenge_mastery_bonus,
            "streak_bonus": streak_bonus,
            "coin_sweep_bonus": coin_sweep_bonus,
            "efficiency_bonus": efficiency_bonus,
            "full_clear_bonus": full_clear_bonus,
            "bonus_score": bonus_score,
            "shadow_final_score": self.compute_final_score + bonus_score,
        }

    @property
    def compute_final_score(self) -> int:
        return self.league_score_breakdown["final_score"]

    @property
    def compute_shadow_score(self) -> int:
        return self.shadow_score_breakdown["shadow_final_score"]

    # ------------------------------------------------------------------
    # State snapshot
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        """Return a JSON-serialisable snapshot of all game state."""
        league_breakdown = self.league_score_breakdown
        shadow_breakdown = self.shadow_score_breakdown
        return {
            "grid":               [row[:] for row in self.grid],
            "player_pos":         list(self.player_pos),
            "lives":              self.lives,
            "score":              self.score,
            "tokens_used":        self.tokens_used,
            "challenges_visited": self.challenges_visited,
            "has_red_key":        self.has_red_key,
            "game_over":          self.game_over,
            "game_won":           self.game_won,
            "steps_taken":        self.steps_taken,
            "coins_collected":    self.coins_collected,
            "initial_coin_count": self.initial_coin_count,
            "successful_challenges": self.successful_challenges,
            "failed_challenges":  self.failed_challenges,
            "max_challenge_streak": self.max_challenge_streak,
            "initial_challenge_count": self.initial_challenge_count,
            "total_coins":        self.initial_coin_count,
            "total_challenges":   self.initial_challenge_count,
            "red_door_unlocked":  bool(self.unlocked_red_doors),
            "final_score":        league_breakdown["final_score"],
            "shadow_score":       shadow_breakdown["shadow_final_score"],
            "league_score_breakdown": league_breakdown,
            "bonus_score":        shadow_breakdown["bonus_score"],
            "shadow_final_score": shadow_breakdown["shadow_final_score"],
            "shadow_score_breakdown": shadow_breakdown,
            "pending_challenge":  self._pending_challenge,
            "challenge_log":      list(self.challenge_log),
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _apply_cell_effect(self, cell: str, row: int, col: int) -> dict:
        """
        Mutates score/lives/grid according to which cell the player entered.
        Does NOT set game_over (that is checked in step() after return).
        """
        base = {"cell": cell, "effect": "normal", "score_delta": 0, "lives_delta": 0,
                "pending_challenge": None}

        if cell == "normal":
            pass  # nothing to do

        elif cell == "treasure":
            self.score   += 2000
            self.game_won = True
            self.game_over = True
            base.update({"effect": "win", "score_delta": 2000})

        elif cell == "c7":  # Coin
            self.score += 250
            self.coins_collected += 1
            self.grid[row][col] = "normal"
            base.update({"effect": "collect", "score_delta": 250})

        elif cell == "c8":  # Spike Trap
            self.lives -= 1
            base.update({"effect": "damage", "lives_delta": -1})

        elif cell == "c30":  # Red Door
            if self.has_red_key:
                self.score += 1000
                self.unlocked_red_doors += 1
                self.grid[row][col] = "normal"
                base.update({"effect": "unlock", "score_delta": 1000})
            else:
                self.lives -= 5
                base.update({"effect": "damage", "lives_delta": -5})

        elif cell == "c40":  # Red Key
            self.score      += 50
            self.has_red_key = True
            self.grid[row][col] = "normal"
            base.update({"effect": "collect", "score_delta": 50})

        elif cell in CHALLENGE_CELLS:  # c1, c2, c3, c4, c5, c18
            self.challenges_visited  += 1
            self._pending_challenge   = cell
            base.update({"effect": "challenge", "pending_challenge": cell})

        return base


# ------------------------------------------------------------------
# Quick self-test (run: python game_engine.py)
# ------------------------------------------------------------------

if __name__ == "__main__":
    print("=== GameEngine self-test ===\n")
    engine = GameEngine()

    # Walk a simple path: right → right → right (collect c7 at [0,1], skip to c40 at [0,3])
    moves = ["right", "right", "right"]
    for m in moves:
        result = engine.step(m)
        print(f"  step({m!r:6}) → cell={result['cell']!r:10} effect={result['effect']!r:10} "
              f"score={engine.score:4}  lives={engine.lives}")

    print(f"\n  has_red_key = {engine.has_red_key}")

    # Trigger a spike trap via left from [0,3] back through [0,2], [0,1], then down to [1,0] (c1)
    spike_path = ["down", "left", "left", "left"]  # [0,3]→[1,3]→[1,2]→[1,1] (wall)
    for m in spike_path:
        result = engine.step(m)
        print(f"  step({m!r:6}) → cell={result['cell']!r:10} effect={result['effect']!r:10} "
              f"score={engine.score:4}  lives={engine.lives}  moved={result['moved']}")

    print(f"\n  Final state preview:")
    state = engine.get_state()
    for k, v in state.items():
        if k != "grid":
            print(f"    {k}: {v}")

    print(f"\n  compute_final_score = {engine.compute_final_score}")
    print("\n=== Test complete ===")
