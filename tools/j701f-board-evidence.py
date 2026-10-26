#!/usr/bin/env python3
"""Extract a small, non-identifying hardware manifest from the live DT capture.

Reads local files only. Never copies chosen/bootargs, serial numbers or MACs.
"""
import hashlib
import json
from pathlib import Path
import struct
import tarfile

ROOT = Path(__file__).resolve().parents[1]
CAPTURE = ROOT / 'build/kernel/j701f-live-device-tree.tar.gz'


def cells(data):
    if len(data) % 4:
        raise ValueError('Property is not an array of 32-bit cells')
    return list(struct.unpack('>' + str(len(data) // 4) + 'I', data))


def capture(path):
    with tarfile.open(path) as archive:
        return {m.name.removeprefix('./'): archive.extractfile(m).read()
                for m in archive if m.isfile()}


def manifest(properties):
    def selected(node, names):
        output = {}
        for name in names:
            key = node + '/' + name
            if key not in properties:
                continue
            data = properties[key]
            output[name] = (data.rstrip(b'\0').decode().split('\0')
                            if name in ('compatible', 'regulator-name', 'status',
                                        'samsung,pins', 'method', 'enable-method')
                            else cells(data))
        return output

    phandles = {cells(value)[0]: key.removesuffix('/phandle')
                for key, value in properties.items() if key.endswith('/phandle')}
    banks = {}
    for key, value in properties.items():
        if key.startswith('gpio_keys/button@') and key.endswith('/gpios'):
            handle, pin, vendor_flags = cells(value)
            banks[key.removesuffix('/gpios')] = {
                'bank': phandles[handle].split('/')[-1], 'pin': pin,
                'vendor_flags': vendor_flags,
                'linux_code': cells(properties[key.removesuffix('/gpios') + '/linux,code'])[0]}
    regulator_prefix = 'hsi2c@10510000/s2mpu05_pmic@66/regulators/'
    regulators = {}
    for key in properties:
        if key.startswith(regulator_prefix) and key.endswith('/regulator-name'):
            node = key.removesuffix('/regulator-name')
            regulators[node.split('/')[-1].lower()] = selected(node, (
                'regulator-name', 'regulator-min-microvolt', 'regulator-max-microvolt',
                'regulator-ramp-delay', 'regulator-always-on', 'regulator-boot-on'))
    reservations = {}
    for key, value in properties.items():
        if key.startswith('reserved-memory/') and key.endswith('/reg'):
            reservations[key.split('/')[1]] = cells(value)
    nodes = ('psci', 'dwmmc0@13540000', 'dwmmc1@13550000', 'usb@13600000',
             'usb@13600000/dwc3', 'phy@135c0000', 'uart@13820000',
             'hsi2c@10510000/s2mpu05_pmic@66', 'i2c@13840000/mms_ts@48',
             'mali@11400000')
    return dict(
        model=properties['model'].rstrip(b'\0').decode(),
        memory={key.removesuffix('/reg'): cells(value) for key, value in properties.items()
                if key.startswith('memory@') and key.endswith('/reg')},
        oscillator_hz=cells(properties['fixed-rate-clocks/oscclk/clock-frequency'])[0],
        reservations=reservations, keys=banks, regulators=regulators,
        nodes={node: selected(node, ('compatible', 'reg', 'interrupts', 'method',
                                    'cpu_on', 'cpu_off', 'cpu_suspend')) for node in nodes},
        limits=['Vendor GPIO flags must be translated, not copied into mainline.',
                'Voltage ranges do not establish board rail-to-consumer wiring.',
                'sysfs DT capture cannot reconstruct the original FDT memreserve table.',
                'This is measured board evidence, not proof of a mainline boot.'])


if __name__ == '__main__':
    result = manifest(capture(CAPTURE))
    result['capture_sha256'] = hashlib.sha256(CAPTURE.read_bytes()).hexdigest()
    destination = ROOT / 'kernel/j701f-hardware.json'
    destination.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print('Saved non-identifying board properties:', destination)
