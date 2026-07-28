"""Gate 0 pre-registration precondition 3 -- the frozen expected-pins JSON and the
eval.score_gate0.SOURCE_PIN_FILES manifests that point at them."""
import hashlib
import json
from pathlib import Path

import pytest

import eval.score_gate0 as scorer
import tools.check_gate0_codex as checker
from tools.check_gate0_codex import PIN_FIELDS, CONSTANCY_FIELDS

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_PINS_PATHS = {
    "red": ROOT / "eval" / "fixtures" / "gate0_expected_pins_red.json",
    "miniwob": ROOT / "eval" / "fixtures" / "gate0_expected_pins_miniwob.json",
}
LIVE_BREAKER_PATH = ROOT / "runs" / "gate0_live_breaker" / "live_breaker_dry_run_trip.json"


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("arm", ["red", "miniwob"])
def test_expected_pins_file_exists_and_loads(arm):
    pins = _load(EXPECTED_PINS_PATHS[arm])
    assert pins["schema_version"] == 2
    assert pins["arm"] == arm


@pytest.mark.parametrize("arm", ["red", "miniwob"])
def test_expected_pins_has_every_pin_field(arm):
    pins = _load(EXPECTED_PINS_PATHS[arm])
    missing = [field for field in PIN_FIELDS if field not in pins]
    assert missing == []


@pytest.mark.parametrize("arm", ["red", "miniwob"])
@pytest.mark.parametrize("field", PIN_FIELDS)
def test_expected_pins_refuses_a_partial_file_missing_any_one_field(arm, field):
    pins = dict(_load(EXPECTED_PINS_PATHS[arm]))
    del pins[field]
    failures = checker._expected_failures({}, pins)
    assert f"expected_missing:{field}" in failures


@pytest.mark.parametrize("arm", ["red", "miniwob"])
def test_expected_pins_field_values_satisfy_the_real_receipt_shape_rules(arm):
    # _receipt_shape_failures() is what a real observed receipt must clear; the frozen pins for
    # the code-mandated-constant fields must themselves already satisfy it, or no real receipt
    # could ever match them.
    pins = _load(EXPECTED_PINS_PATHS[arm])
    assert pins["readiness"] == "NO_GO_INSUFFICIENT_WAKES"
    assert pins["paid_execution_enabled"] is False
    assert pins["auth_method"] == "chatgpt"
    assert pins["critical_config_transport"] == "explicit_cli_overrides"
    assert pins["mcp_servers_observed"] == [checker.SERVER]
    assert pins["mcp_tools_observed"] == checker.TOOLS[arm]
    expected_tag = "gb-mcp-world" if arm == "red" else "miniwob-world"
    assert pins["world_image_tag"] == expected_tag
    for field in ("codex_executable_sha256", "brain_config_sha256", "task_sha256",
                  "tool_schema_sha256"):
        value = pins[field]
        assert isinstance(value, str) and len(value) == 64
        assert all(c in "0123456789abcdef" for c in value)
    # Resolved from PR #117's rebuild receipt -- must be a real immutable image ID, exactly the
    # format _receipt_shape_failures() enforces on receipts.
    image_id = pins["world_image_id"]
    assert image_id.startswith("sha256:") and len(image_id) == 71
    assert all(c in "0123456789abcdef" for c in image_id[7:])
    for path in ("/app/world_mcp.py", "/app/core/miniwob_world.py"):
        for key in ("host_code_sha256", "image_code_sha256"):
            digest = pins[key][path]
            assert len(digest) == 64 and all(c in "0123456789abcdef" for c in digest)
    # host/image code parity is the whole point of precondition 9's rebuild target.
    assert pins["host_code_sha256"] == pins["image_code_sha256"]
    # The two remaining run-time-only fields must stay fail-closed CONSTRAINT strings (never a
    # valid 64-hex hash) until frozen at signature -- see gate0_expected_pins.SOURCES.md.
    for field in ("config_sha256", "codex_mcp_list_sha256"):
        assert pins[field].startswith("CONSTRAINT:")


def test_the_two_arms_pin_distinct_rebuilt_images():
    red = _load(EXPECTED_PINS_PATHS["red"])
    miniwob = _load(EXPECTED_PINS_PATHS["miniwob"])
    assert red["world_image_id"] != miniwob["world_image_id"]
    assert red["tool_schema_sha256"] != miniwob["tool_schema_sha256"]


def test_constancy_fields_match_exactly_between_the_two_arm_pins():
    red = _load(EXPECTED_PINS_PATHS["red"])
    miniwob = _load(EXPECTED_PINS_PATHS["miniwob"])
    for field in CONSTANCY_FIELDS:
        assert red[field] == miniwob[field], f"CONSTANCY_FIELDS drift on {field}"


