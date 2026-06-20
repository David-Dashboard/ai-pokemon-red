"""Tests for the reset/freshness helper that guards the beta learning boundary (S3).

`is_clean` is load-bearing: under beta aria OWNS within-run memory, so the paid drivers refuse to start
a fresh run on un-reset aria memory (it would leak the prior run). These pin that detection.
"""
from reset_aria_memory import SEED, is_clean


def _seed(d):
    for name in SEED:
        (d / name).write_text("seed", encoding="utf-8")
    (d / "embed_model_cache").mkdir()   # a KEEP_CACHES dir — not experience


def test_is_clean_true_when_only_seed_and_caches(tmp_path):
    d = tmp_path / "data"
    d.mkdir()
    _seed(d)
    assert is_clean(str(d)) is True


def test_is_clean_false_with_run_generated_journal(tmp_path):
    d = tmp_path / "data"
    d.mkdir()
    _seed(d)
    (d / "journal").mkdir()             # every aria turn writes here -> the un-reset signal
    assert is_clean(str(d)) is False


def test_is_clean_false_with_a_run_written_file(tmp_path):
    d = tmp_path / "data"
    d.mkdir()
    _seed(d)
    (d / "memstore.db").write_text("x", encoding="utf-8")
    assert is_clean(str(d)) is False


def test_is_clean_true_for_missing_dir(tmp_path):
    # nothing on disk -> nothing to leak
    assert is_clean(str(tmp_path / "does-not-exist")) is True
