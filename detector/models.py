##########################################################################################
#
# Script name: models.py
#
# Description: Core datatypes for the power detector.
#
# Author: John Macdonald
#
##########################################################################################

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict


class EventKind(str, Enum):
    '''Event kinds emitted by the detector state machine.'''
    POWER_LOSS = 'power_loss'
    POWER_RESTORE = 'power_restore'
    WAN_LOSS = 'wan_loss'
    WAN_RESTORE = 'wan_restore'


@dataclass
class ProbeResult:
    '''Result of a single probe execution.'''
    ok: bool
    reason: str
    latency_ms: int
    observed_at: float


@dataclass
class AlertEvent:
    '''A notification-ready state transition event.'''
    kind: EventKind
    started_at: float
    duration_seconds: int
    details: str
    is_reminder: bool = False
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass
class DetectorConfig:
    '''Validated runtime settings used by the detector loop.'''
    poll_interval_seconds: int
    power_loss_threshold_seconds: int
    power_restore_stability_seconds: int
    wan_loss_threshold_seconds: int
    wan_restore_stability_seconds: int
    event_cooldown_seconds: int
    outage_cadence_mode: str
    outage_reminder_interval_seconds: int
