from __future__ import annotations

from html import escape
from html.parser import HTMLParser
from urllib.parse import urlparse

try:  # Production dependency; offline test environments may not have it preinstalled.
    import nh3  # type: ignore
except ImportError:  # pragma: no cover - exercised only in minimal/offline environments
    nh3 = None

_ALLOWED_TAGS = {
    "a", "p", "br", "strong", "em", "b", "i", "u", "s", "blockquote",
    "ul", "ol", "li", "h1", "h2", "h3", "h4", "h5", "h6", "pre", "code",
    "hr", "img", "figure", "figcaption", "table", "thead", "tbody", "tr", "th", "td",
    "details", "summary", "span", "div"
}
_ALLOWED_ATTRIBUTES = {
    "a": {"href", "title", "rel"},
    "img": {"src", "alt", "title", "width", "height", "loading"},
    "*": {"class"},
}
_VOID = {"br", "hr", "img"}


class _FallbackSanitizer(HTMLParser):
    """Fail-closed-ish stdlib fallback used only when nh3 is unavailable.

    It deliberately supports a small allowlist and drops script/style blocks entirely.
    Production installs use nh3.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.blocked_depth = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in {"script", "style", "iframe", "object", "embed", "form"}:
            self.blocked_depth += 1
            return
        if self.blocked_depth or tag not in _ALLOWED_TAGS:
            return
        allowed = _ALLOWED_ATTRIBUTES.get(tag, set()) | _ALLOWED_ATTRIBUTES.get("*", set())
        cleaned = []
        for k, v in attrs:
            k = k.lower()
            if k not in allowed or v is None:
                continue
            if k in {"href", "src"}:
                parsed = urlparse(v)
                if parsed.scheme and parsed.scheme not in {"http", "https", "mailto"}:
                    continue
            cleaned.append(f' {k}="{escape(v, quote=True)}"')
        self.out.append(f"<{tag}{''.join(cleaned)}>")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in {"script", "style", "iframe", "object", "embed", "form"}:
            if self.blocked_depth:
                self.blocked_depth -= 1
            return
        if self.blocked_depth or tag not in _ALLOWED_TAGS or tag in _VOID:
            return
        self.out.append(f"</{tag}>")

    def handle_data(self, data):
        if not self.blocked_depth:
            self.out.append(escape(data))


def sanitize_html(value: str | None) -> str | None:
    if value is None:
        return None
    if nh3 is not None:
        # nh3 >= 0.3.7 raises if `rel` is in the allowlist while `link_rel` is set.
        # We manage `rel` ourselves (source links carry meaningful rel values), so
        # disable nh3's automatic link_rel injection.
        return nh3.clean(
            value,
            tags=_ALLOWED_TAGS,
            attributes=_ALLOWED_ATTRIBUTES,
            url_schemes={"http", "https", "mailto"},
            strip_comments=True,
            link_rel=None,
        )
    parser = _FallbackSanitizer()
    parser.feed(value)
    parser.close()
    return "".join(parser.out)
