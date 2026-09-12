"""Convert stage: parse variant CSVs into validated JSON, one file per input.

Invalid rows are skipped with a logged warning. A file that cannot be read
at all is logged as an error and skipped, so one bad input never stops the run.
"""

import csv
import logging
import sys
from src.io_utils import configure_logging, write_json_atomic
from src.paths import CONVERTED_DIR, INPUT_DIR
from src.validation import REQUIRED_FIELDS, validate_row

logger = logging.getLogger("convert")

def convert_file(csv_path, output_dir):
    """Convert one CSV into one JSON file.

    Returns:
        True if the file was converted, False if it was unusable and skipped.
    """
    valid_variants = []
    skipped = 0
    rows_read = 0

    try:
        # newline="" lets the csv module handle CRLF line endings itself.
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
        # --- File-level checks ---
        # reader.fieldnames is None for a completely empty file,
        # otherwise a list of the header column names.
            if reader.fieldnames is None:
                logger.error("%s: empty file", csv_path.name)
                return False
            missing_fields = set(REQUIRED_FIELDS) - set(reader.fieldnames)
            if missing_fields:
                logger.error(
                    "%s: missing required header fields: %s",
                    csv_path.name, ", ".join(sorted(missing_fields))
                )
                return False
    
            for row in reader:
                rows_read += 1
                variant, reason = validate_row(row)
                if variant is None:
                    skipped += 1
                    logger.warning("%s: line %d skipped: %s", csv_path.name, reader.line_num, reason)
                else:
                    valid_variants.append(variant)

    except (OSError, UnicodeDecodeError) as exc:
        logger.error("%s: cannot read file (%s)", csv_path.name, exc)
        return False
    except csv.Error as exc:
        logger.error("%s: malformed CSV (%s)", csv_path.name, exc)
        return False

    payload = {
        "source_file": csv_path.name,
        "rows_read": rows_read,
        "valid_count": len(valid_variants),
        "skipped_count": skipped,
        "variants": valid_variants,
    }

    output_path = output_dir / f"{csv_path.stem}.json"
    write_json_atomic(payload, output_path)
    logger.info("%s: %d valid, %d skipped -> %s",csv_path.name, len(valid_variants), skipped, output_path.name,)
    return True


def convert_all(input_dir=INPUT_DIR, output_dir=CONVERTED_DIR):
    """Convert every CSV in input_dir. Returns (converted_count, failed_count)."""
    # sorted() gives a deterministic order, which keeps runs comparable.
    csv_paths = sorted(input_dir.glob("*.csv"))
    if not csv_paths:
        logger.warning("No CSV files found in %s", input_dir)
        return 0, 0
    converted, failed = 0, 0
    for csv_path in csv_paths:
        if convert_file(csv_path, output_dir):
            converted += 1
        else:
            failed += 1
    return converted, failed

            



def main():
    configure_logging()
    converted, failed = convert_all()
    logger.info("Convert stage complete: %d converted, %d failed", converted, failed)
    # Exit non-zero only if nothing could be converted at all.
    return 1 if converted == 0 else 0


if __name__ == "__main__":
    sys.exit(main())