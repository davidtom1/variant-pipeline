import json
import logging

import pytest

from src.aggregate import read_metrics, build_summary, write_summary, aggregate_all


def write_metrics_file(output_dir, name, source_file=None, valid_count=1, skipped_count=0,
                        duration_seconds=1.0, variants_per_chromosome=None, omit_keys=None):
    """Write a metrics file matching the shape process.py writes."""
    if source_file is None:
        source_file = name.replace(".json", ".csv")
    if variants_per_chromosome is None:
        variants_per_chromosome = {"chr1": valid_count} if valid_count else {}
    metrics = {
        "source_file": source_file,
        "converted_file": name,
        "started_at": "2026-01-01T00:00:00+00:00",
        "ended_at": "2026-01-01T00:00:01+00:00",
        "duration_seconds": duration_seconds,
        "rows_read": valid_count + skipped_count,
        "valid_count": valid_count,
        "skipped_count": skipped_count,
        "variants_per_chromosome": variants_per_chromosome,
    }
    for key in omit_keys or ():
        metrics.pop(key, None)
    path = output_dir / name
    path.write_text(json.dumps(metrics), encoding="utf-8")
    return path


def make_metrics(source_file, valid_count=1, skipped_count=0, duration_seconds=1.0,
                  variants_per_chromosome=None):
    """Build an in-memory metrics dict for build_summary (no filesystem)."""
    if variants_per_chromosome is None:
        variants_per_chromosome = {"chr1": valid_count} if valid_count else {}
    return {
        "source_file": source_file,
        "valid_count": valid_count,
        "skipped_count": skipped_count,
        "duration_seconds": duration_seconds,
        "variants_per_chromosome": variants_per_chromosome,
    }


# --- read_metrics ------------------------------------------------------------

def test_read_metrics_returns_dict_for_well_formed_file(tmp_path):
    path = write_metrics_file(tmp_path, "sample.json", valid_count=5, skipped_count=1)

    metrics = read_metrics(path)

    assert metrics is not None
    assert metrics["source_file"] == "sample.csv"
    assert metrics["valid_count"] == 5
    assert metrics["skipped_count"] == 1


def test_read_metrics_missing_key_returns_none_and_logs_error(tmp_path, caplog):
    path = write_metrics_file(tmp_path, "sample.json", omit_keys=["skipped_count", "duration_seconds"])

    with caplog.at_level(logging.ERROR, logger="aggregate"):
        result = read_metrics(path)

    assert result is None
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1
    message = errors[0].getMessage()
    assert "skipped_count" in message
    assert "duration_seconds" in message


def test_read_metrics_invalid_json_returns_none(tmp_path, caplog):
    path = tmp_path / "bad.json"
    path.write_text("not valid json {", encoding="utf-8")

    with caplog.at_level(logging.ERROR, logger="aggregate"):
        result = read_metrics(path)

    assert result is None
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1


def test_read_metrics_nonexistent_path_returns_none(tmp_path, caplog):
    path = tmp_path / "does_not_exist.json"

    with caplog.at_level(logging.ERROR, logger="aggregate"):
        result = read_metrics(path)

    assert result is None
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1


# --- build_summary -------------------------------------------------------------

def test_build_summary_totals_are_sums():
    metrics_list = [
        make_metrics("a.csv", valid_count=3, skipped_count=1, duration_seconds=1.5),
        make_metrics("b.csv", valid_count=4, skipped_count=2, duration_seconds=2.25),
    ]

    summary = build_summary(metrics_list, failed_count=0)

    assert summary["total_variants"] == 7
    assert summary["total_skipped"] == 3
    assert summary["total_duration_seconds"] == 3.75


def test_build_summary_merges_variants_per_chromosome_across_files():
    metrics_list = [
        make_metrics("a.csv", variants_per_chromosome={"chr1": 2, "chr2": 1}),
        make_metrics("b.csv", variants_per_chromosome={"chr1": 3, "chr3": 5}),
    ]

    summary = build_summary(metrics_list, failed_count=0)

    assert summary["variants_per_chromosome"] == {"chr1": 5, "chr2": 1, "chr3": 5}


def test_build_summary_keys_in_genomic_order():
    metrics_list = [
        make_metrics("a.csv", variants_per_chromosome={"chr10": 1, "chr2": 1, "chr1": 1, "chrX": 1}),
    ]

    summary = build_summary(metrics_list, failed_count=0)

    assert list(summary["variants_per_chromosome"].keys()) == ["chr1", "chr2", "chr10", "chrX"]


def test_build_summary_unknown_chromosome_sorts_last():
    metrics_list = [
        make_metrics("a.csv", variants_per_chromosome={"chrUnknown": 1, "chrX": 1, "chr1": 1}),
    ]

    summary = build_summary(metrics_list, failed_count=0)

    assert list(summary["variants_per_chromosome"].keys()) == ["chr1", "chrX", "chrUnknown"]


def test_build_summary_input_files_lists_every_source_file_sorted():
    metrics_list = [
        make_metrics("b.csv"),
        make_metrics("a.csv"),
        make_metrics("c.csv"),
    ]

    summary = build_summary(metrics_list, failed_count=0)

    assert summary["input_files"] == ["a.csv", "b.csv", "c.csv"]


def test_build_summary_files_processed_equals_input_length():
    metrics_list = [make_metrics("a.csv"), make_metrics("b.csv"), make_metrics("c.csv")]

    summary = build_summary(metrics_list, failed_count=0)

    assert summary["files_processed"] == 3


def test_build_summary_metrics_files_failed_carries_through():
    metrics_list = [make_metrics("a.csv")]

    summary = build_summary(metrics_list, failed_count=4)

    assert summary["metrics_files_failed"] == 4


