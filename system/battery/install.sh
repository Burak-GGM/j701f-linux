#!/bin/sh
# Written by Claude 2026-10-13. Run ON THE PHONE, once, to make the battery
# helper a boot service (it has not been run: installing a boot service waits
# for the owner's yes):
#     sudo sh ~/j701f/battery/install.sh
# Undo: sudo rc-update del j701f-battery default; sudo rc-service j701f-battery stop;
#       sudo rm /etc/init.d/j701f-battery /usr/local/sbin/j701f-battery
set -e
[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 1; }
D=$(dirname "$(readlink -f "$0")")
command -v i2cset >/dev/null || apk add i2c-tools
install -m 755 "$D/j701f-battery" /usr/local/sbin/j701f-battery
install -m 755 "$D/j701f-battery.initd" /etc/init.d/j701f-battery
# a copy started by hand would fight the service over the same register
pkill -f 'j701f/battery/j701f-battery' 2>/dev/null || true
rc-update add j701f-battery default
rc-service j701f-battery restart
rc-service j701f-battery status
