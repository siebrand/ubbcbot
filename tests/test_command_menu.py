"""The command menus Telegram suggests: one for groups, one for customers, one for the admin.

setup-commands.sh builds the Telegram requests from telegram-commands.json. These tests run the script in dry-run mode,
so what would be sent to Telegram is checked without calling it, and they tie the menus to what the bot really routes.
"""

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

from services.command_router import CommandRouter
from services.routing.command_table import COMMAND_ROUTES

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "setup-commands.sh"
MENUS = json.loads((ROOT / "telegram-commands.json").read_text())

ALIASES = {f"/{alias}" for alias in CommandRouter.PERMANENT_ALIASES}
ADMIN_ONLY = {command for command, route in COMMAND_ROUTES.items() if route.admin_only}
CUSTOMER_ROUTES = set(COMMAND_ROUTES) - ADMIN_ONLY


def _names(menu: str) -> set[str]:
    return {"/" + entry["command"] for entry in MENUS[menu]}


def _admin_id(environment: str) -> int:
    samconfig = (ROOT / "samconfig.toml").read_text()
    return int(re.search(rf"Environment={environment} AdminUserId=(\d+)", samconfig).group(1))


def _dry_run(environment: str) -> list[tuple[str, dict]]:
    """The Telegram API calls the script would make, as (method, payload)"""
    result = subprocess.run(
        ["bash", str(SCRIPT), environment],
        env={**os.environ, "DRY_RUN": "1"},
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    calls = []
    for line in result.stdout.splitlines():
        if line.startswith("DRY_RUN "):
            method, payload = line.removeprefix("DRY_RUN ").split(" ", 1)
            calls.append((method, json.loads(payload)))
    return calls


def _scope_key(scope: dict) -> str:
    return json.dumps(scope, sort_keys=True)


def _menus_set_by_script(environment: str) -> dict[str, list[dict]]:
    return {
        _scope_key(payload["scope"]): payload["commands"]
        for method, payload in _dry_run(environment)
        if method == "setMyCommands"
    }


# --- what each menu may contain -----------------------------------------------------------------------------


class TestMenuContents:
    def test_the_menus_exist(self):
        assert set(MENUS) == {"group", "customer", "admin"}

    @pytest.mark.parametrize("menu", ["group", "customer", "admin"])
    def test_every_entry_is_valid_for_telegram(self, menu):
        assert 0 < len(MENUS[menu]) <= 100
        for entry in MENUS[menu]:
            assert re.fullmatch(r"[a-z0-9_]{1,32}", entry["command"]), entry
            assert 1 <= len(entry["description"]) <= 256, entry

    @pytest.mark.parametrize("menu", ["group", "customer", "admin"])
    def test_no_command_is_listed_twice(self, menu):
        commands = [entry["command"] for entry in MENUS[menu]]

        assert len(commands) == len(set(commands))

    @pytest.mark.parametrize("menu", ["group", "customer", "admin"])
    def test_every_suggested_command_is_a_command_of_the_bot(self, menu):
        assert sorted(_names(menu) - set(COMMAND_ROUTES) - ALIASES) == []

    def test_the_group_menu_only_has_commands_that_work_in_a_production_group(self):
        assert _names("group") <= CommandRouter.GROUP_ALLOWED_COMMANDS

    def test_customers_are_not_offered_admin_commands(self):
        assert sorted(_names("customer") & ADMIN_ONLY) == []
        assert sorted(_names("group") & ADMIN_ONLY) == []

    def test_the_admin_menu_has_every_admin_command_and_every_customer_suggestion(self):
        assert _names("admin") >= ADMIN_ONLY
        assert _names("customer") <= _names("admin")

    def test_the_admin_menu_has_nothing_else(self):
        assert sorted(_names("admin") - ADMIN_ONLY - _names("customer")) == []


# --- what the script sends ----------------------------------------------------------------------------------


@pytest.mark.parametrize("environment", ["test", "prod"])
class TestScript:
    def test_a_group_gets_only_the_group_menu(self, environment):
        menus = _menus_set_by_script(environment)

        assert menus[_scope_key({"type": "all_group_chats"})] == MENUS["group"]

    def test_private_chats_and_the_default_get_the_customer_menu(self, environment):
        menus = _menus_set_by_script(environment)

        assert menus[_scope_key({"type": "all_private_chats"})] == MENUS["customer"]
        assert menus[_scope_key({"type": "default"})] == MENUS["customer"]

    def test_only_the_private_chat_of_the_admin_gets_the_admin_menu(self, environment):
        menus = _menus_set_by_script(environment)

        admin_scope = _scope_key({"type": "chat", "chat_id": _admin_id(environment)})
        assert menus[admin_scope] == MENUS["admin"]
        assert [key for key, commands in menus.items() if commands == MENUS["admin"]] == [admin_scope]

    def test_no_other_scope_is_set(self, environment):
        menus = _menus_set_by_script(environment)

        assert len(menus) == 4

    def test_nothing_that_is_set_is_deleted_afterwards(self, environment):
        calls = _dry_run(environment)
        set_scopes = [_scope_key(p["scope"]) for m, p in calls if m == "setMyCommands"]

        for method, payload in calls:
            if method == "deleteMyCommands":
                assert all(_scope_key(payload["scope"]) != scope for scope in set_scopes), payload

    def test_old_group_overrides_are_removed_so_the_group_menu_applies(self, environment):
        deleted = [_scope_key(p["scope"]) for m, p in _dry_run(environment) if m == "deleteMyCommands"]

        assert any('"type": "chat_administrators"' in scope for scope in deleted)
        assert any('"type": "chat"' in scope and "chat_id" in scope for scope in deleted)
        assert _scope_key({"type": "all_chat_administrators"}) in deleted
