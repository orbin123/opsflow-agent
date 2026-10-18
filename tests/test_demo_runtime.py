"""Deployment boundaries and actual child process termination."""

import subprocess
import sys

import pytest

from deploy import run_demo


@pytest.fixture
def proxy_files(monkeypatch, tmp_path):
    monkeypatch.setattr(run_demo, "RUNTIME", tmp_path / "runtime")
    for key in ("OPSFLOW_API_URL", "OPSFLOW_TEMPORARY_DEMO", "SMTP_USERNAME",
                "SMTP_PASSWORD", "OPSFLOW_USER_EMAIL"):
        monkeypatch.setenv(key, run_demo.os.environ.get(key, ""))
    monkeypatch.setenv("OPSFLOW_DEMO_PASSWORD", "demo-password-for-review")
    monkeypatch.delenv("OPSFLOW_METRICS_PASSWORD", raising=False)
    monkeypatch.delenv("PORT", raising=False)
    calls = []

    def htpasswd(command, **kwargs):
        calls.append((command, kwargs))
        from pathlib import Path
        Path(command[4]).write_text(command[5] + ":test-hash")

    monkeypatch.setattr(run_demo.subprocess, "run", htpasswd)
    return calls


def test_metrics_disabled_without_configuration(proxy_files):
    config = run_demo.prepare_proxy().read_text()
    assert "location = /metrics {\n            return 404;" in config
    assert "metrics-htpasswd" not in config
    assert len(proxy_files) == 1


def test_metrics_credential_is_separate_and_removed_from_child_environment(proxy_files, monkeypatch):
    secret = "metrics-password-for-review"
    monkeypatch.setenv("OPSFLOW_METRICS_PASSWORD", secret)
    config = run_demo.prepare_proxy().read_text()
    assert "http://127.0.0.1:8000/metrics" in config
    assert 'proxy_set_header Authorization "";' in config
    assert "location /api/ { return 404; }" in config
    assert secret not in config
    assert "OPSFLOW_METRICS_PASSWORD" not in run_demo.os.environ
    assert "OPSFLOW_DEMO_PASSWORD" not in run_demo.os.environ
    assert [command[-1] for command, _ in proxy_files] == ["opsflow", "opsflow-metrics"]
    assert proxy_files[1][1]["input"] == secret + "\n"
    assert secret not in str(proxy_files[1][0])
    assert (run_demo.RUNTIME / "metrics-htpasswd").stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("secret", ["", "short", "é" * 37, "a" * 20 + "\n",
                                    "a" * 20 + "\r",
                                    "demo-password-for-review", " metrics-password-for-review "])
def test_invalid_metrics_configuration_fails_before_writing_credentials(proxy_files, monkeypatch, secret):
    monkeypatch.setenv("OPSFLOW_METRICS_PASSWORD", secret)
    with pytest.raises(ValueError, match="separate metrics password"):
        run_demo.prepare_proxy()
    assert not proxy_files


@pytest.mark.parametrize("password", ["", "short", "x" * 73, "a" * 20 + "\n"])
def test_proxy_refuses_missing_or_invalid_password(monkeypatch, password):
    monkeypatch.setenv("OPSFLOW_DEMO_PASSWORD", password)
    with pytest.raises(ValueError):
        run_demo.prepare_proxy()


@pytest.mark.parametrize("port", ["not-a-port", "80", "8000", "8501", "65536"])
def test_proxy_refuses_invalid_or_internal_public_port(monkeypatch, port):
    monkeypatch.setenv("PORT", port)
    with pytest.raises(ValueError):
        run_demo.prepare_proxy()


def test_shutdown_terminates_and_reaps_real_children():
    children = [subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
                for _ in range(2)]
    try:
        run_demo.stop_children(children, grace=2)
        assert all(child.poll() is not None for child in children)
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
                child.wait()


def test_shutdown_kills_child_that_ignores_termination():
    child = subprocess.Popen([
        sys.executable, "-u", "-c",
        "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        "print('ready', flush=True); time.sleep(60)",
    ], stdout=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline().strip() == "ready"
        run_demo.stop_children([child], grace=0.1)
        assert child.returncode is not None
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()
        child.stdout.close()


def test_readiness_stops_when_child_exits():
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    with pytest.raises(RuntimeError, match="interrupted"):
        run_demo.wait_ready([child], "http://127.0.0.1:1", lambda: False)
