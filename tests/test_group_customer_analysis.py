"""Tests for the --show-unapproved logic in scripts/group_customer_analysis.py (no network)."""

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from group_customer_analysis import GroupCustomerAnalyzer


def _analyzer(statuses):
    a = GroupCustomerAnalyzer.__new__(GroupCustomerAnalyzer)
    a.get_customer_details = lambda uid: {
        "telegram_user_id": uid,
        "first_name": f"U{uid}",
        "last_name": "",
        "username": f"user{uid}",
        "authorization_status": statuses[uid],
    }
    return a


def _p(uid, first="A", last=None, username=None, bot=False, deleted=False):
    return SimpleNamespace(id=uid, first_name=first, last_name=last, username=username, bot=bot, deleted=deleted)


class TestNormalizeParticipants:
    def test_skips_bots_and_deleted(self):
        members, skipped = GroupCustomerAnalyzer.normalize_participants(
            [_p(1), _p(2, bot=True), _p(3, deleted=True), _p(4, first=None)]
        )
        assert set(members) == {1, 4}
        assert skipped == {"bots": 1, "deleted": 1}

    def test_missing_names_become_empty_strings(self):
        members, _ = GroupCustomerAnalyzer.normalize_participants([_p(1, first=None, last=None, username=None)])
        assert members[1] == {"first_name": "", "last_name": "", "username": ""}


class TestUnapprovedMembers:
    def test_splits_unapproved_and_unregistered(self):
        a = _analyzer({1: "approved", 2: "unauthorized", 3: "rejected"})
        members = {1: {}, 2: {}, 3: {}, 9: {"first_name": "New", "last_name": "Person", "username": "np"}}

        unapproved, unregistered = a.get_unapproved_group_members(members, {1, 2, 3, 4})

        assert [(d["telegram_user_id"], d["authorization_status"]) for d in unapproved] == [
            (2, "unauthorized"),
            (3, "rejected"),
        ]
        assert unregistered == [{"id": 9, "first_name": "New", "last_name": "Person", "username": "np"}]

    def test_all_approved_gives_empty_result(self):
        a = _analyzer({1: "approved"})
        assert a.get_unapproved_group_members({1: {}}, {1}) == ([], [])

    def test_registered_customer_outside_the_group_is_ignored(self):
        a = _analyzer({5: "unauthorized"})
        assert a.get_unapproved_group_members({}, {5}) == ([], [])


class TestPrintUnapproved:
    def test_user_account_failure_falls_back_to_bot_api_members(self, capsys):
        a = _analyzer({1: "unauthorized"})

        def boom():
            raise RuntimeError("no session")

        a.get_user_account_participants = boom

        a._print_unapproved_members({1}, {1})

        out = capsys.readouterr().out
        assert "Could not list members with the user account (no session)" in out
        assert "Registered, not approved (1)" in out
        assert "cannot be listed" in out

    def test_user_account_listing_shows_unregistered_members(self, capsys):
        a = _analyzer({1: "approved"})
        a.get_user_account_participants = lambda: (
            {1: {}, 9: {"first_name": "New", "last_name": "", "username": "np"}},
            {"bots": 2, "deleted": 1},
        )

        a._print_unapproved_members({1}, {1})

        out = capsys.readouterr().out
        assert "Count: 1" in out
        assert "New (@np) - ID: 9" in out
        assert "Skipped: 2 bots, 1 deleted accounts." in out
