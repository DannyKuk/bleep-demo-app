import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def post_hang(port: int) -> None:
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/faults/hang",
        data=json.dumps({"password": "pw"}).encode(),
        headers={"Content-Type": "application/json"},
    )
    urllib.request.urlopen(request, timeout=5).read()


def test_sigterm_ends_a_hung_process_quickly():
    port = free_port()
    env = {**os.environ, "PORT": str(port), "HOST": "127.0.0.1", "DEMO_PASSWORD": "pw"}
    proc = subprocess.Popen([sys.executable, "-m", "demo_app"], env=env, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1)
                break
            except OSError:
                time.sleep(0.1)
        post_hang(port)
        time.sleep(0.6)
        proc.send_signal(signal.SIGTERM)
        started = time.monotonic()
        proc.wait(timeout=5)
        assert time.monotonic() - started < 3
    finally:
        if proc.poll() is None:
            proc.kill()
