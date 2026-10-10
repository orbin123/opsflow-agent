from pathlib import Path
import os
import socket
from unittest.mock import Mock

import pytest

from app.workflows import faq_workflow, keyword_workflow, sentiment_workflow


@pytest.mark.parametrize("workflow,model_setting", [
    (sentiment_workflow, "GROQ_SENTIMENT_MODEL"),
    (keyword_workflow, "GROQ_KEYWORD_MODEL"),
    (faq_workflow, "GROQ_FAQ_MODEL"),
])
@pytest.mark.parametrize("environment_key", [None, "environment-test-key"])
def test_root_dotenv_loads_without_overriding_environment(
    monkeypatch, tmp_path, workflow, model_setting, environment_key,
):
    monkeypatch.setattr(os, "environ", os.environ.copy())
    monkeypatch.setattr(socket.socket, "connect", Mock(side_effect=AssertionError("Network forbidden")))
    root = tmp_path / "repository"
    module_path = root / "app" / "workflows" / Path(workflow.__file__).name
    module_path.parent.mkdir(parents=True)
    module_path.touch()
    (root / ".env").write_text(
        f"GROQ_API_KEY=dotenv-test-key\n{model_setting}=openai/gpt-oss-120b\n",
    )
    monkeypatch.setattr(workflow, "__file__", str(module_path))
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PYTHON_DOTENV_DISABLED", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv(model_setting, raising=False)
    if environment_key is not None:
        monkeypatch.setenv("GROQ_API_KEY", environment_key)
        monkeypatch.setenv(model_setting, "openai/gpt-oss-20b")
    client = Mock()
    monkeypatch.setattr(workflow, "ChatGroq", client)

    workflow._create_model(workflow._EXTRACTION_SCHEMA, "Extraction")

    assert client.call_args.kwargs["api_key"] == (environment_key or "dotenv-test-key")
    assert client.call_args.kwargs["model"] == (
        "openai/gpt-oss-20b" if environment_key else "openai/gpt-oss-120b"
    )
