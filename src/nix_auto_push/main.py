from multiprocessing.connection import Client
from dataclasses import dataclass
from typing_extensions import Annotated

import cappa

from nix_auto_push.common import CommonArgs


@cappa.command()
@dataclass(kw_only=True)
class NixAutoPushClient(CommonArgs):
    store_path: Annotated[str, cappa.Arg(help="Store path to upload")]

    def __call__(self):
        conn = Client(self.socket_path, family="AF_UNIX")
        conn.send(self.store_path)
        conn.close()
        print("Sent message from client")


def main():
    _ = cappa.invoke(NixAutoPushClient)


if __name__ == "__main__":
    main()
