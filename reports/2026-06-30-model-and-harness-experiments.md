# Navigator follow-ups: ReAct, a variant bake-off, and the model-vs-harness question

_2026-06-30._

Follow-up to [`reports/2026-06-29-navigator-bakeoff.md`](2026-06-29-navigator-bakeoff.md) (the GB/GBA/NDS
VLM-vs-OCR+LLM boot-to-gameplay bake-off, where a blind escape-ladder beat both LLM navigators on the
button consoles and the dominant failure was the **`a`-collapse** — a 3B model mashing `a`×24 on hard menus).
This report records the four follow-up experiments and their central conclusion.

## TL;DR — the `a`-collapse is the HARNESS, not the model
The one-shot navigator (`max_tokens=8`, "reply with one button word") makes a small model emit `a`×24 on
name-grids / cursor-menus. We tested whether a *better model* fixes it: **Qwen3-VL-4B (newer generation,
larger) collapses identically** (`ax24/1u`) and ties-or-trails the 2.5-VL-3B on the GB set. So model
generation/scale (3B→4B) is **not** the lever — the crippled one-shot harness is. Reasoning-room (ReAct)
breaks the collapse *behaviorally* but doesn't convert at small scale. The structured blind ladder (free
System-1) stays champion (5/8). The conclusive frontier-model test (Claude on the *same* harness) is built
and ready, blocked only on a live API key.

## Experiment 1 — ReAct (stateful reasoning), local 3B
Wired `ReActNavigator` (one Thought/Action/Observation conversation, stall/loop detection) into the bake-off
(`vlm-react`/`ocr-react`). GB: **vlm-react 3/8 = vlm one-shot 3/8; ocr-react 2/8.** It breaks the `a`-collapse
(distinct buttons 1→3–7) but **explores without converting** — wanders FFA's name grid (Boy→Girl) without
finding "End". Its memory is a sliding 8-turn window with **no durable lessons**. Strip-verified; the detector
`reached` over-counts intros/menus.

## Experiment 2 — three improvement variants (from a 4-lens ideation fan-out)
Four parallel agents (memory/learning · prompting/priors · hybrid-structure · perception) ranked cheap,
testable ideas; we built + benchmarked the top three. **None beat the ladder (5/8):**

| variant | GB reached/8 | what happened |
|---|--:|---|
| `ladder-llm` (ladder default; wake LLM only on a novelty-stall) | 4 | runs at ~2 LLM wakes/run, but a stall-correction *derails* a ladder win (Sword of Hope II) → net −1 |
| `vlm-prime` / `ocr-prime` (port the missing UI priors + rotate the `or "a"` fallback) | 2 / 1 | **backfired** — the "prefer start" prior traded the `a`-collapse for a `start`-collapse (`startx24/1u`) |
| `vlm-mem` (`core/outcome.OutcomeMemory` dead-button ledger + lesson scratchpad) | 2/6* | the ledger broke the collapse (4–6 distinct buttons) but didn't convert; the **3B authored ZERO lessons** |

*2 ROMs timed out (slow ReAct path). Lessons: **naive fixes just *move* the mode** (a→start); **a model too
weak to navigate is too weak to author lessons** (explore yes, learn no). Code: `core/navigators.py`
(`LadderLLMNavigator`, `MemNavigator`, a `primed` flag), `eval/bakeoff.py` kinds, `tests/test_navigator_variants.py`
— built by a Sonnet agent, **452 suite green, but UNCOMMITTED**.

## Experiment 3 — model swaps (binding constraint: the GPU is an RTX 3080, 10 GB)
- **Qwen3-VL-4B** (official GGUF + mmproj, runs on the today-dated llama.cpp `25a1d63`): one-shot `vlm` **2/8**,
  `vlm-react` **2/8** — ≈ or below the 2.5-VL-3B (3/8 each), **identical failure modes**. Generation/scale is
  not the lever; makes us *less* optimistic 8B would crack it.
