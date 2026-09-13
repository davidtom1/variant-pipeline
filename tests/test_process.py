import json
import logging
from datetime import datetime

import pytest

from src.process import get_sleep_seconds, process_file, process_all


def write_converted_json(output_dir, name, variants, source_file=None, rows_read=None,
                          valid_count=None, skipped_count=0):
    """Write a converted-JSON file built from a list of variant dicts."""
    if source_file is None:
        source_file = name.replace(".json", ".csv")
    if rows_read is None:
        rows_read = len(variants)
    if valid_count is None:
        valid_count = len(variants)
    payload = {
        "source_file": source_file,
        "rows_read": rows_read,
        "valid_count": valid_count,
        "skipped_count": skipped_count,
        "variants": variants,
    }
    path = output_dir / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


@pytest.fixture
def converted_dir(tmp_path):
    d = tmp_path / "converted"
    d.mkdir()
    return d


@pytest.fixture
def processed_dir(tmp_path):
    return tmp_path / "processed"


# --- get_sleep_seconds -------------------------------------------------------

def test_get_sleep_seconds_default_when_unset(monkeypatch):
    monkeypatch.delenv("PROCESS_SLEEP_SECONDS", raising=False)

    assert get_sleep_seconds() == 30.0


def test_get_sleep_seconds_zero(monkeypatch):
    monkeypatch.setenv("PROCESS_SLEEP_SECONDS", "0")

    assert get_sleep_seconds() == 0.0


def test_get_sleep_seconds_fractional(monkeypatch):
    monkeypatch.setenv("PROCESS_SLEEP_SECONDS", "0.5")

    assert get_sleep_seconds() == 0.5


def test_get_sleep_seconds_non_numeric_falls_back(monkeypatch, caplog):
    monkeypatch.setenv("PROCESS_SLEEP_SECONDS", "not-a-number")

    with caplog.at_level(logging.WARNING, logger="process"):
        result = get_sleep_seconds()

    assert result == 30.0
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "not-a-number" in warnings[0].getMessage()


def test_get_sleep_seconds_negative_falls_back(monkeypatch, caplog):
    monkeypatch.setenv("PROCESS_SLEEP_SECONDS", "-5")

    with caplog.at_level(logging.WARNING, logger="process"):
        result = get_sleep_seconds()

    assert result == 30.0
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "-5" in warnings[0].getMessage()


# --- process_file: success ---------------------------------------------------

def test_process_file_writes_metrics_named_after_stem(converted_dir, processed_dir):
    json_path = write_converted_json(converted_dir, "sample.json", [{"chrom": "chr1"}])

    result = process_file(json_path, processed_dir, sleep_seconds=0)

    assert result is True
    assert (processed_dir / "sample.json").exists()


def test_process_file_metrics_contain_expected_fields(converted_dir, processed_dir):
    json_path = write_converted_json(
        converted_dir, "sample.json", [{"chrom": "chr1"}], source_file="sample.csv",
        rows_read=3, valid_count=1, skipped_count=2,
    )

    process_file(json_path, processed_dir, sleep_seconds=0)

    metrics = json.loads((processed_dir / "sample.json").read_text())
    assert metrics["source_file"] == "sample.csv"
    assert metrics["converted_file"] == "sample.json"
    assert "started_at" in metrics
    assert "ended_at" in metrics
    assert "duration_seconds" in metrics
    assert metrics["rows_read"] == 3
    assert metrics["valid_count"] == 1
    assert metrics["skipped_count"] == 2
    assert metrics["variants_per_chromosome"] == {"chr1": 1}


def test_process_file_variants_per_chromosome_counts_and_sorts(converted_dir, processed_dir):
    variants = [
        {"chrom": "chr2"},
        {"chrom": "chr1"},
        {"chrom": "chr2"},
        {"chrom": "chr10"},
        {"chrom": "chr1"},
        {"chrom": "chr1"},
    ]
    json_path = write_converted_json(converted_dir, "sample.json", variants)

    process_file(json_path, processed_dir, sleep_seconds=0)

    metrics = json.loads((processed_dir / "sample.json").read_text())
    assert metrics["variants_per_chromosome"] == {"chr1": 3, "chr10": 1, "chr2": 2}
    assert list(metrics["variants_per_chromosome"].keys()) == ["chr1", "chr2", "chr10"]




def test_process_file_timestamps_are_iso_with_utc_offset_and_ordered(converted_dir, processed_dir):
    json_path = write_converted_json(converted_dir, "sample.json", [{"chrom": "chr1"}])

    process_file(json_path, processed_dir, sleep_seconds=0)

    metrics = json.loads((processed_dir / "sample.json").read_text())
    started = datetime.fromisoformat(metrics["started_at"])
    ended = datetime.fromisoformat(metrics["ended_at"])
    assert started.utcoffset() is not None
    assert ended.utcoffset() is not None
    assert ended >= started


