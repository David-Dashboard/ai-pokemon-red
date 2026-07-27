"""$0 byte-level close-out of the open `pin_mismatch:tool_schema_sha256` question.

reports/2026-07-24-gate0-paired-verdict.md:281-296 flagged (its words) "flagged, not fixed, not
certain": eval/score_gate0.py audits the banked paid arms against the NON-`.appserver` fixtures,
whose `tool_schema_sha256` was captured 2026-07-19 by the PowerShell exec-path launcher
(`ConvertTo-Json -Depth 20 -Compress` + trailing LF), while the banked app-server runs write
`json.dumps(tools) + "\\n"`. That report performed no byte-level diff. This does.

Two byte streams, both already on disk, both hashing to a value already pinned somewhere:
  PS  : runs/gate0_readiness_2026-07-14/{red-v3,miniwob-v2}/mcp-tools.json
        -> the exact bytes behind eval/fixtures/gate0_expected_pins_{arm}.json:tool_schema_sha256
  PY  : runs/gate0_paid/{red,miniwob}/mcp-tools.json
        -> the exact bytes behind the banked handshake-receipt.json:tool_schema_sha256 and behind
           eval/fixtures/gate0_expected_pins_{arm}.appserver.json:tool_schema_sha256

If the two decode to the SAME Python object, the difference is purely serialization and the tool
surface never changed. This reports which specific serialization axes differ, and proves the claim
by re-serializing the PY object with the PS recipe and checking it reproduces the PS bytes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ARMS = {"red": ("red-v3", "red"), "miniwob": ("miniwob-v2", "miniwob")}


def probe(name: str, raw: bytes) -> dict:
    return {
        "label": name,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "n_bytes": len(raw),
        "utf8_bom": raw[:3] == b"\xef\xbb\xbf",
        "trailing_newline": raw.endswith(b"\n"),
        "crlf_count": raw.count(b"\r\n"),
        "lone_lf_count": raw.count(b"\n") - raw.count(b"\r\n"),
        "space_count": raw.count(b" "),
        "backslash_u_escapes": raw.count(b"\\u"),
        "non_ascii_bytes": sum(1 for b in raw if b > 127),
        "first_120_bytes": raw[:120].decode("utf-8", "replace"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs-root", type=Path, required=True, help="path to runs/ (read-only)")
    args = parser.parse_args()
    out = {}
    for arm, (ps_dir, py_dir) in ARMS.items():
        ps_raw = (args.runs_root / "gate0_readiness_2026-07-14" / ps_dir / "mcp-tools.json").read_bytes()
        py_raw = (args.runs_root / "gate0_paid" / py_dir / "mcp-tools.json").read_bytes()
        ps_obj = json.loads(ps_raw.decode("utf-8-sig"))
        py_obj = json.loads(py_raw.decode("utf-8-sig"))

        # First byte position where the two streams diverge.
        first_div = next((i for i in range(min(len(ps_raw), len(py_raw))) if ps_raw[i] != py_raw[i]),
                         min(len(ps_raw), len(py_raw)))

        # Does the PY object, re-serialized the PS way, reproduce the PS bytes exactly?
        # Three axes, established empirically below:
        #   1. separators   -- PS -Compress emits ","/":"; json.dumps defaults to ", "/": "
        #   2. non-ASCII    -- PS emits raw UTF-8 (U+2014); json.dumps defaults ensure_ascii=True
        #   3. apostrophe   -- PS 5.1 escapes U+0027 as '; Python never does (red arm only:
        #                      red tool descriptions contain 4 apostrophes, miniwob contains 0)
        # Plus a trailing LF, UTF-8, no BOM -- which BOTH recipes already share.
        ps_recipe = (json.dumps(py_obj, separators=(",", ":"), ensure_ascii=False)
                     .replace("'", "\\u0027").encode("utf-8") + b"\n")
        # Same, minus axis 3, to show axis 3 is what miniwob does not need and red does.
        ps_recipe_no_apos = (json.dumps(py_obj, separators=(",", ":"), ensure_ascii=False)
                             .encode("utf-8") + b"\n")

        out[arm] = {
            "ps_exec_era": probe("powershell ConvertTo-Json -Compress", ps_raw),
            "py_appserver": probe('python json.dumps(tools) + "\\n"', py_raw),
            "decoded_objects_equal": ps_obj == py_obj,
            "key_order_identical": (
                json.dumps(ps_obj, sort_keys=False) == json.dumps(py_obj, sort_keys=False)),
            "tool_names_ps": [t.get("name") for t in ps_obj],
            "tool_names_py": [t.get("name") for t in py_obj],
            "first_divergent_byte_offset": first_div,
            "ps_context_at_divergence": ps_raw[max(0, first_div - 40):first_div + 40].decode("utf-8", "replace"),
            "py_context_at_divergence": py_raw[max(0, first_div - 40):first_div + 40].decode("utf-8", "replace"),
            "axis1_separators_ps_vs_py": ('","/":"', '", "/": "'),
            "axis2_nonascii_chars_raw_in_ps": sorted(
                set(c for c in ps_raw.decode("utf-8") if ord(c) > 127)),
            "axis3_apostrophes_in_payload": py_raw.count(b"'") + ps_raw.count(b"\\u0027"),
            "reserialized_axes_1_2_only_sha256": hashlib.sha256(ps_recipe_no_apos).hexdigest(),
            "reserialized_axes_1_2_only_equals_ps_bytes": ps_recipe_no_apos == ps_raw,
            "reserialized_axes_1_2_3_sha256": hashlib.sha256(ps_recipe).hexdigest(),
            "reserialized_axes_1_2_3_equals_ps_bytes": ps_recipe == ps_raw,
        }
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
