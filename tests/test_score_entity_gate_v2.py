"""Unit tests for eval/score_entity_gate_v2.py — the consequence-anchored BACKWARD-attribution entity
gate (v2; v1's forward contact-prediction FAILED live and stays on the books). Builds small synthetic
transcript.jsonl + oracle.jsonl fixtures (no real MCP run needed) to pin the ENT/NEAR/DECLARE/REJECT
parser, the watermark, the WINDOW=15 coverage math, the q_k/b_k/margin test, and the PASS/FAIL/
INSUFFICIENT_DROPS/INSUFFICIENT_DATA/NO_DECLARE verdicts at the pinned constants (margin=0.30,
min_near=3, min_session_drops=5, min_total_steps=30). Mirrors tests/test_score_entity_gate.py's style."""
from __future__ import annotations

import json
import tempfile

from eval.score_entity_gate_v2 import (
    MARGIN,
    MIN_NEAR,
    MIN_SESSION_DROPS,
    MIN_TOTAL_STEPS,
    RETROACTIVE_MAX_FRACTION,
    WINDOW,
    _bcd,
    _coverage,
    _drop_steps,
    parse_transcript,
    score,
)

SERVER = "mcp__cave-noire-gate"


def _remember_pair(call_id: str, lesson: str) -> list[dict]:
    return [
        {"message": {"content": [{"type": "tool_use", "id": call_id, "name": f"{SERVER}__remember",
                                  "input": {"lesson": lesson}}]}},
        {"message": {"content": [{"type": "tool_result", "tool_use_id": call_id, "content": "ok"}]}},
    ]


def _reveal_pair(call_id: str, step: int, tool: str = "whats_changed") -> list[dict]:
    """A world-observation tool call + its result reporting `step=<N>` — advances the retroactive
    guard's revealed-step watermark, the way a real observe/read_region/whats_changed result does."""
    return [
        {"message": {"content": [{"type": "tool_use", "id": call_id, "name": f"{SERVER}__{tool}",
                                  "input": {"x0": 0, "y0": 0, "x1": 8, "y1": 8}}]}},
        {"message": {"content": [{"type": "tool_result", "tool_use_id": call_id,
                                  "content": [{"type": "text",
                                               "text": f"[{tool} step={step} (0,0)-(8,8): unchanged]"}]}]}},
    ]


