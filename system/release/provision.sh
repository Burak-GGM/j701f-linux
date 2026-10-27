#!/bin/sh
# Populate an offline AArch64 Alpine root. Run as root in an Alpine build
# container after apk --arch aarch64 --scripts=false has installed packages.
set -eu
root=${1:?offline root path required}
src=${2:?project source path required}
[ -d "$root/etc" ] && [ -f "$root/etc/alpine-release" ] || exit 1
[ ! -e "$root/etc/j701f-system-version" ] || { echo 'Root already provisioned' >&2; exit 1; }

copy() {
    from=$1; to=$2; mode=${3:-755}
    install -D -m "$mode" "$src/$from" "$root/$to"
}
write() {
    path=$1; mode=$2; shift 2
    mkdir -p "$(dirname "$root/$path")"
    printf '%s\n' "$@" > "$root/$path"
    chmod "$mode" "$root/$path"
}
link_service() {
    level=$1; service=$2
    [ -e "$root/etc/init.d/$service" ] || { echo "Missing service: $service" >&2; exit 1; }
    mkdir -p "$root/etc/runlevels/$level"
    ln -s "/etc/init.d/$service" "$root/etc/runlevels/$level/$service"
}
add_group() {
    name=$1; gid=$2; members=${3:-}
    grep -q "^$name:" "$root/etc/group" && return
    printf '%s:x:%s:%s\n' "$name" "$gid" "$members" >> "$root/etc/group"
}
add_user() {
    name=$1; uid=$2; gid=$3; home=$4; shell=$5; password=${6-!}
    grep -q "^$name:" "$root/etc/passwd" && return
    printf '%s:x:%s:%s::%s:%s\n' "$name" "$uid" "$gid" "$home" "$shell" >> "$root/etc/passwd"
    # Empty last-change field: no password ageing. A 0 there means "change the
    # password now"; with it SDDM's autologin failed on the first hardware run.
    printf '%s:%s::0:99999:7:::\n' "$name" "$password" >> "$root/etc/shadow"
}
add_member() {
    name=$1; member=$2
    # All entries added here have an empty initial member list. Existing
    # Alpine groups are amended without duplicating the member.
    awk -F: -v n="$name" -v m="$member" 'BEGIN {OFS=":"}
      $1==n { split($4,a,","); found=0; for(i in a) if(a[i]==m) found=1;
              if(!found) $4=($4=="" ? m : $4 "," m) } { print }' \
      "$root/etc/group" > "$root/etc/group.new"
    mv "$root/etc/group.new" "$root/etc/group"
}

# Alpine APK post-install scripts cannot run while cross-installing AArch64
# packages from an x86 build host. Provision the service identities explicitly.
add_group burak-alpine 1000
add_group avahi 86 avahi
add_group messagebus 101 messagebus
add_group seat 102 burak-alpine
add_group pipewire 103
add_group plugdev 104
add_group sddm 105
add_group rtkit 106 rtkit
add_group polkitd 107 polkitd
add_group geoclue 108 geoclue
add_group feedbackd 109
add_group dnsmasq 110 dnsmasq
add_user burak-alpine 1000 1000 /home/burak-alpine /bin/sh ''
add_user avahi 86 86 /dev/null /sbin/nologin
add_user messagebus 100 101 /dev/null /sbin/nologin
add_user sddm 101 27 /var/lib/sddm /sbin/nologin
add_user rtkit 102 106 /dev/null /sbin/nologin
add_user polkitd 103 107 /var/empty /sbin/nologin
add_user geoclue 104 108 /var/lib/geoclue /sbin/nologin
add_user dnsmasq 105 110 /dev/null /sbin/nologin
for group in video input audio seat plugdev; do add_member "$group" burak-alpine; done
add_member video sddm
chmod 644 "$root/etc/group" "$root/etc/passwd"
# apk --no-scripts extracted these before their groups existed and left them
# root-owned: D-Bus could then not start wpa_supplicant and polkitd could not
# read its rules (first hardware run, 2026-10-27).
# Group numbers come from the target's own group file, not the build container's.
target_gid() { awk -F: -v n="$1" '$1==n {print $3}' "$root/etc/group"; }
chgrp "$(target_gid messagebus)" "$root/usr/libexec/dbus-daemon-launch-helper"
chmod 4750 "$root/usr/libexec/dbus-daemon-launch-helper"
chgrp "$(target_gid polkitd)" "$root/etc/polkit-1/rules.d"
chmod 750 "$root/etc/polkit-1/rules.d"
chgrp shadow "$root/etc/shadow"
chmod 640 "$root/etc/shadow"

