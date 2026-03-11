##########################################################################################
#
# Script name: power_detector.py
#
# Description: Detect power loss and send warning SMS notifications.
#
# Author: John Macdonald
#
##########################################################################################

import argparse
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys
import time
from datetime import date

from detector.config import ConfigError, load_config, load_env_file
from detector.models import AlertEvent, EventKind
from detector.notifier import Notifier
from detector.probes import DeviceIdShellyProbe, MockSequenceProbe, ShellyHttpProbe, WanProbe
from detector.state_machine import DetectorStateMachine


# ****************************************************************************************
# Global data and configuration
# ****************************************************************************************
# Set global variables here and log.debug them below

# Logging config
log = logging.getLogger(os.path.basename(sys.argv[0]))
log.setLevel(logging.DEBUG)

formatter = logging.Formatter(
    '%(asctime)-15s [%(funcName)25s:%(lineno)-5s] %(levelname)-8s %(message)s')

# File handler for logging
fh = logging.FileHandler('power-detector.log', mode='a')
fh.setLevel(logging.DEBUG)
fh.setFormatter(formatter)
log.addHandler(fh)  # Add file handler to logger

log.debug('Global data and configuration for this script...')


# ****************************************************************************************
# Exceptions
# ****************************************************************************************

class Error(Exception):
    '''
    Base class for exceptions in this module.
    '''
    pass


class RuntimeConfigError(Error):
    '''
    Raised for runtime config validation and loading failures.
    '''
    def __init__(self, config_path, original_error):
        self.message = f'Failed to load config {config_path}: {original_error}'
        super().__init__(self.message)


# ****************************************************************************************
# Functions
# ****************************************************************************************

def _configure_console_logging(args):
    '''Attach stdout handler with verbosity controlled by CLI flags.'''
    ch = logging.StreamHandler(sys.stdout)
    if args.verbose:
        ch.setLevel(logging.DEBUG)
    elif args.quiet:
        ch.setLevel(logging.ERROR)
    else:
        ch.setLevel(logging.INFO)

    ch.setFormatter(formatter)
    log.addHandler(ch)


def _reconfigure_file_logging(config):
    '''Switch file logging path and rotation after config is loaded.'''
    file_cfg = config.get('logging', {})
    file_path = file_cfg.get('file_path', './power-detector.log')
    max_mb = int(file_cfg.get('max_mb', 10))
    backup_count = int(file_cfg.get('backup_count', 3))

    for handler in list(log.handlers):
        if isinstance(handler, logging.FileHandler):
            log.removeHandler(handler)
            handler.close()

    rotating_handler = RotatingFileHandler(
        file_path,
        maxBytes=max_mb * 1024 * 1024,
        backupCount=backup_count,
    )
    rotating_handler.setLevel(logging.DEBUG)
    rotating_handler.setFormatter(formatter)
    log.addHandler(rotating_handler)


def _make_power_probe(config, args):
    '''Create either real or mock power probe based on CLI flags.'''
    if args.mock_sentinel:
        sequence = config.get('mock', {}).get('sentinel_sequence', 'ok:120,fail:120,ok:120')
        log.info(f'Using mock sentinel probe sequence: {sequence}')
        return MockSequenceProbe(sequence)

    sentinel_cfg = config['sentinel']
    host = str(sentinel_cfg.get('host', '')).strip()
    device_id = str(sentinel_cfg.get('device_id', '')).strip()
    devices_file = str(sentinel_cfg.get('devices_file', '')).strip()
    if not host and (device_id or devices_file):
        if device_id:
            log.info(f'Using device_id-based sentinel resolution for id={device_id}.')
        else:
            log.info(f'Using dynamic device-registry sentinel resolution from {devices_file}.')
        return DeviceIdShellyProbe(config, log)

    return ShellyHttpProbe(
        host=host,
        timeout_seconds=sentinel_cfg.get('timeout_seconds', 2),
    )


