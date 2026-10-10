"""Load only the repository's trusted intent artifact and its routing metadata."""

from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path

import joblib


_MODEL_DIR = Path(__file__).resolve().parents[2] / "artifacts/models"


@lru_cache(maxsize=1)
def load_router():
    metadata = json.loads((_MODEL_DIR / "intent_router_svm_metadata.json").read_text())
    artifact = _MODEL_DIR / "intent_router_svm.joblib"
    if hashlib.sha256(artifact.read_bytes()).hexdigest() != metadata["model_sha256"]:
        raise ValueError("Intent artifact does not match its metadata")
    threshold = metadata["routing_threshold"]["selected"]
    if not math.isfinite(threshold) or not 0 < threshold <= 1:
        raise ValueError("Invalid routing threshold")
    return joblib.load(artifact), threshold


def classify_request(message: str) -> tuple[str, float, float]:
    model, threshold = load_router()
    probabilities = model.predict_proba([message])[0]
    index = probabilities.argmax()
    confidence = float(probabilities[index])
    if not math.isfinite(confidence) or not 0 <= confidence <= 1:
        raise ValueError("Invalid classifier confidence")
    return str(model.classes_[index]), confidence, threshold
