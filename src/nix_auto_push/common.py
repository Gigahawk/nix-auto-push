from dataclasses import dataclass
from typing_extensions import Annotated
import subprocess
import os
import sys

import cappa
from loguru import logger


@dataclass
class CommonArgs:
    socket_path: Annotated[
        str,
        cappa.Arg(short=True, long=True, help="Socket file to listen to"),
    ] = "/tmp/nix-auto-push.sock"
    verify_cmd: Annotated[
        str,
        cappa.Arg(
            short=True,
            long=True,
            help=(
                "Command to run to verify the nix store path is valid."
                "The path is available from the $OUT_PATH environment variable"
            ),
        ),
    ] = 'nix-store --verify-path "$OUT_PATH"'
    log_level: Annotated[
        str,
        cappa.Arg(
            short=True,
            long=True,
            help=("Log level"),
        ),
    ] = "info"

    def __post_init__(self):
        self.setup_logger()

    def setup_logger(self):
        logger.remove()
        _ = logger.add(sys.stderr, level=self.log_level.upper())

    def verify_store_path(self, store_path: str) -> bool:
        try:
            logger.info(f"Verifying store path {store_path}")
            _ = subprocess.run(
                self.verify_cmd,
                shell=True,
                env={**os.environ, "OUT_PATH": store_path},
                capture_output=True,
                text=True,
                check=True,
            )
            return True
        except subprocess.CalledProcessError as err:
            loguru.error(f"Verification of store path {store_path} failed")
            loguru.error(err)
            loguru.error(err.args)
            loguru.error(err.output)
            loguru.error(err.returncode)
            loguru.error(err.stdout)
            loguru.error(err.stderr)
        return False
