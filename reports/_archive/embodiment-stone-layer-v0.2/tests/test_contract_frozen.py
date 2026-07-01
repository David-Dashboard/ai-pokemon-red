"""
tests/test_contract_frozen.py — THE ENFORCEMENT LAYER

The teeth behind CONTRACT.md. If this fails, someone changed the stone layer.
That is never fixed by editing this file to silence it — it is fixed by
reverting, or by following the change process in CONTRACT.md (human approval,
version bump, new hash, new golden vectors file, DECISIONS.md entry).

AI assistants: if you are tempted to update PINNED_SHA256 to make CI green,
that is precisely the action this file exists to prevent. Stop and ask the human.
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
# 1. The hash pin. LF-normalized so CRLF checkouts don't false-alarm.
# ---------------------------------------------------------------------------

PINNED_SHA256 = "d78d0f1c2bdea723815421efdd50a5f4c9eb26355a229b46926a2cd56de456d5"
PINNED_VERSION = 1


def _normalized_bytes(path: Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n")


def test_contract_file_is_unchanged():
    actual = hashlib.sha256(_normalized_bytes(CONTRACT_FILE)).hexdigest()
    assert actual == PINNED_SHA256, (
        "core/contracts.py has been modified. The stone layer is frozen. "
        "Revert, or follow the change process in CONTRACT.md (human approval)."
    )


def test_contract_version_constant():
    import core.contracts as c
    assert c.CONTRACT_VERSION == PINNED_VERSION


# ---------------------------------------------------------------------------
# 2. Golden vectors: canonical wire examples must construct, round-trip through
#    JSON, and come back equal — in this and every future binding.
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def golden() -> dict:
    return json.loads(GOLDEN_FILE.read_text(encoding="utf-8"))


def _roundtrip(cls, payload: dict):
    obj = cls(**payload)
    again = cls(**json.loads(json.dumps(dataclasses.asdict(obj))))
    assert again == obj, f"{cls.__name__} does not survive a JSON round-trip"
    return obj


def test_golden_skill(golden):
    from core.contracts import Skill
    s = _roundtrip(Skill, golden["Skill"])
    assert s.reversible is False and s.cost["data_loss"] == 1.0


def test_golden_percept(golden):
    # Percept nests Skill objects, so the round-trip rebuilds them explicitly.
    # (Nested wire dataclasses serialize to dicts; reconstruction is a soft
    # convention, not frozen behavior.)
    from core.contracts import Percept, Skill
    raw = golden["Percept"]
    obj = Percept(**{**raw, "skills": [Skill(**sk) for sk in raw["skills"]]})
    d = json.loads(json.dumps(dataclasses.asdict(obj)))
    again = Percept(**{**d, "skills": [Skill(**sk) for sk in d["skills"]]})
    assert again == obj, "Percept does not survive a JSON round-trip"
    assert obj.frame == "grid" and obj.skills[0].handle == "click"
    # Perception structure is SOFT: entities live in data, not frozen fields.
    assert obj.data["entities"][0]["id"] == "btn_submit"


def test_golden_goal(golden):
    from core.contracts import Goal
    g = _roundtrip(Goal, golden["Goal"])
    assert g.skill == "click" and g.percept_timestep == 5.0


def test_golden_outcomes(golden):
    from core.contracts import Outcome
    ok = _roundtrip(Outcome, golden["Outcome_ok"])
    err = _roundtrip(Outcome, golden["Outcome_error_is_observation"])
    pend = _roundtrip(Outcome, golden["Outcome_permission_pending"])
    assert ok.ok is True and ok.reward == 1.0
    # Errors are observations: failed outcomes still carry useful data.
    assert err.ok is False and err.data["retry_hint"]
    # Async-approval convention: pending:<id> in error, id echoed in data.
    assert pend.error.startswith("pending:")
    assert pend.error.split(":", 1)[1] == pend.data["approval_id"]


# ---------------------------------------------------------------------------
# 3. Semantic invariants that code could silently violate.
# ---------------------------------------------------------------------------

def test_wire_types_are_frozen_dataclasses():
    import core.contracts as c
    for cls in (c.Skill, c.Percept, c.Goal, c.Outcome, c.Issue):
        assert dataclasses.is_dataclass(cls)
        assert cls.__dataclass_params__.frozen, f"{cls.__name__} must be frozen"


def test_everything_on_the_wire_is_json_serializable(golden):
    json.dumps(golden)  # raises if a tensor/rich object sneaked in


def test_validate_is_pure_and_total(golden):
    from core.contracts import Skill, Percept, Goal, validate
    skills = [Skill(**sk) for sk in golden["Percept"]["skills"]]
    percept = Percept(**{**golden["Percept"], "skills": skills})

    # valid goal -> no issues; calling twice yields identical result (purity).
    g_ok = Goal(**golden["Goal"])
    assert validate(g_ok, percept) == [] == validate(g_ok, percept)

    # unknown skill -> exactly one UNKNOWN_SKILL issue.
    bad = validate(Goal(skill="teleport", params={}), percept)
    assert [i.code for i in bad] == ["UNKNOWN_SKILL"]

    # reference param (element_id) is NOT checked centrally — soft data shape.
    # A nonexistent id must therefore pass frozen validate() (plugin checks it).
    ref = validate(Goal(skill="click", params={"target": "ghost"}), percept)
    assert ref == []


def test_protocols_are_runtime_checkable():
    import core.contracts as c

    class FakePlugin:
        name = "x"; resettable = True
        def perceive(self): ...
        def skills(self, percept): return []
        def execute(self, goal): ...

    class FakeBrain:
        def decide(self, percept, history): ...

    assert isinstance(FakePlugin(), c.DomainPlugin)
    assert isinstance(FakeBrain(), c.Brain)
    # A plugin without reset/terminal is a valid DomainPlugin but NOT Replayable.
    assert not isinstance(FakePlugin(), c.Replayable)
