##########################################################################################
#
# Script name: notifier.py
#
# Description: SMTP email-to-SMS notifier for detector events.
#
# Author: John Macdonald
#
##########################################################################################

import logging
import os
import smtplib
import socket
import time
from email.message import EmailMessage
from typing import Dict, List

from detector.config import resolve_recipient_address
from detector.models import AlertEvent


class Notifier:
    '''Handles event filtering and SMTP delivery for alert events.'''

    def __init__(self, config: Dict, logger: logging.Logger):
        self.config = config
        self.log = logger

    def _event_enabled(self, event_kind: str) -> bool:
        enabled = self.config['notification'].get('events_enabled', [])
        return event_kind in enabled

    def _recipient_addresses(self) -> List[str]:
        recipients = self.config['notification'].get('recipients', [])
        addresses = []
        for recipient in recipients:
            addresses.append(resolve_recipient_address(recipient))
        return addresses

    def _compose_message(self, event: AlertEvent, host_label: str) -> str:
        reminder_suffix = ' REMINDER' if event.is_reminder else ''
        return (
            f'[{event.kind.value.upper()}{reminder_suffix}] '
            f'host={host_label} '
            f'duration={event.duration_seconds}s '
            f'details={event.details}'
        )

    def _send_email(self, subject: str, body: str, recipients: List[str], dry_run: bool) -> bool:
        smtp_cfg = self.config['notification']['smtp']

        if dry_run:
            self.log.info(f'DRY RUN notify subject={subject} recipients={recipients} body={body}')
            return True

        password_env_var = smtp_cfg['password_env_var']
        password = os.environ.get(password_env_var)
        if not password:
            self.log.error(f'SMTP password env var {password_env_var} is not set.')
            return False

        max_retries = smtp_cfg['max_retries']
        backoffs = smtp_cfg['retry_backoff_seconds']

        msg = EmailMessage()
        msg['From'] = smtp_cfg['from_address']
        msg['To'] = ','.join(recipients)
        msg['Subject'] = subject
        msg.set_content(body)

        for attempt in range(1, max_retries + 1):
            try:
                with smtplib.SMTP(
                    smtp_cfg['host'],
                    smtp_cfg['port'],
                    timeout=smtp_cfg['timeout_seconds'],
                ) as smtp:
                    if smtp_cfg.get('use_starttls', True):
                        smtp.starttls()
                    smtp.login(smtp_cfg['username'], password)
                    smtp.send_message(msg)
                    self.log.info(f'Notification sent on attempt {attempt}.')
                    return True
            except (smtplib.SMTPException, OSError, socket.error) as exc:
                self.log.error(f'Notification attempt {attempt} failed: {exc}')
                if attempt < max_retries:
                    backoff = backoffs[min(attempt - 1, len(backoffs) - 1)]
                    time.sleep(backoff)

        return False

    def notify(self, event: AlertEvent, dry_run: bool = False) -> bool:
        '''Send one event notification if enabled and supported by config.'''
        if not self.config['notification'].get('enabled', True):
            self.log.debug('Notification disabled; event suppressed.')
            return True

        if not self._event_enabled(event.kind.value):
            self.log.debug(f'Event kind {event.kind.value} disabled; event suppressed.')
            return True

        recipients = self._recipient_addresses()
        host_label = socket.gethostname()
        subject = f'Power Detector {event.kind.value}'
        body = self._compose_message(event, host_label)
        return self._send_email(subject, body, recipients, dry_run)
