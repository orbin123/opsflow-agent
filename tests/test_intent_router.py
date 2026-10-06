import hashlib
import json
from unittest.mock import Mock

import pytest

from app import intent_router


def test_bundled_model_and_threshold_load_from_any_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    intent_router.load_router.cache_clear()
    intent, confidence, threshold = intent_router.classify_request("What is the remote-work policy?")
    assert intent == "faq_retrieval" and threshold == 0.71
    assert threshold <= confidence <= 1
    assert intent_router.classify_request("What is the remote-work policy?") == (intent, confidence, threshold)
    intent_router.load_router.cache_clear()


@pytest.mark.parametrize(("digest", "threshold"), [("bad-digest", 0.71), (None, 0), (None, 1.1)])
def test_bad_artifact_or_threshold_rejected_before_deserialization(tmp_path, monkeypatch, digest, threshold):
    artifact = b"not a pickle"
    (tmp_path / "intent_router_svm.joblib").write_bytes(artifact)
    metadata = {"model_sha256": digest or hashlib.sha256(artifact).hexdigest(), "routing_threshold": {"selected": threshold}}
    (tmp_path / "intent_router_svm_metadata.json").write_text(json.dumps(metadata))
    monkeypatch.setattr(intent_router, "_MODEL_DIR", tmp_path)
    loader = Mock()
    monkeypatch.setattr(intent_router.joblib, "load", loader)
    intent_router.load_router.cache_clear()
    with pytest.raises(ValueError):
        intent_router.load_router()
    loader.assert_not_called()
    intent_router.load_router.cache_clear()
