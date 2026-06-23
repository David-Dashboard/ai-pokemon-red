"""Lock the held-out leakage guard (eval/dataset_split.py) — the single line keeping the held-out games
(incl. ViZDoom, whose 3D recorder writes no meta ROM) out of the dev corpus. No ROM/PyBoy needed."""
from __future__ import annotations

from eval.dataset_split import is_heldout_rom, is_heldout_run


def test_heldout_roms_flagged():
    assert is_heldout_rom("Crystalis (USA).gbc")
    assert is_heldout_rom("Legend of Zelda, The - Link's Awakening (U) (V1.2) [!].gb")
    assert is_heldout_rom("Super Mario Land (World) (Rev 1).gb")
    assert is_heldout_rom("F-1 Race (World).gb")


def test_dev_roms_not_flagged():
    assert not is_heldout_rom("PokemonRed.gb")
    assert not is_heldout_rom("Kirby's Dream Land (USA, Europe).gb")
    assert not is_heldout_rom("Cave Noire (Japan) [T-En by Aeon Genesis v1.00].gb")  # a DEV fixed unit
    assert not is_heldout_rom("")


def test_vizdoom_heldout_by_dir_name(tmp_path):
    # the ViZDoom recorder writes NO meta.json ROM -> held-out must be caught by the run-dir NAME ("doom").
    d = tmp_path / "vizdoom_mywayhome"
    d.mkdir()
    assert is_heldout_run(str(d))


def test_dev_run_not_heldout_by_name(tmp_path):
    d = tmp_path / "2026-06-23_kirby_play"
    d.mkdir()
    assert not is_heldout_run(str(d))
