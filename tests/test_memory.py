import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app


def test_save_and_read_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "MEMORY_FILE", tmp_path / "agent_memory.json")

    assert app.save_memory_entry("user_name", "Tomas") == "Sparat: user_name"
    assert app.get_memory_entry("user_name") == "user_name: Tomas"


def test_read_missing_key(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "MEMORY_FILE", tmp_path / "agent_memory.json")

    assert app.get_memory_entry("does_not_exist") == "Inget sparat för 'does_not_exist'."


def test_read_all_when_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "MEMORY_FILE", tmp_path / "agent_memory.json")

    assert app.get_memory_entry("_all") == "Minnet är tomt."


def test_read_all_lists_every_entry(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "MEMORY_FILE", tmp_path / "agent_memory.json")

    app.save_memory_entry("user_name", "Tomas")
    app.save_memory_entry("favorite_editor", "VS Code")

    result = app.get_memory_entry("_all")
    assert "user_name: Tomas" in result
    assert "favorite_editor: VS Code" in result
