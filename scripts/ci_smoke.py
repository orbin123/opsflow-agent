"""Exercise the built demo image without model credentials or executing work."""

import base64
import http.client
import os
import secrets
import subprocess
import sys
import time


def docker(*args, **kwargs):
    return subprocess.check_output(["docker", *args], text=True, **kwargs).strip()


def response(port, path, authorization=None, *, websocket=False):
    headers = {}
    if authorization:
        headers["Authorization"] = authorization
    if websocket:
        headers.update({
            "Connection": "Upgrade", "Upgrade": "websocket",
            "Sec-WebSocket-Version": "13",
            "Sec-WebSocket-Key": base64.b64encode(secrets.token_bytes(16)).decode(),
            "Sec-WebSocket-Protocol": "streamlit",
        })
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    try:
        connection.request("GET", path, headers=headers)
        return connection.getresponse().status
    finally:
        connection.close()


def main(image):
    password = secrets.token_urlsafe(24)
    environment = {**os.environ, "OPSFLOW_DEMO_PASSWORD": password}
    container = docker("run", "-d", "-p", "127.0.0.1::10000",
                       "-e", "OPSFLOW_DEMO_PASSWORD", image, env=environment)
    try:
        port = int(docker("port", container, "10000/tcp").rsplit(":", 1)[1])
        deadline = time.monotonic() + 90
        while True:
            if docker("inspect", "--format", "{{.State.Running}}", container) != "true":
                raise RuntimeError("Demo exited before becoming healthy")
            try:
                if response(port, "/health") == 200:
                    break
            except OSError:
                pass
            if time.monotonic() >= deadline:
                raise RuntimeError("Demo did not become healthy within 90 seconds")
            time.sleep(0.5)

        authorization = "Basic " + base64.b64encode(f"opsflow:{password}".encode()).decode()
        wrong = "Basic " + base64.b64encode(b"opsflow:incorrect-password").decode()
        for path, auth, websocket, expected in [
            ("/", None, False, 401),
            ("/", wrong, False, 401),
            ("/", authorization, False, 200),
            ("/_stcore/stream", None, True, 401),
            ("/_stcore/stream", wrong, True, 401),
            ("/_stcore/stream", authorization, True, 101),
            *[(path, authorization, False, 404)
              for path in ("/api/v1/chats", "/metrics", "/docs", "/openapi.json")],
        ]:
            actual = response(port, path, auth, websocket=websocket)
            if actual != expected:
                raise RuntimeError(f"{path}: expected HTTP {expected}, received {actual}")
        print("Container health, UI/WebSocket authentication and hidden backend paths pass.")
    except Exception:
        print(docker("logs", container), file=sys.stderr)
        raise
    finally:
        docker("stop", "--time", "30", container)
        docker("rm", "-f", container)

    missing_password = docker("run", "-d", image)
    try:
        code = docker("wait", missing_password, timeout=20)
        if code != "1":
            raise RuntimeError("Container without a password did not fail closed")
        print("Missing-password startup fails closed.")
    finally:
        docker("rm", "-f", missing_password)


if __name__ == "__main__":
    main(sys.argv[1])
