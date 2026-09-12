import pytest

from src.validation import validate_row


def make_row(chrom, pos, ref, alt, index=None):
    """Build a row dict for validate_row with a correctly-formed index.

    chrom, pos, ref, alt may include surrounding whitespace; the generated
    index is built from their stripped forms, matching what validate_row
    rebuilds internally. Pass `index` explicitly to test a mismatched or
    empty index.
    """
    pos_str = str(pos)
    if index is None:
        index = f"{chrom.strip()}:{pos_str.strip()}_{ref.strip()}/{alt.strip()}"
    return {"index": index, "CHROM": chrom, "POS": pos_str, "REF": ref, "ALT": alt}


# --- Valid cases -----------------------------------------------------------

@pytest.mark.parametrize(
    "chrom, pos, ref, alt",
    [
        pytest.param("chr1", 17282953, "G", "T", id="plain-substitution"),
        pytest.param("chr1", 1000, "GAAGTC", "G", id="multi-base-ref-deletion"),
        pytest.param("chr1", 1000, "G", "GAAGTC", id="multi-base-alt-insertion"),
        pytest.param("chrX", 15329847, "C", "T", id="chrX"),
        pytest.param("chrY", 1000000, "A", "G", id="chrY"),
        pytest.param("chr1", 1, "A", "T", id="pos-exactly-1"),
        pytest.param("chr1", 248956422, "G", "T", id="pos-exactly-chrom-length"),
    ],
)
def test_valid_rows(chrom, pos, ref, alt):
    row = make_row(chrom, pos, ref, alt)

    variant, reason = validate_row(row)

    assert reason is None
    assert variant is not None
    assert isinstance(variant["pos"], int)
    assert variant["pos"] == int(pos)
    assert variant["chrom"] == chrom
    assert variant["ref"] == ref
    assert variant["alt"] == alt


def test_valid_row_with_surrounding_whitespace():
    row = make_row(" chr1 ", " 17282953 ", "G", "T")

    variant, reason = validate_row(row)

    assert reason is None
    assert variant is not None
    assert isinstance(variant["pos"], int)
    assert variant["pos"] == 17282953
    assert variant["chrom"] == "chr1"


# --- Invalid: index issues ---------------------------------------------------

def test_invalid_empty_index():
    row = make_row("chr1", 17282953, "G", "T", index="")

    variant, reason = validate_row(row)

    assert variant is None
    assert "index" in reason


def test_invalid_index_disagrees_with_other_columns():
    row = make_row("chr1", 17282953, "G", "T", index="chr1:99999_A/C")

    variant, reason = validate_row(row)

    assert variant is None
    assert "index" in reason


# --- Invalid: chromosome ----------------------------------------------------

@pytest.mark.parametrize("chrom", ["chr23", "chrM", "7"])
def test_invalid_unknown_chromosome(chrom):
    row = make_row(chrom, 1000, "G", "T")

    variant, reason = validate_row(row)

    assert variant is None
    assert chrom in reason


# --- Invalid: POS ------------------------------------------------------------

@pytest.mark.parametrize("pos_raw", ["not_a_number", "-5", "12.5"])
def test_invalid_pos_not_numeric(pos_raw):
    row = make_row("chr1", pos_raw, "G", "T")

    variant, reason = validate_row(row)

    assert variant is None
    assert pos_raw in reason


@pytest.mark.parametrize("pos", ["0", 248956423])
def test_invalid_pos_out_of_bounds(pos):
    row = make_row("chr1", pos, "G", "T")

    variant, reason = validate_row(row)

    assert variant is None
    assert str(pos) in reason


# --- Invalid: empty REF / ALT ------------------------------------------------

def test_invalid_empty_ref():
    row = make_row("chr1", 1000, "", "T")

    variant, reason = validate_row(row)

    assert variant is None
    assert "REF" in reason


def test_invalid_empty_alt():
    row = make_row("chr1", 1000, "G", "")

    variant, reason = validate_row(row)

    assert variant is None
    assert "ALT" in reason


# --- Invalid: base characters -------------------------------------------------

def test_invalid_lowercase_base():
    row = make_row("chr1", 1000, "g", "T")

    variant, reason = validate_row(row)

    assert variant is None
    assert "g" in reason


def test_invalid_n_base():
    row = make_row("chr1", 1000, "G", "N")

    variant, reason = validate_row(row)

    assert variant is None
    assert "N" in reason


def test_invalid_ref_equals_alt():
    row = make_row("chr1", 1000, "G", "G")

    variant, reason = validate_row(row)

    assert variant is None
    assert "G" in reason


# --- Invalid: missing / None fields ------------------------------------------

def test_invalid_required_field_is_none():
    row = make_row("chr1", 1000, "G", "T")
    row["POS"] = None

    variant, reason = validate_row(row)

    assert variant is None
    assert "POS" in reason


def test_invalid_required_field_missing_entirely():
    row = make_row("chr1", 1000, "G", "T")
    del row["ALT"]

    variant, reason = validate_row(row)

    assert variant is None
    assert "ALT" in reason