def test_process_file_duration_is_non_negative(converted_dir, processed_dir):
    json_path = write_converted_json(converted_dir, "sample.json", [{"chrom": "chr1"}])

    process_file(json_path, processed_dir, sleep_seconds=0)

    metrics = json.loads((processed_dir / "sample.json").read_text())
    assert metrics["duration_seconds"] >= 0


def test_process_file_duration_reflects_sleep_seconds(converted_dir, processed_dir):
    json_path = write_converted_json(converted_dir, "sample.json", [{"chrom": "chr1"}])

    process_file(json_path, processed_dir, sleep_seconds=0.05)

    metrics = json.loads((processed_dir / "sample.json").read_text())
    assert metrics["duration_seconds"] >= 0.05


# --- process_file: failure ---------------------------------------------------

def test_process_file_fails_on_invalid_json(converted_dir, processed_dir, caplog):
    json_path = converted_dir / "bad.json"
    json_path.write_text("not valid json {", encoding="utf-8")

    with caplog.at_level(logging.ERROR, logger="process"):
        result = process_file(json_path, processed_dir, sleep_seconds=0)

    assert result is False
    assert not (processed_dir / "bad.json").exists()
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1


def test_process_file_fails_on_missing_required_keys(converted_dir, processed_dir, caplog):
    json_path = converted_dir / "incomplete.json"
    json_path.write_text(json.dumps({"source_file": "incomplete.csv"}), encoding="utf-8")

    with caplog.at_level(logging.ERROR, logger="process"):
        result = process_file(json_path, processed_dir, sleep_seconds=0)

    assert result is False
    assert not (processed_dir / "incomplete.json").exists()
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1
    assert "incomplete.json" in errors[0].getMessage()


def test_process_file_fails_on_nonexistent_path(converted_dir, processed_dir, caplog):
    json_path = converted_dir / "does_not_exist.json"

    with caplog.at_level(logging.ERROR, logger="process"):
        result = process_file(json_path, processed_dir, sleep_seconds=0)

    assert result is False
    assert not (processed_dir / "does_not_exist.json").exists()
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1


# --- process_all --------------------------------------------------------------

def test_process_all_processes_every_json(converted_dir, processed_dir, monkeypatch):
    monkeypatch.setenv("PROCESS_SLEEP_SECONDS", "0")
    write_converted_json(converted_dir, "a.json", [{"chrom": "chr1"}])
    write_converted_json(converted_dir, "b.json", [{"chrom": "chr2"}])

    processed, failed = process_all(input_dir=converted_dir, output_dir=processed_dir)

    assert (processed, failed) == (2, 0)
    assert (processed_dir / "a.json").exists()
    assert (processed_dir / "b.json").exists()


def test_process_all_one_bad_file_does_not_stop_the_run(converted_dir, processed_dir, monkeypatch):
    monkeypatch.setenv("PROCESS_SLEEP_SECONDS", "0")
    write_converted_json(converted_dir, "good.json", [{"chrom": "chr1"}])
    (converted_dir / "bad.json").write_text("not valid json {", encoding="utf-8")

    processed, failed = process_all(input_dir=converted_dir, output_dir=processed_dir)

    assert (processed, failed) == (1, 1)
    assert (processed_dir / "good.json").exists()
    assert not (processed_dir / "bad.json").exists()


def test_process_all_nonexistent_input_dir_returns_zero_zero(tmp_path, processed_dir, caplog, monkeypatch):
    monkeypatch.setenv("PROCESS_SLEEP_SECONDS", "0")
    missing_dir = tmp_path / "does_not_exist"

    with caplog.at_level(logging.ERROR, logger="process"):
        processed, failed = process_all(input_dir=missing_dir, output_dir=processed_dir)

    assert (processed, failed) == (0, 0)
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1


def test_process_all_empty_directory_returns_zero_zero(converted_dir, processed_dir, caplog, monkeypatch):
    monkeypatch.setenv("PROCESS_SLEEP_SECONDS", "0")

    with caplog.at_level(logging.WARNING, logger="process"):
        processed, failed = process_all(input_dir=converted_dir, output_dir=processed_dir)

    assert (processed, failed) == (0, 0)
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1


# --- idempotency -----------------------------------------------------------

def test_process_file_is_idempotent(converted_dir, processed_dir):
    json_path = write_converted_json(converted_dir, "sample.json", [{"chrom": "chr1"}])

    process_file(json_path, processed_dir, sleep_seconds=0)
    first = json.loads((processed_dir / "sample.json").read_text())

    process_file(json_path, processed_dir, sleep_seconds=0)
    second = json.loads((processed_dir / "sample.json").read_text())

    output_files = list(processed_dir.glob("*.json"))
    assert len(output_files) == 1

    timing_keys = {"started_at", "ended_at", "duration_seconds"}
    first_stable = {k: v for k, v in first.items() if k not in timing_keys}
    second_stable = {k: v for k, v in second.items() if k not in timing_keys}
    assert first_stable == second_stable
