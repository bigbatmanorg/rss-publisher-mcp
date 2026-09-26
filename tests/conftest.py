from __future__ import annotations

import pytest
from rss_publisher.config import Settings
from rss_publisher.service import PublisherService


@pytest.fixture
def settings(tmp_path):
    return Settings(
        data_dir=tmp_path / "data",
        public_dir=tmp_path / "public",
        public_base_url="https://rss.example.test",
        feed_path="/feed.xml",
        entry_path="/entries",
        media_path="/media",
        files_path="/files",
        embeddings_enabled=False,
    )


@pytest.fixture
def service(settings):
    return PublisherService(settings)
