"""Run the temporary demo's private API/UI and authenticated public proxy."""

import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from urllib.request import urlopen


RUNTIME = Path("/tmp/opsflow-runtime")
SHUTDOWN_SECONDS = 140


def prepare_proxy():
    port = int(os.environ.get("PORT", "10000"))
    if not 1024 <= port <= 65535 or port in {8000, 8501}:
        raise ValueError("Invalid public port")
    password = os.environ.pop("OPSFLOW_DEMO_PASSWORD", "")
    if not 16 <= len(password.encode()) <= 72 or "\n" in password or "\r" in password:
        raise ValueError("Set a demo password of 16–72 bytes without line breaks")
    RUNTIME.mkdir(mode=0o700, exist_ok=True)
    subprocess.run(["htpasswd", "-i", "-B", "-c", str(RUNTIME / "htpasswd"), "opsflow"],
                   input=password + "\n", text=True, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    (RUNTIME / "htpasswd").chmod(0o600)
    template = Path(__file__).with_name("nginx.conf.template").read_text()
    config = RUNTIME / "nginx.conf"
    config.write_text(template.replace("__PORT__", str(port)))
    # Demo packaging always keeps requests internal and never starts delivery.
    os.environ["OPSFLOW_API_URL"] = "http://127.0.0.1:8000"
    os.environ["OPSFLOW_TEMPORARY_DEMO"] = "1"
    for key in ("SMTP_USERNAME", "SMTP_PASSWORD", "OPSFLOW_USER_EMAIL"):
        os.environ.pop(key, None)
    return config


def stop_children(children, *, grace=SHUTDOWN_SECONDS):
    for child in reversed(children):
        if child.poll() is None:
            child.terminate()
    deadline = time.monotonic() + grace
    for child in children:
        try:
            child.wait(timeout=max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()


def wait_ready(children, url, stopping, *, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if stopping() or any(child.poll() is not None for child in children):
            raise RuntimeError("Demo startup interrupted")
        try:
            with urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except OSError:
            pass
        time.sleep(0.2)
    raise RuntimeError("Demo startup timed out")


def main():
    children = []
    stopping = False

    def request_stop(signum, frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    try:
        config = prepare_proxy()
        children.append(subprocess.Popen([
            sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
            "--port", "8000", "--workers", "1", "--no-access-log",
            "--timeout-graceful-shutdown", "135",
        ]))
        # Read storage before publishing the listener; this never executes a turn.
        wait_ready(children, "http://127.0.0.1:8000/api/v1/chats", lambda: stopping)
        children.append(subprocess.Popen([
            sys.executable, "-m", "streamlit", "run", "streamlit_app.py",
            "--server.address", "127.0.0.1", "--server.port", "8501",
            "--server.headless", "true", "--server.fileWatcherType", "none",
            "--browser.serverAddress", os.environ.get("RENDER_EXTERNAL_HOSTNAME", "localhost"),
            "--browser.gatherUsageStats", "false",
        ]))
        wait_ready(children, "http://127.0.0.1:8501/_stcore/health", lambda: stopping)
        children.append(subprocess.Popen(["nginx", "-e", "stderr", "-c", str(config), "-g", "daemon off;"]))
        port = int(os.environ.get("PORT", "10000"))
        wait_ready(children, f"http://127.0.0.1:{port}/health", lambda: stopping)
        print("Temporary demo ready; reminder delivery is disabled.", flush=True)
        while not stopping:
            if any(child.poll() is not None for child in children):
                print("Demo process exited; stopping service.", file=sys.stderr, flush=True)
                return 1
            time.sleep(0.2)
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
        print("Demo startup failed; check runtime configuration.", file=sys.stderr, flush=True)
        return 1
    finally:
        stop_children(children)


if __name__ == "__main__":
    sys.exit(main())
