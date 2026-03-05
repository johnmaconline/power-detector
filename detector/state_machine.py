##########################################################################################
#
# Script name: state_machine.py
#
# Description: Stateful timing logic for outage detection and alert transitions.
#
# Author: John Macdonald
#
##########################################################################################

from typing import Dict, List, Optional

from detector.models import AlertEvent, EventKind


class DetectorStateMachine:
    '''Tracks probe transitions and emits deduplicated alert events.'''

    def __init__(self, config: dict):
        self.config = config

        self.power_failure_started_at: Optional[float] = None
        self.power_recovery_started_at: Optional[float] = None
        self.power_alerted: bool = False
        self.power_alert_anchor_at: Optional[float] = None
        self.power_last_reminder_at: Optional[float] = None

        self.wan_failure_started_at: Optional[float] = None
        self.wan_recovery_started_at: Optional[float] = None
        self.wan_alerted: bool = False
        self.wan_alert_anchor_at: Optional[float] = None

        self.last_sent_by_kind: Dict[EventKind, float] = {}

    def _opposite_event(self, kind: EventKind) -> Optional[EventKind]:
        '''Map an event kind to its opposite transition event kind.'''
        opposites = {
            EventKind.POWER_LOSS: EventKind.POWER_RESTORE,
            EventKind.POWER_RESTORE: EventKind.POWER_LOSS,
            EventKind.WAN_LOSS: EventKind.WAN_RESTORE,
            EventKind.WAN_RESTORE: EventKind.WAN_LOSS,
        }
        return opposites.get(kind)

    def _can_emit(self, kind: EventKind, now_ts: float) -> bool:
        '''Check per-kind cooldown eligibility for a new event.'''
        cooldown = self.config['event_cooldown_seconds']
        last_sent = self.last_sent_by_kind.get(kind)
        if last_sent is None:
            return True
        return (now_ts - last_sent) >= cooldown

    def _record_emit(self, kind: EventKind, now_ts: float) -> None:
        '''Record event emission and clear opposite cooldown marker.'''
        self.last_sent_by_kind[kind] = now_ts
        opposite = self._opposite_event(kind)
        if opposite in self.last_sent_by_kind:
            del self.last_sent_by_kind[opposite]

    def _new_event(
        self,
        kind: EventKind,
        now_ts: float,
        started_at: float,
        details: str,
        is_reminder: bool = False,
    ) -> AlertEvent:
        '''Build a normalized alert event object.'''
        duration = int(max(0, now_ts - started_at))
        return AlertEvent(
            kind=kind,
            started_at=started_at,
            duration_seconds=duration,
            details=details,
            is_reminder=is_reminder,
        )

    def _process_power(self, now_ts: float, power_ok: bool) -> List[AlertEvent]:
        '''Apply power probe signal to power state and emit events if needed.'''
        events: List[AlertEvent] = []

        if power_ok:
            self.power_failure_started_at = None

            if self.power_alerted:
                if self.power_recovery_started_at is None:
                    self.power_recovery_started_at = now_ts

                stabilized = (
                    now_ts - self.power_recovery_started_at
                    >= self.config['power_restore_stability_seconds']
                )

                if stabilized and self._can_emit(EventKind.POWER_RESTORE, now_ts):
                    events.append(
                        self._new_event(
                            EventKind.POWER_RESTORE,
                            now_ts,
                            self.power_alert_anchor_at or self.power_recovery_started_at,
                            'Power sentinel recovered and stabilized.',
                        )
                    )
                    self._record_emit(EventKind.POWER_RESTORE, now_ts)
                    self.power_alerted = False
                    self.power_alert_anchor_at = None
                    self.power_last_reminder_at = None
                    self.power_recovery_started_at = None
            else:
                self.power_recovery_started_at = None

            return events

        self.power_recovery_started_at = None

        if self.power_failure_started_at is None:
            self.power_failure_started_at = now_ts

        if not self.power_alerted:
            crossed = (
                now_ts - self.power_failure_started_at
                >= self.config['power_loss_threshold_seconds']
            )
            if crossed and self._can_emit(EventKind.POWER_LOSS, now_ts):
                events.append(
                    self._new_event(
                        EventKind.POWER_LOSS,
                        now_ts,
                        self.power_failure_started_at,
                        'Power sentinel unreachable past outage threshold.',
                    )
                )
                self._record_emit(EventKind.POWER_LOSS, now_ts)
                self.power_alerted = True
                self.power_alert_anchor_at = self.power_failure_started_at
                self.power_last_reminder_at = now_ts
            return events

        if self.config['outage_cadence_mode'] == 'periodic':
            if self.power_last_reminder_at is None:
                self.power_last_reminder_at = now_ts

            due = (
                now_ts - self.power_last_reminder_at
                >= self.config['outage_reminder_interval_seconds']
            )
            if due and self._can_emit(EventKind.POWER_LOSS, now_ts):
                events.append(
                    self._new_event(
                        EventKind.POWER_LOSS,
                        now_ts,
                        self.power_alert_anchor_at or self.power_failure_started_at,
                        'Power outage reminder.',
                        is_reminder=True,
                    )
                )
                self._record_emit(EventKind.POWER_LOSS, now_ts)
                self.power_last_reminder_at = now_ts

        return events

    def _process_wan(self, now_ts: float, wan_ok: bool) -> List[AlertEvent]:
        '''Apply WAN probe signal to WAN state and emit events if needed.'''
        events: List[AlertEvent] = []

        if wan_ok:
            self.wan_failure_started_at = None

            if self.wan_alerted:
                if self.wan_recovery_started_at is None:
                    self.wan_recovery_started_at = now_ts

                stabilized = (
                    now_ts - self.wan_recovery_started_at
                    >= self.config['wan_restore_stability_seconds']
                )

                if stabilized and self._can_emit(EventKind.WAN_RESTORE, now_ts):
                    events.append(
                        self._new_event(
                            EventKind.WAN_RESTORE,
                            now_ts,
                            self.wan_alert_anchor_at or self.wan_recovery_started_at,
                            'WAN connectivity restored and stabilized.',
                        )
                    )
                    self._record_emit(EventKind.WAN_RESTORE, now_ts)
                    self.wan_alerted = False
                    self.wan_alert_anchor_at = None
                    self.wan_recovery_started_at = None
            else:
                self.wan_recovery_started_at = None

            return events

        self.wan_recovery_started_at = None

        if self.wan_failure_started_at is None:
            self.wan_failure_started_at = now_ts

        if not self.wan_alerted:
            crossed = (
                now_ts - self.wan_failure_started_at
                >= self.config['wan_loss_threshold_seconds']
            )
            if crossed and self._can_emit(EventKind.WAN_LOSS, now_ts):
                events.append(
                    self._new_event(
                        EventKind.WAN_LOSS,
                        now_ts,
                        self.wan_failure_started_at,
                        'WAN connectivity failed past threshold.',
                    )
                )
                self._record_emit(EventKind.WAN_LOSS, now_ts)
                self.wan_alerted = True
                self.wan_alert_anchor_at = self.wan_failure_started_at

        return events

    def evaluate(self, now_ts: float, power_ok: bool, wan_ok: bool) -> List[AlertEvent]:
        '''Run one state-machine cycle and return all emitted events.'''
        events: List[AlertEvent] = []
        events.extend(self._process_power(now_ts, power_ok))
        events.extend(self._process_wan(now_ts, wan_ok))
        return events
