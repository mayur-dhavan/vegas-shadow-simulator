# System Context: AWS AI League - Vegas Shadow Simulator (Full Tournament Edition)

## Overview
I am preparing for the AWS AI League 2026 Global Finals. I need a local "Shadow Simulator" combining a Next.js frontend and a Python `boto3` backend (Bedrock/Claude 3.5 Sonnet v2). The simulator must recreate the "Dungeons of Agentic Interactions" engine, the Bedrock AgentCore/Guardrails, and strictly enforce the 3-phase tournament rules.

## The 3-Phase Tournament Architecture
The Next.js UI must have a dropdown to switch between these three modes, changing the timer and lock states:
1. **Phase 1: Build Mode (3 Hours):** - Timer counts down from 3:00:00.
   - Code is unlocked. Agent runs are unlimited. Used to test basic tool connections (AgentCore Memory, Bedrock Guardrails, Lambda tools).
2. **Phase 2: Semi-Final Mode (6 Minutes):** - Timer counts down from 06:00.
   - Goal: Maximize score. The user can run the agent, watch it on the grid, and if it fails, hit "Stop", hot-fix the Python backend code, and "Rerun".
3. **Phase 3: Live Finale Mode (45 Seconds):** - Timer counts down from 00:45.
   - **CRITICAL:** Backend code is assumed LOCKED. The UI only provides a `<textarea>` for the system prompt. Exactly when the timer hits 00:00, the text area disables, and the prompt is automatically POSTed to the backend for execution.

## The Game Engine Rules & Scoring
The engine tracks Lives (max 5), Score (start 0), Tokens Used, and Challenges Visited. 
`Final Score = Base Points + Token Bonus + Life Bonus`
- **Treasure (`treasure`):** Ends game. +2000 points.
- **Coins (`c7`):** +250 points.
- **Spike Trap (`c8`):** -1 Life if stepped on.
- **Red Door (`c30`):** -5 Lives if hit without Red Key (`c40`). +1000 points when unlocked.
- **Red Key (`c40`):** Requires AgentCore Memory. +50 points.
- **Web Search (`c4`):** +800 points for success, -1 Life for failure.
- **Code Challenge (`c2`):** +600 points for success, -1 Life for failure.
- **Violent Violet (`c1`):** Tests Bedrock Guardrails (blocking violence/illegal activity). +400 points, -1 Life for failure.
- **Life Bonus:** +250 points per remaining life.
- **Token Bonus:** `1000 - (Total Tokens Used / Challenges Visited)`.

## Current Backend Architecture
- **Model:** `anthropic.claude-3-5-sonnet-20241022-v2:0` via Bedrock Converse API.
- **Tools:** `use_smart_loot` (Pathfinder), `scrape_website` (c4), `execute_code` (c2).
- **Guardrails:** A mock layer in Python that intercepts prompts before Bedrock and throws a Guardrail exception if "illegal", "violence", or "edible flowers" are mentioned (for the c1 challenge).

## Goal for Copilot
1. **Build `game_engine.py`:** A robust Python class tracking the 2D grid state, applying the point/life logic, and tracking the token economics from the Bedrock responses.
2. **Build `orchestrator.py`:** The multi-turn `boto3` Bedrock execution loop. It must handle tool-calling, inject a mock Bedrock Guardrail check, and manage AgentCore Memory (simulated by maintaining a persistent conversation history array).
3. **Build the Next.js UI (`page.tsx`):** A React dashboard with:
   - A Mode Selector (Build, Semi-Final, Finale).
   - The corresponding strict countdown timer.
   - A visual 2D grid rendering the game map using emojis or colored divs.
   - Real-time tally of Lives, Tokens, and Total Score.
   - A System Prompt input box that enforces the lockout rules of Phase 3.
