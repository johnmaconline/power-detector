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
from urllib.parse import urljoin
from email.message import EmailMessage
from typing import Dict, List

import requests

from detector.config import resolve_recipient_address, resolve_recipient_phone
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

    def _recipient_phones(self) -> List[str]:
        recipients = self.config['notification'].get('recipients', [])
        numbers = []
        for recipient in recipients:
            numbers.append(resolve_recipient_phone(recipient))
        return numbers

    def _compose_message(self, event: AlertEvent, host_label: str) -> str:
        reminder_suffix = ' REMINDER' if event.is_reminder else ''
        parts = [
            f'[{event.kind.value.upper()}{reminder_suffix}]',
            f'host={host_label}',
        ]

        device_name = str(event.metadata.get('device_name', '')).strip()
        device_id = str(event.metadata.get('device_id', '')).strip()
        device_host = str(event.metadata.get('device_host', '')).strip()

        if device_name:
            parts.append(f'device={device_name}')
        if device_id:
            parts.append(f'device_id={device_id}')
        if device_host:
            parts.append(f'device_host={device_host}')
        monitored_devices = str(event.metadata.get('monitored_devices', '')).strip()
        up_devices = str(event.metadata.get('up_devices', '')).strip()
        down_devices = str(event.metadata.get('down_devices', '')).strip()
        if monitored_devices:
            parts.append(f'monitored_devices={monitored_devices}')
        if up_devices:
            parts.append(f'up_devices={up_devices}')
        if down_devices:
            parts.append(f'down_devices={down_devices}')

        parts.extend([
            f'duration={event.duration_seconds}s',
            f'details={event.details}',
        ])
        return ' '.join(parts)

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

    def _send_twilio_sms(self, body: str, recipients: List[str], dry_run: bool) -> bool:
        twilio_cfg = self.config['notification'].get('twilio', {})
        account_sid = str(twilio_cfg.get('account_sid', '')).strip()
        auth_env_var = str(twilio_cfg.get('auth_token_env_var', '')).strip()
        from_number = str(twilio_cfg.get('from_number', '')).strip()
        service_sid = str(twilio_cfg.get('messaging_service_sid', '')).strip()

        token = os.environ.get(auth_env_var)
        if not token and not dry_run:
            self.log.error(f'Twilio auth token env var {auth_env_var} is not set.')
            return False

        if dry_run:
            self.log.info(f'DRY RUN Twilio notify recipients={recipients} body={body}')
            return True

        max_retries = int(twilio_cfg.get('max_retries', 3))
        backoffs = twilio_cfg.get('retry_backoff_seconds', [2, 5, 10])
        timeout_seconds = int(twilio_cfg.get('timeout_seconds', 10))
        url = f'https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json'

        all_sent = True
        for recipient in recipients:
            sent_for_recipient = False
            for attempt in range(1, max_retries + 1):
                payload = {
                    'To': recipient,
                    'Body': body,
                }
                if service_sid:
                    payload['MessagingServiceSid'] = service_sid
                else:
                    payload['From'] = from_number

                try:
                    response = requests.post(
                        url,
                        data=payload,
                        auth=(account_sid, token),
                        timeout=timeout_seconds,
                    )
                    if response.status_code in (200, 201):
                        self.log.info(
                            f'Twilio notification sent to {recipient} on attempt {attempt}.')
                        sent_for_recipient = True
                        break

                    self.log.error(
                        f'Twilio send failed for {recipient} attempt {attempt}: '
                        f'HTTP {response.status_code} {response.text[:240]}')
                except requests.RequestException as exc:
                    self.log.error(
                        f'Twilio send exception for {recipient} attempt {attempt}: {exc}')

                if attempt < max_retries:
                    backoff = backoffs[min(attempt - 1, len(backoffs) - 1)]
                    time.sleep(backoff)

            if not sent_for_recipient:
                all_sent = False

        return all_sent

    def _send_ntfy_push(self, title: str, body: str, dry_run: bool) -> bool:
        ntfy_cfg = self.config['notification'].get('ntfy', {})
        server_url = str(ntfy_cfg.get('server_url', 'https://ntfy.sh')).rstrip('/') + '/'
        topic = str(ntfy_cfg.get('topic', '')).strip()
        timeout_seconds = int(ntfy_cfg.get('timeout_seconds', 10))
        token_env_var = str(ntfy_cfg.get('token_env_var', '')).strip()
        default_priority = str(ntfy_cfg.get('default_priority', 'default'))
        default_tags = ntfy_cfg.get('default_tags', [])

        if dry_run:
            self.log.info(
                f'DRY RUN ntfy notify topic={topic} title={title} body={body}')
            return True

        headers = {
            'Title': title,
            'Priority': default_priority,
        }
        if isinstance(default_tags, list) and len(default_tags) > 0:
            headers['Tags'] = ','.join(str(tag) for tag in default_tags)

        if token_env_var:
            token = os.environ.get(token_env_var)
            if not token:
                self.log.error(f'ntfy token env var {token_env_var} is not set.')
                return False
            headers['Authorization'] = f'Bearer {token}'

        url = urljoin(server_url, topic)

        try:
            response = requests.post(
                url,
                data=body.encode('utf-8'),
                headers=headers,
                timeout=timeout_seconds,
            )
            if response.status_code in (200, 201):
                self.log.info(f'ntfy notification sent to topic={topic}.')
                return True

            self.log.error(
                f'ntfy send failed: HTTP {response.status_code} {response.text[:240]}')
            return False
        except requests.RequestException as exc:
            self.log.error(f'ntfy send exception: {exc}')
            return False

    def notify(self, event: AlertEvent, dry_run: bool = False) -> bool:
        '''Send one event notification if enabled and supported by config.'''
        if not self.config['notification'].get('enabled', True):
            self.log.debug('Notification disabled; event suppressed.')
            return True

        if not self._event_enabled(event.kind.value):
            self.log.debug(f'Event kind {event.kind.value} disabled; event suppressed.')
            return True

        transport = self.config['notification'].get('transport')
        host_label = socket.gethostname()
        title = f'Power Detector {event.kind.value}'
        body = self._compose_message(event, host_label)

        if transport == 'ntfy_push':
            return self._send_ntfy_push(title, body, dry_run)

        if transport == 'twilio_sms':
            recipients = self._recipient_phones()
            return self._send_twilio_sms(body, recipients, dry_run)

        recipients = self._recipient_addresses()
        return self._send_email(title, body, recipients, dry_run)