def test_host_code_sha256_matches_the_real_repo_git_blobs():
    # Independently re-derive the pin the same way it was frozen (canonical git blob at HEAD),
    # so a future edit to world_mcp.py / core/miniwob_world.py without re-freezing is caught here
    # rather than silently shipping a stale pin.
    import subprocess
    pins = _load(EXPECTED_PINS_PATHS["red"])
    for rel_path, app_path in (("world_mcp.py", "/app/world_mcp.py"),
                               ("core/miniwob_world.py", "/app/core/miniwob_world.py")):
        blob = subprocess.run(["git", "cat-file", "blob", f"HEAD:{rel_path}"],
                              cwd=ROOT, check=True, capture_output=True).stdout
        assert pins["host_code_sha256"][app_path] == hashlib.sha256(blob).hexdigest(), (
            f"{rel_path} changed since the pins were frozen -- re-freeze host_code_sha256/"
            f"image_code_sha256 in eval/fixtures/gate0_expected_pins_*.json")


@pytest.mark.parametrize("mode,seed_fixture", [
    ("readiness_dev", "gate0_miniwob_dev_seeds.json"),
    ("paid_gate0", "gate0_miniwob_paid_seeds.json"),
    ("paid_gate0_v2", "gate0_miniwob_paid_v2_seeds.json"),
])
def test_source_pins_manifest_exists_where_the_scorer_expects_it(mode, seed_fixture):
    path = scorer.SOURCE_PIN_FILES[mode]
    assert path.exists(), f"{path} missing -- eval.score_gate0.SOURCE_PIN_FILES[{mode!r}] points here"
    pins = _load(path)
    assert pins["schema_version"] == 1
    assert pins["mode"] == mode


@pytest.mark.parametrize("mode,seed_fixture", [
    ("readiness_dev", "gate0_miniwob_dev_seeds.json"),
    ("paid_gate0", "gate0_miniwob_paid_seeds.json"),
    ("paid_gate0_v2", "gate0_miniwob_paid_v2_seeds.json"),
])
def test_frozen_seed_hash_matches_the_real_seed_fixture(mode, seed_fixture):
    pins = _load(scorer.SOURCE_PIN_FILES[mode])
    seed_path = ROOT / "eval" / "fixtures" / seed_fixture
    assert pins["frozen_seed_sha256"] == _sha256(seed_path)


@pytest.mark.parametrize("mode", ["readiness_dev", "paid_gate0", "paid_gate0_v2"])
def test_expected_pins_sha256_matches_the_real_expected_pins_files(mode):
    pins = _load(scorer.SOURCE_PIN_FILES[mode])
    for arm in ("red", "miniwob"):
        assert pins["expected_pins_sha256"][arm] == _sha256(EXPECTED_PINS_PATHS[arm])


@pytest.mark.parametrize("mode", ["readiness_dev", "paid_gate0", "paid_gate0_v2"])
def test_audit_paths_shape_is_complete_for_both_arms(mode):
    pins = _load(scorer.SOURCE_PIN_FILES[mode])
    for arm in ("red", "miniwob"):
        entry = pins["audit_paths"][arm]
        assert set(entry) == set(scorer.AUDIT_PATH_KEYS)
        for key, value in entry.items():
            assert isinstance(value, str) and value, f"{mode}/{arm}/{key} must be a non-empty string"
        assert entry["expected_pins"] == f"eval/fixtures/gate0_expected_pins_{arm}.json"


@pytest.mark.parametrize("mode", ["readiness_dev", "paid_gate0", "paid_gate0_v2"])
def test_artifact_paths_has_all_six_required_keys(mode):
    pins = _load(scorer.SOURCE_PIN_FILES[mode])
    required = ("red_agent", "red_human", "miniwob_agent", "miniwob_human",
                "wake_boundary", "live_breaker")
    assert set(pins["artifact_paths"]) == set(required)
    assert set(pins["artifact_sha256"]) == set(required)


@pytest.mark.parametrize("mode", ["readiness_dev", "paid_gate0", "paid_gate0_v2"])
def test_verify_audit_paths_accepts_a_manifest_pointing_at_the_real_pins(mode):
    # End-to-end shape check against the REAL committed fixtures (not a monkeypatched tmp_path
    # stand-in): a manifest whose codex_audit/oracle exactly match this mode's frozen audit_paths
    # is accepted, and the expected_pins hash pin matches the real committed files.
    pins = _load(scorer.SOURCE_PIN_FILES[mode])
    manifest = {"mode": mode, "arms": {}}
    for arm in ("red", "miniwob"):
        entry = dict(pins["audit_paths"][arm])
        oracle = entry.pop("oracle")
        manifest["arms"][arm] = {"codex_audit": entry, "oracle": oracle}
    resolved, failures = scorer._verify_audit_paths(manifest)
    assert failures == []
    assert set(resolved) == {"red", "miniwob"}


