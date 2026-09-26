from __future__ import annotations

import json
import sys

import pytest

from rss_publisher import cli


def _run(monkeypatch, argv, tmp_path):
    monkeypatch.setenv("RSS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("RSS_PUBLIC_DIR", str(tmp_path / "public"))
    monkeypatch.setenv("RSS_PUBLIC_BASE_URL", "https://rss.example.test")
    monkeypatch.setenv("RSS_EMBEDDINGS_ENABLED", "false")
    monkeypatch.setattr(sys, "argv", ["rss-publisher", *argv])
    cli.main()


def test_cli_validate(monkeypatch, tmp_path, capsys):
    _run(monkeypatch, ["validate"], tmp_path)
    out = json.loads(capsys.readouterr().out)
    assert out["valid"] is True


def test_cli_audit(monkeypatch, tmp_path, capsys):
    _run(monkeypatch, ["audit"], tmp_path)
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True


def test_cli_rebuild(monkeypatch, tmp_path, capsys):
    _run(monkeypatch, ["rebuild"], tmp_path)
    out = json.loads(capsys.readouterr().out)
    assert out["valid"] is True


def test_cli_export_state_to_stdout(monkeypatch, tmp_path, capsys):
    _run(monkeypatch, ["export-state"], tmp_path)
    out = json.loads(capsys.readouterr().out)
    assert out["schema_version"] == 1


def test_cli_export_state_to_file(monkeypatch, tmp_path, capsys):
    target = tmp_path / "state.json"
    _run(monkeypatch, ["export-state", "--output", str(target)], tmp_path)
    assert target.exists()
    assert json.loads(target.read_text())["schema_version"] == 1
    assert str(target) in capsys.readouterr().out


def test_cli_requires_subcommand(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "argv", ["rss-publisher"])
    with pytest.raises(SystemExit):
        cli.main()
