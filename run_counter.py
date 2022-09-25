#!/usr/bin/env python3

import argparse
import collections
from functools import partial
import http.server
import json
import logging
import logging.handlers
import os
import socketserver
import threading
import time

import serial


DEFAULT_SERIAL_DEVICE = '/dev/ttyACM0'
DEFAULT_STATE_FILE = 'pulse_counter.state'
DEFAULT_LOG_FILE = 'pulse_counter.log'
DEFAULT_PORT = 8000


LOG = logging.getLogger(__name__)


class PulseTelegram(collections.namedtuple('PulseTelegram', [
    'device_id',  # S0 pulse counter device id
    'interval',  # telegram interval
    'pulses',  # list of 5 counts since previous interval
    'pulses_total',  # list of 5 total counts since device boot
])):
    def __repr__(self):
        return f'PulseTelegram(device_id={self.device_id}; interval={self.interval}; pulses={",".join([str(p) for p in self.pulses])}; total={",".join([str(p) for p in self.pulses_total])})'


class CounterStates:
    def __init__(self, path: str):
        self.path = path
        self.states = [0] * 5
        self._lock = threading.Lock()
        self.load_states()

    def load_states(self):
        with self._lock:
            if not os.path.exists(self.path):
                LOG.info('no state recoverd; counters reset')
                return False

            with open(self.path, 'rt') as f:
                line = f.readline().strip().split(',')
                self.states = [int(v) for v in line]
                LOG.info(f'counters initialized at {",".join([str(v) for v in self.states])}')
                return True

    def save_states(self):
        with self._lock:
            try:
                with open(self.path, 'wt') as f:
                    f.write(','.join([str(v) for v in self.states]))
            except Exception as e:
                LOG.warning(f'failed to save counter states: {e}')

    def increment(self, pulses):
        with self._lock:
            for i in range(len(pulses)):
                if pulses[i] > 0:
                    LOG.debug(f'increment counter {i} by {pulses[i]}')
                self.states[i] += pulses[i]

        if sum(pulses) > 0:
            self.save_states()


class Handler(http.server.BaseHTTPRequestHandler):
    def __init__(self, states: CounterStates, *args, **kwargs):
        self.states = states
        super().__init__(*args, **kwargs)

    def do_get_unsafe(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(self.states.states).encode('ascii'))
        else:
            n = self.path[1:]
            if not n.isdigit():
                raise FileNotFoundError(self.path)
            n = int(n)
            if n >= len(self.states.states):
                raise IndexError(n)

            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(str(self.states.states[n]).encode('ascii'))

    def send_error(self, code, message=None, explain=None):
        self.send_response(code)
        self.send_header("Content-type", "application/json")
        self.end_headers()
        if message is not None:
            self.wfile.write(json.dumps({'message': message}).encode('ascii'))
        

    def do_GET(self):
        try:
            self.do_get_unsafe()
        except FileNotFoundError:
            self.send_error(404, 'not found')
        except IndexError:
            self.send_error(400, 'bad index')
        except Exception as e:
            LOG.warning(f'error while handling GET: {e}', e)
            self.send_error(500, 'error')


def read_serial(dev: serial.Serial, states: CounterStates):
    while True:
        line = dev.readline().decode('ascii').rstrip()
        elems = line.split(':')
        if len(elems) == 2 and elems[0] == '/42001':
            LOG.debug('header received')
        else:
            assert elems[0] == 'ID', f'illegal input: {line}'
            assert len(elems) == 19, f'illegal input: {line}'
            device_id = int(elems[1])
            interval = int(elems[3])
            pulses = [int(elems[5 + i*3]) for i in range(5)]
            pulses_total = [int(elems[6 + i*3]) for i in range(5)]
            telegram = PulseTelegram(device_id, interval, pulses, pulses_total)
            states.increment(telegram.pulses)


def run_serial(device: str, states: CounterStates):
    while True:
        if not os.path.exists(device):
            LOG.warning(f'not found: {device} (will keep trying)')
            while not os.path.exists(device):
                time.sleep(1)

        try:
            with serial.Serial(device, baudrate=9600, bytesize=serial.SEVENBITS, parity=serial.PARITY_EVEN, stopbits=serial.STOPBITS_ONE) as ser:
                read_serial(ser, states)
        except KeyboardInterrupt:
            break
        except serial.serialutil.SerialException as e:
            LOG.warning(f'serial error: {e} (will try again in 10 seconds)')
            time.sleep(10)
        except Exception as e:
            LOG.warning(f's0 counter error {e} (will try again in 10 seconds)', e)
            time.sleep(10)


if __name__ == '__main__':
    default_state_file = os.path.join(os.path.dirname(__file__), DEFAULT_STATE_FILE)
    default_log_file = os.path.join(os.path.dirname(__file__), DEFAULT_LOG_FILE)

    parser = argparse.ArgumentParser(description='Pulse counter service.')
    parser.add_argument('--device', metavar='DEVICE', default=DEFAULT_SERIAL_DEVICE, help=f'pulse counter serial device (default: {DEFAULT_SERIAL_DEVICE})')
    parser.add_argument('--state', metavar='PATH', default=default_state_file, help=f'path to persistent state file (default: {default_state_file})')
    parser.add_argument('--port', metavar='PORT', default=DEFAULT_PORT, type=int, help=f'port for rest API to listen on (default: {DEFAULT_PORT})')
    parser.add_argument('--logfile', metavar='PATH', default=default_log_file, help=f'log file (default: {default_log_file})')
    args = parser.parse_args()

    logging.getLogger().setLevel(logging.DEBUG)
    log_formatter = logging.Formatter("%(asctime)s [%(levelname)-4.4s]  %(message)s")

    file_handler = logging.handlers.RotatingFileHandler(args.logfile, maxBytes=1024*1024, backupCount=3)
    file_handler.setFormatter(log_formatter)
    file_handler.setLevel(logging.WARN)
    logging.getLogger().addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_formatter)
    file_handler.setLevel(logging.INFO)
    logging.getLogger().addHandler(console_handler)

    LOG.info('launching pulse counter service')
    states = CounterStates(args.state)

    t1 = threading.Thread(target=run_serial, args=(args.device, states))
    t1.start()

    handler = partial(Handler, states)
    with socketserver.TCPServer(("", args.port), handler) as httpd:
        LOG.info(f'serving at port {args.port}')
        httpd.serve_forever()
