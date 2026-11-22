"""Launch the D2IC desktop GUI in a local browser, using CPU-only JAX."""

from __future__ import annotations

# Set both selectors before importing the application or any numerical package.
import os

os.environ["JAX_PLATFORMS"] = "cpu"
os.environ["JAX_PLATFORM_NAME"] = "cpu"

import argparse
import socket
import threading
import time
import urllib.error
import urllib.request
import webbrowser


def _arguments(argv=None):
    parser = argparse.ArgumentParser(description="D2IC_GUI CPU local application")
    parser.add_argument("study_folder", nargs="?", help="Optional folder of an existing study")
    parser.add_argument("--port", type=int, default=0, help="Local port (default: choose a free port)")
    parser.add_argument("--no-browser", action="store_true", help="Do not open a browser")
    return parser.parse_args(argv)


def _bind_loopback(port):
    """Bind and listen on one loopback socket, retaining it through server startup."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", port))
        sock.listen(socket.SOMAXCONN)
        sock.setblocking(False)
        return sock
    except BaseException:
        sock.close()
        raise


def _open_browser_when_ready(url, stopped, timeout=30.0):
    """Open the local page after an HTTP request confirms the app is serving."""
    deadline = time.monotonic() + timeout
    while not stopped.is_set() and time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=0.5):
                webbrowser.open(url)
                return
        except (urllib.error.URLError, TimeoutError, OSError):
            stopped.wait(0.1)


def main(argv=None):
    args = _arguments(argv)
    if not 0 <= args.port <= 65535:
        raise SystemExit("--port doit être compris entre 0 et 65535")

    # These imports can load JAX transitively through the GUI and stay below the
    # CPU environment selection above.
    import uvicorn
    from .server import create_app

    sock = _bind_loopback(args.port)
    port = sock.getsockname()[1]
    url = f"http://127.0.0.1:{port}/"
    stopped = threading.Event()
    browser_thread = None
    if not args.no_browser:
        browser_thread = threading.Thread(
            target=_open_browser_when_ready, args=(url, stopped), daemon=True,
            name="d2ic-browser-ready",
        )
        browser_thread.start()

    print(f"D2IC_GUI disponible sur {url}", flush=True)
    try:
        server = uvicorn.Server(uvicorn.Config(create_app(args.study_folder), host="127.0.0.1",
                                              port=port, log_level="info"))
        server.run(sockets=[sock])
    finally:
        stopped.set()
        sock.close()
        if browser_thread is not None:
            browser_thread.join(timeout=1.0)


if __name__ == "__main__":
    main()
