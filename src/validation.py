"""Verifies the correctness of the input data and ensures that the data meets the required standards before further processing."""

import re

CHROM_LENGTHS = {
    "chr1": 248956422,  "chr2": 242193529,  "chr3": 198295559,
    "chr4": 190214555,  "chr5": 181538259,  "chr6": 170805979,
    "chr7": 159345973,  "chr8": 145138636,  "chr9": 138394717,
    "chr10": 133797422, "chr11": 135086622, "chr12": 133275309,
    "chr13": 114364328, "chr14": 107043718, "chr15": 101991189,
    "chr16": 90338345,  "chr17": 83257441,  "chr18": 80373285,
    "chr19": 58617616,  "chr20": 64444167,  "chr21": 46709983,
    "chr22": 50818468,  "chrX": 156040895,  "chrY": 57227415,
}

REQUIRED_FIELDS = ("index", "CHROM", "POS", "REF", "ALT")
BASES_PATTERN = re.compile(r"^[ACGT]+$")

def validate_row(row):
    """Validate one CSV row.

    Args:
        row: dict from csv.DictReader, e.g.
             {"index": "chr1:17282953_G/T", "CHROM": "chr1",
              "POS": "17282953", "REF": "G", "ALT": "T"}
             Values are strings. A value may be None if the row had
             fewer columns than the header.

    Returns:
        (variant, None) if valid, where variant is
            {"index": str, "chrom": str, "pos": int, "ref": str, "alt": str}
        (None, reason) if invalid, where reason names the offending value.
    """
    # 1. Missing columns entirely (row had fewer fields than the header).
    #    Also catches a key being absent.
    for field in REQUIRED_FIELDS:
        if row.get(field) is None:
            return None, f"missing column {field}"

    # 2. Strip whitespace from every value.
    index = row["index"].strip()
    chrom = row["CHROM"].strip()
    pos_raw = row["POS"].strip()
    ref = row["REF"].strip()
    alt = row["ALT"].strip()

    # 3. Empty values after stripping.
    for field, value in (("index", index), ("CHROM", chrom),
                     ("POS", pos_raw), ("REF", ref), ("ALT", alt)):
        if not value:
            return None, f"empty value for {field}"

    # 4. CHROM must be known.
    if chrom not in CHROM_LENGTHS:
        return None, f"unknown chromosome {chrom}"

    # 5. POS must be digits, >= 1, <= CHROM_LENGTHS[chrom].
    if not pos_raw.isdigit():
        return None, f"POS is not a valid integer: {pos_raw}"
    pos = int(pos_raw)
    if not (1 <= pos <= CHROM_LENGTHS[chrom]):
        return None, f"POS is out of bounds for {chrom}: {pos}"
 
    # 6. REF and ALT must match BASES_PATTERN.
    if not BASES_PATTERN.match(ref):
        return None, f"REF contains invalid characters: {ref}"
    if not BASES_PATTERN.match(alt):
        return None, f"ALT contains invalid characters: {alt}"

    # 7. ALT must differ from REF.
    if ref == alt:
        return None, f"ALT is the same as REF: {alt}"

    # 8. index must equal the rebuilt value.
    rebuilt_index = f"{chrom}:{pos_raw}_{ref}/{alt}"
    if index != rebuilt_index:
        return None, f"index does not match rebuilt value: {rebuilt_index}"

    return {
        "index": index,
        "chrom": chrom,
        "pos": pos,
        "ref": ref,
        "alt": alt,
    }, None