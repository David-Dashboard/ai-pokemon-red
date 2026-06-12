"""
tests/test_contract_frozen.py — THE ENFORCEMENT LAYER

This test suite is the teeth behind CONTRACT.md. If it fails, someone
changed the stone layer. That is never fixed by editing this file to
make the failure go away — it is fixed by reverting, or by following
the change process in CONTRACT.md (human approval, version bump, new
hash, new golden vectors file, DECISIONS.md entry).

AI assistants: if you are tempted to update PINNED_SHA256 to make CI
green, that is precisely the action this file exists to prevent. Stop
and raise it with the human instead.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CONTRACT_FILE = ROOT / "core" / "contracts.py"
GOLDEN_FILE = ROOT / "contracts" / "golden_vectors_v1.json"

# ---------------------------------------------------------------------------
# 1. The hash pin. Newlines are normalized to LF so Windows checkouts with
#    CRLF do not produce false alarms.
# ---------------------------------------------------------------------------

PINNED_SHA256 = "1f2162807ab51446f6732fd0be117e65cf79f1b567bd8b70b7f117e917c2c6ce"
PINNED_VERSION = 1


def _normalized_bytes(path: Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n")


def test_contract_file_is_unchanged():
    actual = hashlib.sha256(_normalized_bytes(CONTRACT_FILE)).hexdigest()
    assert actual == PINNED_SHA256, (
        "core/contracts.py has been modified. The stone layer is frozen. "
        "Revert the change, or follow the change process in CONTRACT.md "
        "(human approval required)."
    )


def test_contract_version_constant():
    import core.contracts as c

    assert c.CONTRACT_VERSION == PINNED_VERSION


# ---------------------------------------------------------------------------
# 2. Golden vectors: the canonical wire examples must construct, round-trip
#    through JSON, and come back equal — in this and every future binding.
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def golden() -> dict:
    return json.loads(GOLDEN_FILE.read_text(encoding="utf-8"))


def _roundtrip(cls, payload: dict):
    obj = cls(**payload)
    again = cls(**json.loads(json.dumps(dataclasses.asdict(obj))))
    assert again == obj, f"{cls.__name__} does not survive a JSON round-trip"
    return obj


def test_golden_toolspec(golden):
    from core.contracts import ToolSpec

    spec = _roundtrip(ToolSpec, golden["ToolSpec"])
    assert spec.mutating is True and spec.cost == 1


def test_golden_toolcall(golden):
    from core.contracts import ToolCall

    call = _roundtrip(ToolCall, golden["ToolCall"])
    assert call.tool == "move" and call.args["uci"] == "e2e4"


def test_golden_toolresults(golden):
    from core.contracts import ToolResult

    ok = _roundtrip(ToolResult, golden["ToolResult_ok"])
    err = _roundtrip(ToolResult, golden["ToolResult_error_is_observation"])
    pend = _roundtrip(ToolResult, golden["ToolResult_permission_pending"])
    assert ok.ok is True
    # Errors are observations: failed results still carry useful data.
    assert err.ok is False and err.data["legal_sample"]
    # Async-approval convention: pending:<id> in error, id echoed in data.
    assert pend.error.startswith("pending:")
    assert pend.error.split(":", 1)[1] == pend.data["approval_id"]


def test_golden_events(golden):
    from core.contracts import Event

    r = _roundtrip(Event, golden["Event_reward"])
    w = _roundtrip(Event, golden["Event_world_level"])
    assert r.reward == 1.0
    assert w.agent_id is None, "world-level events carry agent_id=None"


def test_golden_observation(golden):
    from core.contracts import Observation

    obs = _roundtrip(Observation, golden["Observation"])
    assert obs.text and isinstance(obs.data, dict)


# ---------------------------------------------------------------------------
# 3. Semantic invariants that code could silently violate.
# ---------------------------------------------------------------------------

def test_wire_types_are_frozen_dataclasses():
    import core.contracts as c

    for cls in (c.ToolSpec, c.ToolCall, c.ToolResult, c.Event, c.Observation):
        assert dataclasses.is_dataclass(cls)
        params = getattr(cls, "__dataclass_params__")
        assert params.frozen, f"{cls.__name__} must be frozen"
        with pytest.raises(dataclasses.FrozenInstanceError):
            obj = cls(**{f.name: _dummy(f) for f in dataclasses.fields(cls)})
            object.__getattribute__(obj, "__class__")  # construct ok
            setattr(obj, dataclasses.fields(cls)[0].name, None)


def _dummy(f: dataclasses.Field):
    if f.default is not dataclasses.MISSING:
        return f.default
    if f.default_factory is not dataclasses.MISSING:  # type: ignore[misc]
        return f.default_factory()  # type: ignore[misc]
    return {"str": "x", "float": 0.0}.get(getattr(f.type, "__name__", str(f.type)), "x")


def test_everything_on_the_wire_is_json_serializable(golden):
    """No tensors, no rich objects: every golden value must be pure JSON."""
    json.dumps(golden)  # raises if not


def test_protocols_are_runtime_checkable():
    import core.contracts as c

    class FakePlugin:
        def tools(self, agent_id): return []
        def handle(self, call): ...
        def observe(self, agent_id): ...
        def drain_events(self): return []

    class FakeBrain:
        def decide(self, obs, tools, context): return None

    assert isinstance(FakePlugin(), c.GamePlugin)
    assert isinstance(FakeBrain(), c.Brain)
    # A plugin without reset/step is a valid GamePlugin but NOT Replayable:
    assert not isinstance(FakePlugin(), c.Replayable)
