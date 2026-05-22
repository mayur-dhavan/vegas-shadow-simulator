"""
orchestrator.py — AWS AI League Vegas Shadow Simulator
Multi-turn Bedrock Converse loop with tool routing, mock Guardrail, and AgentCore Memory.
"""

import boto3
import json
import time

from game_engine import GameEngine
from tools.webscraper import lambda_handler as run_scraper
from tools.code_executor import lambda_handler as run_executor
from tools.pathfinder import lambda_handler as run_pathfinder

MODEL_ID = "us.amazon.nova-pro-v1:0"  # Amazon Nova Pro — works with AWS credits, no Marketplace required
# Switch to Anthropic once a credit card is added to the account:
#   us.anthropic.claude-haiku-4-5-20251001-v1:0  (fast)
#   us.anthropic.claude-sonnet-4-5-20250929-v1:0 (best)
MAX_TURNS        = 20
MAIN_TURN_MAX_TOKENS = 350
CHALLENGE_TURN_MAX_TOKENS = 220
MAIN_TURN_RETRY_MAX_TOKENS = 900
CHALLENGE_TURN_RETRY_MAX_TOKENS = 500
MAX_HISTORY_MESSAGES = 6
MAX_HISTORY_CHARS = 6000
MAX_TOOL_RESULT_CHARS = 500
TOOL_USE_ERROR_FRAGMENT = "invalid sequence as part of ToolUse"
# All keywords confirmed from the Bengaluru 2026 competition rules.
GUARDRAIL_KEYWORDS = [
    "illegal", "violence", "violent", "hate", "misconduct",
    "edible flowers", "transplanting", "weeds",
]

CELL_TOKENS = {
    "normal": "..",
    "wall": "##",
    "treasure": "TT",
    "c7": "c7",
    "c8": "c8",
    "c30": "30",
    "c40": "40",
    "c1": "c1",
    "c2": "c2",
    "c3": "c3",
    "c4": "c4",
    "c5": "c5",
    "c18": "18",
}

# Simulated inter-turn delay (seconds).
# Competition Claude 3.5 Sonnet on real AWS infra took 5–8s per call.
# Set BEDROCK_TURN_DELAY > 0 to pad each turn and stretch the run duration.
# Example: BEDROCK_TURN_DELAY = 6 → 20 turns × 6s = up to 120s run time.
BEDROCK_TURN_DELAY = 0  # seconds; 0 = run at full speed (default)

# ---------------------------------------------------------------------------
# Pre-computed challenge answers (avoids hallucination in evaluation)
# ---------------------------------------------------------------------------

def _sum_primes_below(limit: int) -> int:
    """Return sum of all prime numbers strictly below `limit`."""
    sieve = [True] * limit
    sieve[0] = sieve[1] = False
    for i in range(2, int(limit ** 0.5) + 1):
        if sieve[i]:
            for j in range(i * i, limit, i):
                sieve[j] = False
    return sum(i for i, is_prime in enumerate(sieve) if is_prime)

# c2 Code Challenge — expected answer known at startup
_C2_CODE_QUESTION  = (
    "CHALLENGE — Code Challenge: What is the sum of all prime numbers below 100? "
    "Use your code execution tool to calculate it. Respond with ONLY the number."
)
_C2_EXPECTED = str(_sum_primes_below(100))  # "1060"

# c5 Simple Question — straightforward factual
_C5_QUESTION  = "CHALLENGE — Simple Question: How many legs does a spider have? Respond with ONLY the number."
_C5_EXPECTED  = "8"

# c4 Web Search — scrape example.com and answer a question about it
_C4_QUESTION  = (
    "CHALLENGE — Web Search: According to https://example.com, "
    "what is this domain used for? Use your web search tool to find the answer. "
    "Be concise (one sentence)."
)

# c18 Healthcare API — convert sentence to JSON
_C18_INPUT = (
    "Patient ID is P-12345, patient first name is John, last name is Doe, "
    "provider name is Dr. Smith, insurance ID is INS-67890."
)
_C18_QUESTION = (
    f"CHALLENGE — Healthcare API: Convert this patient intake to JSON:\n\n"
    f"'{_C18_INPUT}'\n\n"
    "Output ONLY valid JSON with exactly these keys: "
    "patient_id, first_name, last_name, provider_name, insurance_id"
)
_C18_EXPECTED = {
    "patient_id": "P-12345",
    "first_name": "John",
    "last_name": "Doe",
    "provider_name": "Dr. Smith",
    "insurance_id": "INS-67890",
}


