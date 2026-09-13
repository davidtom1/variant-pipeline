"""Aggregate stage: combines all per-file metrics into a single run summary.

The summary is rebuilt from scratch on every run so that repeated runs over the
same inputs produce the same totals. A timestamped copy is archived under
history/ as an append-only record of past runs.
"""
import json
import logging
import sys
from collections import Counter
from datetime import datetime, timezone
from src.validation import chrom_sort_key

from src.io_utils import configure_logging, write_json_atomic
from src.paths import HISTORY_DIR, PROCESSED_DIR, SUMMARY_FILE

logger = logging.getLogger("aggregate")


def read_metrics(metrics_path):
    """Read and validate one metrics file written by the process stage.
    Returns the metrics dict, or None if the file cannot be read, is not
    valid JSON, or is missing any of the fields the summary depends on.
    """
    try:
        with open(metrics_path, encoding="utf-8") as f:
            metrics = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.error("Failed to read metrics file %s: %s", metrics_path, e)
        return None
    expected_keys = {"source_file", "valid_count", "skipped_count", "duration_seconds", "variants_per_chromosome"}
    missing = expected_keys - metrics.keys()
    if missing:
        logger.error("Metrics file %s is missing required keys: %s", metrics_path, ", ".join(sorted(missing)))
        return None
    return metrics



def build_summary(metrics_list, failed_count):
    """Combine per-file metrics into a single run summary.

    Pure function: given the same metrics it always returns the same summary,
    which is what makes repeated runs produce identical results. Total
    processing time is the sum of each file's duration, not the wall-clock
    span of the run; the two differ once files are processed in parallel.

    Args:
        metrics_list: metrics dicts that were read successfully.
        failed_count: how many metrics files could not be read, recorded in
            the summary so it states its own coverage.
    """
    total_variants = sum(m["valid_count"] for m in metrics_list)
    total_skipped = sum(m["skipped_count"] for m in metrics_list)
    total_duration = round(sum(m["duration_seconds"] for m in metrics_list), 3)
    variants_per_chromosome = Counter()
    for m in metrics_list:
        variants_per_chromosome.update(m["variants_per_chromosome"])
    summary = {
        "total_variants": total_variants,
        "total_skipped": total_skipped,
        "total_duration_seconds": total_duration,
        "variants_per_chromosome": dict(sorted(variants_per_chromosome.items(), key=lambda kv: chrom_sort_key(kv[0]))),
        "input_files": sorted(m["source_file"] for m in metrics_list),
        "files_processed": len(metrics_list),
        "metrics_files_failed": failed_count,

    }
    return summary



def write_summary(summary, summary_file=SUMMARY_FILE, history_dir=HISTORY_DIR):
    """Write the summary to its fixed path and archive a timestamped copy.

    The fixed path is overwritten on every run. The history directory is an
    append-only record of past runs and is never read back by this stage.
    """
    write_json_atomic(summary, summary_file)
    logger.info("Wrote summary to %s", summary_file)
    archive_name = datetime.now(timezone.utc).strftime("summary_%Y%m%dT%H%M%S_%fZ.json")
    write_json_atomic(summary, history_dir / archive_name)
    logger.info("Archived summary to %s", history_dir / archive_name)



def aggregate_all(input_dir=PROCESSED_DIR, summary_file=SUMMARY_FILE,
                  history_dir=HISTORY_DIR):
    """Read all metrics files, build the summary, and write it.
    Returns the summary dict, or None if there was nothing to aggregate.
    """
    if not input_dir.exists():
        logger.error("Input directory %s does not exist. Process stage may not have run.", input_dir)
        return None
    metrics_paths = sorted(input_dir.glob("*.json"))
    if not metrics_paths:
        logger.warning("No metrics files found in %s. Nothing to aggregate.", input_dir)
        return None
    good_metrics = []
    failed_count = 0
    for metrics_path in metrics_paths:
        metrics = read_metrics(metrics_path)
        if metrics is not None:
            good_metrics.append(metrics)
        else:
            failed_count += 1
    if not good_metrics:
        logger.error("No valid metrics files could be read. Nothing to aggregate.")
        return None
    if failed_count > 0:
        logger.warning("%d metrics files could not be read and were skipped.", failed_count)
    summary = build_summary(good_metrics, failed_count)
    write_summary(summary, summary_file, history_dir)
    logger.info("Aggregated %d metrics files into summary.", len(good_metrics))
    return summary


def main():
    """Main entry point for the aggregate stage."""
    configure_logging()
    summary = aggregate_all()
    if summary is None:
        logger.error("Aggregation failed or produced no summary.")
        return 1
    else:
        logger.info("Aggregated %d files: %d variants, %d skipped, %.1fs total",
            summary["files_processed"], summary["total_variants"],
            summary["total_skipped"], summary["total_duration_seconds"])
        return 0


if __name__ == "__main__":
    sys.exit(main())