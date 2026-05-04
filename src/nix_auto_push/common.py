from dataclasses import dataclass
from typing_extensions import Annotated

import cappa


@dataclass
class CommonArgs:
    socket_path: Annotated[
        str,
        cappa.Arg(short=True, long=True, help="Socket file to listen to"),
    ] = "/tmp/nix-auto-push.sock"