@pytest.mark.parametrize("mode", ["readiness_dev", "paid_gate0", "paid_gate0_v2"])
def test_verify_sources_reports_only_the_still_open_gaps(mode):
    # Precondition 3 closes seed/pins hashing regardless of machine state. The four artifacts
    # owned by other/still-open workstreams (human baselines' numbers, the agent attempt) and
    # wake accounting correctly remain source_unreadable / wake_boundary_artifact -- expected, not
    # a regression. live_breaker is asserted separately below (it's a real local-only artifact;
    # runs/ is gitignored, so a fresh clone/CI legitimately doesn't have it yet).
    failures = scorer._verify_sources({"mode": mode, "arms": {}}, {})[1]
    assert "source_pins_unreadable" not in failures
    assert "frozen_seed_contents" not in failures
    assert "frozen_seed_hash" not in failures
    for key in ("red_agent", "red_human", "miniwob_agent", "miniwob_human"):
        assert f"source_unreadable:{key}" in failures
    assert "wake_boundary_artifact" in failures


@pytest.mark.skipif(not LIVE_BREAKER_PATH.exists(),
                     reason="local-only artifact (runs/ is gitignored); see "
                            "reports/2026-07-19-gate0-live-breaker-dry-run.md for the committed copy")
class TestLiveBreakerArtifactLocallyPresent:
    def test_hash_pin_matches_the_local_file(self):
        for mode in ("readiness_dev", "paid_gate0", "paid_gate0_v2"):
            pins = _load(scorer.SOURCE_PIN_FILES[mode])
            assert pins["artifact_sha256"]["live_breaker"] == _sha256(LIVE_BREAKER_PATH)

    @pytest.mark.parametrize("mode", ["readiness_dev", "paid_gate0", "paid_gate0_v2"])
    def test_verify_sources_finds_no_live_breaker_failure(self, mode):
        failures = scorer._verify_sources({"mode": mode, "arms": {}}, {})[1]
        assert "source_hash:live_breaker" not in failures
        assert "source_unreadable:live_breaker" not in failures
        assert "live_breaker_artifact" not in failures


# ---------------------------------------------------------------------------------------------
# paid_gate0_v2 -- Gate 0 v2's fresh held-out block (prereg §4.1/P9). The mode is purely ADDITIVE:
# every assertion here is about v2, plus one that nails paid_gate0 down byte-for-byte.
# ---------------------------------------------------------------------------------------------

V2_SEEDS = [417545, 662948, 660918, 981149, 558952]


def test_paid_gate0_is_unchanged_by_the_v2_addition():
    """The banked v1 result must stay scoreable exactly as it was. If a future edit reaches into
    paid_gate0's seed list, seed fixture, or pins fixture, this fails before anything subtler does."""
    seed_path, seeds = scorer.MODES["paid_gate0"]
    assert seeds == [1000, 1001, 1002, 1003, 1004]
    assert seed_path == ROOT / "eval" / "fixtures" / "gate0_miniwob_paid_seeds.json"
    assert scorer.SOURCE_PIN_FILES["paid_gate0"] == (
        ROOT / "eval" / "fixtures" / "gate0_paid_source_pins.json")
    assert _load(scorer.SOURCE_PIN_FILES["paid_gate0"])["frozen_seed_sha256"] == _sha256(seed_path)


def test_v2_seed_block_reproduces_the_pre_registered_derivation():
    """prereg §4.1.1's published formula, re-walked from scratch. Positions 0-3 are the first four
    accepted candidates; position 4 is §4.1.2's mandated replacement -- the next accepted candidate
    that renders six checkboxes (558952, measured empirically at i=8; 751969/824167/567613 at
    i=5..7 were accepted by the base filter but passed over as 5/3/2-checkbox layouts)."""
    def candidate(i):
        return int.from_bytes(hashlib.sha256(f"gate0-v2-armW:{i}".encode()).digest()[:4], "big") % 1_000_000

    accepted = []
    for i in range(9):
        c = candidate(i)
        if c in range(0, 5) or c in range(1000, 1005) or c in accepted:
            continue
        accepted.append(c)
    assert accepted[:4] == V2_SEEDS[:4]
    assert accepted[4] == 189410, "the pre-replacement 5th draw, replaced per §4.1.2"
    assert candidate(8) == V2_SEEDS[4] == 558952