# These identities and the ext4 UUID are checked before the BOOT loader
# mounts USERDATA writable. Do not change them without a BOOT migration.
write etc/j701f-root 644 J701F_ALPINE_ROOT_V1
write etc/j701f-system-version 644 BURAK_ALPINE_0_1
write etc/hostname 644 burak-linux
copy system/release/fstab etc/fstab 644
write etc/j701f-wifi-nm 644 'NetworkManager owns wlan0 on mainline.'
write etc/j701f-wifi-nm-persistent 644 'Keep NetworkManager running while Wi-Fi is unconfigured.'
write etc/j701f-netguard-off 644 'Fresh installations must boot without saved Wi-Fi credentials.'
write etc/wpa_supplicant/wlan0.conf 600 'ctrl_interface=/run/wpa_supplicant' 'update_config=0'
write etc/resolv.conf 644 'nameserver 1.1.1.1'
write etc/apk/repositories 644 \
    'https://dl-cdn.alpinelinux.org/alpine/v3.24/main' \
    'https://dl-cdn.alpinelinux.org/alpine/v3.24/community'
write usr/share/glib-2.0/schemas/99_j701f_feedbackd.gschema.override 644 \
    '[org.sigxcpu.feedbackd]' "profile='quiet'"

copy system/start sbin/j701f-start
copy system/openrc-runlevel sbin/j701f-openrc
copy system/display-select sbin/j701f-display
copy system/netguard sbin/j701f-netguard
copy system/wifi sbin/j701f-wifi-classic
copy system/release/wifi.sh sbin/j701f-wifi
copy system/wifi-dhcp sbin/j701f-wifi-dhcp
copy system/sshd sbin/j701f-sshd
copy system/usb-shell bin/usb-shell
copy ramdisk/bin/usb-debug bin/usb-debug
copy system/display-status bin/display-status
copy ramdisk/bin/ondevice-terminal bin/ondevice-terminal
copy ramdisk/bin/fb-heartbeat bin/fb-heartbeat
copy system/inittab etc/inittab 644
copy ramdisk/etc/usb-baseline.conf etc/usb-baseline.conf 644
copy system/sshd-config etc/ssh/sshd_config.d/00-j701f.conf 644
copy system/sudoers etc/sudoers.d/j701f 440
copy system/session-profile.sh etc/profile.d/j701f-session.sh 644
copy system/sddm-autologin.conf etc/sddm.conf.d/10-j701f-autologin.conf 644
copy system/polkit/49-j701f.rules etc/polkit-1/rules.d/49-j701f.rules 644
copy system/apps/koko-wrapper usr/local/bin/koko
copy system/display-native/switch.sh usr/local/sbin/j701f-display-switch
copy system/display-native/j701f-display.initd etc/init.d/j701f-display
copy system/usb-mtp/start.sh usr/local/sbin/j701f-usb-mtp
copy system/usb-mtp/umtprd.conf etc/umtprd/umtprd.conf 644
copy system/release/j701f-usb-mtp.start etc/local.d/j701f-usb-mtp.start
chmod 700 "$root/etc/umtprd"
copy system/release/firstboot.sh usr/local/sbin/j701f-release-firstboot
copy system/release/j701f-release-setup.initd etc/init.d/j701f-release-setup

for item in \
    audio-autoload:j701f-audio.start \
    tune:j701f-tune.start \
    gpufreq-limit:j701f-gpufreq.start \
    stamps-stop:j701f-stamps.stop; do
    copy "system/${item%%:*}" "etc/local.d/${item#*:}"