def _raw(hp: int) -> int:
    """int hp -> BCD-encoded raw byte (10 -> 0x10, 7 -> 0x07)."""
    return ((hp // 10) << 4) | (hp % 10)


def _oracle_rec(step: int, hp_raw: int) -> dict:
    return {"step": step, "t": 1_000_000.0 + step, "watch": {"hp": hp_raw}}


def _write_jsonl(path, records) -> str:
    p = str(path)
    with open(p, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    return p


def _run_score(transcript, oracle):
    with tempfile.TemporaryDirectory() as d:
        tp = _write_jsonl(f"{d}/transcript.jsonl", transcript)
        op = _write_jsonl(f"{d}/oracle.jsonl", oracle)
        return score(tp, op)


# ---------------------------------------------------------------------------
# Shared session fixture: oracle over steps 1..98 (97 scoreable, steps 2..98), one hp point lost at
# each drop step. DROPS_5 = {19, 38, 57, 76, 97} -> 5 drop steps, 92 non-drop scoreable steps.
# ---------------------------------------------------------------------------

DROPS_5 = (19, 38, 57, 76, 97)


def _oracle_98(drop_at=DROPS_5):
    oracle = []
    hp = 10
    for step in range(1, 99):
        if step in drop_at:
            hp -= 1
        oracle.append(_oracle_rec(step, _raw(hp)))
    return oracle


def _near_calls(eid: int, steps, prefix: str) -> list[dict]:
    calls = []
    for i, s in enumerate(steps):
        calls += _remember_pair(f"{prefix}{i}", f"NEAR id={eid} step={s}")
    return calls


def _declares() -> list[dict]:
    return (_remember_pair("d1", "DECLARE threat=1")
            + _remember_pair("d2", "REJECT id=2 reason=never near me before a drop"))


# Benign id=2 NEARs at steps 1..3: matched, accepted, but too early for any window to reach the first
# drop step (19 - WINDOW = 4 > 3) -> q=0, correctly rejected.
BENIGN_EARLY = (1, 2, 3)


# ---------------------------------------------------------------------------
# 1. Parser: ENT / NEAR / DECLARE / REJECT extraction + dedupe.
# ---------------------------------------------------------------------------

def test_parse_ent_line():
    transcript = _remember_pair("t1", "ENT id=1 region=(40,60,56,76) step=5 claim=threat")
    parsed = parse_transcript(transcript, [])
    e = parsed["ent_claims"][1][0]
    assert e["region"] == (40, 60, 56, 76) and e["step"] == 5 and e["claim"] == "threat"


def test_parse_near_line_matched_and_deduped():
    transcript = (
        _remember_pair("t1", "NEAR id=2 step=10")
        + _remember_pair("t2", "NEAR id=2 step=10")   # exact repeat: dedupe, first wins
        + _remember_pair("t3", "NEAR id=2 step=11")
    )
    oracle = [_oracle_rec(9, 5), _oracle_rec(10, 3), _oracle_rec(11, 3)]
    parsed = parse_transcript(transcript, oracle)
    entries = parsed["nears"][2]
    assert len(entries) == 2
    assert entries[0]["step"] == 10 and entries[0]["matched"] is True
    assert parsed["duplicates"] == 1


def test_parse_declare_threat_benign_and_reject():
    transcript = (
        _remember_pair("t1", "DECLARE threat=1")
        + _remember_pair("t2", "DECLARE benign=2")
        + _remember_pair("t3", "REJECT id=3 reason=never near before a drop")
    )
    parsed = parse_transcript(transcript, [])
    assert parsed["declared_threats"] == {1}
    assert parsed["declared_benign"] == {2}
    assert parsed["rejected"][3] == "never near before a drop"


def test_bcd_decode():
    assert _bcd(0x00) == 0
    assert _bcd(0x07) == 7
    assert _bcd(0x10) == 10


def test_unmatched_near_step_has_no_oracle_row():
    transcript = _remember_pair("t1", "NEAR id=1 step=99")
    oracle = [_oracle_rec(1, 5)]
    parsed = parse_transcript(transcript, oracle)
    assert parsed["nears"][1][0]["matched"] is False


# ---------------------------------------------------------------------------
# 2. Watermark (retroactive-NEAR guard): strictly-greater, identical rule to v1's CONTACT guard.
# ---------------------------------------------------------------------------

def test_near_at_exactly_the_revealed_step_is_not_retroactive():
    """The reveal rule is STRICTLY-greater: the result reporting step n is what gives the brain the
    step number to log at all, so a NEAR at the current revealed step must count."""
    transcript = _reveal_pair("r1", 7) + _remember_pair("c1", "NEAR id=1 step=7")
    parsed = parse_transcript(transcript, [_oracle_rec(7, 5)])
    assert parsed["retroactive"] == 0
    assert len(parsed["nears"][1]) == 1


def test_near_logged_after_a_later_step_is_retroactive():
    """Watermark > n -> the brain has already seen step n's consequence -> RETROACTIVE, excluded."""
    transcript = _reveal_pair("r1", 8) + _remember_pair("c1", "NEAR id=1 step=7")
    parsed = parse_transcript(transcript, [_oracle_rec(7, 5)])
    assert parsed["retroactive"] == 1
    assert 1 not in parsed["nears"]


def test_real_read_region_and_whats_changed_texts_advance_the_watermark():
    """The REAL wire shapes (verbatim from world_mcp.py's _read_region/_whats_changed text) must
    advance the watermark — these are the only tools that report `step=<N>` to the brain."""
    read_region_text = ("[read_region step=42 (0,125)-(64,138), upscaled 3x — when logging a reading "
                        "of this image, use this exact step: HYP region=(0,125,64,138) step=42 "
                        "reading=<value>]")
    whats_changed_text = ("[whats_changed step=44 (vs step=43) (0,125)-(64,138): changed "
                          "(mean-abs-diff=5.31)]")
    transcript = [
        {"message": {"content": [{"type": "tool_use", "id": "r1", "name": f"{SERVER}__read_region",
                                  "input": {"x0": 0, "y0": 125, "x1": 64, "y1": 138}}]}},
        {"message": {"content": [{"type": "tool_result", "tool_use_id": "r1",
                                  "content": [{"type": "text", "text": read_region_text}]}]}},
        {"message": {"content": [{"type": "tool_use", "id": "w1", "name": f"{SERVER}__whats_changed",
                                  "input": {"x0": 0, "y0": 125, "x1": 64, "y1": 138}}]}},
        {"message": {"content": [{"type": "tool_result", "tool_use_id": "w1",
                                  "content": [{"type": "text", "text": whats_changed_text}]}]}},
    ]
    transcript += _remember_pair("c1", "NEAR id=1 step=43")   # watermark is 44 > 43 -> retroactive
    parsed = parse_transcript(transcript, [_oracle_rec(43, 5)])
    assert parsed["retroactive"] == 1
    assert 1 not in parsed["nears"]


def test_real_bare_observe_text_does_not_advance_the_watermark():
    """A REAL bare observe() result (perception_plugin._render_symbolic's text, entities line included)
    carries NO step token — world_mcp's _content() serializes only obs.text and drops obs.data["step"].
    The watermark therefore does NOT advance on bare observe. Documented residual leak (PR #61 finding
    2): self-mitigating because step numbers reach the brain ONLY via read_region/whats_changed, which
    DO advance it — an accurate `NEAR ... step=n` implies the watermark already reached n; a guessed
    step lands in the unmatched guard. Do not 'fix' this test by fabricating a payload shape the
    harness never emits."""
    observe_text = ("Your position (dead-reckoned, approximate): (3, 4).\n"
                    "Last move 'up' -> moved.\n"
                    "Unexplored/open directions from here (head toward these to make progress): up, left.\n"
                    "Cells explored in this area so far: 12.\n"
                    "Entities on screen (sprites/enemies/items): 2 at (40,60), (81,22).")
    observe_pair = [
        {"message": {"content": [{"type": "tool_use", "id": "o1", "name": f"{SERVER}__observe",
                                  "input": {}}]}},
        {"message": {"content": [{"type": "tool_result", "tool_use_id": "o1",
                                  "content": [{"type": "text", "text": observe_text}]}]}},
    ]
    transcript = observe_pair + _remember_pair("c1", "NEAR id=1 step=5")
    parsed = parse_transcript(transcript, [_oracle_rec(5, 5)])
    assert parsed["retroactive"] == 0        # watermark never advanced -> nothing to be retroactive to
    assert len(parsed["nears"][1]) == 1


def test_pure_retroactive_transcript_gets_no_verdict():
    """The exploit shape v1's guard was built for: observe the whole session first (watermark at the
    end), THEN back-tag NEARs onto the drop-adjacent steps. Every NEAR is retroactive -> tainted."""
    calls = _reveal_pair("r_end", 98)   # outcome of every step now observable
    calls += _near_calls(1, (18, 37, 56, 75, 96), "c1_")
    calls += _near_calls(2, BENIGN_EARLY, "c2_")
    calls += _declares()
    result = _run_score(calls, _oracle_98())
    assert result["retroactive_lines"] == 8
    assert result["verdict"] == "INSUFFICIENT_DATA"
    assert "RETROACTIVE" in result["reason"]


def test_mixed_retroactive_below_cap_is_reported_but_verdict_stands():
    """A few retroactive lines strictly below the 20% cap are excluded + reported; the verdict from
    the legitimate prospective majority stands."""
    calls = []
    for s in (18, 37, 56, 75, 96):
        calls += _reveal_pair(f"r{s}", s)
        calls += _remember_pair(f"c1_{s}", f"NEAR id=1 step={s}")
    # benign logged prospectively too (before any reveal advanced past their steps is not needed —
    # they were logged first): rebuild with benign first so the watermark (max 96) can't taint them.
    calls = _near_calls(2, BENIGN_EARLY, "c2_") + calls
    # one retroactive back-tag after the last reveal: 1 retro / (8 accepted + 1) = 11.1% < 20%
    calls += _remember_pair("late", "NEAR id=1 step=18")
    calls += _declares()
    result = _run_score(calls, _oracle_98())
    assert result["retroactive_lines"] == 1
    assert (result["retroactive_lines"] / (result["retroactive_lines"] + 8)) < RETROACTIVE_MAX_FRACTION
    assert result["verdict"] == "PASS"


# ---------------------------------------------------------------------------
# 3. Window coverage: s-15 covers, s-16 does not, s itself covers.
# ---------------------------------------------------------------------------

def test_window_boundary_near_at_s_minus_window_covers():
    entries = [{"step": 100 - WINDOW, "matched": True}]
    assert _coverage(entries, {100}) == 1


def test_window_boundary_near_at_s_minus_window_minus_one_does_not_cover():
    entries = [{"step": 100 - WINDOW - 1, "matched": True}]
    assert _coverage(entries, {100}) == 0


def test_window_boundary_near_at_s_itself_covers():
    entries = [{"step": 100, "matched": True}]
    assert _coverage(entries, {100}) == 1


def test_unmatched_near_never_covers():
    entries = [{"step": 100, "matched": False}]
    assert _coverage(entries, {100}) == 0


# ---------------------------------------------------------------------------
# 4. _drop_steps (identical machinery to v1, re-pinned here).
# ---------------------------------------------------------------------------

def test_drop_steps_basic():
    hp_by_step = {1: 10, 2: 10, 3: 8, 4: 8, 5: 5}
    drops, n_with_prior = _drop_steps(hp_by_step)
    assert drops == {3, 5}
    assert n_with_prior == 4


def test_drop_steps_gap_breaks_prior_chain():
    hp_by_step = {1: 10, 2: None, 3: 8}
    drops, n_with_prior = _drop_steps(hp_by_step)
    assert drops == set()
    assert n_with_prior == 0


# ---------------------------------------------------------------------------
# 5. score(): PASS / FAIL / margin boundary / spam exploit.
# ---------------------------------------------------------------------------

def test_score_pass_threat_grounds_and_benign_rejected():
    """Threat NEAR one step before each of the 5 drops: q=5/5=1.0; its windows cover 62/92 non-drop
    steps -> b~0.674; 1.0 >= 0.674+0.30 -> GROUNDED. Benign's early NEARs cover no drop -> rejected."""
    calls = _near_calls(1, (18, 37, 56, 75, 96), "c1_")
    calls += _near_calls(2, BENIGN_EARLY, "c2_")
    calls += _declares()
    result = _run_score(calls, _oracle_98())
    assert result["verdict"] == "PASS"
    assert result["arm_a"] is True and result["arm_b"] is True
    t = result["threat_scores"][1]
    assert t["q_k"] == 1.0 and t["grounded"] is True
    b = result["benign_scores"][2]
    assert b["q_k"] == 0.0 and b["insufficient"] is False


def test_score_fail_when_threat_does_not_ground():
    """Threat's NEARs sit far from every drop -> q=0 -> arm (a) fails -> FAIL (not INSUFFICIENT)."""
    calls = _near_calls(1, BENIGN_EARLY, "c1_")   # early steps: threat's windows reach no drop
    calls += _near_calls(2, (5, 6, 7), "c2_")     # benign covers drop 19 (q=0.2) but stays under the bar
    calls += _declares()
    result = _run_score(calls, _oracle_98())
    assert result["verdict"] == "FAIL"
    assert result["arm_a"] is False


def test_margin_boundary_q_exactly_b_plus_margin_grounds():
    """Engineered so q_k == b_k + MARGIN exactly: threat NEARs at drop steps 19, 38, 57 (each window
    [n, n+15] covers its drop + 15 non-drop steps) and at 97 (covers drop 97 + non-drop 98 only).
    q = 4/5 = 0.8; b = (15*3 + 1)/92 = 46/92 = 0.5; 0.8 >= 0.5 + 0.30 must ground (>=, not >)."""
    calls = _near_calls(1, (19, 38, 57, 97), "c1_")
    calls += _near_calls(2, BENIGN_EARLY, "c2_")
    calls += _declares()
    result = _run_score(calls, _oracle_98())
    t = result["threat_scores"][1]
    assert abs(t["q_k"] - 0.8) < 1e-9
    assert abs(t["b_k"] - 0.5) < 1e-9
    assert abs(t["q_k"] - (t["b_k"] + MARGIN)) < 1e-9
    assert t["grounded"] is True
    assert result["verdict"] == "PASS"


def test_spam_near_every_step_self_defeats():
    """The obvious exploit: log NEAR id=1 at EVERY step -> q=1.0 but b -> 1.0 too, the margin cannot
    clear -> not grounded (this is the reason b_k's denominator is the non-drop steps)."""
    calls = _near_calls(1, range(1, 99), "c1_")
    calls += _near_calls(2, BENIGN_EARLY, "c2_")
    calls += _declares()
    result = _run_score(calls, _oracle_98())
    t = result["threat_scores"][1]
    assert t["q_k"] == 1.0
    assert t["b_k"] == 1.0
    assert t["grounded"] is False
    assert result["verdict"] == "FAIL"


# ---------------------------------------------------------------------------
# 6. Verdict guards: NO_DECLARE / INSUFFICIENT_DROPS / INSUFFICIENT_DATA / benign evidence floor.
# ---------------------------------------------------------------------------

def test_score_no_declare_without_threat():
    calls = _remember_pair("c", "NEAR id=1 step=1") + _remember_pair("b", "DECLARE benign=2")
    result = _run_score(calls, [_oracle_rec(1, 5)])
    assert result["verdict"] == "NO_DECLARE"


def test_score_no_declare_without_benign_or_reject():
    calls = _near_calls(1, (18, 37, 56, 75, 96), "c1_")
    calls += _remember_pair("d1", "DECLARE threat=1")
    result = _run_score(calls, _oracle_98())
    assert result["verdict"] == "NO_DECLARE"
    assert "benign" in result["reason"]


def test_insufficient_drops_at_four_drops():
    """4 drop steps < MIN_SESSION_DROPS=5 -> INSUFFICIENT_DROPS, no PASS/FAIL computed (the fix for
    v1's 2-drop starvation)."""
    assert MIN_SESSION_DROPS == 5
    four = (19, 38, 57, 76)
    calls = _near_calls(1, (18, 37, 56, 75), "c1_")
    calls += _near_calls(2, BENIGN_EARLY, "c2_")
    calls += _declares()
    result = _run_score(calls, _oracle_98(drop_at=four))
    assert result["session_drop_steps"] == 4
    assert result["verdict"] == "INSUFFICIENT_DROPS"


def test_insufficient_data_too_few_total_steps():
    oracle = [_oracle_rec(s, _raw(10 - (s // 5))) for s in range(1, MIN_TOTAL_STEPS)]  # < 30 scoreable
    calls = _near_calls(1, (4, 9, 14), "c1_") + _near_calls(2, (1, 2, 3), "c2_") + _declares()
    result = _run_score(calls, oracle)
    assert result["verdict"] == "INSUFFICIENT_DATA"
    assert "scoreable oracle steps" in result["reason"]


def test_too_many_unmatched_near_steps_is_insufficient_data():
    calls = _near_calls(1, (18, 37, 56, 75, 96), "c1_")
    calls += _near_calls(2, BENIGN_EARLY, "c2_")
    calls += _near_calls(1, range(9000, 9005), "bad_")   # 5 unmatched of 13 >> 5%
    calls += _declares()
    result = _run_score(calls, _oracle_98())
    assert result["verdict"] == "INSUFFICIENT_DATA"
    assert result["unmatched_lines"] == 5


def test_too_many_malformed_lines_is_insufficient_data():
    calls = _near_calls(1, (18, 37, 56, 75, 96), "c1_")
    calls += _near_calls(2, BENIGN_EARLY, "c2_")
    calls += _declares()
    for i in range(20):
        calls += _remember_pair(f"m{i}", "NEAR id=garbled step=notanumber")
    result = _run_score(calls, _oracle_98())
    assert result["malformed_lines"] == 20
    assert result["verdict"] == "INSUFFICIENT_DATA"


def test_benign_with_too_few_nears_not_counted_as_correctly_rejected():
    """A benign entity with < MIN_NEAR accepted NEARs is INSUFFICIENT — it cannot supply arm (b), so a
    run whose only benign is under-evidenced gets INSUFFICIENT_DATA, not a cheap PASS."""
    calls = _near_calls(1, (18, 37, 56, 75, 96), "c1_")
    calls += _near_calls(2, BENIGN_EARLY[:MIN_NEAR - 1], "c2_")   # only 2 NEARs for the benign
    calls += _declares()
    result = _run_score(calls, _oracle_98())
    assert result["benign_scores"][2]["insufficient"] is True
    assert result["verdict"] == "INSUFFICIENT_DATA"


def test_conflicting_declaration_excluded_from_both_arms():
    """An id declared BOTH threat and benign/REJECTed is CONFLICTING (PR #61 finding 4): excluded from
    both arms and reported, while the consistent declarations still produce a verdict."""
    calls = _near_calls(1, (18, 37, 56, 75, 96), "c1_")   # consistent threat, grounds
    calls += _near_calls(2, BENIGN_EARLY, "c2_")          # consistent benign, correctly rejected
    calls += _near_calls(3, (5, 6, 7), "c3_")             # the conflicted id, with plenty of NEARs
    calls += _declares()
    calls += _remember_pair("d3a", "DECLARE threat=3")
    calls += _remember_pair("d3b", "REJECT id=3 reason=changed my mind")
    result = _run_score(calls, _oracle_98())
    assert result["conflicting_declarations"] == [3]
    assert 3 not in result["threat_scores"]
    assert 3 not in result["benign_scores"]
    assert result["verdict"] == "PASS"


def test_conflicting_declaration_starving_an_arm_is_no_declare():
    """If excluding the conflicted id leaves an arm with no declared id at all, the verdict is
    NO_DECLARE (the contradiction cannot supply either arm), with the conflict named in the reason."""
    calls = _near_calls(1, (18, 37, 56, 75, 96), "c1_")
    calls += _remember_pair("d1", "DECLARE threat=1")
    calls += _remember_pair("d2", "REJECT id=1 reason=second thoughts")   # same id: conflict
    result = _run_score(calls, _oracle_98())
    assert result["conflicting_declarations"] == [1]
    assert result["verdict"] == "NO_DECLARE"
    assert "CONFLICTING" in result["reason"]
