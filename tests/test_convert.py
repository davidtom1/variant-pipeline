import json
import logging

import pytest

from src.convert import convert_all, convert_file

VALID_HEADER = "index,CHROM,POS,REF,ALT"
VALID_ROW = "chr1:17282953_G/T,chr1,17282953,G,T"
VALID_ROW_2 = "chr2:696264_T/G,chr2,696264,T,G"
UNKNOWN_CHROM_ROW = "chr23:1000_G/T,chr23,1000,G,T"
MISSING_COLUMN_HEADER = "index,CHROM,POS,REF"


def write_csv(input_dir, name, lines):
    """Write a CSV file made of `lines` (joined with newlines) into input_dir."""
    path = input_dir / name
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def input_dir(tmp_path):
    d = tmp_path / "input"
    d.mkdir()
    return d


@pytest.fixture
def output_dir(tmp_path):
    return tmp_path / "output"


# --- convert_file: success ---------------------------------------------------

def test_convert_file_produces_json_named_after_stem(input_dir, output_dir):
    csv_path = write_csv(input_dir, "sample.csv", [VALID_HEADER, VALID_ROW])

    result = convert_file(csv_path, output_dir)

    assert result is True
    output_path = output_dir / "sample.json"
    assert output_path.exists()


def test_convert_file_json_has_expected_keys_and_types(input_dir, output_dir):
    csv_path = write_csv(input_dir, "sample.csv", [VALID_HEADER, VALID_ROW])

    convert_file(csv_path, output_dir)

    payload = json.loads((output_dir / "sample.json").read_text())
    assert set(payload.keys()) == {
        "source_file", "rows_read", "valid_count", "skipped_count", "variants",
    }
    assert payload["source_file"] == "sample.csv"
    assert payload["rows_read"] == 1
    assert payload["valid_count"] == 1
    assert payload["skipped_count"] == 0
    assert len(payload["variants"]) == 1
    assert isinstance(payload["variants"][0]["pos"], int)
    assert payload["variants"][0]["pos"] == 17282953


def test_convert_file_mixed_valid_and_invalid_rows(input_dir, output_dir, caplog):
    csv_path = write_csv(
        input_dir, "mixed.csv",
        [VALID_HEADER, VALID_ROW, UNKNOWN_CHROM_ROW, VALID_ROW_2],
    )

    with caplog.at_level(logging.WARNING, logger="convert"):
        result = convert_file(csv_path, output_dir)

    assert result is True
    payload = json.loads((output_dir / "mixed.json").read_text())
    assert payload["rows_read"] == 3
    assert payload["valid_count"] == 2
    assert payload["skipped_count"] == 1
    assert payload["valid_count"] + payload["skipped_count"] == payload["rows_read"]
    assert len(payload["variants"]) == 2
    assert all(v["chrom"] != "chr23" for v in payload["variants"])

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "mixed.csv" in warnings[0].message or "mixed.csv" in warnings[0].getMessage()
    assert "chr23" in warnings[0].getMessage()


def test_convert_file_header_only_csv_succeeds_with_zero_variants(input_dir, output_dir):
    csv_path = write_csv(input_dir, "empty_data.csv", [VALID_HEADER])

    result = convert_file(csv_path, output_dir)

    assert result is True
    payload = json.loads((output_dir / "empty_data.json").read_text())
    assert payload["rows_read"] == 0
    assert payload["valid_count"] == 0
    assert payload["skipped_count"] == 0
    assert payload["variants"] == []


def test_convert_file_columns_in_different_order(input_dir, output_dir):
    header = "CHROM,index,ALT,REF,POS"
    row = "chr1,chr1:17282953_G/T,T,G,17282953"
    csv_path = write_csv(input_dir, "reordered.csv", [header, row])

    result = convert_file(csv_path, output_dir)

    assert result is True
    payload = json.loads((output_dir / "reordered.json").read_text())
    assert payload["valid_count"] == 1
    assert payload["variants"][0]["pos"] == 17282953


def test_convert_file_tolerates_extra_unknown_columns(input_dir, output_dir):
    header = VALID_HEADER + ",NOTE"
    row = VALID_ROW + ",some note"
    csv_path = write_csv(input_dir, "extra_col.csv", [header, row])

    result = convert_file(csv_path, output_dir)

    assert result is True
    payload = json.loads((output_dir / "extra_col.json").read_text())
    assert payload["valid_count"] == 1


# --- convert_file: failure ----------------------------------------------------

def test_convert_file_fails_on_completely_empty_file(input_dir, output_dir, caplog):
    csv_path = input_dir / "empty.csv"
    csv_path.write_text("", encoding="utf-8")

    with caplog.at_level(logging.ERROR, logger="convert"):
        result = convert_file(csv_path, output_dir)

    assert result is False
    assert not (output_dir / "empty.json").exists()
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1
    assert "empty.csv" in errors[0].getMessage()


def test_convert_file_fails_on_missing_required_column(input_dir, output_dir, caplog):
    csv_path = write_csv(
        input_dir, "missing_col.csv",
        [MISSING_COLUMN_HEADER, "chr1:17282953_G/T,chr1,17282953,G"],
    )

    with caplog.at_level(logging.ERROR, logger="convert"):
        result = convert_file(csv_path, output_dir)

    assert result is False
    assert not (output_dir / "missing_col.json").exists()
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1
    message = errors[0].getMessage()
    assert "missing_col.csv" in message
    assert "ALT" in message


def test_convert_file_fails_on_nonexistent_path(input_dir, output_dir, caplog):
    csv_path = input_dir / "does_not_exist.csv"

    with caplog.at_level(logging.ERROR, logger="convert"):
        result = convert_file(csv_path, output_dir)

    assert result is False
    assert not (output_dir / "does_not_exist.json").exists()
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1
    assert "does_not_exist.csv" in errors[0].getMessage()


# --- convert_all ---------------------------------------------------------------

def test_convert_all_converts_every_csv(input_dir, output_dir):
    write_csv(input_dir, "a.csv", [VALID_HEADER, VALID_ROW])
    write_csv(input_dir, "b.csv", [VALID_HEADER, VALID_ROW_2])

    converted, failed = convert_all(input_dir=input_dir, output_dir=output_dir)

    assert (converted, failed) == (2, 0)
    assert (output_dir / "a.json").exists()
    assert (output_dir / "b.json").exists()


def test_convert_all_one_bad_file_does_not_stop_the_run(input_dir, output_dir):
    write_csv(input_dir, "good.csv", [VALID_HEADER, VALID_ROW])
    write_csv(input_dir, "bad.csv", [MISSING_COLUMN_HEADER, "a,chr1,1000,G"])

    converted, failed = convert_all(input_dir=input_dir, output_dir=output_dir)

    assert (converted, failed) == (1, 1)
    assert (output_dir / "good.json").exists()
    assert not (output_dir / "bad.json").exists()


def test_convert_all_empty_directory_returns_zero_zero(input_dir, output_dir):
    converted, failed = convert_all(input_dir=input_dir, output_dir=output_dir)

    assert (converted, failed) == (0, 0)


# --- idempotency -----------------------------------------------------------

def test_convert_file_is_idempotent(input_dir, output_dir):
    csv_path = write_csv(input_dir, "sample.csv", [VALID_HEADER, VALID_ROW])

    convert_file(csv_path, output_dir)
    first = json.loads((output_dir / "sample.json").read_text())

    convert_file(csv_path, output_dir)
    second = json.loads((output_dir / "sample.json").read_text())

    output_files = list(output_dir.glob("*.json"))
    assert len(output_files) == 1
    assert first == second
