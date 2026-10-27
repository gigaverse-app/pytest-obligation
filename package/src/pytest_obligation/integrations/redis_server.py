"""Disposable Redis for destructive tests; requires a local redis-server on POSIX."""

import os
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import redis


@contextmanager
def redis_server(*, executable: str = "redis-server") -> Iterator[str]:
    """Yield a private TCP URL, then stop the owned process, even after failures.

    No environment URL or default database is reused. Each context owns its
    server, so FLUSHDB and server-wide fault injection cannot affect another
    test or the developer's Redis. Child workers may inherit the yielded URL.
    Persistence is disabled and the temporary directory is removed on exit.
    """
    with tempfile.TemporaryDirectory(prefix="obligation-redis-") as directory:
        # Redis cannot inherit a listening socket; a bind race fails startup.
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        unix_socket = str(Path(directory) / "redis.sock")
        with (Path(directory) / "redis.log").open("w+") as log:
            process = subprocess.Popen(
                [
                    executable,
                    "--bind",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--unixsocket",
                    unix_socket,
                    "--unixsocketperm",
                    "700",
                    "--save",
                    "",
                    "--appendonly",
                    "no",
                    "--dir",
                    directory,
                ],
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            try:
                # Readiness uses our private socket, never a possibly reused TCP port.
                with redis.Redis(unix_socket_path=unix_socket, socket_timeout=0.1) as client:
                    deadline = time.monotonic() + 10
                    while True:
                        if process.poll() is not None or time.monotonic() >= deadline:
                            log.seek(0)
                            raise RuntimeError(f"disposable Redis failed to start: {log.read()}")
                        try:
                            if client.ping():
                                break
                        except (redis.ConnectionError, redis.TimeoutError):
                            time.sleep(0.02)
                yield f"redis://127.0.0.1:{port}/0"
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()


@contextmanager
def redis_environment() -> Iterator[dict[str, str]]:
    """Own two servers and yield a subprocess environment with isolated endpoints.

    The caller's environment is untouched. Celery endpoint overrides are removed
    so each test worker can derive its databases from the owned REDIS_URL.
    """
    with redis_server() as server, redis_server() as fault_broker:
        env = {
            **os.environ,
            "REDIS_URL": server,
            "CELERY_OWN_BROKER_URL": fault_broker,
            "PYTEST_OBLIGATION_REDIS_RESET": "1",
        }
        # Celery's environment override would defeat the per-xdist-worker URLs
        # derived from REDIS_URL by the test application. Never inherit one.
        for variable in ("CELERY_BROKER_URL", "CELERY_RESULT_BACKEND", "CELERY_RECORDS_URL"):
            env.pop(variable, None)
        yield env


def main(argv: list[str] | None = None) -> int:
    """Run a test command with two disposable servers, including a separate fault broker."""
    command = list(sys.argv[1:] if argv is None else argv)
    if command[:1] == ["--"]:
        command.pop(0)
    if not command:
        raise SystemExit("usage: python -m pytest_obligation.integrations.redis_server -- pytest [arguments]")
    with redis_environment() as env:
        return subprocess.call(command, env=env)


if __name__ == "__main__":
    raise SystemExit(main())
