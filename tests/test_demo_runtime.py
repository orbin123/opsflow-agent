"""Deployment boundaries and actual child process termination."""

import subprocess
import sys

import pytest

from deploy import run_demo


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
