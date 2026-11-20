"""Tests for Gene Day. The build runs these through LocalRunner."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pippa_agentapp_sdk import LocalRunner

from app import (
    App,
    BedtimeUnreadable,
    FoodMissing,
    FoodUnknown,
    MetabolismUnknown,
    RawDnaRefused,
)

NOW = datetime(2026, 11, 20, 14, 0, tzinfo=timezone.utc)


def call(outcome: str, inputs: dict, *, explicit: bool = False):
    return LocalRunner(App()).call(
        outcome, inputs, granted_secrets={}, now=NOW, request_id="test-1",
        explicit=explicit,
    ).result


def test_the_manifest_is_valid():
    app = App()
    assert app.manifest.app_id.startswith("hack.")
    assert [o.id for o in app.manifest.outcomes] == ["caffeine.cutoff", "lactose.check"]


def test_slow_metaboliser_cutoff():
    result = call("caffeine.cutoff", {"caffeine_metabolism": "slow", "bedtime": "23:00"})
    assert result.data["last_coffee_time"] == "13:00"
    assert result.data["hours_before_bed"] == 10


def test_fast_metaboliser_pm_bedtime():
    result = call("caffeine.cutoff", {"caffeine_metabolism": "fast", "bedtime": "10:30pm"})
    assert result.data["last_coffee_time"] == "16:30"


def test_cutoff_wraps_past_midnight():
    result = call("caffeine.cutoff", {"caffeine_metabolism": "slow", "bedtime": "02:00"})
    assert result.data["last_coffee_time"] == "16:00"


def test_default_bedtime():
    result = call("caffeine.cutoff", {"caffeine_metabolism": "normal", "bedtime": ""})
    assert result.data["bedtime_used"] == "23:00"
    assert result.data["last_coffee_time"] == "15:00"


def test_unknown_metabolism_is_refused():
    with pytest.raises(MetabolismUnknown):
        call("caffeine.cutoff", {"caffeine_metabolism": "", "bedtime": "23:00"})


def test_bad_bedtime_is_refused():
    with pytest.raises(BedtimeUnreadable):
        call("caffeine.cutoff", {"caffeine_metabolism": "slow", "bedtime": "late"})


def test_raw_genotype_is_refused():
    with pytest.raises(RawDnaRefused):
        call("caffeine.cutoff", {"caffeine_metabolism": "rs762551 AC", "bedtime": "23:00"})
    with pytest.raises(RawDnaRefused):
        call("lactose.check", {"food": "latte", "lactose_status": "GG"}, explicit=True)


def test_latte_for_intolerant():
    result = call("lactose.check", {"food": "a large latte", "lactose_status": "intolerant"})
    assert result.data["food_matched"] == "latte"
    assert result.data["verdict"] == "likely symptoms"
    assert result.data["likely_ok"] is False


def test_oat_milk_beats_milk():
    result = call("lactose.check", {"food": "oat milk", "lactose_status": "intolerant"})
    assert result.data["food_matched"] == "oat milk"
    assert result.data["verdict"] == "fine"


def test_tolerant_is_fine():
    result = call("lactose.check", {"food": "milkshake", "lactose_status": "tolerant"})
    assert result.data["verdict"] == "fine"


def test_missing_and_unknown_food():
    with pytest.raises(FoodMissing):
        call("lactose.check", {"food": "", "lactose_status": "intolerant"})
    with pytest.raises(FoodUnknown):
        call("lactose.check", {"food": "sushi", "lactose_status": "intolerant"})
