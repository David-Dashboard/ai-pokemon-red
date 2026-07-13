"""Sealed Gate 0 reachability check. Never expose held-out task contents."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import math
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parents[1]
PAID_MANIFEST = ROOT / "eval" / "fixtures" / "gate0_miniwob_paid_seeds.json"
EXPECTED_SEEDS = list(range(1000, 1005))
VIEWPORT_WIDTH = 160
VIEWPORT_HEIGHT = 177
_DOM_KEYS = {"ref", "parent", "left", "top", "width", "height", "tag", "text", "value",
             "id", "classes", "flags"}


def _number(value) -> float:
    if isinstance(value, bool):
        raise ValueError
    if hasattr(value, "item"):
        value = value.item()
    elif isinstance(value, (list, tuple)):
        if len(value) != 1:
            raise ValueError
        value = value[0]
    number = float(value)
    if not math.isfinite(number):
        raise ValueError
    return number


def _center_reachable(row: dict) -> bool:
    try:
        left, top = _number(row["left"]), _number(row["top"])
        width, height = _number(row["width"]), _number(row["height"])
    except Exception:
        return False
    if width <= 0 or height <= 0:
        return False
    x, y = left + width / 2, top + height / 2
    return 0 <= x < VIEWPORT_WIDTH and 0 <= y < VIEWPORT_HEIGHT


def observation_reachable(observation: dict) -> bool:
    """Return false on every unproven field-to-control mapping."""
    try:
        fields = observation["fields"]
        rows = observation["dom_elements"]
        if not isinstance(fields, (list, tuple)) or not isinstance(rows, (list, tuple)):
            return False
        pairs = []
        for pair in fields:
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                return False
            key, value = pair
            if not isinstance(key, str) or not isinstance(value, str):
                return False
            pairs.append((key, value))
        button_fields = [value for key, value in pairs if key == "button"]
        target_fields = [(key, value) for key, value in pairs if key != "button"]
        if button_fields != ["submit"]:
            return False
        if [key for key, _ in target_fields] != [f"target {i}" for i in range(len(target_fields))]:
            return False
        labels = [value for _, value in target_fields]
        if any(not value for value in labels) or len(labels) != len(set(labels)):
            return False

        if any(not isinstance(row, dict) or not _DOM_KEYS.issubset(row) for row in rows):
            return False
        refs = [row["ref"] for row in rows]
        if any(isinstance(ref, bool) or not isinstance(ref, int) or ref == 0 for ref in refs):
            return False
        if len(refs) != len(set(refs)):
            return False
        by_ref = {row["ref"]: row for row in rows}

        resolved_checkboxes = []
        for label in labels:
            label_rows = [row for row in rows if label in (row["text"], row["value"])]
            if len(label_rows) != 1:
                return False
            parent = by_ref.get(label_rows[0]["parent"])
            if parent is None:
                return False
            checkboxes = [row for row in rows
                          if row["parent"] == parent["ref"]
                          and str(row["tag"]).casefold() == "input_checkbox"]
            if len(checkboxes) != 1 or not _center_reachable(checkboxes[0]):
                return False
            resolved_checkboxes.append(checkboxes[0]["ref"])
        if len(resolved_checkboxes) != len(set(resolved_checkboxes)):
            return False

        submit = [row for row in rows
                  if str(row["tag"]).casefold() == "button"
                  and any(isinstance(value, str) and value.casefold() == "submit"
                          for value in (row["text"], row["value"]))]
        return len(submit) == 1 and _center_reachable(submit[0])
    except Exception:
        return False


def _default_env_factory():
    import miniwob  # noqa: F401
    from miniwob.envs.miniwob_envs import ClickCheckboxesEnv
    return ClickCheckboxesEnv(render_mode=None)


def evaluate(env_factory: Callable = _default_env_factory,
             manifest_path: Path = PAID_MANIFEST) -> bool:
    env = None
    passed = False
    try:
        manifest_bytes = Path(manifest_path).read_bytes()
        seeds = json.loads(manifest_bytes)
        if seeds != EXPECTED_SEEDS:
            return False
        env = env_factory()
        for seed in seeds:
            result = env.reset(seed=seed)
            if not isinstance(result, tuple) or len(result) != 2:
                return False
            if not observation_reachable(result[0]):
                return False
        passed = True
    except BaseException:
        passed = False
    finally:
        if env is not None:
            try:
                env.close()
            except BaseException:
                passed = False
    return passed


def _sha256(path: Path) -> str:
    try:
        payload = Path(path).read_bytes()
    except OSError:
        payload = b""
    return hashlib.sha256(payload).hexdigest()


def main(env_factory: Callable = _default_env_factory,
         manifest_path: Path = PAID_MANIFEST,
         code_path: Path | None = None) -> int:
    code_path = Path(__file__) if code_path is None else Path(code_path)
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        try:
            reachable = evaluate(env_factory, Path(manifest_path))
        except BaseException:
            reachable = False
    print(f"all_reachable={'true' if reachable else 'false'}")
    print(f"seed_manifest_sha256={_sha256(Path(manifest_path))}")
    print(f"preflight_code_sha256={_sha256(code_path)}")
    return 0 if reachable else 1


if __name__ == "__main__":
    raise SystemExit(main())
