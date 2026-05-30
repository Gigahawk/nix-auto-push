import sys
import subprocess
import random
import string
from pathlib import Path
from time import sleep

from loguru import logger

import nix_auto_push.daemon
import nix_auto_push.main


def test_push():
    random_str = "".join(random.choices(string.ascii_letters, k=64))
    log_path = Path("/tmp/nix-auto-push-test_push.log")
    socket_path = Path("/tmp/nix-auto-push-test_push_socket.socket")
    if log_path.exists():
        log_path.unlink()
    if socket_path.exists():
        socket_path.unlink()
    assert not log_path.exists()
    assert not socket_path.exists()

    logger.info("Starting daemon")
    daemon_proc = subprocess.Popen(
        [
            sys.executable,
            nix_auto_push.daemon.__file__,
            "--socket-path",
            socket_path,
            "--cmd",
            f'env printf "$OUT_PATH" >> {log_path}',
            "--verify-cmd",
            "true",  # Don't bother validating
        ]
    )

    logger.info("Waiting for socket to come up")
    for _ in range(100):
        sleep(0.1)
        if socket_path.exists():
            break
    else:
        raise ValueError("Socket did not come up after 10s")

    logger.info("Starting client")
    client_proc = subprocess.Popen(
        [
            sys.executable,
            nix_auto_push.main.__file__,
            "--socket-path",
            socket_path,
            "--verify-cmd",
            "true",  # Don't bother validating
            random_str,
        ]
    )

    logger.info("Waiting for client to exit")
    client_proc.wait()

    # Wait a bit to ensure queue is flushed
    sleep(1)
    logger.info("Killing daemon")
    daemon_proc.terminate()

    logger.info(f"Checking output is in {log_path}")
    with open(log_path, "r", encoding="utf-8") as f:
        data = f.read()
        logger.debug("Log data:")
        logger.debug(data)
        assert random_str in data
