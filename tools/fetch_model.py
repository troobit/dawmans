"""Populate the gitignored `models/` cache with the embedding model.

Run once per machine, with `make fetch-model`. This sits deliberately outside the
ingestion path: ingestion runs with `HF_HUB_OFFLINE=1` and fails immediately when the
cache is absent (requirement 8.5), so the single network access this project needs
happens here and nowhere else.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

MODEL_NAME = "BAAI/bge-small-en-v1.5"
CACHE_DIR = Path(__file__).resolve().parent.parent / "models"


def main() -> int:
    # The ingestion environment pins this on; fetching is the one place that must not.
    os.environ.pop("HF_HUB_OFFLINE", None)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    from fastembed import TextEmbedding

    print(f"Fetching {MODEL_NAME} into {CACHE_DIR}")
    TextEmbedding(model_name=MODEL_NAME, cache_dir=str(CACHE_DIR))
    print("Done. Ingestion can now run offline.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
