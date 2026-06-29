# Boot-to-gameplay navigator bake-off: VLM vs OCR+LLM vs blind ladder (GB / GBA / NDS)

_2026-06-29._

**Question.** From a cold boot, does reading **pixels** (a VLM) or reading **our own symbols** (RapidOCR
text / structural touch-target blobs → a text LLM) get more games into actual gameplay — versus a free
**blind escape-ladder** (the modality-driven button cycler, `core/autoplay.ModalAutoPolicy`)?

**Answer (short).** VLM and OCR+LLM **tie on every console**. A **blind ladder beats both** smart
navigators on button-only consoles (GB, GBA). The navigators only win where they have a capability the
ladder lacks — **touch, on NDS**.

## Setup
- Harness: `eval/bakeoff.py` (the committed navigator harness) driven by a small instrumented runner
  (`scratchpad/bakeoff_run.py`) that adds a per-step modality trace, a `reached` verdict, the full action
  trace, and a captioned strip. One ROM per process; 24 steps each.
- Models: local llama.cpp, free — **Qwen2.5-VL-3B** (`:8080`) for the pixel arm, **Qwen2.5-3B** text
  (`:8081`) for the symbol arm. GB+NDS ran on Windows `.venv-win`; GBA ran in WSL on the `~/gba-spike`
  mgba build.
- ROMs: the menu/title-stuck set per console (`reach_labels.json`, `truth_reached=false`, skipping pure
  "loading" screens a navigator can't help). GB 8, GBA 7, NDS 6 (incl. the touch-primary Phoenix Wright
  & Professor Layton). Policies: `ladder`, `vlm`, `ocr` (NDS uses the touch-capable `nds-vlm` / `nds-ocr`).
- 63 runs total.

## Result — reached gameplay (detector verdict, strip-checked)

| console | ladder | vlm | ocr / blob |
|---|--:|--:|--:|
| **GB** (8) | **5** | 3 | 3 |
| **GBA** (7) | **6** | 3 | 3 |
| **NDS** (6, touch) | 1 | **2** | **2** |

Button-only (GB+GBA combined): **ladder 11/15 (73%)** vs navigators **6/15 (40%)** each. NDS: **ladder
1/6 (17%)** vs **touch-navigators 2/6 (33%)** each. VLM == OCR on **every** console.

## Failure modes
1. **The `a`-collapse (dominant one-shot failure).** Both navigators emit `a`×24 in ~80% of GB/GBA runs —
   a 3B model asked to "advance" defaults to the confirm button. It works *only* on `a`-advanceable menus
   (Cave Noire, Kirby: Nightmare in Dreamland, Naruto, NSMB) and **stalls** on:
   - **Name-entry grids** — Final Fantasy Adventure: `a` just appends letters → "AAAA" forever; the ladder's
     `start`/`right` confirms the default name and escapes. *(strip-verified)*
   - **Cursor / `start` menus** — F-1 Race, Pokémon Gold, Pokémon Emerald, Minish Cap need `right`/`start`;
     `a` stalls.
2. **OCR garbling on pixel fonts.** RapidOCR reads GB/GBA text but it is mostly noise (`"New Game"` →
   `"TNOY"`), so the symbol arm gets no usable signal beyond the VLM → the same `a`-collapse. OCR's symbol
   advantage only appears when the symbol is **clean** — NDS structural blobs, where `nds-ocr` genuinely
   **taps** (tap16–24 per run).
3. **The ladder's own blind spots.** Not magic: it stalls on Mortal Kombat (GB+GBA), Pokémon Red, and the
   touch-primary Phoenix Wright. It mashes a fixed cycle; where that cycle doesn't fit, it stalls too.
4. **Touch payoff and its ceiling.** Touch beats button-only on NDS (`nds-vlm`/`nds-ocr` both reach the
   overworld / main menu where the ladder cannot), but touch-*primary* games with no clean tap target still
   fail (Phoenix Wright: all 3 policies failed).
5. **Detector over-counts.** The pixels-only `reached` verdict counts intros/menus as gameplay (Kirby's
   "reached" is really the file-select menu; FFA ladder's is the intro crawl). The **relative ordering**
   above holds; absolute "reached *actual* gameplay" is lower than the table.

## Reading of the result
The one-shot navigators are **too weak to make "smart pixels vs smart symbols" a meaningful question** — a
3B model `a`-collapses and never notices it's looping. The differentiator that *did* matter was a
**capability** (touch), not a perception channel. Two consequences:
- The **stateful navigators** (`HarnessNavigator`, `ReActNavigator` — already in `core/navigators.py`, with
  stall/loop detection) are the natural next test: they exist precisely to break the `a`-loop by noticing
  "I pressed `a` and nothing changed."
- Touch is worth keeping/expanding (a touch-capable ReAct for NDS is a later step).

## Caveats
3B local models; 24 steps; detector-based `reached` (over-counts; ordering is the trustworthy part);
one human-free run per (ROM, policy) — no repeats, so per-cell noise is real. The ranking is robust; the
exact counts are not.

## Next
- **Follow-up (in progress): the ReAct loop.** Wire `ReActNavigator` into the bake-off (`vlm-react` /
  `ocr-react`) and re-run the GB set — the direct test of whether reasoning-with-memory breaks the
  `a`-collapse on the name-grid / cursor-menu cases.
- Later: touch-capable ReAct for NDS; a larger model; more steps; repeats for error bars.

## Reproduce
```
# GB+NDS (Windows .venv-win): python scratchpad/bakeoff_run.py <console> <rom> <kind> <out.png> <steps> <jsonl>
# GBA (WSL): LD_LIBRARY_PATH=~/gba-spike PYTHONPATH=~/gba-spike/...:<repo>  ~/.venv-bakeoff/bin/python ...
# summarize: python scratchpad/summarize.py results.jsonl results_gba.jsonl
```
Sweep scripts + the instrumented runner live in the session scratchpad; strips in `scratchpad/bakeoff_out/`.
