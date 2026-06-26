"""Tests for ``mos plugin create`` — the interactive scaffolder.

These exercise the scaffolding in non-interactive mode against a
``tmp_path`` so they don't touch the user's real filesystem.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from mos.cli.plugin import (
    _scaffold_plugin,
    _validate_entry_name,
    _validate_package_name,
    create,
)


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


class TestValidatePackageName:
    def test_accepts_simple_name(self):
        assert _validate_package_name("mos_demo") == "mos_demo"

    def test_accepts_name_with_underscores_and_digits(self):
        assert _validate_package_name("mos_my_plugin_2") == "mos_my_plugin_2"

    def test_strips_whitespace(self):
        assert _validate_package_name("  mos_demo  ") == "mos_demo"

    @pytest.mark.parametrize("bad", ["", "   ", "Demo", "1demo", "demo-x", "demo.x"])
    def test_rejects_invalid(self, bad):
        from click import BadParameter

        with pytest.raises(BadParameter):
            _validate_package_name(bad)


class TestValidateEntryName:
    def test_accepts_simple_name(self):
        assert _validate_entry_name("demo") == "demo"

    @pytest.mark.parametrize("bad", ["", "Demo", "1demo", "demo-x"])
    def test_rejects_invalid(self, bad):
        from click import BadParameter

        with pytest.raises(BadParameter):
            _validate_entry_name(bad)


# ---------------------------------------------------------------------------
# _scaffold_plugin — direct file generation
# ---------------------------------------------------------------------------


class TestScaffoldPlugin:
    """Drive ``_scaffold_plugin`` directly so we don't depend on Click
    prompt / tty detection. The Click-level behaviour is covered in
    ``TestCreateCli`` below."""

    def test_creates_expected_layout(self, tmp_path: Path):
        written = _scaffold_plugin(
            target_dir=tmp_path / "mos_demo",
            pkg="mos_demo",
            entry="demo",
            version="0.1.0",
            description="A demo plugin",
            author="Alice",
        )

        # Returned list contains every file in deterministic order.
        assert [p.name for p in written] == [
            "pyproject.toml",
            "README.md",
            ".gitignore",
            "__init__.py",
            "__init__.py",
            "__init__.py",
            "config.py",
        ]

        root = tmp_path / "mos_demo"
        assert (root / "pyproject.toml").is_file()
        assert (root / "README.md").is_file()
        assert (root / ".gitignore").is_file()
        assert (root / "src" / "mos_demo" / "__init__.py").is_file()
        assert (root / "src" / "mos_demo" / "cli" / "__init__.py").is_file()
        assert (root / "src" / "mos_demo" / "core" / "__init__.py").is_file()
        assert (root / "src" / "mos_demo" / "core" / "config.py").is_file()

    def test_pyproject_substitutes_user_values(self, tmp_path: Path):
        _scaffold_plugin(
            target_dir=tmp_path / "pkg",
            pkg="mos_widget",
            entry="widget",
            version="2.3.4",
            description="Widget plugin",
            author="Bob",
        )

        text = (tmp_path / "pkg" / "pyproject.toml").read_text(encoding="utf-8")
        assert 'name = "mos_widget"' in text
        assert 'version = "2.3.4"' in text
        assert 'description = "Widget plugin"' in text
        # TOML inline table — the doubled ``{{``/``}}`` in the template
        # must come out as a single brace pair.
        assert '{name = "Bob"}' in text
        # Entry point declaration
        assert 'widget = "mos_widget:describe_plugin"' in text
        # The MOS plugin group key
        assert '[project.entry-points."mos.plugins"]' in text

    def test_init_module_uses_user_entry_and_pkg(self, tmp_path: Path):
        _scaffold_plugin(
            target_dir=tmp_path / "pkg",
            pkg="mos_widget",
            entry="widget",
            version="0.1.0",
            description="Widget plugin",
            author="Bob",
        )

        text = (tmp_path / "pkg" / "src" / "mos_widget" / "__init__.py").read_text(
            encoding="utf-8"
        )
        assert "from mos_widget.cli import widget" in text
        assert "from mos_widget.core.config import get_config" in text
        assert 'name="widget"' in text
        assert 'command=widget' in text
        assert '__version__ = "0.1.0"' in text

    def test_cli_group_module_defines_click_group(self, tmp_path: Path):
        _scaffold_plugin(
            target_dir=tmp_path / "pkg",
            pkg="mos_widget",
            entry="widget",
            version="0.1.0",
            description="Widget plugin",
            author="Bob",
        )

        text = (tmp_path / "pkg" / "src" / "mos_widget" / "cli" / "__init__.py").read_text(
            encoding="utf-8"
        )
        assert "@click.group()" in text
        assert "def widget():" in text

    def test_core_config_subclass_targets_plugin_path(self, tmp_path: Path):
        _scaffold_plugin(
            target_dir=tmp_path / "pkg",
            pkg="mos_widget",
            entry="widget",
            version="0.1.0",
            description="Widget plugin",
            author="Bob",
        )

        text = (tmp_path / "pkg" / "src" / "mos_widget" / "core" / "config.py").read_text(
            encoding="utf-8"
        )
        # Class name is the entry name capitalized; config file name
        # matches the entry, not the package (e.g. ``widget.json``,
        # not ``mos_widget.json``), so the two don't collide if the
        # user has multiple plugins.
        assert "class WidgetConfig" in text
        assert 'DEFAULT_WIDGET_CONFIG_PATH' in text
        assert 'Path.home() / ".mos" / "widget.json"' in text
        assert "def get_config" in text

    def test_readme_references_user_values(self, tmp_path: Path):
        _scaffold_plugin(
            target_dir=tmp_path / "pkg",
            pkg="mos_widget",
            entry="widget",
            version="0.1.0",
            description="Widget plugin",
            author="Bob",
        )

        text = (tmp_path / "pkg" / "README.md").read_text(encoding="utf-8")
        assert "# mos_widget" in text
        assert "Widget plugin" in text
        assert "mos widget --help" in text


# ---------------------------------------------------------------------------
# Click-level integration via CliRunner (non-interactive)
# ---------------------------------------------------------------------------


class TestCreateCli:
    """End-to-end Click test. The ``--non-interactive`` flag forces the
    command to skip all ``click.prompt`` calls, which is what makes
    CliRunner usable here."""

    def test_non_interactive_creates_plugin(self, tmp_path: Path, monkeypatch):
        # CliRunner.isolated_filesystem() gives us a clean CWD.
        from click.testing import CliRunner

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path) as td:
            result = runner.invoke(
                create,
                [
                    "--name",
                    "demo",
                    "--description",
                    "Demo plugin",
                    "--author",
                    "Alice",
                    "--non-interactive",
                ],
            )

        assert result.exit_code == 0, result.output
        assert "已在" in result.output  # "[OK] 已在 ..."

        created = Path(td) / "mos_demo"
        assert (created / "pyproject.toml").is_file()
        assert (created / "src" / "mos_demo" / "__init__.py").is_file()
        assert (created / "src" / "mos_demo" / "cli" / "__init__.py").is_file()
        assert (created / "src" / "mos_demo" / "core" / "config.py").is_file()

    def test_non_existing_dir_is_created(self, tmp_path: Path):
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path) as td:
            result = runner.invoke(
                create,
                [
                    "--name",
                    "demo",
                    "--dir",
                    "custom_dir",
                    "--non-interactive",
                ],
            )

        assert result.exit_code == 0, result.output
        assert (Path(td) / "custom_dir" / "pyproject.toml").is_file()

    def test_refuses_to_overwrite_non_empty_dir_without_force(
        self, tmp_path: Path
    ):
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path) as td:
            target = Path(td) / "mos_demo"
            target.mkdir()
            (target / "preexisting.txt").write_text("hi")

            result = runner.invoke(
                create,
                [
                    "--name",
                    "demo",
                    "--non-interactive",
                ],
            )

        assert result.exit_code != 0
        # Click's BadParameter surfaces in result.output.
        assert "已存在" in result.output or "non-empty" in result.output.lower()

    def test_force_overwrites_non_empty_dir(self, tmp_path: Path):
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path) as td:
            target = Path(td) / "mos_demo"
            target.mkdir()
            (target / "preexisting.txt").write_text("hi")

            result = runner.invoke(
                create,
                [
                    "--name",
                    "demo",
                    "--force",
                    "--non-interactive",
                ],
            )

        assert result.exit_code == 0, result.output
        assert (target / "pyproject.toml").is_file()

    def test_empty_dir_is_fine_without_force(self, tmp_path: Path):
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path) as td:
            target = Path(td) / "mos_demo"
            target.mkdir()  # exists but empty

            result = runner.invoke(
                create,
                [
                    "--name",
                    "demo",
                    "--non-interactive",
                ],
            )

        assert result.exit_code == 0, result.output
        assert (target / "pyproject.toml").is_file()

    def test_invalid_entry_name_rejected(self, tmp_path: Path):
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(
                create,
                [
                    "--name",
                    "BadName",
                    "--non-interactive",
                ],
            )

        assert result.exit_code != 0
        assert "非法" in result.output
