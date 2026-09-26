from __future__ import annotations

import pytest

from rss_publisher import sanitize
from rss_publisher.sanitize import sanitize_html


def test_none_passthrough():
    assert sanitize_html(None) is None


def test_nh3_removes_script_and_keeps_allowed_markup():
    result = sanitize_html("<p>Hello <strong>world</strong></p><script>alert(1)</script>")
    assert result is not None
    assert "<strong>world</strong>" in result
    assert "script" not in result
    assert "alert(1)" not in result


def test_nh3_preserves_rel_attribute_on_links():
    # Regression: nh3 >= 0.3.7 raises when `rel` is allowlisted while link_rel is set.
    result = sanitize_html('<a href="https://example.com" rel="source">x</a>')
    assert result is not None
    assert 'rel="source"' in result


def test_nh3_drops_disallowed_url_scheme():
    result = sanitize_html('<a href="javascript:alert(1)">x</a>')
    assert result is not None
    assert "javascript:" not in result


def test_nh3_strips_comments():
    result = sanitize_html("<p>a</p><!-- secret --><p>b</p>")
    assert result is not None
    assert "secret" not in result


def test_fallback_sanitizer_used_when_nh3_missing(monkeypatch):
    monkeypatch.setattr(sanitize, "nh3", None)
    result = sanitize_html(
        '<p class="x">Hi <a href="https://e.com" rel="via">link</a>'
        '<script>bad()</script><iframe src="https://evil"></iframe></p>'
    )
    assert result is not None
    assert "<p" in result
    assert 'class="x"' in result
    assert 'rel="via"' in result
    assert "bad()" not in result
    assert "iframe" not in result


def test_fallback_sanitizer_drops_unknown_tags_and_bad_schemes(monkeypatch):
    monkeypatch.setattr(sanitize, "nh3", None)
    result = sanitize_html('<marquee>no</marquee><a href="javascript:alert(1)">x</a>')
    assert result is not None
    assert "marquee" not in result
    assert "javascript:" not in result


def test_fallback_sanitizer_handles_void_and_self_closing(monkeypatch):
    monkeypatch.setattr(sanitize, "nh3", None)
    result = sanitize_html('<p>a<br>b</p><img src="https://e.com/i.png" alt="i"/>')
    assert result is not None
    assert "<br>" in result
    assert "<img" in result
    assert "</br>" not in result


def test_fallback_sanitizer_escapes_text(monkeypatch):
    monkeypatch.setattr(sanitize, "nh3", None)
    result = sanitize_html("<p>1 < 2 & 3 > 2</p>")
    assert result is not None
    assert "&lt;" in result
    assert "&amp;" in result
