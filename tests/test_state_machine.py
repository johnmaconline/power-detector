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
