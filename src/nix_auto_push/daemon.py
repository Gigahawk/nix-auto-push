from multiprocessing.connection import Listener
import subprocess

import click

class NixAutoPushDaemon:
    def __init__()


@click.command()
@click.option(
    "--socket",
    "socket_path",
    help="Socket file to listen to",
    default="/tmp/nix-auto-push.sock",
    type=str,
)
@click.option(
    "--cmd",
    help=(
        "Command to run for every nix store path sent to the daemon."
        "The path is available from the $OUT_PATH environment variable"
    ),
    default='/usr/bin/env printf "$OUT_PATH"',
    type=str,
)
def main(socket_path, cmd):
    listener = Listener(socket_path, family="AF_UNIX")
    print(f"Listening on {socket_path}")

    while True:
        conn = listener.accept()
        try:
            msg = str(conn.recv())
            for line in msg.splitlines():
                print("Got message")
                print(msg)
                print("Running:")
                print(cmd)
                result = subprocess.run(
                    cmd,
                    shell=True,
                    env={"OUT_PATH": msg},
                    capture_output=True,
                    text=True,
                )
                print("Output")
                print(result.stdout, result.stderr)
                print("Returncode")
                print(result.returncode)
        finally:
            conn.close()


if __name__ == "__main__":
    main()