def test_build_summary_empty_list_gives_zero_totals():
    summary = build_summary([], failed_count=0)

    assert summary["total_variants"] == 0
    assert summary["total_skipped"] == 0
    assert summary["total_duration_seconds"] == 0
    assert summary["variants_per_chromosome"] == {}
    assert summary["input_files"] == []
    assert summary["files_processed"] == 0


def test_build_summary_is_deterministic_across_calls():
    metrics_list = [
        make_metrics("b.csv", variants_per_chromosome={"chr2": 1, "chr1": 2}),
        make_metrics("a.csv", variants_per_chromosome={"chr1": 3}),
    ]

    first = build_summary(metrics_list, failed_count=1)
    second = build_summary(metrics_list, failed_count=1)

    assert first == second


# --- write_summary -------------------------------------------------------------

def test_write_summary_writes_to_given_path(tmp_path):
    summary = {"total_variants": 1}
    summary_file = tmp_path / "summary.json"
    history_dir = tmp_path / "history"

    write_summary(summary, summary_file, history_dir)

    assert json.loads(summary_file.read_text()) == summary


def test_write_summary_writes_exactly_one_archive(tmp_path):
    summary = {"total_variants": 1}
    summary_file = tmp_path / "summary.json"
    history_dir = tmp_path / "history"

    write_summary(summary, summary_file, history_dir)

    archive_files = list(history_dir.glob("*"))
    assert len(archive_files) == 1
    assert archive_files[0].name.startswith("summary_")
    assert archive_files[0].name.endswith(".json")
    assert json.loads(archive_files[0].read_text()) == summary


def test_write_summary_two_calls_produce_distinct_archives(tmp_path):
    summary = {"total_variants": 1}
    summary_file = tmp_path / "summary.json"
    history_dir = tmp_path / "history"

    write_summary(summary, summary_file, history_dir)
    write_summary(summary, summary_file, history_dir)

    archive_files = list(history_dir.glob("*"))
    assert len(archive_files) == 2
    assert archive_files[0].name != archive_files[1].name


# --- aggregate_all ---------------------------------------------------------------

def test_aggregate_all_writes_summary_and_archive_and_returns_it(tmp_path):
    input_dir = tmp_path / "processed"
    input_dir.mkdir()
    write_metrics_file(input_dir, "a.json", valid_count=2, skipped_count=1)
    write_metrics_file(input_dir, "b.json", valid_count=3, skipped_count=0)
    summary_file = tmp_path / "summary.json"
    history_dir = tmp_path / "history"

    summary = aggregate_all(input_dir, summary_file, history_dir)

    assert summary is not None
    assert summary["total_variants"] == 5
    assert json.loads(summary_file.read_text()) == summary
    assert len(list(history_dir.glob("*"))) == 1


def test_aggregate_all_missing_input_dir_returns_none_and_logs_error(tmp_path, caplog):
    input_dir = tmp_path / "does_not_exist"
    summary_file = tmp_path / "summary.json"
    history_dir = tmp_path / "history"

    with caplog.at_level(logging.ERROR, logger="aggregate"):
        result = aggregate_all(input_dir, summary_file, history_dir)

    assert result is None
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1


def test_aggregate_all_empty_dir_returns_none_and_logs_warning(tmp_path, caplog):
    input_dir = tmp_path / "processed"
    input_dir.mkdir()
    summary_file = tmp_path / "summary.json"
    history_dir = tmp_path / "history"

    with caplog.at_level(logging.WARNING, logger="aggregate"):
        result = aggregate_all(input_dir, summary_file, history_dir)

    assert result is None
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1


def test_aggregate_all_one_good_one_malformed_covers_only_good(tmp_path):
    input_dir = tmp_path / "processed"
    input_dir.mkdir()
    write_metrics_file(input_dir, "good.json", valid_count=5, skipped_count=1)
    (input_dir / "bad.json").write_text("not valid json {", encoding="utf-8")
    summary_file = tmp_path / "summary.json"
    history_dir = tmp_path / "history"

    summary = aggregate_all(input_dir, summary_file, history_dir)

    assert summary is not None
    assert summary["total_variants"] == 5
    assert summary["files_processed"] == 1
    assert summary["metrics_files_failed"] == 1
    assert summary["input_files"] == ["good.csv"]


def test_aggregate_all_no_readable_metrics_returns_none(tmp_path, caplog):
    input_dir = tmp_path / "processed"
    input_dir.mkdir()
    (input_dir / "bad.json").write_text("not valid json {", encoding="utf-8")
    summary_file = tmp_path / "summary.json"
    history_dir = tmp_path / "history"

    with caplog.at_level(logging.ERROR, logger="aggregate"):
        result = aggregate_all(input_dir, summary_file, history_dir)

    assert result is None


# --- idempotency -------------------------------------------------------------

def test_aggregate_all_is_idempotent(tmp_path):
    input_dir = tmp_path / "processed"
    input_dir.mkdir()
    write_metrics_file(input_dir, "a.json", valid_count=2, skipped_count=1)
    write_metrics_file(input_dir, "b.json", valid_count=3, skipped_count=0)
    summary_file = tmp_path / "summary.json"
    history_dir = tmp_path / "history"

    aggregate_all(input_dir, summary_file, history_dir)
    first_bytes = summary_file.read_bytes()

    aggregate_all(input_dir, summary_file, history_dir)
    second_bytes = summary_file.read_bytes()

    assert first_bytes == second_bytes
    summary = json.loads(second_bytes)
    assert summary["total_variants"] == 5
    assert summary["total_skipped"] == 1
    assert len(list(history_dir.glob("*"))) == 2