- **UI-TARS-2B-SFT** (a GUI-grounding *specialist*, 1.1 GB Q4): hosted via a **borrowed Qwen2-VL-2B mmproj**
  (UI-TARS GGUF repos ship none; the base's vision tower matches, so it loads). **Grounding verified precise** —
  asked to point at "New Game" on a 160×144 *monochrome* GB menu (its worst case) it lands dead-on (normalized
  0–1000 coords; needs `--image-min-tokens 1024`). Paradigm fits **NDS touch** directly (`click(x,y)`≈`touch`);
  GB/GBA buttons need a ground→dpad/hotkey bridge (**not yet built** — the open work toward "UI-TARS for all
  use cases").

## Experiment 4 — frontier model on the same harness (built; pending auth)
`scratchpad/claude_test.py` monkeypatches LiteLLM so `anthropic/*` calls use the env key, then runs the
**exact** `VLMNavigator`/`ReActNavigator` against `claude-sonnet-4-6` on FFA+Gold. SSL workaround
(`litellm.ssl_verify=False` — this machine can't verify public TLS certs) and auth-routing both proven.
**Blocked**: the `ai-aria/.env` key is a well-formed `sk-ant-api` key (len 108) that Anthropic rejects as
invalid (revoked/expired). The moment a live `ANTHROPIC_API_KEY` is in the env, this fires — the conclusive
harness-vs-model test. Predicted tell: one-shot Claude *still* one-buttons → it's the harness; Claude+ReAct
reaches gameplay → the small models were just too weak.

## Synthesis — where the lever actually is
Not a bigger/newer general model (3B→4B is flat). The promising paths:
1. **Keep the structured ladder** as the cheap System-1 floor (5/8, ~0 cost).
2. **A grounding specialist (UI-TARS-2B) in a proper harness** — cheap, precise grounding; natural for NDS
   touch; needs the button-bridge for GB/GBA. The open build.
3. Fold the one mechanical win — the **dead-button ledger** (forced diversity) — into the ladder.

## Operational state (READ before continuing)
- **Where things run:** GB+NDS on **Windows `.venv-win`** (pyboy + py-desmume + litellm + rapidocr [added via
  uv] + pytest 9.0.3); **GBA in WSL `~/.venv-bakeoff`** (uv, py3.11) + `~/gba-spike` mgba via
  `LD_LIBRARY_PATH=~/gba-spike` + `PYTHONPATH=~/gba-spike/mgba-build/python/lib.linux-x86_64-3.8` (abi3 on 3.11).
- **Models** in `/home/nvidia/models/` (WSL, user `nvidia`): original `Qwen2.5-VL-3B-Instruct-Q4_K_M`+mmproj +
  `qwen2.5-3b-instruct` (text); `UI-TARS-2B-SFT-Q4_K_M` + `mmproj-Qwen2-VL-2B-Instruct-F16`;
  `Qwen3VL-4B-Instruct-Q4_K_M` + `mmproj-Qwen3VL-4B-Instruct-F16`. All fit 10 GB one-or-two at a time.
- **⚠ SERVER STATE CHANGED:** `Qwen3-VL-4B` is on `:8080`; the **original two 3B servers are STOPPED**. Restore
  (both from `~/llama.cpp/build/bin/`):
  - `:8080` — `llama-server -m Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf --mmproj mmproj-Qwen2.5-VL-3B-Instruct-f16.gguf -ngl 99 --host 127.0.0.1 --port 8080 -c 4096 --no-webui`
  - `:8081` — `llama-server -m qwen2.5-3b-instruct-q4_k_m.gguf -ngl 99 --host 127.0.0.1 --port 8081 -c 4096 --no-webui`
- **Cert issue:** this machine's Python can't verify public TLS certs → set `litellm.ssl_verify=False` (or fix
  the CA store / use `truststore`) for any cloud-LLM call.

## Reproduce
Session-local scratchpad tooling: `bakeoff_run.py` (instrumented runner: action trace + modality + reached +
strip), `summarize.py`/`cmp*.py` (tables), the GB/GBA/NDS sweep scripts, `claude_test.py`, the WSL host/download
scripts. Strips + `results*.jsonl` in `scratchpad/bakeoff_out/`. Model picks + VRAM fit:
[`2026-06-30`] RTX 3080 10 GB — Qwen3-VL (2B/4B/8B) and UI-TARS (2B/7B) all fit at Q4.
