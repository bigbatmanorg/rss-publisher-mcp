from __future__ import annotations

import copy
import hashlib
import json
import os
import sqlite3
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .assets import ingest_temp_file
from .config import Settings
from .db import Database
from .embeddings import EmbeddingProvider, cosine, semantic_hash, semantic_text
from .models import FeedConfig, FeedEntry, MutationResult, utcnow
from .renderer import local_permalink, render_entry_page, render_feed, render_index
from .urls import is_privateish_url, normalize_url


class RevisionConflict(RuntimeError):
    pass


class PublisherService:
    def __init__(self, settings: Settings | None = None, *, embedder: EmbeddingProvider | None = None):
        self.settings = settings or Settings.from_env()
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)
        self.settings.public_dir.mkdir(parents=True, exist_ok=True)
        self.db = Database(self.settings.db_path)
        self.embedder = embedder or EmbeddingProvider(self.settings)
        self._ensure_feed()
        if not (self.settings.public_dir / self.settings.feed_path.lstrip("/")).exists():
            self.rebuild_public()

    def _ensure_feed(self) -> None:
        with self.db.connect() as conn:
            row = conn.execute("SELECT json FROM feed_config WHERE id=1").fetchone()
            if not row:
                config = FeedConfig()
                conn.execute("INSERT INTO feed_config(id,json) VALUES(1,?)", (self._json(config),))
                conn.execute("INSERT OR IGNORE INTO meta(key,value) VALUES('feed_revision_at',?)", (utcnow().isoformat(),))
                conn.commit()

    def get_feed(self) -> dict[str, Any]:
        with self.db.connect() as conn:
            return {
                "config": self._feed_config(conn).model_dump(mode="json"),
                "revision": self.db.revision(conn),
                "feed_url": self.settings.feed_url,
                "public_base_url": self.settings.public_base_url,
            }

    def configure_feed(self, patch: dict[str, Any], expected_revision: int | None = None) -> MutationResult:
        with self.db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._check_revision(conn, expected_revision)
            current = self._feed_config(conn)
            candidate = FeedConfig.model_validate({**current.model_dump(mode="python"), **patch})
            if candidate.model_dump(mode="json") == current.model_dump(mode="json"):
                conn.rollback()
                return MutationResult(status="unchanged", feed_revision=self.db.revision(), feed_changed=False)
            conn.execute("UPDATE feed_config SET json=? WHERE id=1", (self._json(candidate),))
            self._archive_overflow(conn, candidate.max_items)
            revision = self._commit_mutation(conn, "configure_feed", None, {"changed": sorted(patch)})
        self.rebuild_public()
        return MutationResult(status="updated", feed_revision=revision, feed_changed=True, changes=sorted(patch))

    def list_active_entries(self) -> dict[str, Any]:
        with self.db.connect() as conn:
            config = self._feed_config(conn)
            entries = self._active_entries(conn, config.max_items)
            return {
                "feed_revision": self.db.revision(conn),
                "entries": [self._compact_entry(x) for x in entries],
            }

    def list_entries(self, lifecycle: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        with self.db.connect() as conn:
            if lifecycle:
                rows = conn.execute("SELECT json FROM entries WHERE lifecycle=? ORDER BY sort_published_at DESC LIMIT ?", (lifecycle, limit)).fetchall()
            else:
                rows = conn.execute("SELECT json FROM entries ORDER BY sort_published_at DESC LIMIT ?", (limit,)).fetchall()
            return [FeedEntry.model_validate_json(r[0]).model_dump(mode="json") for r in rows]

    def get_entry(self, entry_id: str) -> dict[str, Any] | None:
        with self.db.connect() as conn:
            row = conn.execute("SELECT json FROM entries WHERE id=?", (entry_id,)).fetchone()
            return FeedEntry.model_validate_json(row[0]).model_dump(mode="json") if row else None

    def create_entry(self, entry: FeedEntry | dict[str, Any], expected_revision: int | None = None) -> MutationResult:
        entry = FeedEntry.model_validate(entry)
        now = utcnow()
        if entry.id is None:
            entry.id = f"urn:uuid:{uuid.uuid4()}"
        if entry.published_at is None:
            entry.published_at = now
        if entry.updated_at is None:
            entry.updated_at = entry.published_at
        if not entry.private_metadata.get("local_permalink_path"):
            entry.private_metadata["local_permalink_path"] = self._new_permalink_path(entry)
        entry.content_html = self._sanitize_content(entry.content_html)
        self._validate_entry_urls(entry)
        with self.db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._check_revision(conn, expected_revision)
            existing = conn.execute("SELECT 1 FROM entries WHERE id=?", (entry.id,)).fetchone()
            if existing:
                conn.rollback()
                raise ValueError(f"entry already exists: {entry.id}")
            if entry.continuity_key:
                row = conn.execute("SELECT id FROM entries WHERE continuity_key=? AND lifecycle IN ('published','corrected','retracted')", (entry.continuity_key,)).fetchone()
                if row:
                    conn.rollback()
                    raise ValueError(f"active continuity_key already belongs to {row['id']}")
            self._insert_entry(conn, entry)
            self._archive_overflow(conn)
            revision = self._commit_mutation(conn, "create_entry", entry.id, {"kind": entry.kind})
        warnings = self._post_mutation()
        return MutationResult(status="created", id=entry.id, feed_revision=revision, feed_changed=True, warnings=warnings, changes=["created"])

    def update_entry(self, entry_id: str, patch: dict[str, Any], expected_revision: int | None = None) -> MutationResult:
        if "id" in patch and patch["id"] not in {None, entry_id}:
            raise ValueError("GUID/id is immutable")
        patch = {k: v for k, v in patch.items() if k != "id"}
        with self.db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._check_revision(conn, expected_revision)
            current = self._entry(conn, entry_id)
            if current is None:
                conn.rollback()
                raise KeyError(entry_id)
            if current.lifecycle == "archived":
                conn.rollback()
                return MutationResult(status="archived_target", id=entry_id, feed_revision=self.db.revision(), feed_changed=False)
            raw = current.model_dump(mode="python")
            for key, value in patch.items():
                raw[key] = value
            raw["id"] = entry_id
            candidate = FeedEntry.model_validate(raw)
            candidate.content_html = self._sanitize_content(candidate.content_html)
            self._validate_entry_urls(candidate)
            before = self._state_fingerprint(current)
            after = self._state_fingerprint(candidate)
            if before == after:
                conn.rollback()
                return MutationResult(status="unchanged", id=entry_id, feed_revision=self.db.revision(), feed_changed=False)
            public_before = self._public_fingerprint(current)
            if public_before != self._public_fingerprint(candidate):
                candidate.updated_at = utcnow()
            self._update_entry_row(conn, candidate)
            self._archive_overflow(conn)
            changed = self._changed_fields(current, candidate)
            revision = self._commit_mutation(conn, "update_entry", entry_id, {"changed": changed})
        warnings = self._post_mutation()
        return MutationResult(status="updated", id=entry_id, feed_revision=revision, feed_changed=public_before != self._public_fingerprint(candidate), warnings=warnings, changes=changed)

    def correct_entry(self, entry_id: str, correction_note: str, patch: dict[str, Any] | None = None) -> MutationResult:
        data = dict(patch or {})
        data["lifecycle"] = "corrected"
        data["correction_note"] = correction_note
        result = self.update_entry(entry_id, data)
        if result.status == "updated":
            result.status = "updated"
        return result

    def retract_entry(self, entry_id: str, reason: str | None = None) -> MutationResult:
        patch: dict[str, Any] = {"lifecycle": "retracted"}
        if reason:
            patch["correction_note"] = reason
        result = self.update_entry(entry_id, patch)
        if result.status == "updated":
            result.status = "retracted"
        return result

    def unpublish_entry(self, entry_id: str) -> MutationResult:
        result = self.update_entry(entry_id, {"lifecycle": "archived"})
        if result.status == "updated":
            result.status = "unpublished"
        return result

    def republish_entry(self, entry_id: str) -> MutationResult:
        with self.db.connect() as conn:
            current = self._entry(conn, entry_id)
        if current is None:
            raise KeyError(entry_id)
        if current.lifecycle != "archived":
            return MutationResult(status="unchanged", id=entry_id, feed_revision=self.db.revision(), feed_changed=False)
        # Bypass archived guard in update_entry intentionally.
        with self.db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            current = self._entry(conn, entry_id)
            assert current is not None
            current.lifecycle = "published"
            current.updated_at = utcnow()
            self._update_entry_row(conn, current)
            self._archive_overflow(conn)
            revision = self._commit_mutation(conn, "republish_entry", entry_id, {})
        warnings = self._post_mutation()
        return MutationResult(status="republished", id=entry_id, feed_revision=revision, feed_changed=True, warnings=warnings, changes=["lifecycle"])

    def publish_batch(self, operations: list[dict[str, Any]], expected_revision: int | None = None) -> dict[str, Any]:
        # Batch intentionally operates through one SQLite transaction and one public rebuild.
        results: list[dict[str, Any]] = []
        changed_any = False
        with self.db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._check_revision(conn, expected_revision)
            for op in operations:
                kind = op.get("operation", "upsert")
                if kind == "create":
                    entry = FeedEntry.model_validate(op["entry"])
                    if not entry.id:
                        entry.id = f"urn:uuid:{uuid.uuid4()}"
                    if entry.published_at is None:
                        entry.published_at = utcnow()
                    if entry.updated_at is None:
                        entry.updated_at = entry.published_at
                    entry.private_metadata.setdefault("local_permalink_path", self._new_permalink_path(entry))
                    entry.content_html = self._sanitize_content(entry.content_html)
                    self._validate_entry_urls(entry)
                    self._insert_entry(conn, entry)
                    results.append({"status": "created", "id": entry.id})
                    changed_any = True
                elif kind in {"update", "upsert"}:
                    entry_id = op.get("id") or (op.get("entry") or {}).get("id")
                    existing = self._entry(conn, entry_id) if entry_id else None
                    if existing is None and kind == "upsert":
                        entry = FeedEntry.model_validate(op.get("entry") or op.get("patch") or {})
                        if not entry.id:
                            entry.id = f"urn:uuid:{uuid.uuid4()}"
                        entry.published_at = entry.published_at or utcnow()
                        entry.updated_at = entry.updated_at or entry.published_at
                        entry.private_metadata.setdefault("local_permalink_path", self._new_permalink_path(entry))
                        entry.content_html = self._sanitize_content(entry.content_html)
                        self._validate_entry_urls(entry)
                        self._insert_entry(conn, entry)
                        results.append({"status": "created", "id": entry.id})
                        changed_any = True
                    elif existing is None:
                        raise KeyError(entry_id)
                    else:
                        if existing.lifecycle == "archived":
                            results.append({"status": "archived_target", "id": entry_id})
                            continue
                        raw = existing.model_dump(mode="python")
                        raw.update(op.get("patch") or op.get("entry") or {})
                        raw["id"] = entry_id
                        candidate = FeedEntry.model_validate(raw)
                        candidate.content_html = self._sanitize_content(candidate.content_html)
                        self._validate_entry_urls(candidate)
                        if self._state_fingerprint(existing) == self._state_fingerprint(candidate):
                            results.append({"status": "unchanged", "id": entry_id})
                            continue
                        if self._public_fingerprint(existing) != self._public_fingerprint(candidate):
                            candidate.updated_at = utcnow()
                        self._update_entry_row(conn, candidate)
                        results.append({"status": "updated", "id": entry_id})
                        changed_any = True
                else:
                    raise ValueError(f"unsupported batch operation: {kind}")
            if changed_any:
                self._archive_overflow(conn)
                revision = self._commit_mutation(conn, "publish_batch", None, {"results": results})
            else:
                revision = self.db.revision(conn)
                conn.rollback()
        warnings = self._post_mutation() if changed_any else []
        return {"status": "changed" if changed_any else "unchanged", "feed_revision": revision, "results": results, "warnings": warnings}

    def find_similar_active_entries(self, *, text: str | None = None, entry: dict[str, Any] | None = None, limit: int = 5) -> dict[str, Any]:
        with self.db.connect() as conn:
            revision = self.db.revision(conn)
            config = self._feed_config(conn)
            active = self._active_entries(conn, config.max_items)
            if entry:
                probe = FeedEntry.model_validate(entry)
                # Exact continuity is authoritative and returned first.
                if probe.continuity_key:
                    exact = [x for x in active if x.continuity_key == probe.continuity_key]
                    if exact:
                        return {"feed_revision": revision, "matches": [{**self._compact_entry(exact[0]), "score": 1.0, "signals": ["continuity_key"]}]}
                text = semantic_text(probe)
            if not text:
                raise ValueError("text or entry is required")
            if not self.settings.embeddings_enabled:
                return {"feed_revision": revision, "matches": [], "degraded": "embeddings_disabled"}
            query = self.embedder.embed(text)
            rows = conn.execute("SELECT entry_id, model, dimensions, vector_json FROM embeddings").fetchall()
            active_ids = {x.id for x in active}
            scored: list[dict[str, Any]] = []
            by_id = {x.id: x for x in active}
            for row in rows:
                if row["entry_id"] not in active_ids:
                    continue
                vector = json.loads(row["vector_json"])
                score = cosine(query, vector)
                scored.append({**self._compact_entry(by_id[row["entry_id"]]), "score": score, "signals": ["embedding"]})
            scored.sort(key=lambda x: x["score"], reverse=True)
            return {"feed_revision": revision, "matches": scored[:limit]}

    def add_asset(self, temp_path: Path, filename: str | None, supplied_mime: str | None) -> dict[str, Any]:
        metadata = ingest_temp_file(self.settings, temp_path, filename, supplied_mime)
        with self.db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute("SELECT * FROM assets WHERE sha256=?", (metadata["sha256"],)).fetchone()
            if existing:
                conn.rollback()
                asset = self._asset_row(existing)
                asset["asset_id"] = asset["id"]
                asset["public_url"] = self.settings.absolute(asset["public_path"])
                return asset
            conn.execute(
                "INSERT INTO assets(id,sha256,original_filename,mime_type,size_bytes,width,height,public_path,storage_path,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (metadata["id"], metadata["sha256"], metadata["original_filename"], metadata["mime_type"], metadata["size_bytes"], metadata["width"], metadata["height"], metadata["public_path"], metadata["storage_path"], metadata["created_at"]),
            )
            self.db.audit(conn, "add_asset", None, {"asset_id": metadata["id"]}, utcnow().isoformat())
            conn.commit()
        return {**metadata, "asset_id": metadata["id"], "public_url": self.settings.absolute(metadata["public_path"])}

    def get_asset(self, asset_id: str) -> dict[str, Any] | None:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM assets WHERE id=?", (asset_id,)).fetchone()
            if not row:
                return None
            asset = self._asset_row(row)
            asset["asset_id"] = asset["id"]
            asset["public_url"] = self.settings.absolute(asset["public_path"])
            return asset

    def validate_feed(self) -> dict[str, Any]:
        feed = self.settings.public_dir / self.settings.feed_path.lstrip("/")
        issues: list[str] = []
        if not feed.exists():
            issues.append("feed.xml is missing")
        else:
            import xml.etree.ElementTree as ET
            try:
                root = ET.parse(feed).getroot()
                if root.tag != "rss":
                    issues.append("root element is not rss")
                channel = root.find("channel")
                if channel is None:
                    issues.append("channel missing")
                else:
                    for field in ("title", "link", "description"):
                        if not channel.findtext(field):
                            issues.append(f"channel missing {field}")
                    ids: set[str] = set()
                    for item in channel.findall("item"):
                        guid = item.findtext("guid")
                        if not guid:
                            issues.append("item missing guid")
                        elif guid in ids:
                            issues.append(f"duplicate guid: {guid}")
                        else:
                            ids.add(guid)
                        if not (item.findtext("title") or item.findtext("description")):
                            issues.append(f"item {guid or '?'} lacks title and description")
            except Exception as exc:
                issues.append(f"invalid XML: {exc}")
        return {"valid": not issues, "issues": issues, "path": str(feed)}

    def audit_feed(self) -> dict[str, Any]:
        warnings: list[str] = []
        with self.db.connect() as conn:
            config = self._feed_config(conn)
            active = self._active_entries(conn, config.max_items)
        if is_privateish_url(self.settings.public_base_url):
            warnings.append("public base URL appears local/private; FreshRSS 1.30+ may require INTERNAL_HOST_ALLOWLIST")
        now = utcnow()
        for entry in active:
            if entry.published_at and entry.published_at > now:
                warnings.append(f"{entry.id}: publication date is in the future")
            if entry.hero_image and not entry.hero_image.alt:
                warnings.append(f"{entry.id}: hero image has no alt text")
            for ref in ([entry.hero_image] if entry.hero_image else []) + list(entry.media):
                if ref.url:
                    normalized = normalize_url(self.settings, ref.url, base_path=self.settings.media_path)
                    if normalized and is_privateish_url(normalized):
                        warnings.append(f"{entry.id}: media URL appears local/private")
        return {"ok": True, "warnings": sorted(set(warnings)), "active_entries": len(active)}

    def export_state(self) -> dict[str, Any]:
        with self.db.connect() as conn:
            config = self._feed_config(conn)
            rows = conn.execute("SELECT json FROM entries ORDER BY sort_published_at ASC").fetchall()
            assets = conn.execute("SELECT * FROM assets ORDER BY created_at ASC").fetchall()
            return {
                "schema_version": 1,
                "feed_revision": self.db.revision(conn),
                "feed": config.model_dump(mode="json"),
                "entries": [FeedEntry.model_validate_json(r[0]).model_dump(mode="json") for r in rows],
                "assets": [self._asset_row(r) for r in assets],
            }

    def rebuild_public(self) -> None:
        with self.db.connect() as conn:
            config = self._feed_config(conn)
            active = self._active_entries(conn, config.max_items)
            all_rows = conn.execute("SELECT json FROM entries WHERE lifecycle != 'draft' ORDER BY sort_published_at DESC").fetchall()
            all_entries = [FeedEntry.model_validate_json(r[0]) for r in all_rows]
            at_raw = conn.execute("SELECT value FROM meta WHERE key='feed_revision_at'").fetchone()
            at = datetime.fromisoformat(at_raw[0]) if at_raw else utcnow()
        xml = render_feed(self.settings, config, active, self.get_asset, at)
        import xml.etree.ElementTree as ET
        ET.fromstring(xml)  # fail before touching public artifact
        feed_path = self.settings.public_dir / self.settings.feed_path.lstrip("/")
        self._atomic_write(feed_path, xml)
        self._atomic_write(self.settings.public_dir / "index.html", render_index(self.settings, config, active).encode("utf-8"))
        entries_dir = self.settings.public_dir / self.settings.entry_path.strip("/")
        entries_dir.mkdir(parents=True, exist_ok=True)
        for entry in all_entries:
            path = entry.private_metadata.get("local_permalink_path") or f"{self.settings.entry_path}/{entry.id}"
            target = self.settings.public_dir / str(path).strip("/") / "index.html"
            self._atomic_write(target, render_entry_page(self.settings, config, entry, self.get_asset).encode("utf-8"))

    def _post_mutation(self) -> list[str]:
        warnings: list[str] = []
        self.rebuild_public()
        try:
            self._sync_embeddings()
        except Exception as exc:
            warnings.append(f"embedding index degraded: {exc}")
        return warnings

    def _sync_embeddings(self) -> None:
        with self.db.connect() as conn:
            config = self._feed_config(conn)
            active = self._active_entries(conn, config.max_items)
            active_ids = {x.id for x in active}
            conn.execute("DELETE FROM embeddings WHERE entry_id NOT IN ({})".format(",".join("?" for _ in active_ids)) if active_ids else "DELETE FROM embeddings", tuple(active_ids) if active_ids else ())
            if not self.settings.embeddings_enabled:
                conn.commit()
                return
            for entry in active:
                text = semantic_text(entry)
                sem_hash = semantic_hash(text)
                row = conn.execute("SELECT model,semantic_hash FROM embeddings WHERE entry_id=?", (entry.id,)).fetchone()
                if row and row["model"] == self.settings.embeddings_model and row["semantic_hash"] == sem_hash:
                    continue
                vector = self.embedder.embed(text)
                conn.execute(
                    "INSERT INTO embeddings(entry_id,model,dimensions,semantic_hash,vector_json,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(entry_id) DO UPDATE SET model=excluded.model,dimensions=excluded.dimensions,semantic_hash=excluded.semantic_hash,vector_json=excluded.vector_json,updated_at=excluded.updated_at",
                    (entry.id, self.settings.embeddings_model, len(vector), sem_hash, json.dumps(vector), utcnow().isoformat()),
                )
            conn.commit()

    def _archive_overflow(self, conn: sqlite3.Connection, max_items: int | None = None) -> list[str]:
        if max_items is None:
            max_items = self._feed_config(conn).max_items
        rows = conn.execute(
            "SELECT id,json FROM entries WHERE lifecycle IN ('published','corrected','retracted') ORDER BY sort_published_at DESC, id ASC"
        ).fetchall()
        archived: list[str] = []
        for row in rows[max_items:]:
            entry = FeedEntry.model_validate_json(row["json"])
            entry.lifecycle = "archived"
            self._update_entry_row(conn, entry)
            archived.append(entry.id or "")
        return archived

    def _active_entries(self, conn: sqlite3.Connection, max_items: int) -> list[FeedEntry]:
        rows = conn.execute(
            "SELECT json FROM entries WHERE lifecycle IN ('published','corrected','retracted') ORDER BY sort_published_at DESC, id ASC LIMIT ?",
            (max_items,),
        ).fetchall()
        return [FeedEntry.model_validate_json(r[0]) for r in rows]

    def _entry(self, conn: sqlite3.Connection, entry_id: str | None) -> FeedEntry | None:
        if not entry_id:
            return None
        row = conn.execute("SELECT json FROM entries WHERE id=?", (entry_id,)).fetchone()
        return FeedEntry.model_validate_json(row[0]) if row else None

    def _feed_config(self, conn: sqlite3.Connection) -> FeedConfig:
        row = conn.execute("SELECT json FROM feed_config WHERE id=1").fetchone()
        return FeedConfig.model_validate_json(row[0])

    def _insert_entry(self, conn: sqlite3.Connection, entry: FeedEntry) -> None:
        sem = semantic_hash(semantic_text(entry))
        conn.execute(
            "INSERT INTO entries(id,continuity_key,lifecycle,published_at,updated_at,sort_published_at,semantic_hash,json) VALUES(?,?,?,?,?,?,?,?)",
            (entry.id, entry.continuity_key, entry.lifecycle, self._dt(entry.published_at), self._dt(entry.updated_at), self._dt(entry.published_at), sem, self._json(entry)),
        )

    def _update_entry_row(self, conn: sqlite3.Connection, entry: FeedEntry) -> None:
        sem = semantic_hash(semantic_text(entry))
        conn.execute(
            "UPDATE entries SET continuity_key=?, lifecycle=?, published_at=?, updated_at=?, sort_published_at=?, semantic_hash=?, json=? WHERE id=?",
            (entry.continuity_key, entry.lifecycle, self._dt(entry.published_at), self._dt(entry.updated_at), self._dt(entry.published_at), sem, self._json(entry), entry.id),
        )

    def _commit_mutation(self, conn: sqlite3.Connection, operation: str, entry_id: str | None, detail: dict) -> int:
        revision = self.db.bump_revision(conn)
        at = utcnow().isoformat()
        conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('feed_revision_at',?)", (at,))
        self.db.audit(conn, operation, entry_id, detail, at)
        conn.commit()
        return revision

    def _check_revision(self, conn: sqlite3.Connection, expected: int | None) -> None:
        if expected is not None and expected != self.db.revision(conn):
            raise RevisionConflict(f"expected feed revision {expected}, current is {self.db.revision(conn)}")

    def _validate_entry_urls(self, entry: FeedEntry) -> None:
        for value in [entry.url, entry.origin_feed_url] + [x.url for x in entry.links]:
            if value:
                normalize_url(self.settings, value)
        for ref in ([entry.hero_image] if entry.hero_image else []) + entry.media:
            if ref and ref.url:
                normalize_url(self.settings, ref.url, base_path=self.settings.media_path)
        self._validate_asset_refs(entry)

    def _validate_asset_refs(self, entry: FeedEntry) -> None:
        """Reject references to unknown assets before committing canonical state.

        Rendering resolves asset ids lazily; without this check a bad reference
        would be committed and then make every subsequent rebuild fail.
        """
        refs: list[Any] = []
        if entry.hero_image:
            refs.append(entry.hero_image)
        refs.extend(entry.media)
        if entry.primary_enclosure:
            refs.append(entry.primary_enclosure)
        for ref in refs:
            asset_id = getattr(ref, "asset_id", None)
            if asset_id and self.get_asset(asset_id) is None:
                raise ValueError(f"unknown asset: {asset_id}")

    def _new_permalink_path(self, entry: FeedEntry) -> str:
        # Stable on first publication even if title changes later.
        from .renderer import stable_slug
        return f"{self.settings.entry_path}/{stable_slug(entry)}"

    def _compact_entry(self, entry: FeedEntry) -> dict[str, Any]:
        return {
            "id": entry.id,
            "kind": entry.kind,
            "continuity_key": entry.continuity_key,
            "title": entry.title,
            "summary": entry.summary,
            "published_at": entry.published_at.isoformat() if entry.published_at else None,
            "updated_at": entry.updated_at.isoformat() if entry.updated_at else None,
            "categories": entry.categories,
            "url": entry.url or local_permalink(self.settings, entry),
        }

    def _state_fingerprint(self, entry: FeedEntry) -> str:
        data = entry.model_dump(mode="json")
        data.pop("updated_at", None)
        return self._hash_obj(data)

    def _public_fingerprint(self, entry: FeedEntry) -> str:
        data = entry.model_dump(mode="json")
        data.pop("updated_at", None)
        data.pop("private_metadata", None)
        data.pop("continuity_key", None)
        return self._hash_obj(data)

    def _changed_fields(self, old: FeedEntry, new: FeedEntry) -> list[str]:
        a = old.model_dump(mode="json")
        b = new.model_dump(mode="json")
        return sorted(k for k in set(a) | set(b) if k != "updated_at" and a.get(k) != b.get(k))

    @staticmethod
    def _hash_obj(value: Any) -> str:
        payload = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _sanitize_content(value: str | None) -> str | None:
        if value is None:
            return None
        from .sanitize import sanitize_html
        return sanitize_html(value)

    @staticmethod
    def _json(model) -> str:
        return json.dumps(model.model_dump(mode="json"), sort_keys=True, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _dt(value: datetime | None) -> str | None:
        return value.isoformat() if value else None

    @staticmethod
    def _atomic_write(path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.read_bytes() == content:
            return
        fd, tmp = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    @staticmethod
    def _asset_row(row) -> dict[str, Any]:
        return {key: row[key] for key in row.keys()}
