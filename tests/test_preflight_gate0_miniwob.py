from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from tools import preflight_gate0_miniwob as preflight


def _row(ref, parent, tag, *, text="", value="", left=0, top=0, width=10, height=10):
    return {"ref": ref, "parent": parent, "left": left, "top": top, "width": width,
            "height": height, "tag": tag, "text": text, "value": value, "id": "",
            "classes": "", "flags": [0, 0, 0, 1]}


def _observation(*, checkbox_top=20, duplicate_label=False, missing_label=False,
                 two_checkboxes=False, submit_top=140):
    rows = [
        _row(1, 0, "BODY", width=160, height=210),
        _row(10, 1, "LABEL"),
        _row(11, 10, "INPUT_checkbox", left=10, top=checkbox_top, width=20, height=12),
        _row(20, 1, "BUTTON", text="Submit", left=40, top=submit_top, width=60, height=20),
    ]
    if not missing_label:
        rows.append(_row(-1, 10, "t", text="PRIVATE-LABEL", left=32, top=checkbox_top))
    if duplicate_label:
        rows.append(_row(-2, 10, "t", value="PRIVATE-LABEL", left=50, top=checkbox_top))
    if two_checkboxes:
        rows.append(_row(12, 10, "INPUT_checkbox", left=70, top=checkbox_top, width=20, height=12))
    return {"fields": (("target 0", "PRIVATE-LABEL"), ("button", "submit")),
            "dom_elements": tuple(rows)}


class _FakeEnv:
    def __init__(self, observation=None, error=False):
        self.observation = observation
        self.error = error
        self.seeds = []
        self.closed = False

    def reset(self, seed=None):
        self.seeds.append(seed)
        if self.error:
            raise RuntimeError("PRIVATE-ERROR")
        return self.observation, {}

    def close(self):
        self.closed = True


def _manifest(tmp_path):
    path = tmp_path / "paid.json"
    path.write_bytes(json.dumps(preflight.EXPECTED_SEEDS).encode())
    return path


def test_reachable_mapping_and_exact_seeds(tmp_path):
    env = _FakeEnv(_observation())
    assert preflight.evaluate(lambda: env, _manifest(tmp_path)) is True
    assert env.seeds == preflight.EXPECTED_SEEDS
    assert env.closed is True


def test_offscreen_checkbox_or_submit_fails_closed():
    assert preflight.observation_reachable(_observation(checkbox_top=180)) is False
    assert preflight.observation_reachable(_observation(submit_top=180)) is False


def test_ambiguous_or_missing_mapping_fails_closed():
    assert preflight.observation_reachable(_observation(duplicate_label=True)) is False
    assert preflight.observation_reachable(_observation(missing_label=True)) is False
    assert preflight.observation_reachable(_observation(two_checkboxes=True)) is False


def test_exception_fails_closed_and_closes_env(tmp_path):
    env = _FakeEnv(error=True)
    assert preflight.evaluate(lambda: env, _manifest(tmp_path)) is False
    assert env.closed is True


def test_main_emits_only_three_approved_lines(tmp_path, capsys):
    manifest = _manifest(tmp_path)
    env = _FakeEnv(_observation())
    rc = preflight.main(lambda: env, manifest, Path(preflight.__file__))
    output = capsys.readouterr()
    lines = output.out.splitlines()
    assert rc == 0 and output.err == "" and len(lines) == 3
    assert lines[0] == "all_reachable=true"
    assert lines[1] == f"seed_manifest_sha256={hashlib.sha256(manifest.read_bytes()).hexdigest()}"
    assert lines[2] == f"preflight_code_sha256={hashlib.sha256(Path(preflight.__file__).read_bytes()).hexdigest()}"
    assert all(re.fullmatch(r"(?:all_reachable=(?:true|false)|"
                            r"(?:seed_manifest|preflight_code)_sha256=[0-9a-f]{64})", line)
               for line in lines)
    lowered = output.out.casefold()
    for forbidden in ("private-label", "private-error", "input_checkbox", "submit", "bbox", "x=", "y="):
        assert forbidden not in lowered


def test_false_result_has_same_sealed_output_shape(tmp_path, capsys):
    manifest = _manifest(tmp_path)
    rc = preflight.main(lambda: _FakeEnv(_observation(missing_label=True)), manifest,
                        Path(preflight.__file__))
    output = capsys.readouterr()
    assert rc == 1 and output.err == ""
    assert output.out.splitlines()[0] == "all_reachable=false"
    assert len(output.out.splitlines()) == 3
