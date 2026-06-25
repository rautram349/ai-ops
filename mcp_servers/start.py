"""Launch all four MCP servers in parallel subprocesses.

Usage::

    python -m mcp_servers.start

Each server is started as a separate process running its own ``__main__``
module.  Output from each server is prefixed with a coloured server label so
the combined stream is readable.  Ctrl-C stops all servers cleanly.
"""

from __future__ import annotations

import logging
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

from mcp_servers.config import (
    MCP_INVENTORY_PORT,
    MCP_MARKETING_PORT,
    MCP_METRICS_PORT,
    MCP_SUPPORT_PORT,
)

# ── ANSI colour codes (no external deps) ──────────────────────────────────────
_COLOURS = [
    "\033[36m",
    "\033[32m",
    "\033[33m",
    "\033[35m",
]  # cyan, green, yellow, magenta
_RESET = "\033[0m"

_SERVERS = [
    ("metrics", "mcp_servers.metrics"),
    ("inventory", "mcp_servers.inventory"),
    ("marketing", "mcp_servers.marketing"),
    ("support", "mcp_servers.support"),
]

_ROOT = Path(__file__).resolve().parent.parent
logger = logging.getLogger(__name__)


def _is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.2)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _kill_port(port: int) -> None:
    """Kill whichever process is listening on *port* (Windows + Unix)."""
    if sys.platform == "win32":
        # netstat -ano lists PID in the last column for LISTENING entries
        try:
            out = subprocess.check_output(
                ["netstat", "-ano"], text=True, stderr=subprocess.DEVNULL
            )
            for line in out.splitlines():
                if f":{port} " in line and "LISTENING" in line:
                    pid = line.split()[-1]
                    subprocess.call(
                        ["taskkill", "/F", "/PID", pid],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
        except Exception as exc:
            logger.warning("Failed to clear port %d on Windows: %s", port, exc)
    else:
        try:
            subprocess.call(
                ["fuser", "-k", f"{port}/tcp"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as exc:
            logger.warning("Failed to clear port %d on Unix: %s", port, exc)


def _stream(proc: subprocess.Popen, label: str, colour: str) -> None:
    """Forward a subprocess stream to stdout with a coloured prefix."""
    prefix = f"{colour}[{label}]{_RESET} "
    assert proc.stdout is not None
    for raw in proc.stdout:
        line = raw.decode(errors="replace").rstrip("\n")
        print(prefix + line, flush=True)


def main() -> None:
    python = sys.executable
    procs: list[subprocess.Popen] = []
    threads: list[threading.Thread] = []

    print("Starting MCP servers…\n")

    # Resolve ports from environment so we know what to clear
    ports = {
        "metrics":   MCP_METRICS_PORT,
        "inventory": MCP_INVENTORY_PORT,
        "marketing": MCP_MARKETING_PORT,
        "support":   MCP_SUPPORT_PORT,
    }

    # Clear any lingering processes on the target ports
    for name, port in ports.items():
        if _is_port_in_use(port):
            print(f"  [start] port {port} in use — clearing ({name})…")
            _kill_port(port)
            time.sleep(0.4)  # give OS time to release the port

    for idx, (name, module) in enumerate(_SERVERS):
        colour = _COLOURS[idx % len(_COLOURS)]
        proc = subprocess.Popen(
            [python, "-m", module],
            cwd=str(_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env={**os.environ},
        )
        procs.append(proc)

        t = threading.Thread(target=_stream, args=(proc, name, colour), daemon=True)
        t.start()
        threads.append(t)

    print(f"  metrics   → http://localhost:{ports['metrics']}/sse")
    print(f"  inventory → http://localhost:{ports['inventory']}/sse")
    print(f"  marketing → http://localhost:{ports['marketing']}/sse")
    print(f"  support   → http://localhost:{ports['support']}/sse")
    print("\nPress Ctrl-C to stop all servers.\n")

    try:
        # Block until any process exits unexpectedly
        while True:
            for proc in procs:
                ret = proc.poll()
                if ret is not None:
                    name = _SERVERS[procs.index(proc)][0]
                    print(
                        f"\n[start] ⚠  {name} exited with code {ret} — stopping all servers."
                    )
                    raise SystemExit(1)
            # Sleep briefly without busy-spinning
            threading.Event().wait(0.5)
    except KeyboardInterrupt:
        print("\n[start] Ctrl-C received — stopping all servers…")
    finally:
        for proc in procs:
            proc.terminate()
        for proc in procs:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        print("[start] All servers stopped.")


if __name__ == "__main__":
    main()
