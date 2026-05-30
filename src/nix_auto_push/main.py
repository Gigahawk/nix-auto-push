from multiprocessing.connection import Client
from dataclasses import dataclass
from typing_extensions import Annotated
from collections.abc import Iterable
import sys

import cappa
from loguru import logger

from nix_auto_push.common import CommonArgs


@cappa.command()
@dataclass(kw_only=True)
class NixAutoPushClient(CommonArgs):
    # Ignore mypy error 'Attributes without a default cannot follow attributes with one'
    # For normal instantiation of dataclasses this would be problematic but because
    # we always invoke with Cappa it doesn't matter
    store_paths: Annotated[list[str], cappa.Arg(help="Store path(s) to upload")]  # type: ignore[misc]

    def __call__(self) -> int:
        # Ensure we get an iterable
        if not isinstance(self.store_paths, Iterable):
            self.store_paths = self.store_paths.split()

        # Handle elements with spaces (i.e. "/nix/store/aaa /nix/store/bbb")
        store_paths = []
        for store_path in self.store_paths:
            store_paths.extend(store_path.split())
        retcode = 0
        for store_path in store_paths:
            if not self.verify_store_path(store_path):
                retcode += 1
                continue
            # Client can't be reused???
            conn = Client(self.socket_path, family="AF_UNIX")
            conn.send(store_path)
            logger.info(f"Sent store path {store_path} from client")
            conn.close()
        return retcode


def main() -> int:
    # Wrapper will sys.exit with this code
    return cappa.invoke(NixAutoPushClient)


if __name__ == "__main__":
    sys.exit(main())
