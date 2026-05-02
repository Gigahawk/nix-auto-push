from multiprocessing.connection import Client

import click


@click.command()
@click.option(
    "--socket",
    "socket_path",
    help="Socket file to listen to",
    default="/tmp/nix-auto-push.sock",
    type=str,
)
def main(socket_path):
    conn = Client(socket_path, family="AF_UNIX")
    conn.send("Hello from client")
    conn.close()
    print("Sent message from client")


if __name__ == "__main__":
    main()
