from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Lifecycle = Literal["draft", "published", "corrected", "retracted", "archived"]
EntryKind = Literal[
    "generic", "article", "note", "status", "update", "release", "incident",
    "announcement", "link", "media", "episode", "changelog", "result"
]


class Author(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    email: str | None = None
    url: str | None = None


class Link(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rel: str = "related"
    title: str | None = None
    url: str


class AssetRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset_id: str | None = None
    url: str | None = None
    mime_type: str | None = None
    title: str | None = None
    alt: str | None = None
    credit: str | None = None
    width: int | None = None
    height: int | None = None
    duration_seconds: float | None = None

    @model_validator(mode="after")
    def has_locator(self) -> "AssetRef":
        if not self.asset_id and not self.url:
            raise ValueError("asset reference needs asset_id or url")
        return self


class Enclosure(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset_id: str | None = None
    url: str | None = None
    mime_type: str
    size_bytes: int

    @model_validator(mode="after")
    def has_locator(self) -> "Enclosure":
        if not self.asset_id and not self.url:
            raise ValueError("enclosure needs asset_id or url")
        return self


class FeedEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str | None = None
    kind: EntryKind = "generic"
    continuity_key: str | None = None
    lifecycle: Lifecycle = "published"
    title: str | None = None
    summary: str | None = None
    content_text: str | None = None
    content_html: str | None = None
    url: str | None = None
    published_at: datetime | None = None
    updated_at: datetime | None = None
    language: str | None = None
    authors: list[Author] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    links: list[Link] = Field(default_factory=list)
    hero_image: AssetRef | None = None
    media: list[AssetRef] = Field(default_factory=list)
    primary_enclosure: Enclosure | None = None
    origin_feed_url: str | None = None
    origin_feed_title: str | None = None
    public_metadata: dict[str, Any] = Field(default_factory=dict)
    private_metadata: dict[str, Any] = Field(default_factory=dict)
    correction_note: str | None = None

    @model_validator(mode="after")
    def readable(self) -> "FeedEntry":
        if self.lifecycle != "draft" and not any([self.title, self.summary, self.content_text, self.content_html]):
            raise ValueError("entry needs title, summary, content_text, or content_html")
        return self

    @field_validator("categories")
    @classmethod
    def normalize_categories(cls, value: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for item in value:
            item = " ".join(item.split()).strip()
            key = item.casefold()
            if item and key not in seen:
                seen.add(key)
                result.append(item)
        return result


class FeedConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = "RSS Publisher"
    description: str = "Published by RSS Publisher"
    site_url: str | None = None
    feed_url: str | None = None
    language: str = "en"
    copyright: str | None = None
    logo_url: str | None = None
    categories: list[str] = Field(default_factory=list)
    ttl_minutes: int | None = 20
    max_items: int = 200
    generator: str = "bigbatmanorg/rss-publisher-mcp"
    websub_hub_url: str | None = None

    @field_validator("max_items")
    @classmethod
    def positive_max_items(cls, value: int) -> int:
        if value < 1:
            raise ValueError("max_items must be >= 1")
        return value


class MutationResult(BaseModel):
    status: Literal["created", "updated", "unchanged", "archived_target", "conflict", "retracted", "unpublished", "republished"]
    id: str | None = None
    feed_revision: int
    feed_changed: bool = False
    warnings: list[str] = Field(default_factory=list)
    changes: list[str] = Field(default_factory=list)


class EntryPatch(BaseModel):
    """Partial FeedEntry used for updates.

    Every field is optional so callers can patch only what changed. This exists so
    the MCP tool schema advertises the real FeedEntry field names instead of an
    opaque object, which previously let models invent fields such as
    ``presentation_html`` and fail validation.
    """

    model_config = ConfigDict(extra="forbid")
    kind: EntryKind | None = None
    continuity_key: str | None = None
    lifecycle: Lifecycle | None = None
    title: str | None = None
    summary: str | None = None
    content_text: str | None = None
    content_html: str | None = None
    url: str | None = None
    published_at: datetime | None = None
    updated_at: datetime | None = None
    language: str | None = None
    authors: list[Author] | None = None
    categories: list[str] | None = None
    links: list[Link] | None = None
    hero_image: AssetRef | None = None
    media: list[AssetRef] | None = None
    primary_enclosure: Enclosure | None = None
    origin_feed_url: str | None = None
    origin_feed_title: str | None = None
    public_metadata: dict[str, Any] | None = None
    private_metadata: dict[str, Any] | None = None
    correction_note: str | None = None


class BatchOperation(BaseModel):
    """One create/update/upsert operation inside publish_batch."""

    model_config = ConfigDict(extra="forbid")
    operation: Literal["create", "update", "upsert"] = "upsert"
    id: str | None = None
    entry: FeedEntry | None = None
    patch: EntryPatch | None = None


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
