
"""Process stage: reads each converted JSON file, simulates a compute-intensive
step with a configurable sleep, and writes a per-file metrics JSON."""
from datetime import datetime, timezone
import logging
import json
import os
import sys
import time 
from collections import Counter

from src.io_utils import write_json_atomic, configure_logging
from src.paths import CONVERTED_DIR, PROCESSED_DIR

logger = logging.getLogger("process")

def get_sleep_seconds():
    raw =  os.environ.get("PROCESS_SLEEP_SECONDS", "30")
    try:
        value = float(raw)
    except ValueError:
        logger.warning("Invalid PROCESS_SLEEP_SECONDS value: %s. Using default of 30 seconds.", raw)
        return 30
    if value < 0:
        logger.warning("Negative PROCESS_SLEEP_SECONDS value: %s. Using default of 30 seconds.", raw)
        return 30.0
    return value


def process_file(json_path, output_dir, sleep_seconds):
    try:
        with open(json_path, encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.error(f"Failed to decode JSON from {json_path}: {e}")
        return False
    
    missing = {"source_file", "rows_read", "valid_count", "skipped_count", "variants"} - payload.keys()
    if missing:
        logger.error("%s: not a converted file, missing keys: %s",
                    json_path.name, ", ".join(sorted(missing)))
        return False
    started_at = datetime.now(timezone.utc).isoformat()
    t0 = time.monotonic()
    time.sleep(sleep_seconds)
    duration = round(time.monotonic() - t0, 3)
    ended_at = datetime.now(timezone.utc).isoformat()
    counts = Counter(v["chrom"] for v in payload["variants"])
    metrics = {
        "source_file": payload["source_file"],
        "converted_file": json_path.name,
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_seconds": duration,
        "rows_read": payload["rows_read"],
        "valid_count": payload["valid_count"],
        "skipped_count": payload["skipped_count"],
        "variants_per_chromosome": dict(sorted(counts.items())),
    }
    output_path = output_dir / f"{json_path.stem}.json"
    write_json_atomic(metrics, output_path)
    logger.info(
        "%s: %d variants in %.1fs -> %s",
        payload["source_file"], payload["valid_count"], duration, output_path.name,
    )
    return True

def process_all(input_dir=CONVERTED_DIR, output_dir=PROCESSED_DIR):
    """Process every converted JSON file. Returns (processed, failed)."""
    if not input_dir.exists():
        logger.error("Converted directory %s does not exist; run the convert stage first", input_dir)
        return 0, 0

    sleep_seconds = get_sleep_seconds()
    logger.info("Sleeping %.1fs per file", sleep_seconds)

    json_paths = sorted(input_dir.glob("*.json"))
    if not json_paths:
        logger.warning("No converted files found in %s", input_dir)
        return 0, 0

    processed = 0
    failed = 0
    for json_path in json_paths:
        if process_file(json_path, output_dir, sleep_seconds):
            processed += 1
        else:
            failed += 1
    return processed, failed


def main():
    """Main entry point for the process stage."""
    configure_logging()
    processed, failed = process_all()
    logger.info("Processing complete. Processed: %s, Failed: %s", processed, failed)
    if processed == 0:
        return 1
    else: 
        return 0
    
if __name__ == "__main__":
    sys.exit(main())

