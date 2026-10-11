"""Start the SSH local port forward used to access Qdrant in the CentOS VM."""

from __future__ import annotations

import subprocess
import sys


def main() -> int:
    command = [
        "ssh",
        "-N",
        "-o",
        "ExitOnForwardFailure=yes",
        "-o",
        "ServerAliveInterval=30",
        "-o",
        "ServerAliveCountMax=3",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-L",
        "127.0.0.1:6333:127.0.0.1:6333",
        "root@192.168.59.100",
    ]
    print("Starting Qdrant tunnel: 127.0.0.1:6333 -> VM 127.0.0.1:6333")
    print("Keep this process running while using Qdrant. Press Ctrl+C to stop it.")
    try:
        return subprocess.call(command)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
