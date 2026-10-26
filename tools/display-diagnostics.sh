#!/bin/sh
# Read-only runtime display report; executed through the existing USB shell.
printf 'J701F display diagnostics\n'
cat /proc/uptime /proc/fb
for node in /sys/class/graphics/fb* /sys/class/backlight/* /sys/class/lcd/*; do
    [ -d "$node" ] || continue
    printf '\nNODE %s\n' "$node"
    /bin/busybox readlink -f "$node"
    for attr in name dev bits_per_pixel virtual_size stride state blank brightness max_brightness actual_brightness bl_power lcd_power lcd_type power/runtime_status; do
        [ -r "$node/$attr" ] || continue
        printf '%s: ' "$attr"
        cat "$node/$attr"
        printf '\n'
    done
    printf 'Attributes: '
    /bin/busybox ls --color=never "$node"
done
printf '\nDISPLAY KERNEL LOG\n'
dmesg | /bin/busybox grep -i -E 'decon|dsim|lcd panel|backlight|framebuffer|fb0|underrun|displayon'
printf '\nDISPLAY DIAGNOSTICS COMPLETE\n'
