from dataclasses import dataclass
from typing_extensions import Annotated
import subprocess
import os

import cappa


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

    def verify_store_path(self, store_path: str) -> bool:
        try:
            print(f"Verifying store path {store_path}")
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
            print(f"Verification of store path {store_path} failed")
            print(err)
            print(err.args)
            print(err.output)
            print(err.returncode)
            print(err.stdout)
            print(err.stderr)
        return False
