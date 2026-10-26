#!/usr/bin/env python3
"""Send explicitly entered short text to the attached PC via USB HID keyboard."""
from __future__ import annotations

import sys
import time

DEVICE = "/dev/hidg0"
MAX_CHARS = 160
BASE = {chr(ord('a') + i): (0x04 + i, False) for i in range(26)}
BASE.update({c: (0x1e + i, False) for i, c in enumerate('1234567890')})
BASE.update({'\n': (0x28, False), ' ': (0x2c, False), '-': (0x2d, False), '=': (0x2e, False),
             '[': (0x2f, False), ']': (0x30, False), '\\': (0x31, False),
             ';': (0x33, False), "'": (0x34, False), '`': (0x35, False),
             ',': (0x36, False), '.': (0x37, False), '/': (0x38, False)})
SHIFTED = {'!': '1', '@': '2', '#': '3', '$': '4', '%': '5', '^': '6', '&': '7',
           '*': '8', '(': '9', ')': '0', '_': '-', '+': '=', '{': '[', '}': ']',
           '|': '\\', ':': ';', '"': "'", '~': '`', '<': ',', '>': '.', '?': '/'}
RELEASE = bytes(8)


def encode(char: str) -> bytes:
    if 'A' <= char <= 'Z':
        key, _ = BASE[char.lower()]
        shift = True
    elif char in SHIFTED:
        key, _ = BASE[SHIFTED[char]]
        shift = True
    else:
        key, shift = BASE[char]
    return bytes((0x02 if shift else 0, 0, key, 0, 0, 0, 0, 0))


def validate(text: str) -> list[bytes]:
    if not text or len(text) > MAX_CHARS:
        raise ValueError(f'Enter 1..{MAX_CHARS} characters')
    try:
        return [encode(char) for char in text]
    except KeyError as exc:
        raise ValueError('Only US keyboard ASCII text is supported') from exc


def send(text: str, device: str = DEVICE) -> None:
    reports = validate(text)
    with open(device, 'wb', buffering=0) as output:
        try:
            for report in reports:
                output.write(report)
                time.sleep(0.025)
                output.write(RELEASE)
                time.sleep(0.025)
        finally:
            output.write(RELEASE)


if __name__ == '__main__':
    data = sys.stdin.read(MAX_CHARS + 1)
    try:
        send(data)
    except (OSError, ValueError) as exc:
        print(f'HID: {exc}', file=sys.stderr)
        sys.exit(1)
    print(f'Sent {len(data)} characters over USB keyboard')
