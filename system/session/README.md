Written by Claude 2026-10-10. Per-user session settings installed for the optimisation goal
(see wiki/reference/performance.md). Each file here is copied to the path in its first line.

freezer/ is the background-application freezer (stops applications that stay out of the
foreground, continues them on activation). Install: j701f-freezer.py and freezer.js to
~/.local/lib/j701f-freezer/, j701f-freezer.desktop to ~/.config/autostart/, j701f-freezer.conf
to ~/.config/. Needs the packages py3-dbus and py3-gobject3. Log: ~/.local/state/j701f-freezer.log

VLC hardware decoding is one line in ~/.config/vlc/vlcrc: avcodec-codec=h264_v4l2m2m (the
shipped file has it commented out as "#avcodec-codec="). Backup of the file before the change:
~/.config/vlc/vlcrc.claude-backup-hwdec

Angelfish launcher override: ~/.local/share/applications/org.kde.angelfish.desktop is a copy of
/usr/share/applications/org.kde.angelfish.desktop with
Exec=env QSG_RENDER_LOOP=basic angelfish %u
(start-up 6.0-6.3 s -> 5.5 s, scrolling unchanged; see wiki/reference/performance.md).
