"""Shared test arrangement through Wagtail's production task registration."""

from wagtail.contrib.frontend_cache.tasks import purge_urls_from_cache_task


def enqueue_purge(url: str) -> str:
    """Create an owed purge through the real backend and return its task identity."""
    return str(purge_urls_from_cache_task.enqueue([url]).id)