def _make_wan_probe(config, args):
    '''Create either real or mock WAN probe based on CLI flags.'''
    if args.mock_wan:
        sequence = config.get('mock', {}).get('wan_sequence', 'ok:300,fail:180,ok:300')
        log.info(f'Using mock WAN probe sequence: {sequence}')
        return MockSequenceProbe(sequence)

    wan_cfg = config['wan_probe']
    return WanProbe(
        dns_targets=wan_cfg.get('dns_targets', []),
        http_targets=wan_cfg.get('http_targets', []),
        timeout_seconds=config.get('sentinel', {}).get('timeout_seconds', 2),
    )


def _power_event_metadata(config, power_probe):
    '''Build structured sentinel metadata for power-related notifications.'''
    if hasattr(power_probe, 'get_target_metadata'):
        metadata = power_probe.get_target_metadata()
        if metadata:
            return metadata

    sentinel_cfg = config.get('sentinel', {})
    metadata = {}
    host = str(sentinel_cfg.get('host', '')).strip()
    device_id = str(sentinel_cfg.get('device_id', '')).strip()
    if host:
        metadata['device_host'] = host
    if device_id:
        metadata['device_id'] = device_id.upper()
    return metadata


def _run_test_notification(config, args):
    '''Send a synthetic test alert and exit with status code.'''
    notifier = Notifier(config, log)
    now_ts = time.monotonic()
    test_event = AlertEvent(
        kind=EventKind.POWER_LOSS,
        started_at=now_ts,
        duration_seconds=0,
        details='Operator-requested test notification.',
        is_reminder=False,
    )

    ok = notifier.notify(test_event, dry_run=args.dry_run_notify)
    if ok:
        log.info('Test notification completed successfully.')
        return 0

    log.error('Test notification failed.')
    return 1


def _auto_load_env(args):
    '''Load dotenv secrets from known local paths without overriding existing env vars.'''
    loaded_total = 0
    config_dir = str(Path(args.config).resolve().parent)
    candidates = [
        os.environ.get('POWER_DETECTOR_ENV_FILE', '').strip(),
        os.path.join(os.getcwd(), '.env'),
        os.path.join(config_dir, '.env'),
    ]

    seen = set()
    for candidate in candidates:
        if not candidate:
            continue
        candidate_path = os.path.abspath(candidate)
        if candidate_path in seen:
            continue
        seen.add(candidate_path)
        loaded = load_env_file(candidate_path, override=False)
        if loaded > 0:
            log.info(f'Loaded {loaded} environment variable(s) from {candidate_path}.')
            loaded_total += loaded

    if loaded_total == 0:
        log.debug('No .env file variables loaded.')


def _loop(config, args):
    '''Execute the detector probe/transition/notify loop.'''
    state_machine = DetectorStateMachine(config)
    notifier = Notifier(config, log)
    power_probe = _make_power_probe(config, args)
    wan_probe = _make_wan_probe(config, args)

    poll_interval = config['poll_interval_seconds']
    startup_sent = False
    startup_enabled = bool(config.get('notification', {}).get('startup_message_enabled', True))

    while True:
        now_ts = time.monotonic()

        power_result = power_probe.check()
        wan_result = wan_probe.check()
        power_metadata = _power_event_metadata(config, power_probe)
        if hasattr(power_probe, 'describe_target'):
            sentinel_identity = power_probe.describe_target()
        else:
            sentinel_cfg = config.get('sentinel', {})
            sentinel_identity = str(sentinel_cfg.get('device_id', '')).strip() or str(
                sentinel_cfg.get('host', '')).strip()

        log.debug(
            f'Probe power_ok={power_result.ok} reason={power_result.reason} '
            f'latency_ms={power_result.latency_ms}')
        log.debug(
            f'Probe wan_ok={wan_result.ok} reason={wan_result.reason} '
            f'latency_ms={wan_result.latency_ms}')

        if not args.oneshot and not startup_sent and startup_enabled and power_result.ok:
            startup_event = AlertEvent(
                kind=EventKind.MONITORING_STARTED,
                started_at=now_ts,
                duration_seconds=0,
                details=(
                    f'Power detected. Monitoring started for sentinel={sentinel_identity}. '
                    f'probe={power_result.reason}'
                ),
                metadata=power_metadata,
            )
            sent = notifier.notify(startup_event, dry_run=args.dry_run_notify)
            if sent:
                startup_sent = True
                log.info('Startup monitoring notification sent.')
            else:
                log.error('Startup monitoring notification failed; will retry next cycle.')

        events = state_machine.evaluate(now_ts, power_result.ok, wan_result.ok)

        if len(events) == 0:
            log.info('No state transition events this cycle.')
        else:
            for event in events:
                if event.kind in (EventKind.POWER_LOSS, EventKind.POWER_RESTORE):
                    event.metadata.update(power_metadata)
                log.info(
                    f'Event kind={event.kind.value} reminder={event.is_reminder} '
                    f'duration={event.duration_seconds}s details={event.details}')
                sent = notifier.notify(event, dry_run=args.dry_run_notify)
                if not sent:
                    log.error(f'Failed to send notification for event {event.kind.value}.')

        if args.oneshot:
            log.info('Oneshot mode complete.')
            return 0

        time.sleep(poll_interval)


