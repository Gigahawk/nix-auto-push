from multiprocessing.connection import Listener
import subprocess
from typing_extensions import Annotated
from typing import cast
from io import TextIOWrapper
from dataclasses import dataclass, field
import threading
import os
import time
import sys

import cappa
from loguru import logger

from nix_auto_push.job_queue import JobQueue
from nix_auto_push.common import CommonArgs


@cappa.command(default_long=True, default_short=True)
@dataclass
class NixAutoPushDaemon(CommonArgs):
    cmd: Annotated[
        str,
        cappa.Arg(
            help=(
                "Command to run for every nix store path sent to the daemon."
                "The path is available from the $OUT_PATH environment variable"
            )
        ),
    ] = '/usr/bin/env printf "$OUT_PATH"'
    network_check_cmd: Annotated[
        str,
        cappa.Arg(
            help=("Command to run to verify the daemon still has a network connection"),
        ),
    ] = "true"
    network_check_timeout: Annotated[
        int,
        cappa.Arg(
            short="-nt",
            help="Time in seconds to wait for --network-check-cmd to pass",
        ),
    ] = 1
    queue_path: Annotated[
        str,
        cappa.Arg(
            help="Path to store sqlite database used to track submission progress"
        ),
    ] = "./nix-auto-push.sqlite"
    retry_attempts: Annotated[
        int,
        cappa.Arg(help="Max number of attempts to push a particular store path"),
    ] = 5
    delete_attempts: Annotated[
        int,
        cappa.Arg(
            help="Max number of attempts before the push of a particular store path is permanently cancelled"
        ),
    ] = 10
    push_workers: Annotated[
        int,
        cappa.Arg(
            help="Number of simultaneous workers pushing objects in the background"
        ),
    ] = 1
    poll_rate: Annotated[
        int,
        cappa.Arg(
            short="-pr",
            help="Seconds between checks to see if push jobs are available",
        ),
    ] = 1

    _running_push_workers: list[threading.Thread] = field(init=False)
    _listener: Listener | None = field(init=False)
    job_queue: JobQueue | None = field(init=False)
    queue_handler_thread: threading.Thread | None = field(init=False)

    def submit_path(self, store_path: str):
        def _worker(_store_path: str):
            if self.verify_store_path(_store_path):
                logger.info(f"Submitting store path {_store_path} to queue")
                if self.job_queue is not None:
                    self.job_queue.submit_job(_store_path)
                else:
                    logger.critical("Job queue not initialized?")

        t = threading.Thread(
            target=_worker,
            args=(store_path,),
        )
        t.start()
        return t

    def start_queue_handler(self):
        if (
            self.queue_handler_thread is not None
            and self.queue_handler_thread.is_alive()
        ):
            logger.debug("Queue handling thread already started, not restarting")
            return

        def _worker():
            while True:
                time.sleep(self.poll_rate)
                # Remove finished push workers from the queue
                self._running_push_workers = [
                    t for t in self._running_push_workers if t.is_alive()
                ]
                if len(self._running_push_workers) >= self.push_workers:
                    continue

                if self.job_queue is None:
                    logger.critical(
                        "Error: job queue not initialized in queue handler?"
                    )
                    continue
                if self.job_queue.job_available():
                    logger.debug("Job is available")
                    if self.has_network():
                        self._running_push_workers.append(self.start_push_worker())

        self.queue_handler_thread = threading.Thread(
            target=_worker,
            daemon=True,
        )
        self.queue_handler_thread.start()

    def has_network(self) -> bool:
        try:
            _ = subprocess.run(
                self.network_check_cmd,
                capture_output=True,
                timeout=self.network_check_timeout,
                shell=True,
                check=True,
            )
            return True
        except (
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
        ) as err:
            logger.error("Network is not available")
            logger.error(err)
            logger.error(err.args)
            logger.error(err.output)
            if _ret := getattr(err, "returncode", None) is not None:
                logger.error(f"Return code: {_ret}")
            logger.error(err.stdout)
            logger.error(err.stderr)
        return False

    def __post_init__(self):
        super().__post_init__()
        self.queue_handler_thread = None
        self.job_queue = None
        self._listener = None
        self._running_push_workers = []

    def start_push_worker(self):
        if self.job_queue is None:
            raise RuntimeError("Job queue was not initialized?")
        job_id, store_path = self.job_queue.start_job()

        def _worker(_store_path: str):
            try:
                _res = subprocess.run(
                    self.cmd,
                    shell=True,
                    env={**os.environ, "OUT_PATH": _store_path},
                    capture_output=True,
                    text=True,
                    check=True,
                )
                logger.success(f"Push of store_path {_store_path} successful")
                logger.debug(_res.stdout)
                logger.debug(_res.stderr)
            except subprocess.CalledProcessError as err:
                logger.error(f"Push of store path {_store_path} failed")
                logger.error(err)
                logger.error(err.args)
                logger.error(err.output)
                logger.error(err.returncode)
                logger.error(err.stdout)
                logger.error(err.stderr)
                if self.job_queue is not None:
                    self.job_queue.finish_job(job_id, err, success=False)
                else:
                    logger.critical("Error: job queue not initialized?")
                return
            if self.job_queue is not None:
                self.job_queue.finish_job(job_id, _res)
            else:
                logger.critical("Error: job queue not initialized?")

        t = threading.Thread(
            target=_worker,
            args=(store_path,),
        )
        t.start()
        return t

    @property
    def listener(self) -> Listener:
        if self._listener is None:
            try:
                self._listener = Listener(self.socket_path, family="AF_UNIX")
            except OSError as err:
                logger.error(err)
                code = err.args[0]
                if code == 98:
                    logger.warning("Attempting to delete old socket")
                    os.remove(self.socket_path)
                    self._listener = Listener(self.socket_path, family="AF_UNIX")
                else:
                    raise err

        return self._listener

    def __call__(self):
        # Ensure sys.stdout is a TextIOWrapper to satisfy mypy
        sys.stdout = cast(TextIOWrapper, sys.stdout)
        sys.stdout.reconfigure(line_buffering=True)

        assert self.listener is not None
        logger.info(f"Listening on {self.socket_path}")

        self.job_queue = JobQueue(
            self.queue_path,
            max_attempts=self.retry_attempts,
            delete_attempts=self.delete_attempts,
        )

        self.start_queue_handler()

        while True:
            conn = self.listener.accept()
            try:
                msg = str(conn.recv())
                for item in msg.split():
                    logger.info("Got message")
                    logger.info(item)
                    self.submit_path(item)
            finally:
                conn.close()


def main():
    _ = cappa.invoke(NixAutoPushDaemon)


if __name__ == "__main__":
    main()
