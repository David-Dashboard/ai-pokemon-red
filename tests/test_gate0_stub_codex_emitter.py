import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parents[1]
EMITTER = ROOT / "tools" / "gate0_stub_codex_emitter.py"


def test_emits_the_requested_number_of_token_count_events_plus_one_passthrough(tmp_path):
    progress = tmp_path / "progress.json"
    result = subprocess.run(
        [sys.executable, str(EMITTER), "--total", "5", "--delay-s", "0", "--out-progress", str(progress)],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert result.returncode == 0, result.stderr
    lines = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    token_count_lines = [line for line in lines if line["type"] == "token_count"]
    assert len(token_count_lines) == 5
    assert any(line["type"] == "agent_message_delta" for line in lines)
    progress_data = json.loads(progress.read_text(encoding="utf-8"))
    assert progress_data == {"intended_total": 5, "emitted_count": 5}


def test_token_count_events_carry_a_correct_cumulative_total(tmp_path):
    progress = tmp_path / "progress.json"
    result = subprocess.run(
        [sys.executable, str(EMITTER), "--total", "3", "--delay-s", "0", "--output-tokens-per-event", "6",
         "--out-progress", str(progress)],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert result.returncode == 0, result.stderr
    lines = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    token_count_lines = [line for line in lines if line["type"] == "token_count"]
    cumulative = [line["info"]["total_token_usage"]["output_tokens"] for line in token_count_lines]
    assert cumulative == [6, 12, 18]
    deltas = [line["info"]["last_token_usage"]["output_tokens"] for line in token_count_lines]
    assert deltas == [6, 6, 6]


def test_progress_file_proves_a_genuine_mid_stream_kill(tmp_path):
    progress = tmp_path / "progress.json"
    proc = subprocess.Popen(
        [sys.executable, str(EMITTER), "--total", "50", "--delay-s", "0.1", "--out-progress", str(progress)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=ROOT,
    )
    time.sleep(0.5)
    proc.kill()
    proc.wait(timeout=5)
    progress_data = json.loads(progress.read_text(encoding="utf-8"))
    assert 0 < progress_data["emitted_count"] < progress_data["intended_total"]
