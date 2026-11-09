"""Loads trained models once; exposes the two-stage inference pipeline."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "ml"))

from ml.rank_profit import Ranker  # noqa: E402
from backend.config import settings

_ranker: Ranker | None = None


def get_ranker() -> Ranker:
    global _ranker
    if _ranker is None:
        _ranker = Ranker(model_dir=settings.MODEL_DIR, data_dir=settings.DATA_DIR)
    return _ranker
