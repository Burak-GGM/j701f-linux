# J701F daily-use application profile

This directory records the owner's application choices for Alpine 3.24 on the
Samsung SM-J701F (`samsung,j7velte`). It is the application layer of the
project, **not** a complete phone installer: it does not write BOOT, RECOVERY,
SYSTEM or USERDATA, provision Wi-Fi, or install the kernel and device services.

On a running J701F Alpine installation with the Alpine repositories configured,
copy this entire directory to the phone, then run:

```sh
sh setup.sh --plan --prune
sudo sh setup.sh --apply --prune
```

The first command shows APK's simulated changes. The second installs the core
apps, removes the optional apps in `prune.txt`, and installs a Koko-only launcher
workaround. Omit `--prune` to keep apps already installed. Use `--development`
to add the compilers, headers, editor and diagnostics in
`optional-development.txt`; those tools remain installed on the owner's phone.
The script checks the device tree before any `--apply` action and refuses other
devices. Re-running it is supported. No personal photos or browser data are
deleted by the script.

Koko 26.04.2 crashes when an image opens in its mobile Kirigami layout on this
device. The wrapper in this directory sets `QT_QUICK_CONTROLS_MOBILE=false` only
for Koko. A synthetic image and a real photo opened successfully after the
workaround; the owner verified the latter on 2026-10-26. To remove the workaround,
delete `/usr/local/bin/koko` only if it still contains the
`J701F_KOKO_WRAPPER` marker.

GNOME Software remains the graphical store, but its scrolling is slow on the
current GPU/GTK path. The current session-level GTK setting avoids black areas;
this profile does not replace it. The store issue and the separate full-device
installation work are tracked in the [userspace reference](../../wiki/reference/userspace.md).
