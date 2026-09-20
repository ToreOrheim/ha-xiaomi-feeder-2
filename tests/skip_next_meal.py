"""Tests for Xiaomi Feeder Skip Next Meal switch."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntry

from custom_components.xiaomi_feeder.coordinator import (
    FeederCoordinatorData,
    XiaomiFeederCoordinator,
)
from custom_components.xiaomi_feeder.switch import XiaomiFeederSkipNextMealSwitch
from xiaomi_feeder_2.models import FeederStatus, ScheduleMeal, SchedulePlan


@pytest.fixture
def mock_entry():
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry_123"
    return entry


@pytest.fixture
def mock_coordinator():
    coord = MagicMock()
    coord.device_name = "Smart Feeder"
    return coord


@pytest.fixture
def mock_hass():
    hass = MagicMock()
    hass.async_add_executor_job = AsyncMock()
    return hass


@pytest.fixture
def make_coordinator(mock_hass):
    def _make():
        with (
            patch("homeassistant.helpers.frame.report_usage"),
            patch("custom_components.xiaomi_feeder.coordinator.Store"),
            patch("custom_components.xiaomi_feeder.coordinator.XiaomiFeeder"),
        ):
            coordinator = XiaomiFeederCoordinator(
                mock_hass, "1.2.3.4", "token", "Smart Feeder", "test_entry_123"
            )
        coordinator.async_request_refresh = AsyncMock()
        coordinator._write_raw_hardware_schedule_sync = MagicMock()
        return coordinator

    return _make


def test_skip_next_meal_switch_is_on(mock_coordinator, mock_entry):
    """Test is_on reflects the coordinator's skip state."""
    switch = XiaomiFeederSkipNextMealSwitch(mock_coordinator, mock_entry)

    status = MagicMock(spec=FeederStatus)
    schedule = SchedulePlan(enabled=True, meals=[], raw_string="")

    mock_coordinator.data = FeederCoordinatorData(
        status=status, schedule=schedule, is_next_feed_skipped=True
    )
    assert switch.is_on is True

    mock_coordinator.data = FeederCoordinatorData(
        status=status, schedule=schedule, is_next_feed_skipped=False
    )
    assert switch.is_on is False

    mock_coordinator.data = None
    assert switch.is_on is False


@pytest.mark.asyncio
async def test_skip_next_meal_switch_turn_on(mock_coordinator, mock_entry):
    """Test turning the switch on skips the next meal."""
    mock_coordinator.async_set_skip_next_meal = AsyncMock()
    switch = XiaomiFeederSkipNextMealSwitch(mock_coordinator, mock_entry)

    await switch.async_turn_on()
    mock_coordinator.async_set_skip_next_meal.assert_awaited_once_with(True)


@pytest.mark.asyncio
async def test_skip_next_meal_switch_turn_off(mock_coordinator, mock_entry):
    """Test turning the switch off resumes the normal schedule."""
    mock_coordinator.async_set_skip_next_meal = AsyncMock()
    switch = XiaomiFeederSkipNextMealSwitch(mock_coordinator, mock_entry)

    await switch.async_turn_off()
    mock_coordinator.async_set_skip_next_meal.assert_awaited_once_with(False)


@pytest.mark.asyncio
async def test_skip_next_meal_disables_next_meal(mock_hass, make_coordinator):
    """Test skipping the next meal disables it in the EEPROM payload."""
    coordinator = make_coordinator()
    coordinator._stored_data = {"master_schedule_raw": "0800027f121e037f"}

    status = MagicMock(spec=FeederStatus)
    meals = [
        ScheduleMeal(time="08:00", portions=2, repeat=127, raw="0800027f"),
        ScheduleMeal(time="18:30", portions=3, repeat=127, raw="121e037f"),
    ]
    next_feed_time = datetime(2026, 8, 16, 8, 0, tzinfo=timezone.utc)
    coordinator.data = FeederCoordinatorData(
        status=status,
        schedule=SchedulePlan(enabled=True, meals=meals, raw_string="0800027f121e037f"),
        next_feed_time=next_feed_time,
    )

    await coordinator.async_set_skip_next_meal(True)

    assert coordinator._skip_next_meal is True
    assert coordinator._skipped_meal_time == next_feed_time
    mock_hass.async_add_executor_job.assert_awaited_once_with(
        coordinator._write_raw_hardware_schedule_sync, "08000200,121e037f"
    )
    coordinator.async_request_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_skip_next_meal_no_upcoming_meal_is_noop(mock_hass, make_coordinator):
    """Test skipping with no upcoming meal is a no-op."""
    coordinator = make_coordinator()
    coordinator._stored_data = {}

    status = MagicMock(spec=FeederStatus)
    coordinator.data = FeederCoordinatorData(
        status=status,
        schedule=SchedulePlan(enabled=True, meals=[], raw_string=""),
        next_feed_time=None,
    )

    await coordinator.async_set_skip_next_meal(True)

    assert coordinator._skip_next_meal is False
    assert coordinator._skipped_meal_time is None
    mock_hass.async_add_executor_job.assert_not_awaited()
    coordinator.async_request_refresh.assert_not_awaited()


@pytest.mark.asyncio
async def test_skip_next_meal_resume_restores_master_schedule(
    mock_hass, make_coordinator
):
    """Test resuming restores the master schedule to EEPROM."""
    coordinator = make_coordinator()
    coordinator._stored_data = {"master_schedule_raw": "0800027f121e037f"}
    coordinator._skip_next_meal = True
    coordinator._skip_meals_count = 1
    coordinator._skipped_meal_time = datetime(2026, 8, 16, 8, 0, tzinfo=timezone.utc)

    await coordinator.async_set_skip_next_meal(False)

    assert coordinator._skip_next_meal is False
    assert coordinator._skip_meals_count == 0
    assert coordinator._skipped_meal_time is None
    mock_hass.async_add_executor_job.assert_awaited_once_with(
        coordinator._write_raw_hardware_schedule_sync, "0800027f121e037f"
    )
    coordinator.async_request_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_skip_next_meal_writes_comma_separated_payload(
    mock_hass, make_coordinator
):
    coordinator = make_coordinator()
    coordinator._stored_data = {"master_schedule_raw": "[1,03000101,15000101,23000101]"}

    status = MagicMock(spec=FeederStatus)
    meals = [
        ScheduleMeal(time="03:00", portions=1, repeat=1, raw="03000101"),
        ScheduleMeal(time="15:00", portions=1, repeat=1, raw="15000101"),
        ScheduleMeal(time="23:00", portions=1, repeat=1, raw="23000101"),
    ]
    coordinator.data = FeederCoordinatorData(
        status=status,
        schedule=SchedulePlan(
            enabled=True,
            meals=meals,
            raw_string="[1,03000101,15000101,23000101]",
        ),
        next_feed_time=datetime(2026, 8, 16, 15, 0, tzinfo=timezone.utc),
    )

    await coordinator.async_set_skip_next_meal(True)

    expected = "03000101,15000100,23000101"
    payload = mock_hass.async_add_executor_job.await_args.args[1]
    assert payload == expected
