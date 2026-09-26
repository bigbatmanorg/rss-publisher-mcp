from __future__ import annotations

import html
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import quote

from .config import Settings
from .models import FeedConfig, FeedEntry
from .sanitize import sanitize_html
from .urls import normalize_url

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "media": "http://search.yahoo.com/mrss/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "rp": "https://bigbatmanorg.github.io/rss-publisher-mcp/ns/1",
}
for prefix, uri in NS.items():
    ET.register_namespace(prefix, uri)


def _q(prefix: str, tag: str) -> str:
    return f"{{{NS[prefix]}}}{tag}"


def _rss_date(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return format_datetime(dt.astimezone(timezone.utc))


def stable_slug(entry: FeedEntry) -> str:
    base = (entry.title or entry.kind or "entry").lower()
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")[:70] or "entry"
    suffix = re.sub(r"[^a-fA-F0-9]", "", entry.id or "")[-8:] or quote((entry.id or "entry")[-8:])
    return f"{base}-{suffix.lower()}"


def local_permalink(settings: Settings, entry: FeedEntry) -> str:
    stored = entry.private_metadata.get("local_permalink_path")
    if stored:
        return settings.absolute(str(stored))
    return settings.absolute(f"{settings.entry_path}/{stable_slug(entry)}/")


def resolve_asset_url(settings: Settings, ref, asset_lookup) -> str:
    if getattr(ref, "asset_id", None):
        asset = asset_lookup(ref.asset_id)
        if not asset:
            raise ValueError(f"unknown asset: {ref.asset_id}")
        return settings.absolute(asset["public_path"])
    return normalize_url(settings, ref.url, base_path=settings.media_path)


def render_feed(settings: Settings, config: FeedConfig, entries: list[FeedEntry], asset_lookup, revision_at: datetime) -> bytes:
    rss = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(rss, "channel")
    feed_url = config.feed_url or settings.feed_url
    site_url = config.site_url or settings.public_base_url
    ET.SubElement(channel, "title").text = config.title
    ET.SubElement(channel, "link").text = site_url
    ET.SubElement(channel, "description").text = config.description
    ET.SubElement(channel, "language").text = config.language
    ET.SubElement(channel, "generator").text = config.generator
    ET.SubElement(channel, "lastBuildDate").text = _rss_date(revision_at)
    if config.ttl_minutes:
        ET.SubElement(channel, "ttl").text = str(config.ttl_minutes)
    if config.copyright:
        ET.SubElement(channel, "copyright").text = config.copyright
    for cat in config.categories:
        ET.SubElement(channel, "category").text = cat
    if config.logo_url:
        image = ET.SubElement(channel, "image")
        ET.SubElement(image, "url").text = normalize_url(settings, config.logo_url, base_path=settings.media_path)
        ET.SubElement(image, "title").text = config.title
        ET.SubElement(image, "link").text = site_url
    ET.SubElement(channel, _q("atom", "link"), {"href": feed_url, "rel": "self", "type": "application/rss+xml"})
    if config.websub_hub_url:
        ET.SubElement(channel, _q("atom", "link"), {"href": config.websub_hub_url, "rel": "hub"})

    for entry in entries:
        if entry.lifecycle not in {"published", "corrected", "retracted"}:
            continue
        item = ET.SubElement(channel, "item")
        guid = ET.SubElement(item, "guid", {"isPermaLink": "false"})
        guid.text = entry.id
        if entry.title:
            ET.SubElement(item, "title").text = entry.title
        permalink = entry.url or local_permalink(settings, entry)
        ET.SubElement(item, "link").text = normalize_url(settings, permalink)
        if entry.summary:
            ET.SubElement(item, "description").text = entry.summary
        elif entry.content_text:
            ET.SubElement(item, "description").text = entry.content_text[:1000]
        full_html = build_full_html(settings, entry, asset_lookup)
        if full_html:
            ET.SubElement(item, _q("content", "encoded")).text = full_html
        if entry.published_at:
            ET.SubElement(item, "pubDate").text = _rss_date(entry.published_at)
        if entry.updated_at:
            ET.SubElement(item, _q("atom", "updated")).text = entry.updated_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        for author in entry.authors:
            ET.SubElement(item, _q("dc", "creator")).text = author.name
            if author.email:
                ET.SubElement(item, "author").text = author.email
        for cat in entry.categories:
            ET.SubElement(item, "category").text = cat
        if entry.origin_feed_url:
            source = ET.SubElement(item, "source", {"url": normalize_url(settings, entry.origin_feed_url)})
            source.text = entry.origin_feed_title or entry.origin_feed_url
        for link in entry.links:
            if link.rel in {"related", "via", "alternate"}:
                attrs = {"href": normalize_url(settings, link.url), "rel": link.rel}
                if link.title:
                    attrs["title"] = link.title
                ET.SubElement(item, _q("atom", "link"), attrs)
        if entry.hero_image:
            _add_media(item, settings, entry.hero_image, asset_lookup, is_thumbnail=True)
        for media in entry.media:
            _add_media(item, settings, media, asset_lookup, is_thumbnail=False)
        if entry.primary_enclosure:
            enc = entry.primary_enclosure
            if enc.asset_id:
                asset = asset_lookup(enc.asset_id)
                if not asset:
                    raise ValueError(f"unknown asset: {enc.asset_id}")
                enc_url = settings.absolute(asset["public_path"])
            else:
                enc_url = normalize_url(settings, enc.url, base_path=settings.files_path)
            ET.SubElement(item, "enclosure", {"url": enc_url, "type": enc.mime_type, "length": str(enc.size_bytes)})
        ET.SubElement(item, _q("rp", "kind")).text = entry.kind
        if entry.public_metadata:
            ET.SubElement(item, _q("rp", "metadata")).text = json.dumps(entry.public_metadata, sort_keys=True, ensure_ascii=False, separators=(",", ":"))

    ET.indent(ET.ElementTree(rss), space="  ")
    return ET.tostring(rss, encoding="utf-8", xml_declaration=True, short_empty_elements=True)


def _add_media(item, settings, ref, asset_lookup, is_thumbnail: bool):
    url = resolve_asset_url(settings, ref, asset_lookup)
    attrs = {"url": url}
    mime = ref.mime_type
    if ref.asset_id:
        asset = asset_lookup(ref.asset_id)
        mime = mime or asset["mime_type"]
        ref.width = ref.width or asset.get("width")
        ref.height = ref.height or asset.get("height")
    if mime:
        attrs["type"] = mime
        attrs["medium"] = "image" if mime.startswith("image/") else "video" if mime.startswith("video/") else "audio" if mime.startswith("audio/") else "document"
    if ref.width:
        attrs["width"] = str(ref.width)
    if ref.height:
        attrs["height"] = str(ref.height)
    if ref.duration_seconds is not None:
        attrs["duration"] = str(int(ref.duration_seconds))
    node = ET.SubElement(item, _q("media", "content"), attrs)
    if ref.title:
        ET.SubElement(node, _q("media", "title")).text = ref.title
    if ref.credit:
        ET.SubElement(node, _q("media", "credit")).text = ref.credit
    if is_thumbnail:
        thumb_attrs = {"url": url}
        if ref.width:
            thumb_attrs["width"] = str(ref.width)
        if ref.height:
            thumb_attrs["height"] = str(ref.height)
        ET.SubElement(item, _q("media", "thumbnail"), thumb_attrs)


def build_full_html(settings: Settings, entry: FeedEntry, asset_lookup) -> str | None:
    pieces: list[str] = []
    if entry.lifecycle == "retracted":
        pieces.append('<div class="rss-publisher-retraction"><strong>Retracted.</strong></div>')
    if entry.correction_note:
        pieces.append(f'<div class="rss-publisher-correction"><strong>Correction:</strong> {html.escape(entry.correction_note)}</div>')
    if entry.hero_image:
        src = resolve_asset_url(settings, entry.hero_image, asset_lookup)
        alt = html.escape(entry.hero_image.alt or entry.title or "")
        credit = f"<figcaption>{html.escape(entry.hero_image.credit)}</figcaption>" if entry.hero_image.credit else ""
        pieces.append(f'<figure><img src="{html.escape(src)}" alt="{alt}" loading="lazy">{credit}</figure>')
    if entry.content_html:
        pieces.append(sanitize_html(entry.content_html) or "")
    elif entry.content_text:
        paragraphs = [f"<p>{html.escape(p.strip())}</p>" for p in entry.content_text.split("\n\n") if p.strip()]
        pieces.extend(paragraphs)
    if entry.links:
        pieces.append("<h2>Links</h2><ul>" + "".join(
            f'<li><a href="{html.escape(normalize_url(settings, link.url) or "")}">{html.escape(link.title or link.url)}</a></li>'
            for link in entry.links
        ) + "</ul>")
    return "\n".join(pieces) or None


def render_entry_page(settings: Settings, config: FeedConfig, entry: FeedEntry, asset_lookup) -> str:
    content = build_full_html(settings, entry, asset_lookup) or ""
    title = html.escape(entry.title or config.title)
    summary = html.escape(entry.summary or "")
    feed_url = html.escape(config.feed_url or settings.feed_url)
    return f"""<!doctype html>
<html lang="{html.escape(entry.language or config.language)}">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><meta name="description" content="{summary}">
<link rel="alternate" type="application/rss+xml" href="{feed_url}" title="{html.escape(config.title)}">
<style>body{{max-width:860px;margin:3rem auto;padding:0 1rem;font:17px/1.6 system-ui,sans-serif}}img,video{{max-width:100%;height:auto}}code,pre{{overflow:auto}}.meta{{opacity:.7}}</style></head>
<body><p><a href="/">← {html.escape(config.title)}</a></p><article><h1>{title}</h1>
<p class="meta">{html.escape(entry.published_at.isoformat() if entry.published_at else '')}</p>
{f'<p>{summary}</p>' if summary else ''}{content}</article></body></html>"""


def render_index(settings: Settings, config: FeedConfig, entries: list[FeedEntry]) -> str:
    items = "".join(
        f'<li><a href="{html.escape(entry.url or local_permalink(settings, entry))}">{html.escape(entry.title or entry.summary or entry.kind)}</a></li>'
        for entry in entries
    )
    return f"""<!doctype html><html lang="{html.escape(config.language)}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(config.title)}</title><link rel="alternate" type="application/rss+xml" href="{html.escape(config.feed_url or settings.feed_url)}"><style>body{{max-width:860px;margin:3rem auto;padding:0 1rem;font:17px/1.6 system-ui,sans-serif}}</style></head><body><h1>{html.escape(config.title)}</h1><p>{html.escape(config.description)}</p><p><a href="{html.escape(settings.feed_path)}">Subscribe to RSS</a> · <a href="/upload/">Upload media</a></p><h2>Latest</h2><ul>{items}</ul></body></html>"""
