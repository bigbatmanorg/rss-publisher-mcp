from __future__ import annotations

import runpy
import sys


def test_dunder_main_invokes_cli(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("RSS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("RSS_PUBLIC_DIR", str(tmp_path / "public"))
    monkeypatch.setenv("RSS_PUBLIC_BASE_URL", "https://rss.example.test")
    monkeypatch.setenv("RSS_EMBEDDINGS_ENABLED", "false")
    monkeypatch.setattr(sys, "argv", ["rss-publisher", "validate"])
    runpy.run_module("rss_publisher.__main__", run_name="__main__")
    assert '"valid": true' in capsys.readouterr().out
