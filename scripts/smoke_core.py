#!/usr/bin/env python3
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from rss_publisher.config import Settings
from rss_publisher.service import PublisherService


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="rss-publisher-smoke-") as tmp:
        root = Path(tmp)
        os.environ["RSS_DATA_DIR"] = str(root / "data")
        os.environ["RSS_PUBLIC_DIR"] = str(root / "public")
        os.environ["RSS_PUBLIC_BASE_URL"] = "https://rss.example.test"
        os.environ["RSS_EMBEDDINGS_ENABLED"] = "false"
        settings = Settings.from_env()
        service = PublisherService(settings)
        service.configure_feed({
            "title": "Smoke Feed",
            "description": "Smoke test feed",
            "site_url": "https://rss.example.test",
            "max_items": 20,
        })
        created = service.create_entry({
            "kind": "status",
            "title": "Smoke test entry",
            "summary": "Publisher core is able to create and render an entry.",
            "categories": ["smoke", "status"],
            "public_metadata": {"check": "core"},
        })
        assert created.status == "created", created
        first = settings.public_dir.joinpath("feed.xml").read_bytes()
        service.rebuild_public()
        second = settings.public_dir.joinpath("feed.xml").read_bytes()
        assert first == second, "rebuild must be byte-identical"
        validated = service.validate_feed()
        assert validated["valid"] is True, validated
        no_op = service.update_entry(created.id, {"summary": "Publisher core is able to create and render an entry."})
        assert no_op.status == "unchanged", no_op
        print("PASS core smoke")
        print(f"feed={settings.public_dir / 'feed.xml'}")
        print(f"entry_id={created.id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