class GuardrailException(Exception):
    """Raised when the mock Bedrock Guardrail blocks a keyword in the system prompt."""


class TournamentOrchestrator:
    """
    Connects the GameEngine to AWS Bedrock (Claude 3.5 Sonnet v2) via the
    Converse API.  Simulates AgentCore Memory by accumulating the full
    conversation history across turns within a single run().

    Usage:
        orch = TournamentOrchestrator()
        state = orch.run(system_prompt, game_map, start_pos)
    """

    def __init__(self):
        self.bedrock_client      = boto3.client("bedrock-runtime", region_name="us-east-1")
        self.tool_config         = self._build_tool_config()
        self.conversation_history: list = []
        self._step_history: list = []   # snapshot after every engine.step()

    # ------------------------------------------------------------------
    # Tool configuration
    # ------------------------------------------------------------------

    def _build_tool_config(self, allowed_tools: list[str] | None = None) -> dict:
        tool_specs = {
            "use_smart_loot": {
                "toolSpec": {
                    "name": "use_smart_loot",
                    "description": "Return the safest path to the treasure. Prefer smart_loot.",
                    "inputSchema": {
                        "json": {
                            "type": "object",
                            "properties": {
                                "game_map": {"type": "array", "description": "2D grid"},
                                "start_pos": {"type": "array", "description": "Current [row, col]"},
                                "strategy": {
                                    "type": "string",
                                    "description": "smart_loot|get_coins|swift",
                                    "enum": ["smart_loot", "get_coins", "swift"],
                                },
                            },
                            "required": ["game_map", "start_pos"],
                        }
                    },
                }
            },
            "scrape_website": {
                "toolSpec": {
                    "name": "scrape_website",
                    "description": "Fetch plain text from a URL.",
                    "inputSchema": {
                        "json": {
                            "type": "object",
                            "properties": {
                                "url": {"type": "string", "description": "URL"}
                            },
                            "required": ["url"],
                        }
                    },
                }
            },
            "execute_code": {
                "toolSpec": {
                    "name": "execute_code",
                    "description": "Run Python and return stdout.",
                    "inputSchema": {
                        "json": {
                            "type": "object",
                            "properties": {
                                "code": {"type": "string", "description": "Python source"}
                            },
                            "required": ["code"],
                        }
                    },
                }
            },
        }

        selected = allowed_tools if allowed_tools is not None else list(tool_specs.keys())
        return {"tools": [tool_specs[name] for name in selected if name in tool_specs]}

    def _converse_with_retry(
        self,
        *,
        messages: list,
        system_prompt: str,
        max_tokens: int,
        retry_max_tokens: int,
        allowed_tools: list[str] | None = None,
    ) -> dict:
        request = {
            "modelId": MODEL_ID,
            "messages": messages,
            "system": [{"text": system_prompt}],
            "inferenceConfig": {"maxTokens": max_tokens, "temperature": 0.0},
        }
        if allowed_tools is not None:
            request["toolConfig"] = self._build_tool_config(allowed_tools)

        try:
            return self.bedrock_client.converse(**request)
        except Exception as exc:
            message = str(exc)
            if allowed_tools is None or TOOL_USE_ERROR_FRAGMENT not in message:
                raise

            retry_request = dict(request)
            retry_request["inferenceConfig"] = {"maxTokens": retry_max_tokens, "temperature": 0.0}
            print(
                f"  [retry] Bedrock tool-use sequence failed at {max_tokens} maxTokens; retrying with {retry_max_tokens}."
            )
            return self.bedrock_client.converse(**retry_request)

    @staticmethod
    def _remaining_cells(engine: GameEngine, targets: set[str]) -> int:
        return sum(cell in targets for row in engine.grid for cell in row)

    @classmethod
    def _compact_grid(cls, engine: GameEngine) -> str:
        player_row, player_col = engine.player_pos
        rows = []
        for row_idx, row in enumerate(engine.grid):
            cells = []
            for col_idx, cell in enumerate(row):
                token = "PL" if (row_idx, col_idx) == (player_row, player_col) else CELL_TOKENS.get(cell, cell[:2])
                cells.append(token)
            rows.append(" ".join(cells))
        return "\n".join(rows)

    @classmethod
    def _compact_state_text(cls, engine: GameEngine, include_grid: bool = False) -> str:
        parts = [
            f"pos={engine.player_pos}",
            f"lives={engine.lives}",
            f"base_score={engine.score}",
            f"final_score={engine.compute_final_score}",
            f"tokens={engine.tokens_used}",
            f"key={'yes' if engine.has_red_key else 'no'}",
            f"coins_left={cls._remaining_cells(engine, {'c7'})}",
            f"challenges_left={cls._remaining_cells(engine, {'c1', 'c2', 'c3', 'c4', 'c5', 'c18'})}",
            f"clears={getattr(engine, 'successful_challenges', 0)}",
        ]
        summary = "State: " + " | ".join(parts)
        if include_grid:
            summary += "\nMap:\n" + cls._compact_grid(engine)
        return summary

    @classmethod
    def _build_navigation_prompt(cls, engine: GameEngine) -> str:
        return (
            "Navigate the dungeon. Call use_smart_loot immediately with strategy='smart_loot'.\n"
            + cls._compact_state_text(engine)
            + "\nGoal: maximize score, preserve lives, and reach the treasure."
        )

    @classmethod
    def _build_challenge_prompt(cls, cell_type: str, question: str, engine: GameEngine) -> str:
        base = cls._compact_state_text(engine)
        if cell_type == "c3":
            return f"{base}\nMap snapshot:\n{cls._compact_grid(engine)}\n\n{question}"
        if cell_type == "c2":
            return f"{question}\nUse execute_code if needed. Return only the final answer."
        if cell_type == "c4":
            return f"{question}\nUse scrape_website if needed. Keep the answer to one sentence."
        if cell_type == "c18":
            return f"{question}\nOutput only the JSON object."
        return f"{base}\n\n{question}"

    @staticmethod
    def _tools_for_challenge(cell_type: str) -> list[str]:
        if cell_type == "c2":
            return ["execute_code"]
        if cell_type == "c4":
            return ["scrape_website"]
        return []

    @staticmethod
    def _clean_text(text: str, limit: int = MAX_TOOL_RESULT_CHARS) -> str:
        return " ".join(str(text).split())[:limit]

    @classmethod
    def _summarize_tool_output(cls, tool_name: str, tool_output: str) -> str:
        if tool_name == "scrape_website":
            return "Website excerpt: " + cls._clean_text(tool_output, 360)
        if tool_name == "execute_code":
            return "Execution result: " + cls._clean_text(tool_output, 140)
        return cls._clean_text(tool_output)

    @classmethod
    def _summarize_path_execution(cls, path: list[str], engine: GameEngine) -> str:
        preview = ", ".join(path[:6])
        if len(path) > 6:
            preview += ", ..."
        return (
            f"Path executed. steps={len(path)}. preview=[{preview}]\n"
            + cls._compact_state_text(engine)
        )

    @staticmethod
    def _message_size(message: dict) -> int:
        return len(json.dumps(message, separators=(",", ":")))

    def _trim_conversation_history(self) -> None:
        while len(self.conversation_history) > MAX_HISTORY_MESSAGES:
            self.conversation_history.pop(0)
        while (
            len(self.conversation_history) > 2
            and sum(self._message_size(message) for message in self.conversation_history) > MAX_HISTORY_CHARS
        ):
            self.conversation_history.pop(0)

    # ------------------------------------------------------------------
    # Mock Bedrock Guardrail (for Violent Violet / c1 challenge)
    # ------------------------------------------------------------------

    def check_guardrail(self, prompt: str) -> None:
        """
        Simulates a Bedrock Guardrail check on the system prompt.
        Raises GuardrailException if any blocked keyword is detected.

        Design intent: competitors whose system prompt contains words like
        "violence" or "illegal" will automatically fail the c1 challenge,
        incentivising clean, safe prompt writing during Build mode.
        """
        lowered = prompt.lower()
        for kw in GUARDRAIL_KEYWORDS:
            if kw in lowered:
                raise GuardrailException(
                    f"[MOCK GUARDRAIL] Blocked keyword detected: '{kw}'. "
                    f"Violent Violet challenge (c1) failed."
                )

    # ------------------------------------------------------------------
    # Challenge outcome helpers
    # ------------------------------------------------------------------

    def challenge_outcome(self, cell_type: str, tool_result: str) -> bool:
        """
        Decides pass/fail for c2 and c4 challenges based on tool output.
        c1 is handled exclusively via check_guardrail().
        """
        lowered = tool_result.lower()

        # Explicit error markers from the Lambda handlers
        if "error" in lowered or "statuscode: 500" in tool_result:
            return False

        if cell_type == "c4":  # Web Search — success if meaningful content returned
            return len(tool_result.strip()) > 50

        if cell_type == "c2":  # Code Challenge — success if no execution error
            return "Execution Error" not in tool_result and "System Error" not in tool_result

        return True

    # ------------------------------------------------------------------
    # Tool routing (local Lambda simulation)
    # ------------------------------------------------------------------

    def _route_tool(self, tool_name: str, inputs: dict) -> str:
        """
        Routes a Bedrock tool call to the appropriate local Lambda handler.
        Returns the response body as a string (may be JSON-encoded for pathfinder).
        """
        if tool_name == "use_smart_loot":
            strategy = inputs.get("strategy", "smart_loot")
            payload  = {
                "game_map":  inputs.get("game_map", []),
                "start_pos": inputs.get("start_pos", [0, 0]),
                "strategy":  strategy,
            }
            result = run_pathfinder(payload, None)
            return result["body"]  # JSON-encoded string — caller must json.loads() it

        elif tool_name == "scrape_website":
            result = run_scraper({"url": inputs.get("url", "")}, None)
            return result["body"]

        elif tool_name == "execute_code":
            result = run_executor({"code": inputs.get("code", "")}, None)
            return result["body"]

        return f"Unknown tool: {tool_name}"

    # ------------------------------------------------------------------
    # Challenge mini-turn (separate Bedrock call per challenge)
    # ------------------------------------------------------------------

    def _run_challenge_turn(
        self, cell_type: str, question: str, system_prompt: str, engine: "GameEngine"
    ) -> tuple[str, dict]:
        """
        Runs a dedicated Bedrock conversation to answer a challenge question.
        The full current game state is included as context so the agent can
        answer memory / map questions without needing external memory.

        Returns (response_text, usage_totals).
        """
        context = self._build_challenge_prompt(cell_type, question, engine)
        messages    = [{"role": "user", "content": [{"text": context}]}]
        total_usage = {"inputTokens": 0, "outputTokens": 0}
        challenge_tools = self._tools_for_challenge(cell_type)

        for _ in range(5):  # max 5 sub-turns per challenge
            resp = self._converse_with_retry(
                messages=messages,
                system_prompt=system_prompt,
                max_tokens=CHALLENGE_TURN_MAX_TOKENS,
                retry_max_tokens=CHALLENGE_TURN_RETRY_MAX_TOKENS,
                allowed_tools=challenge_tools if challenge_tools else None,
            )
            usage = resp.get("usage", {})
            total_usage["inputTokens"]  += usage.get("inputTokens", 0)
            total_usage["outputTokens"] += usage.get("outputTokens", 0)

            msg = resp["output"]["message"]
            messages.append(msg)

            has_tool = False
            for block in msg["content"]:
                if "toolUse" in block:
                    has_tool    = True
                    tool_name   = block["toolUse"]["name"]
                    tool_id     = block["toolUse"]["toolUseId"]
                    inputs      = block["toolUse"]["input"]
                    tool_output = self._route_tool(tool_name, inputs)
                    tool_feedback = self._summarize_tool_output(tool_name, tool_output)
                    messages.append({
                        "role": "user",
                        "content": [{"toolResult": {
                            "toolUseId": tool_id,
                            "content":   [{"text": tool_feedback}],
                        }}]
                    })

            if not has_tool:
                # Extract final text response
                for block in msg["content"]:
                    if "text" in block:
                        return block["text"], total_usage
                return "", total_usage

        return "", total_usage

    # ------------------------------------------------------------------
    # Healthcare JSON validator
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_healthcare_json(response: str) -> bool:
        """Return True if response contains a JSON object with all required healthcare fields."""
        import re
        required = set(_C18_EXPECTED.keys())
        # Pull the first {...} block out of the response
        match = re.search(r"\{[^{}]+\}", response, re.DOTALL)
        if not match:
            return False
        try:
            obj = json.loads(match.group())
            return required.issubset(obj.keys())
        except json.JSONDecodeError:
            return False

    def _handle_challenge(self, cell_type: str, system_prompt: str, engine: GameEngine) -> dict:
        """
        Execute the logic for a challenge cell and call engine.resolve_challenge().

        c1  — Violent Violet  : guardrail keyword check on system_prompt
        c2  — Code Challenge  : Bedrock call → agent uses execute_code tool
        c3  — Memory Trial    : Bedrock call → agent counts map cells from state
        c4  — Web Search      : Bedrock call → agent uses scrape_website tool
        c5  — Simple Question : Bedrock call → agent answers a factual question
        c18 — Healthcare API  : Bedrock call → agent outputs structured JSON
        """
        if cell_type == "c1":
            try:
                self.check_guardrail(system_prompt)
                success = True
                print("  [c1] Guardrail check passed — Violent Violet cleared!")
            except GuardrailException as exc:
                success = False
                print(f"  [c1] {exc}")

        elif cell_type == "c2":
            response, usage = self._run_challenge_turn("c2", _C2_CODE_QUESTION, system_prompt, engine)
            engine.record_tokens(usage["inputTokens"], usage["outputTokens"])
            success = _C2_EXPECTED in response.replace(",", "").replace(" ", "")
            print(f"  [c2] Code Challenge — {'PASS' if success else 'FAIL'} "
                  f"(expected: {_C2_EXPECTED}, got: {response[:80]!r})")

        elif cell_type == "c3":
            spike_count = sum(1 for row in engine.grid for cell in row if cell == "c8")
            question = (
                f"CHALLENGE — Memory Trial: How many c8 spike traps are currently on the dungeon map? "
                f"Reply with ONLY the number."
            )
            response, usage = self._run_challenge_turn("c3", question, system_prompt, engine)
            engine.record_tokens(usage["inputTokens"], usage["outputTokens"])
            success = str(spike_count) in response.strip()
            print(f"  [c3] Memory Trial — {'PASS' if success else 'FAIL'} "
                  f"(expected: {spike_count}, got: {response[:80]!r})")

        elif cell_type == "c4":
            response, usage = self._run_challenge_turn("c4", _C4_QUESTION, system_prompt, engine)
            engine.record_tokens(usage["inputTokens"], usage["outputTokens"])
            lowered = response.lower()
            success = (len(response.strip()) > 40
                       and "error" not in lowered
                       and "cannot" not in lowered)
            print(f"  [c4] Web Search — {'PASS' if success else 'FAIL'} "
                  f"({len(response)} chars returned)")

        elif cell_type == "c5":
            response, usage = self._run_challenge_turn("c5", _C5_QUESTION, system_prompt, engine)
            engine.record_tokens(usage["inputTokens"], usage["outputTokens"])
            success = _C5_EXPECTED in response.strip()
            print(f"  [c5] Simple Question — {'PASS' if success else 'FAIL'} "
                  f"(expected: {_C5_EXPECTED}, got: {response[:80]!r})")

        elif cell_type == "c18":
            response, usage = self._run_challenge_turn("c18", _C18_QUESTION, system_prompt, engine)
            engine.record_tokens(usage["inputTokens"], usage["outputTokens"])
            success = self._validate_healthcare_json(response)
            print(f"  [c18] Healthcare API — {'PASS' if success else 'FAIL'} "
                  f"(response: {response[:80]!r})")

        else:
            success = False
            print(f"  [?] Unknown challenge cell: {cell_type}")

        return engine.resolve_challenge(cell_type, success)

    # ------------------------------------------------------------------
    # Path execution
    # ------------------------------------------------------------------

    def _execute_path(self, path: list, engine: GameEngine, system_prompt: str) -> None:
        """
        Walks through each move in path, calling engine.step() for each.
        Inline challenge handling ensures challenges are resolved before
        the next step — critical for c30 (Red Door) to be passable after c40.
        """
        for move in path:
            if engine.game_over:
                break
            effect = engine.step(move)
            print(f"    → step({move!r:6}) cell={effect.get('cell','?'):10} "
                  f"effect={effect.get('effect','?'):10} "
                  f"score={engine.score:5}  lives={engine.lives}")
            if effect.get("effect") == "challenge":
                self._handle_challenge(effect["cell"], system_prompt, engine)
            self._step_history.append(engine.get_state())  # snapshot after every step
            if engine.game_over:
                break

    # ------------------------------------------------------------------
    # Main synchronous run loop
    # ------------------------------------------------------------------

    def run(self, system_prompt: str, game_map: list, start_pos: list) -> dict:
        """
        Full tournament run.

        1. Initialises a fresh GameEngine.
        2. Runs the Bedrock Converse loop (max MAX_TURNS turns).
        3. On each turn where Claude calls use_smart_loot, the returned path
           is executed step-by-step through the GameEngine.
        4. Returns the final game state dict from engine.get_state().

        The conversation_history accumulates all turns within this run,
        simulating AgentCore persistent memory so Claude can refer back to
        earlier tool results when planning subsequent moves.
        """
        engine = GameEngine(game_map=game_map, start_pos=start_pos)
        self.conversation_history = []
        self._step_history = []

        first_message = {
            "role": "user",
            "content": [{
                "text": self._build_navigation_prompt(engine)
            }]
        }
        self.conversation_history.append(first_message)
        print(f"Tournament Run — model: {MODEL_ID}")
        print(f"Start: {start_pos}  |  Lives: {engine.lives}  |  Score: {engine.score}")
        print(f"{'='*60}\n")

        for turn in range(MAX_TURNS):
            if engine.game_over:
                break

            print(f"--- Bedrock Turn {turn + 1} ---")

            # Pad turn duration to simulate real AWS Bedrock API latency.
            # Competition Claude 3.5 Sonnet took 5–8s/call; Nova Pro takes <1s.
            turn_start = time.time()
            response = self._converse_with_retry(
                messages=self.conversation_history,
                system_prompt=system_prompt,
                max_tokens=MAIN_TURN_MAX_TOKENS,
                retry_max_tokens=MAIN_TURN_RETRY_MAX_TOKENS,
                allowed_tools=["use_smart_loot", "scrape_website", "execute_code"],
            )

            # Track token usage for Token Bonus calculation
            usage = response.get("usage", {})
            engine.record_tokens(
                input_tokens=usage.get("inputTokens", 0),
                output_tokens=usage.get("outputTokens", 0),
            )

            # Pad to simulated turn duration if configured
            elapsed = time.time() - turn_start
            if BEDROCK_TURN_DELAY > 0 and elapsed < BEDROCK_TURN_DELAY:
                time.sleep(BEDROCK_TURN_DELAY - elapsed)
            print(f"  Tokens this turn: in={usage.get('inputTokens',0)}  "
                  f"out={usage.get('outputTokens',0)}  "
                  f"total={engine.tokens_used}")

            output_message = response["output"]["message"]
            self.conversation_history.append(output_message)

            tool_used = False
            for block in output_message["content"]:
                if "toolUse" not in block:
                    if "text" in block:
                        print(f"  Claude: {block['text'][:200]}")
                    continue

                tool_used     = True
                tool_use      = block["toolUse"]
                tool_name     = tool_use["name"]
                tool_id       = tool_use["toolUseId"]
                inputs        = tool_use["input"]

                print(f"  Tool call: {tool_name}")

                # For pathfinding, always use actual engine state — never trust
                # what the model extracted (it may pass stale/wrong map or position).
                if tool_name == "use_smart_loot":
                    tool_output = self._route_tool(tool_name, {
                        "game_map":  [row[:] for row in engine.grid],
                        "start_pos": list(engine.player_pos),
                        "strategy":  "smart_loot",
                    })
                else:
                    tool_output = self._route_tool(tool_name, inputs)

                # If Claude asked for a path, execute it on the GameEngine
                if tool_name == "use_smart_loot":
                    try:
                        path_data = json.loads(tool_output)
                        path      = path_data.get("path", [])
                        print(f"  Path returned: {len(path)} steps — {path}")
                        self._execute_path(path, engine, system_prompt)
                        tool_feedback = self._summarize_path_execution(path, engine)
                    except (json.JSONDecodeError, KeyError) as exc:
                        print(f"  [ERROR] Failed to parse pathfinder output: {exc}")
                        tool_feedback = self._clean_text(tool_output)
                else:
                    tool_feedback = self._summarize_tool_output(tool_name, tool_output)

                # Feed tool result back into history (AgentCore Memory pattern)
                self.conversation_history.append({
                    "role": "user",
                    "content": [{
                        "toolResult": {
                            "toolUseId": tool_id,
                            "content":   [{"text": tool_feedback}],
                        }
                    }]
                })
                self._trim_conversation_history()

            if not tool_used:
                print("  Claude finished without calling more tools.")
                break

        print(f"\n{'='*60}")
        final = engine.get_state()
        final["step_history"] = self._step_history
        print(f"Run complete — game_won={final['game_won']}  "
              f"game_over={final['game_over']}  "
              f"final_score={final['final_score']}  "
              f"steps={len(self._step_history)}")
        print(f"{'='*60}\n")
        return final


    # ------------------------------------------------------------------
    # Streaming generator (used by FastAPI /run/stream)
    # ------------------------------------------------------------------

    def run_step(self, system_prompt: str, game_map: list, start_pos: list):
        """
        Generator version of run() that yields engine.get_state() after every
        single engine.step() call.  Designed for use with FastAPI StreamingResponse.

        Because boto3's converse() is synchronous, each Bedrock call blocks until
        it returns — the generator only yields between individual path steps, not
        between Bedrock turns.  For the tournament scope this is sufficient.
        """
        engine = GameEngine(game_map=game_map, start_pos=start_pos)
        self.conversation_history = []

        initial_state = engine.get_state()
        yield initial_state  # Yield starting state immediately

        self.conversation_history.append({
            "role": "user",
            "content": [{
                "text": self._build_navigation_prompt(engine)
            }]
        })

        for _turn in range(MAX_TURNS):
            if engine.game_over:
                break

            response = self._converse_with_retry(
                messages=self.conversation_history,
                system_prompt=system_prompt,
                max_tokens=MAIN_TURN_MAX_TOKENS,
                retry_max_tokens=MAIN_TURN_RETRY_MAX_TOKENS,
                allowed_tools=["use_smart_loot", "scrape_website", "execute_code"],
            )

            usage = response.get("usage", {})
            engine.record_tokens(
                input_tokens=usage.get("inputTokens", 0),
                output_tokens=usage.get("outputTokens", 0),
            )

            output_message = response["output"]["message"]
            self.conversation_history.append(output_message)

            tool_used = False
            for block in output_message["content"]:
                if "toolUse" not in block:
                    continue

                tool_used   = True
                tool_use    = block["toolUse"]
                tool_name   = tool_use["name"]
                tool_id     = tool_use["toolUseId"]
                inputs      = tool_use["input"]
                tool_output = self._route_tool(tool_name, inputs)

                if tool_name == "use_smart_loot":
                    try:
                        path = json.loads(tool_output).get("path", [])
                        tool_feedback = self._summarize_tool_output(tool_name, tool_output)
                    except (json.JSONDecodeError, KeyError):
                        path = []
                        tool_feedback = self._clean_text(tool_output)

                    for move in path:
                        if engine.game_over:
                            break
                        effect = engine.step(move)
                        if effect.get("effect") == "challenge":
                            self._handle_challenge(effect["cell"], system_prompt, engine)
                        yield engine.get_state()
                    tool_feedback = self._summarize_path_execution(path, engine)
                else:
                    tool_feedback = self._summarize_tool_output(tool_name, tool_output)

                self.conversation_history.append({
                    "role": "user",
                    "content": [{
                        "toolResult": {
                            "toolUseId": tool_id,
                            "content":   [{"text": tool_feedback}],
                        }
                    }]
                })
                self._trim_conversation_history()

            if not tool_used:
                break

        yield engine.get_state()  # Always yield final state


# ------------------------------------------------------------------
# Quick self-test (run: python orchestrator.py)
# Requires valid AWS credentials and Bedrock access in us-east-1.
# ------------------------------------------------------------------

if __name__ == "__main__":
    from game_engine import DEFAULT_MAP

    SYSTEM_PROMPT = (
        "You are an expert dungeon navigator for the AWS AI League tournament. "
        "Your goal is to reach the treasure while maximising score and preserving lives. "
        "Always call use_smart_loot first with strategy='smart_loot' to get the safest path. "
        "If the path is blocked or the game state changes, call use_smart_loot again with "
        "the updated player position. Never stop until game_over is True."
    )

    orch  = TournamentOrchestrator()
    state = orch.run(
        system_prompt=SYSTEM_PROMPT,
        game_map=DEFAULT_MAP,
        start_pos=[0, 0],
    )

    print("Final state:")
    for k, v in state.items():
        if k != "grid":
            print(f"  {k}: {v}")
