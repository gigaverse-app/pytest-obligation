"""Owned Redis processes cannot erase an unrelated server or survive their scope."""

import json
import sys
from pathlib import Path

import pytest
import redis

from pytest_obligation.integrations.redis_server import main, redis_server


def test_isolated_redis_cleanup_preserves_another_server() -> None:
    with redis_server() as unrelated:
        other = redis.Redis.from_url(unrelated)
        other.set("keep", "valuable")
        with pytest.raises(RuntimeError, match="failed run"):
            with redis_server() as owned:
                own = redis.Redis.from_url(owned)
                own.set("remove", "temporary")
                own.flushdb()
                assert other.get("keep") == b"valuable"
                raise RuntimeError("failed run")
        with pytest.raises(redis.ConnectionError):
            own.ping()
        assert other.get("keep") == b"valuable"


def test_unavailable_redis_never_falls_back_to_localhost() -> None:
    with pytest.raises(FileNotFoundError):
        with redis_server(executable="/no/such/redis-server"):
            pytest.fail("must not yield an unowned server")


def test_failed_startup_does_not_yield_a_server() -> None:
    with pytest.raises(RuntimeError, match="disposable Redis failed to start"):
        with redis_server(executable=sys.executable):
            pytest.fail("a process that rejected its arguments is not Redis")


def test_default_urls_cannot_authorize_destructive_setup(monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.redis_databases import redis_url

    monkeypatch.delenv("PYTEST_OBLIGATION_REDIS_RESET", raising=False)
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/14")
    with pytest.raises(RuntimeError, match="dedicated test server"):
        redis_url("rq")


def test_runner_clears_overrides_and_cleans_up_after_command_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CELERY_BROKER_URL", "redis://localhost:6379/10")
    script = tmp_path / "command.py"
    output = tmp_path / "endpoints.json"
    script.write_text("""
import json, os, sys
from pathlib import Path
assert 'CELERY_BROKER_URL' not in os.environ
Path(sys.argv[1]).write_text(json.dumps([os.environ['REDIS_URL'], os.environ['CELERY_OWN_BROKER_URL']]))
sys.exit(7)
""")
    assert main([sys.executable, str(script), str(output)]) == 7
    urls = json.loads(output.read_text())
    assert urls[0] != urls[1]
    for url in urls:
        with pytest.raises(redis.ConnectionError):
            redis.Redis.from_url(url).ping()
