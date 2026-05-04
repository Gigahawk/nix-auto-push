from multiprocessing.connection import Listener
import subprocess
from typing_extensions import Annotated
from dataclasses import dataclass
import threading
import os

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
    verify_cmd: Annotated[
        str,
        cappa.Arg(
            help=(
                "Command to run to verify the nix store path is valid."
                "The path is available from the $OUT_PATH environment variable"
            ),
        ),
    ] = 'nix-store --verify-path "$OUT_PATH"'
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

    def submit_path(self, store_path: str):
        def _worker(_store_path: str):
            try:
                _a = subprocess.run(
                    self.verify_cmd,
                    shell=True,
                    env={**os.environ, "OUT_PATH": _store_path},
                    capture_output=True,
                    text=True,
                    check=True,
                )
            except subprocess.CalledProcessError as err:
                print(f"Verification of store path {_store_path} failed")
                print(err)
                print(err.args)
                print(err.output)
                print(err.returncode)
                print(err.stdout)
                print(err.stderr)
                return
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

    def __post_init__(self):
        self.listener: Listener | None = None
        self.job_queue: JobQueue | None = None

    def __call__(self):
        self.listener = Listener(self.socket_path, family="AF_UNIX")
        print(f"Listening on {self.socket_path}")

        self.job_queue = JobQueue(self.queue_path, max_attempts=self.retry_attempts)

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
