"""Gate 0 precondition 4a -- token -> normalized-credit conversion, pinned at signature time.

PR #118 precondition-4 ruling (4a): "token->normalized-credit conversion pinned for the exact
model (gpt-5.6-sol) per design doc:297-300, wired in front of run_breaker()." This module IS that
wiring. It deliberately does NOT hardcode a dollar rate anywhere -- see the investigation below.

## What Codex CLI actually emits (verified zero-spend, 2026-07-21)

`tools/gate0_credit_breaker.py` already documented that the official token->credit rate is an
open pin (design doc:297-300: "pin the official Codex token-credit rate ... confirm the official
`25 credits = $1.00` equivalence"). Before inventing a shim for "whatever Codex reports", this
module's author checked what codex-cli 0.144.3 (the pinned Gate 0 version, `codex doctor` on the
launch machine, 2026-07-21) actually emits, WITHOUT spending anything:

- `codex exec --help` documents `--json`: "Print events to stdout as JSONL".
- Codex's own on-disk session rollouts (`~/.codex/sessions/**/*.jsonl`, pre-existing paid history
  already on this machine -- reading them spends nothing new) show the event shape directly. Every
  rollout contains `event_msg` entries whose `payload.type == "token_count"` carries:
    `info.total_token_usage`  -- CUMULATIVE for the whole session
    `info.last_token_usage`   -- this turn's DELTA (confirmed empirically: summing successive
                                  `last_token_usage.total_tokens` reproduces the running
                                  `total_token_usage.total_tokens`; `total_tokens ==
                                  input_tokens + output_tokens`, i.e. `cached_input_tokens` is a
                                  priced-differently SUBSET of `input_tokens` and
                                  `reasoning_output_tokens` a subset of `output_tokens`, never
                                  additional tokens)
    `rate_limits.credits`     -- an object `{has_credits, unlimited, balance}`, OBSERVED on this
                                  ChatGPT-subscription (plan_type "plus", auth "chatgpt") account
                                  as `{"has_credits": false, "unlimited": false, "balance": "0"}`.
  `TOKEN_FIELDS` in `tools/check_gate0_codex.py` (already committed, independent of this file)
  matches this exact 4-field shape (`input_tokens, cached_input_tokens, output_tokens,
  reasoning_output_tokens`), corroborating the schema this module targets.

**Conclusion: the CLI does NOT hand back a usable normalized-credit number for the Gate 0
ChatGPT-subscription auth mode.** `rate_limits.credits` is a balance/entitlement object, not a
per-turn spend figure, and reports no credits available on this plan. Only raw token counts are
observable. Per this task's own instruction: "if only tokens, the token->credit rate CANNOT be
invented -- make it an explicit signature-time pin field (rate_source required, fail-closed if
absent)". That is exactly what `load_credit_rate_pin()` below enforces: it refuses to run unless a
human-authored rate-pin JSON exists, names its evidence (`rate_source`), and matches the exact
model being launched. No dollar figure is hardcoded anywhere in this module.

The `--json` stdout envelope for a live `codex exec --json` run was NOT independently re-verified
here (that would require an actual paid exec, forbidden for this build). The extraction below
handles both a bare `{"type": "token_count", ...}` line and one wrapped as `{"msg": {"type":
"token_count", ...}}` (the shape codex-rs's own rollout persistence uses for the same struct) --
whichever the live stream turns out to use, the accountant will find it; a line matching neither
shape is treated as a zero-credit pass-through event (see `codex_event_to_credit_event`), never a
fabricated credit delta.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

# Design doc:297-300 names this token/field vocabulary; kept identical to
# tools/check_gate0_codex.py::TOKEN_FIELDS so the two never drift apart.
TOKEN_FIELDS = ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens")

# Required at signature time. `rate_source` is mandatory prose citing WHERE the dollar-per-token
# numbers came from (an OpenAI pricing page, an invoice, a support confirmation, ...) -- an empty
# or missing rate_source is refused, never defaulted to "trust me". The three usd_per_* fields
# price input, cached input, and output tokens separately because OpenAI prices them separately;
# reasoning_output_tokens is a priced-as-output SUBSET of output_tokens (see module docstring), so
# it does not get its own rate field -- inventing a distinct reasoning rate not evidenced by the
# CLI would be exactly the kind of guess this module exists to forbid.
REQUIRED_RATE_FIELDS = (
    "model",
    "rate_source",
    "credits_per_usd",
    "usd_per_input_token",
    "usd_per_cached_input_token",
    "usd_per_output_token",
)
_NUMERIC_RATE_FIELDS = (
    "credits_per_usd",
    "usd_per_input_token",
    "usd_per_cached_input_token",
    "usd_per_output_token",
)
_USD_PER_TOKEN_FIELDS = ("usd_per_input_token", "usd_per_cached_input_token", "usd_per_output_token")

# PR #122 review Finding 3 / coordinator M3 fix: a positive-but-absurd rate silently defeats the
# 250-credit ceiling in either direction. Reproduced by the reviewer: 1e-12 $/token (a plausible
# units mistake -- e.g. quoting a per-1K- or per-1M-token price as a per-token price) makes the
# ceiling need ~2.5 BILLION turns to reach, i.e. effectively unreachable in any real run; a rate
# 10x too high makes a single trivial 10-token turn alone trip instantly (safe but wastes the one
# pre-registered attempt). These bounds are deliberately wide -- six orders of magnitude around
# real 2026-era frontier-model pricing (roughly $0.0000005-$0.0002 per token, i.e. $0.50-$200 per
# million tokens) -- so a genuine future price change is never blocked, while a >=100x units error
# in either direction is refused. A field pinned exactly to 0.0 is exempt (a genuine "this token
# class is free" tier is a legitimate price, not a units bug -- only a NONZERO-but-astronomically-
# tiny value is the error signature this guards against). `credits_per_usd`'s band brackets the
# design doc's pinned "25 credits = $1.00" (reports/2026-07-13-minimum-north-star-gate-0-design.md:
# 297-300) with the same generosity. Invoke-BreakerSupervisedExec's MaxWallClockS (3600s default,
# tools/run_gate0_codex.ps1) remains a SEPARATE, independent backstop for a rate that is
# implausible-but-still-inside this band -- this check does not replace it, only narrows the gap.
MIN_USD_PER_TOKEN = 1e-8   # $0.01 / million tokens
MAX_USD_PER_TOKEN = 1e-2   # $10,000 / million tokens
MIN_CREDITS_PER_USD = 1
MAX_CREDITS_PER_USD = 1000


class CreditRateNotPinned(Exception):
    """Fail-closed refusal: the paid launcher may not start without a valid, human-signed rate
    pin. Never caught to fall back to a guessed rate -- the caller must refuse to launch."""


def load_credit_rate_pin(path: Path, expected_model: str) -> dict:
    """Load and validate the signature-time credit-rate pin. Raises CreditRateNotPinned for every
    failure mode (missing file, malformed JSON, missing/non-numeric field, empty rate_source, or a
    model mismatch) -- there is no partial-success path."""
    if not path.is_file():
        raise CreditRateNotPinned(f"rate_pin_missing:{path}")
    try:
        # utf-8-sig, not utf-8: strips a leading byte-order mark if present (byte-identical to
        # utf-8 otherwise). Not exploitable today -- the launcher always writes this file itself
        # via Write-Utf8NoBom, confirmed BOM-free -- but matches the same defensive read the
        # credit-event stream reader in gate0_credit_accountant.py already uses, for the same
        # hard-won reason (review MINOR, PR #122).
        pin = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise CreditRateNotPinned(f"rate_pin_unreadable:{path}") from exc
    if not isinstance(pin, dict):
        raise CreditRateNotPinned("rate_pin_not_object")
    missing = [field for field in REQUIRED_RATE_FIELDS if field not in pin]
    if missing:
        raise CreditRateNotPinned(f"rate_pin_missing_fields:{','.join(missing)}")
    if not isinstance(pin["rate_source"], str) or not pin["rate_source"].strip():
        raise CreditRateNotPinned("rate_pin_empty_rate_source")
    for field in _NUMERIC_RATE_FIELDS:
        value = pin[field]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value or value < 0:
            raise CreditRateNotPinned(f"rate_pin_invalid_field:{field}")
    if pin["credits_per_usd"] <= 0:
        raise CreditRateNotPinned("rate_pin_nonpositive_credits_per_usd")
    for field in _USD_PER_TOKEN_FIELDS:
        value = pin[field]
        if value != 0 and not (MIN_USD_PER_TOKEN <= value <= MAX_USD_PER_TOKEN):
            raise CreditRateNotPinned(f"rate_pin_implausible_field:{field}")
    if not (MIN_CREDITS_PER_USD <= pin["credits_per_usd"] <= MAX_CREDITS_PER_USD):
        raise CreditRateNotPinned("rate_pin_implausible_field:credits_per_usd")
    if not isinstance(pin["model"], str) or pin["model"] != expected_model:
        raise CreditRateNotPinned(f"rate_pin_model_mismatch:{pin.get('model')!r}!={expected_model!r}")
    return pin


def token_usage_delta_to_credits(last_token_usage: dict, rate_pin: dict) -> float:
    """Convert one turn's token delta into normalized credits using a pin already validated by
    `load_credit_rate_pin`. Fail closed on a malformed usage object -- never treat a missing/bad
    token field as zero tokens (that would silently under-count real spend)."""
    for field in TOKEN_FIELDS:
        value = last_token_usage.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            raise ValueError(f"invalid_token_field:{field}")
    input_tokens = last_token_usage["input_tokens"]
    cached_tokens = last_token_usage["cached_input_tokens"]
    output_tokens = last_token_usage["output_tokens"]
    if cached_tokens > input_tokens:
        raise ValueError("cached_input_tokens_exceeds_input_tokens")
    uncached_input_tokens = input_tokens - cached_tokens
    usd = (
        uncached_input_tokens * rate_pin["usd_per_input_token"]
        + cached_tokens * rate_pin["usd_per_cached_input_token"]
        + output_tokens * rate_pin["usd_per_output_token"]
    )
    return usd * rate_pin["credits_per_usd"]


def _extract_token_count_payload(raw_event: object) -> Optional[dict]:
    """Find a token_count-shaped payload in a raw codex --json line, accepting either envelope
    this repo has evidence for (see module docstring): bare `{"type": "token_count", "info": {...}}`
    or wrapped `{"msg": {"type": "token_count", "info": {...}}}` (the rollout-persistence shape)."""
    if not isinstance(raw_event, dict):
        return None
    candidate = raw_event
    if raw_event.get("type") != "token_count" and isinstance(raw_event.get("msg"), dict):
        candidate = raw_event["msg"]
    if candidate.get("type") != "token_count":
        return None
    info = candidate.get("info")
    if not isinstance(info, dict):
        return None
    return info


def codex_event_to_credit_event(raw_event: dict, rate_pin: dict) -> dict:
    """Normalize one raw codex --json event into the `{"normalized_credits": N}` shape
    tools/gate0_credit_breaker.py::run_breaker consumes.

    Non-token_count events (agent messages, reasoning deltas, tool calls, ...) are real events --
    they must still be handed to run_breaker to keep its stall clock alive (a wall of tool-call
    events with the model just never checkpointing tokens must not read as a stall) -- but they
    carry zero KNOWN credit delta, so they pass through at normalized_credits=0 rather than being
    dropped or invented. A token_count event with a malformed `last_token_usage` fails closed
    (raises ValueError, which the caller lets propagate as a stream fault -- never silently
    zeroed)."""
    info = _extract_token_count_payload(raw_event)
    if info is None:
        return {"normalized_credits": 0.0, "raw_type": _event_type(raw_event)}
    last_usage = info.get("last_token_usage")
    if not isinstance(last_usage, dict):
        raise ValueError("token_count_event_missing_last_token_usage")
    credits = token_usage_delta_to_credits(last_usage, rate_pin)
    return {"normalized_credits": credits, "raw_type": "token_count", "last_token_usage": last_usage}


def _event_type(raw_event: dict) -> str:
    if raw_event.get("type") == "token_count":
        return "token_count"
    msg = raw_event.get("msg")
    if isinstance(msg, dict) and isinstance(msg.get("type"), str):
        return str(msg["type"])
    value = raw_event.get("type")
    return value if isinstance(value, str) else "unknown"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser(
        "validate",
        help="Fail-closed preflight: exits 0 only if the rate pin exists and matches --model.")
    validate.add_argument("--rate-pin", type=Path, required=True)
    validate.add_argument("--model", required=True)
    args = parser.parse_args()
    if args.command == "validate":
        try:
            load_credit_rate_pin(args.rate_pin, args.model)
        except CreditRateNotPinned as exc:
            print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
            return 1
        print(json.dumps({"ok": True}))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
