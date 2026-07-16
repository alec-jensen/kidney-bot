"""Tests for the pure-data command catalog — the single source of truth for
both the in-Discord /help command and the public GET /api/docs/commands
endpoint."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "kidney-bot"))

from utils.command_catalog import COMMAND_CATALOG


class TestCommandCatalog:
    def test_every_category_has_name_and_commands(self):
        for category in COMMAND_CATALOG:
            assert category.get("name"), f"category missing name: {category}"
            assert "commands" in category, f"category missing commands: {category}"
            assert isinstance(category["commands"], list)

    def test_every_command_has_a_name(self):
        for category in COMMAND_CATALOG:
            for command in category["commands"]:
                assert command.get("name"), f"command missing name in {category['name']}: {command}"

    def test_every_param_has_a_name(self):
        for category in COMMAND_CATALOG:
            for command in category["commands"]:
                for param in command.get("params", []):
                    assert param.get("name"), (
                        f"param missing name in {category['name']} / {command['name']}: {param}"
                    )

    def test_heuristics_thresholds_alert_default_is_40(self):
        antiraid = next(c for c in COMMAND_CATALOG if c["name"] == "Anti-Raid")
        thresholds = next(
            c for c in antiraid["commands"] if c["name"] == "/heuristics thresholds"
        )
        alert_param = next(p for p in thresholds["params"] if p["name"] == "alert")
        assert "Default: 40." in alert_param["desc"]