# ****************************************************************************************
# Handle the arguments
# ****************************************************************************************
def handle_args():
    '''
    Parse CLI arguments and configure console logging handlers.

    Input:
        None directly; reads flags from sys.argv.

    Output:
        argparse.Namespace containing runtime options.

    Side Effects:
        Attaches a stream handler to the module logger with formatting and
        level derived from the parsed arguments.
    '''

    parser = argparse.ArgumentParser(
        description='Detect power loss from a sentinel IoT device and send SMS alerts.')
    parser.add_argument(
        '-v',
        '--verbose',
        action='store_true',
        help='Enable verbose output to stdout.')
    parser.add_argument(
        '-q',
        '--quiet',
        action='store_true',
        help='Minimal stdout.')
    parser.add_argument(
        '--config',
        required=True,
        help='Path to YAML configuration file.')
    parser.add_argument(
        '--oneshot',
        action='store_true',
        help='Run one probe cycle and exit.')
    parser.add_argument(
        '--test-notify',
        action='store_true',
        help='Send a synthetic notification then exit.')
    parser.add_argument(
        '--mock-sentinel',
        action='store_true',
        help='Use mock sentinel probe sequence from config.mock.sentinel_sequence.')
    parser.add_argument(
        '--mock-wan',
        action='store_true',
        help='Use mock WAN probe sequence from config.mock.wan_sequence.')
    parser.add_argument(
        '--dry-run-notify',
        action='store_true',
        help='Do not send SMTP messages; log payload only.')
    args = parser.parse_args()

    _configure_console_logging(args)

    log.debug('Checking script requirements...')
    if not args.verbose and not args.quiet:
        log.debug('No output level specified. Defaulting to INFO.')

    log.info('++++++++++++++++++++++++++++++++++++++++++++++')
    log.info(f'+  {os.path.basename(sys.argv[0])}')
    log.info(f'+  Python Version: {sys.version.split()[0]}')
    log.info(f'+  Today is: {date.today()}')
    log.info(f'+  Config file: {args.config}')
    log.info('++++++++++++++++++++++++++++++++++++++++++++++')

    return args


# ****************************************************************************************
# Main
# ****************************************************************************************
def main():
    '''
    Entrypoint that wires together dependencies and launches detector loop.

    Output:
        Exit status integer.
    '''
    args = handle_args()
    _auto_load_env(args)

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        raise RuntimeConfigError(args.config, exc) from exc

    _reconfigure_file_logging(config)

    try:
        if args.test_notify:
            return _run_test_notification(config, args)
        return _loop(config, args)
    except KeyboardInterrupt:
        log.info('KeyboardInterrupt received; shutting down.')
        return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except RuntimeConfigError as exc:
        log.error(str(exc))
        print(str(exc), file=sys.stderr)
        sys.exit(2)
