#!/bin/sh
# Release-only wrapper: keep NetworkManager available while the owner adds
# the first Wi-Fi connection. The legacy supervisor remains the fallback on
# the 3.18 kernel and for systems without the persistent marker.
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
if [ -e /etc/j701f-wifi-nm-persistent ] &&
   command -v NetworkManager >/dev/null 2>&1 &&
   [ "${J701F_WIFI_FORCE_LEGACY:-0}" != 1 ]; then
    case "$(uname -r)" in 3.18.*) ;; *)
        mkdir -p /run/j701f-wifi
        ip link set lo up
        if rc-service networkmanager start >> /run/j701f-wifi/nm-persistent.log 2>&1; then
            time_sync_started=no
            while rc-service networkmanager status >/dev/null 2>&1; do
                if [ "$time_sync_started" = no ] &&
                   ip -4 addr show dev wlan0 2>/dev/null | grep -q 'inet '; then
                    time_sync_started=yes
                    ( timeout 90 busybox ntpd -n -q -p 0.pool.ntp.org -p time.cloudflare.com &&
                      hwclock -w -u ) > /run/j701f-wifi/time.log 2>&1 &
                fi
                sleep 10
            done
            echo 'NetworkManager stopped; init will restart Wi-Fi supervisor' \
                >> /run/j701f-wifi/nm-persistent.log
            sleep 5
            exit 1
        fi
        ;;
    esac
fi
exec /sbin/j701f-wifi-classic
