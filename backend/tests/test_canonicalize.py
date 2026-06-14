"""URL canonicalization unit tests (no DB / network)."""

import pytest

from app.ingest.feeds import canonicalize_url


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # strips utm_* and known tracking params
        (
            "https://Example.com/news/story?utm_source=rss&utm_medium=feed&id=42",
            "https://example.com/news/story?id=42",
        ),
        # drops the fragment
        ("https://example.com/a/b#section", "https://example.com/a/b"),
        # strips a single trailing slash
        ("https://example.com/a/b/", "https://example.com/a/b"),
        # lowercases the host but preserves path case
        ("https://NEWS.Example.COM/Path", "https://news.example.com/Path"),
        # drops fbclid / gclid
        ("https://example.com/x?fbclid=abc&gclid=def", "https://example.com/x"),
    ],
)
def test_canonicalize_url(raw: str, expected: str) -> None:
    assert canonicalize_url(raw) == expected


def test_canonicalize_is_idempotent() -> None:
    once = canonicalize_url("https://Example.com/a/?utm_source=x#frag")
    assert canonicalize_url(once) == once
