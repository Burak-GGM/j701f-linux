"""Bounded local diagnostics for the J701F touch toolbox."""
from __future__ import annotations

import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import time

IFACE = "wlan0"
CAPTURE_DIR = Path.home() / "j701f" / "captures"
ADDRESS_RE = re.compile(r"(?:\d{1,3}\.){3}\d{1,3}$")


def run_readonly(argv: list[str], timeout: int = 5) -> str:
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return str(exc)
    return (proc.stdout + proc.stderr).strip()


def local_network() -> str | None:
    """Bound scanning to the directly attached IPv4 /24, even on a larger LAN."""
    try:
        raw = subprocess.run(["ip", "-j", "-4", "addr", "show", "dev", IFACE],
                             capture_output=True, text=True, check=True, timeout=5)
        for item in json.loads(raw.stdout):
            for addr in item.get("addr_info", []):
                if addr.get("family") != "inet" or addr.get("scope") != "global":
                    continue
                ip = ipaddress.IPv4Address(addr["local"])
                if ip.is_loopback or ip.is_link_local or ip.is_multicast:
                    continue
                prefix = max(24, min(32, int(addr["prefixlen"])))
                return str(ipaddress.ip_network(f"{ip}/{prefix}", strict=False))
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pass
    return None


def status() -> str:
    network = local_network() or "offline"
    commands = [
        ("IP", ["ip", "-brief", "-4", "addr", "show", "dev", IFACE]),
        ("Gateway", ["ip", "route", "show", "default"]),
        ("Wi-Fi", ["nmcli", "-t", "-f", "IN-USE,SSID,SIGNAL,SECURITY", "device", "wifi", "list", "ifname", IFACE, "--rescan", "no"]),
        ("Bluetooth", ["bluetoothctl", "list"]),
        ("USB", ["ls", "/sys/kernel/config/usb_gadget/j701f_diagnostic/configs/c.1"]),
    ]
    lines = [f"Local scan scope: {network}"]
    for label, argv in commands:
        lines.extend(("", label + ":", run_readonly(argv)))
    return "\n".join(lines)


def capture_path() -> Path:
    CAPTURE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(CAPTURE_DIR, 0o700)
    return CAPTURE_DIR / time.strftime("wlan0-%Y%m%d-%H%M%S.pcap")


def action(name: str, target: str | None = None) -> tuple[list[str], int, str]:
    """Return fixed argv, runtime limit, and UI description. No shell is used."""
    if name == "lan":
        subnet = local_network()
        if subnet is None:
            raise ValueError("Wi-Fi has no local IPv4 address")
        return (["nmap", "-sn", "-n", "--max-retries", "1", "-e", IFACE, subnet],
                90, f"Discovering hosts on {subnet}")
    if name == "ports":
        subnet = local_network()
        if subnet is None or target is None:
            raise ValueError("Connect to Wi-Fi and enter a host IP")
        try:
            address = ipaddress.IPv4Address(target.strip())
            if address not in ipaddress.IPv4Network(subnet):
                raise ValueError("Host is outside this Wi-Fi subnet")
        except ipaddress.AddressValueError as exc:
            raise ValueError("Enter an IPv4 address") from exc
        return (["nmap", "-sT", "-sV", "--version-light", "-n", "-Pn",
                 "--max-retries", "1", "--top-ports", "20", "--host-timeout", "25s",
                 str(address)], 35, f"Checking 20 common TCP ports on {address}")
    if name == "wifi":
        return (["nmcli", "-f", "IN-USE,SSID,SIGNAL,CHAN,SECURITY", "device", "wifi", "list", "ifname", IFACE, "--rescan", "yes"],
                30, "Scanning nearby Wi-Fi networks")
    if name == "bluetooth":
        return (["bluetoothctl", "--timeout", "12", "scan", "on"],
                18, "Discovering nearby Bluetooth devices for 12 seconds")
    if name == "hid-type":
        return (["sudo", "-n", "timeout", "18", "python3", str(Path(__file__).with_name("hid-send.py"))],
                20, "Typing explicitly entered text over USB keyboard")
    if name in ("network-on", "network-off", "hid-on", "hid-off"):
        return (["sudo", "-n", "sh", str(Path(__file__).with_name("usb-profile.sh")), name],
                20, f"Changing USB function: {name}")
    if name == "capture":
        path = capture_path()
        return (["sudo", "-n", "timeout", "115", "tcpdump", "-Z", "burak-alpine", "-i", IFACE,
                 "-p", "-s", "256", "-c", "200", "-w", str(path)],
                120, f"Saving up to 200 packets to {path}")
    raise ValueError("Unknown action")