def test_v2_seeds_are_fresh_distinct_and_scorer_pinned():
    seed_path, seeds = scorer.MODES["paid_gate0_v2"]
    assert seeds == V2_SEEDS
    assert json.loads(seed_path.read_text(encoding="utf-8")) == V2_SEEDS
    # Distinct: duplicates would collide in _miniwob_success's per-episode `seed` row filter and
    # corrupt both episodes' row sets (prereg §4.1.1).
    assert len(set(seeds)) == 5
    # Fresh: disjoint from the dev seeds and from the SPENT v1 paid block.
    assert not set(seeds) & set(scorer.MODES["readiness_dev"][1])
    assert not set(seeds) & set(scorer.MODES["paid_gate0"][1])


def test_v2_expected_pins_hashes_are_frozen_to_the_real_files_and_agree_three_ways():
    """FROZEN 2026-07-28 (prereg P4), replacing the PENDING guard this test used to be: prereg P8's
    world-image rebuild has landed (PR #180), so the digests are knowable and are extracted from the
    real files -- never fabricated, never forward-declared. All three source-pins manifests must
    carry the SAME two values, because all three point their audit_paths[arm]["expected_pins"] at
    the SAME two target files; a divergence means one of the three is stale (the coupling hazard
    each fixture's own _source_expected_pins_sha256 warns about)."""
    v2 = _load(scorer.SOURCE_PIN_FILES["paid_gate0_v2"])
    manifest = {"mode": "paid_gate0_v2", "arms": {}}
    for arm in ("red", "miniwob"):
        value = v2["expected_pins_sha256"][arm]
        assert len(value) == 64 and set(value) <= set("0123456789abcdef"), "must be a real sha256"
        assert value == _sha256(EXPECTED_PINS_PATHS[arm])
        for other in ("readiness_dev", "paid_gate0"):
            assert _load(scorer.SOURCE_PIN_FILES[other])["expected_pins_sha256"][arm] == value
        entry = dict(v2["audit_paths"][arm])
        oracle = entry.pop("oracle")
        manifest["arms"][arm] = {"codex_audit": entry, "oracle": oracle}
    resolved, failures = scorer._verify_audit_paths(manifest)
    assert failures == [], "no expected_pins_hash_pin_missing/mismatch may remain"
    assert set(resolved) == {"red", "miniwob"}


def test_v2_six_checkbox_measurement_is_pinned_to_the_post_rebuild_image():
    """prereg 4.1.2: the six-checkbox property is a fact about the WORLD IMAGE, so the image the
    measurement was taken against must be recorded. Re-confirmed against the post-P8 rebuild on
    2026-07-28 (5/5/2/2/6, 558952 renders six) -- the seed block itself is untouched and binding."""
    measured = _load(scorer.SOURCE_PIN_FILES["paid_gate0_v2"])["_measured_against"]
    miniwob_pins = _load(EXPECTED_PINS_PATHS["miniwob"])
    assert measured["world_image_id"] == miniwob_pins["world_image_id"]
    assert measured["world_image"] == miniwob_pins["world_image_tag"]
    assert measured["superseded_world_image_id"] != measured["world_image_id"]
    assert measured["re_measured_post_p8_on"] == "2026-07-28"
    # The frozen block is the authority, not the re-derivable rule: 558952 stays the H-e case.
    assert scorer.MODES["paid_gate0_v2"][1][4] == 558952


def test_v2_pending_artifact_hashes_are_never_valid_sha256():
    pins = _load(scorer.SOURCE_PIN_FILES["paid_gate0_v2"])
    for key, value in pins["artifact_sha256"].items():
        if value.startswith("PENDING_"):
            assert len(value) != 64, f"{key} placeholder must not look like a real digest"


def test_v2_output_tree_is_separate_from_v1_everywhere():
    """A v2 artifact must never land where v1's pins look, or vice versa."""
    v1, v2 = (_load(scorer.SOURCE_PIN_FILES[m]) for m in ("paid_gate0", "paid_gate0_v2"))
    for key in ("red_agent", "miniwob_agent", "miniwob_human", "wake_boundary"):
        assert v1["artifact_paths"][key] != v2["artifact_paths"][key]
    for arm in ("red", "miniwob"):
        for key in ("transcript", "receipt", "artifacts_dir", "peer_receipt", "oracle"):
            assert v1["audit_paths"][arm][key] != v2["audit_paths"][arm][key]
