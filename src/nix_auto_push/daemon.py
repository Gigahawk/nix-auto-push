from multiprocessing.connection import Listener
import subprocess
from typing_extensions import Annotated
from dataclasses import dataclass
import threading
import os
import time

import cappa

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

    def submit_path(self, store_path: str):
        def _worker(_store_path: str):
            if self.verify_store_path(_store_path):
                print(f"Submitting store path {_store_path} to queue")
                if self.job_queue is not None:
                    self.job_queue.submit_job(_store_path)
                else:
                    print("Error: job queue not initialized?")

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
            print("Queue handling thread already started, not restarting")
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
                    print("Error: job queue not initialized in queue handler?")
                    continue
                if self.job_queue.job_available():
                    print("Job is available")
                    self._running_push_workers.append(self.start_push_worker())

        self.queue_handler_thread = threading.Thread(
            target=_worker,
            daemon=True,
        )
        self.queue_handler_thread.start()

    def __post_init__(self):
        self.listener: Listener | None = None
        self.job_queue: JobQueue | None = None
        self.queue_handler_thread: threading.Thread | None = None
        self._running_push_workers: list[threading.Thread] = []

    def start_push_worker(self):
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
                print(f"Push of store_path {_store_path} successful")
                print(_res.stdout)
                print(_res.stderr)
            except subprocess.CalledProcessError as err:
                print(f"Push of store path {_store_path} failed")
                print(err)
                print(err.args)
                print(err.output)
                print(err.returncode)
                print(err.stdout)
                print(err.stderr)
                if self.job_queue is not None:
                    self.job_queue.finish_job(job_id, err, success=False)
                else:
                    print("Error: job queue not initialized?")
                return
            if self.job_queue is not None:
                self.job_queue.finish_job(job_id, _res)
            else:
                print("Error: job queue not initialized?")

        t = threading.Thread(
            target=_worker,
            args=(store_path,),
        )
        t.start()
        return t

    def __call__(self):
        self.listener = Listener(self.socket_path, family="AF_UNIX")
        print(f"Listening on {self.socket_path}")

        self.job_queue = JobQueue(self.queue_path, max_attempts=self.retry_attempts)

        self.start_queue_handler()

        while True:
            conn = self.listener.accept()
            try:
                msg = str(conn.recv())
                for line in msg.splitlines():
                    print("Got message")
                    print(line)
                    self.submit_path(line)
            finally:
                conn.close()


def main():
    _ = cappa.invoke(NixAutoPushDaemon)


if __name__ == "__main__":
    main()
