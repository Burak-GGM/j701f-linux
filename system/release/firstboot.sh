#!/bin/sh
# Cross-architecture APK installation deliberately skips target postinstall
# scripts. Rebuild machine-local caches on the first real AArch64 boot.
set -u
stamp=/var/lib/j701f-release-firstboot.done
[ ! -e "$stamp" ] || exit 0
log=/var/log/j701f-release-firstboot.log
state=/var/lib/j701f-release-firstboot
mkdir -p /var/lib /var/log "$state"
exec >>"$log" 2>&1
echo "J701F release first boot: $(date -u)"
failed=0
run() {
    key=$1; shift
    [ ! -e "$state/$key.ok" ] || return 0
    command -v "$1" >/dev/null 2>&1 || { echo "Missing: $1"; return 0; }
    tries=0
    [ ! -f "$state/$key.tries" ] || tries=$(cat "$state/$key.tries")
    if [ "$tries" -ge 3 ]; then
        echo "Skipped after three failed boots: $key"
        return 0
    fi
    tries=$((tries + 1))
    printf '%s\n' "$tries" > "$state/$key.tries"
    echo "+ $*"
    if "$@"; then
        : > "$state/$key.ok"
    else
        failed=1
        echo "Failed on attempt $tries/3: $key"
    fi
}
# Unique machine identity and certificates must exist before D-Bus or HTTPS.
run machine-id dbus-uuidgen --ensure=/etc/machine-id
run certificates update-ca-certificates
run glib-schemas glib-compile-schemas /usr/share/glib-2.0/schemas
run gio-modules gio-querymodules /usr/lib/gio/modules
run pixbuf gdk-pixbuf-query-loaders --update-cache
run gtk-input gtk-query-immodules-3.0 --update-cache
run mime update-mime-database /usr/share/mime
run appstream appstreamcli refresh-cache --force
run fonts fc-cache -f
run input-hwdb udevadm hwdb --update
run input-trigger udevadm trigger --subsystem-match=input
for icon_dir in /usr/share/icons/*; do
    [ -d "$icon_dir" ] && [ -f "$icon_dir/index.theme" ] || continue
    run "icon-${icon_dir##*/}" gtk-update-icon-cache -f "$icon_dir"
done
if [ "$failed" -eq 0 ]; then
    : > "$stamp"
    echo 'J701F release first boot: complete'
    exit 0
fi
echo 'J701F release first boot: some caches failed; retry on next boot'
exit 1
