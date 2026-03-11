import copy

from detector.config import DEFAULT_CONFIG
from detector.models import EventKind
from detector.state_machine import DetectorStateMachine


def _cfg(**overrides):
    config = copy.deepcopy(DEFAULT_CONFIG)
    config.update(overrides)
    return config


def test_power_no_alert_before_threshold():
    machine = DetectorStateMachine(_cfg())

    events = machine.evaluate(0, power_ok=False, wan_ok=True)
    assert events == []

    events = machine.evaluate(59, power_ok=False, wan_ok=True)
    assert events == []


def test_power_alert_at_or_after_threshold_once():
    machine = DetectorStateMachine(_cfg())

    assert machine.evaluate(0, power_ok=False, wan_ok=True) == []
    events = machine.evaluate(60, power_ok=False, wan_ok=True)
    assert len(events) == 1
    assert events[0].kind == EventKind.POWER_LOSS

    events = machine.evaluate(61, power_ok=False, wan_ok=True)
    assert events == []


def test_power_restore_after_stability():
    machine = DetectorStateMachine(_cfg())

    machine.evaluate(0, power_ok=False, wan_ok=True)
    loss_events = machine.evaluate(60, power_ok=False, wan_ok=True)
    assert loss_events[0].kind == EventKind.POWER_LOSS

    assert machine.evaluate(61, power_ok=True, wan_ok=True) == []
    assert machine.evaluate(70, power_ok=True, wan_ok=True) == []

    restore_events = machine.evaluate(71, power_ok=True, wan_ok=True)
    assert len(restore_events) == 1
    assert restore_events[0].kind == EventKind.POWER_RESTORE


def test_wan_independent_from_power():
    machine = DetectorStateMachine(_cfg())

    machine.evaluate(0, power_ok=True, wan_ok=False)
    events = machine.evaluate(90, power_ok=True, wan_ok=False)

    assert len(events) == 1
    assert events[0].kind == EventKind.WAN_LOSS


def test_periodic_reminder_respects_cooldown():
    machine = DetectorStateMachine(_cfg(
        outage_cadence_mode='periodic',
        outage_reminder_interval_seconds=60,
        event_cooldown_seconds=180,
    ))

    machine.evaluate(0, power_ok=False, wan_ok=True)
    loss_events = machine.evaluate(60, power_ok=False, wan_ok=True)
    assert len(loss_events) == 1
    assert loss_events[0].kind == EventKind.POWER_LOSS
    assert not loss_events[0].is_reminder

    assert machine.evaluate(120, power_ok=False, wan_ok=True) == []

    reminder_events = machine.evaluate(241, power_ok=False, wan_ok=True)
    assert len(reminder_events) == 1
    assert reminder_events[0].kind == EventKind.POWER_LOSS
    assert reminder_events[0].is_reminder


def test_scheduled_reminders_follow_progressive_schedule():
    machine = DetectorStateMachine(_cfg(
        outage_cadence_mode='scheduled',
        outage_reminder_schedule_minutes=[5, 15, 30],
        outage_reminder_repeat_after_last_minutes=1440,
        event_cooldown_seconds=60,
    ))

    machine.evaluate(0, power_ok=False, wan_ok=True)
    initial_events = machine.evaluate(60, power_ok=False, wan_ok=True)
    assert len(initial_events) == 1
    assert not initial_events[0].is_reminder

    assert machine.evaluate(299, power_ok=False, wan_ok=True) == []

    first_reminder = machine.evaluate(300, power_ok=False, wan_ok=True)
    assert len(first_reminder) == 1
    assert first_reminder[0].is_reminder

    assert machine.evaluate(899, power_ok=False, wan_ok=True) == []

    second_reminder = machine.evaluate(900, power_ok=False, wan_ok=True)
    assert len(second_reminder) == 1
    assert second_reminder[0].is_reminder

    third_reminder = machine.evaluate(1800, power_ok=False, wan_ok=True)
    assert len(third_reminder) == 1
    assert third_reminder[0].is_reminder


def test_scheduled_reminders_repeat_daily_after_last_checkpoint():
    machine = DetectorStateMachine(_cfg(
        outage_cadence_mode='scheduled',
        outage_reminder_schedule_minutes=[5],
        outage_reminder_repeat_after_last_minutes=1440,
        event_cooldown_seconds=60,
    ))

    machine.evaluate(0, power_ok=False, wan_ok=True)
    machine.evaluate(60, power_ok=False, wan_ok=True)
    machine.evaluate(300, power_ok=False, wan_ok=True)

    before_daily = machine.evaluate(86399, power_ok=False, wan_ok=True)
    assert before_daily == []

    daily_reminder = machine.evaluate(86700, power_ok=False, wan_ok=True)
    assert len(daily_reminder) == 1
    assert daily_reminder[0].is_reminder


def test_opposite_transition_resets_cooldown_for_power_loss():
    machine = DetectorStateMachine(_cfg(event_cooldown_seconds=180))

    machine.evaluate(0, power_ok=False, wan_ok=True)
    loss_events = machine.evaluate(60, power_ok=False, wan_ok=True)
    assert len(loss_events) == 1

    machine.evaluate(61, power_ok=True, wan_ok=True)
    restore_events = machine.evaluate(71, power_ok=True, wan_ok=True)
    assert len(restore_events) == 1
    assert restore_events[0].kind == EventKind.POWER_RESTORE

    machine.evaluate(140, power_ok=False, wan_ok=True)
    second_loss_events = machine.evaluate(200, power_ok=False, wan_ok=True)
    assert len(second_loss_events) == 1
    assert second_loss_events[0].kind == EventKind.POWER_LOSS