done
copy system/inputboost usr/local/sbin/j701f-inputboost
copy system/earlyoom.conf etc/default/earlyoom 644
# [Sleep] settings are read from sleep.conf.d only; in logind.conf.d they are
# ignored and PowerDevil suspended the phone after 15 idle minutes, with no key
# to wake it (first hardware run, 2026-10-27).
copy system/elogind-nosleep.conf etc/elogind/sleep.conf.d/10-j701f-nosleep.conf 644
copy system/elogind-powerkey.conf etc/elogind/logind.conf.d/j701f-powerkey.conf 644
copy system/accel-udev.rules etc/udev/rules.d/83-j701f-accel.rules 644
copy system/touchkey.hwdb etc/udev/hwdb.d/83-j701f-touchkey.hwdb 644
copy system/video-udev.rules etc/udev/rules.d/83-j701f-video.rules 644
copy system/flashlight-udev.rules etc/udev/rules.d/83-j701f-flashlight.rules 644
copy system/camera/83-j701f-camera.rules etc/udev/rules.d/83-j701f-camera.rules 644
copy system/session/gtk-env.sh home/burak-alpine/.config/plasma-workspace/env/j701f-gtk.sh 644
copy system/session/webengine-env.sh home/burak-alpine/.config/plasma-workspace/env/j701f-webengine.sh 644
copy system/session/freezer/freezer.js home/burak-alpine/.local/lib/j701f-freezer/freezer.js 644
copy system/session/freezer/j701f-freezer.py home/burak-alpine/.local/lib/j701f-freezer/j701f-freezer.py
copy system/session/freezer/j701f-freezer.conf home/burak-alpine/.config/j701f-freezer.conf 644
copy system/session/freezer/j701f-freezer.desktop home/burak-alpine/.config/autostart/j701f-freezer.desktop 644
copy system/release/kscreenlockerrc home/burak-alpine/.config/kscreenlockerrc 644
copy system/camera/j701f-camera usr/local/bin/j701f-camera
copy system/camera/j701f-photo usr/local/bin/j701f-photo
copy system/camera/j701f-camera-front.desktop usr/local/share/applications/j701f-camera-front.desktop 644
copy system/camera/j701f-camera-rear.desktop usr/local/share/applications/j701f-camera-rear.desktop 644

for level_service in \
    sysinit:cgroups sysinit:devfs sysinit:procfs sysinit:sysfs \
    sysinit:udev sysinit:udev-trigger \
    boot:loopback boot:localmount boot:machine-id boot:seedrng boot:sysctl boot:j701f-release-setup \
    default:apk-polkit-server default:bluetooth default:dbus \
    default:earlyoom default:elogind default:iio-sensor-proxy \
    default:j701f-display default:local default:polkit default:sddm \
    shutdown:killprocs shutdown:mount-ro; do
    link_service "${level_service%%:*}" "${level_service#*:}"
done
mkdir -p "$root/home/burak-alpine/.config/rc/runlevels/default"
for service in dbus pipewire pipewire-pulse wireplumber; do
    [ -e "$root/etc/user/init.d/$service" ] || { echo "Missing user service: $service" >&2; exit 1; }
    ln -s "/etc/user/init.d/$service" \
        "$root/home/burak-alpine/.config/rc/runlevels/default/$service"
done
mkdir -p "$root"/dev/pts "$root"/proc "$root"/sys "$root"/run "$root"/tmp \
         "$root"/media/sdcard \
         "$root"/var/lib/sddm "$root"/var/lib/geoclue "$root"/var/empty \
         "$root"/home/burak-alpine/Pictures "$root"/home/burak-alpine/.ssh \
         "$root"/home/burak-alpine/.local/state "$root"/home/burak-alpine/j701f/modules
chmod 1777 "$root/tmp"
chmod 700 "$root/root" "$root/home/burak-alpine/.ssh"
chown -R 1000:1000 "$root/home/burak-alpine"
chown 101:27 "$root/var/lib/sddm"
chmod 2755 "$root/var/lib/sddm"   # as the sddm package sets it
chown 104:108 "$root/var/lib/geoclue"

# No Wi-Fi profile, SSH key, password, machine-id or host key is copied from the
# developer's phone. OpenSSH creates its unique host key on first boot.
: > "$root/etc/machine-id"
rm -f "$root/etc/ssh/ssh_host_"* "$root/var/lib/dbus/machine-id"
echo 'PROVISIONED_J701F_RELEASE_ROOT'
