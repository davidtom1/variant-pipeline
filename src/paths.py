"""Central definitions of project data paths.

The data root defaults to ``<project_root>/data`` but can be overridden with
the ``VARIANT_PIPELINE_DATA_ROOT`` environment variable, which lets tests
point the pipeline at a temporary directory instead.
"""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_ROOT = Path(os.environ.get("VARIANT_PIPELINE_DATA_ROOT", PROJECT_ROOT / "data"))

INPUT_DIR = DATA_ROOT / "input"

OUTPUT_DIR = DATA_ROOT / "output"
CONVERTED_DIR = OUTPUT_DIR / "converted"
PROCESSED_DIR = OUTPUT_DIR / "processed"
HISTORY_DIR = OUTPUT_DIR / "history"

SUMMARY_FILE = OUTPUT_DIR / "summary.json"
