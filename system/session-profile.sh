# Written by Claude 2026-10-08. Installed as /etc/profile.d/j701f-session.sh.
# Until a logind session (elogind/PAM) provides these, point login shells of the
# phone user at the runtime directory made by /sbin/j701f-start and at the
# OpenRC user-session D-Bus (see /etc/user/conf.d/dbus).
if [ "$(id -u)" = 1000 ] && [ -d /run/user/1000 ]; then
    : "${XDG_RUNTIME_DIR:=/run/user/1000}"
    export XDG_RUNTIME_DIR
    [ ! -S "$XDG_RUNTIME_DIR/bus" ] || export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"
fi
