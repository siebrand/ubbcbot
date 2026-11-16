"""to_utc_datetime: one way to compare dates that are stored as ISO strings and used as datetime objects."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from utils.timezone import to_utc_datetime

NOON = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "value",
    [
        "2026-11-16T12:00:00+00:00",
        "2026-11-16T12:00:00Z",
        "2026-11-16T13:00:00+01:00",
        "2026-11-16T12:00:00",  # no timezone: UTC, like the rest of the bot
        datetime(2026, 11, 16, 12, 0),
        datetime(2026, 11, 16, 13, 0, tzinfo=timezone(timedelta(hours=1))),
        NOON,
    ],
)
def test_every_form_of_noon_is_the_same_moment(value):
    assert to_utc_datetime(value) == NOON


def test_the_result_is_always_timezone_aware_so_that_values_can_be_compared():
    values = ["2026-11-16T12:00:00", datetime(2026, 11, 16, 12, 0), NOON]

    assert len({to_utc_datetime(value) for value in values}) == 1
    assert sorted(to_utc_datetime(value) for value in values)  # no TypeError between naive and aware


@pytest.mark.parametrize("value", [None, "", "not a date"])
def test_a_missing_or_unreadable_date_sorts_before_every_real_date(value):
    assert to_utc_datetime(value) < to_utc_datetime("2000-01-01T00:00:00+00:00")
