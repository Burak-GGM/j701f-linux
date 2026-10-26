#!/bin/sh
# Install the daily-use app profile on an existing Alpine J701F system.
# Preview by default. Removing optional apps requires a separate --prune flag.
set -eu

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
mode=plan
prune=0
development=0
for arg do
    case "$arg" in
        --plan) mode=plan ;;
        --apply) mode=apply ;;
        --prune) prune=1 ;;
        --development) development=1 ;;
        *) echo "Usage: $0 [--plan|--apply] [--prune] [--development]" >&2; exit 2 ;;
    esac
done

if [ "$mode" = apply ] && [ "$(id -u)" -ne 0 ]; then
    echo 'Run --apply as root (for example, sudo sh system/apps/setup.sh --apply).' >&2
    exit 1
fi
if [ "$mode" = apply ]; then
    compatible=/proc/device-tree/compatible
    if [ ! -r "$compatible" ] || ! tr '\000' '\n' < "$compatible" | grep -qx 'samsung,j7velte'; then
        echo 'This application profile is for the J701F (samsung,j7velte) only.' >&2
        exit 1
    fi
fi
command -v apk >/dev/null 2>&1 || { echo 'Alpine apk is required.' >&2; exit 1; }

read_packages() {
    file=$1
    set --
    while IFS= read -r name || [ -n "$name" ]; do
        case "$name" in ''|\#*) continue ;; esac
        case "$name" in *[!a-zA-Z0-9+_.-]*)
            echo "Invalid package name in $file: $name" >&2; exit 1 ;;
        esac
        set -- "$@" "$name"
    done < "$here/$file"
    [ "$#" -gt 0 ] || { echo "Empty package list: $file" >&2; exit 1; }
    if [ "$mode" = plan ]; then
        echo "Preview: apk $action $file"
        apk "$action" --simulate "$@"
    else
        echo "Apply: apk $action $file"
        apk "$action" "$@"
    fi
}

action=add
read_packages core.txt
if [ "$development" -eq 1 ]; then read_packages optional-development.txt; fi
if [ "$prune" -eq 1 ]; then action=del; read_packages prune.txt; fi

# The packaged Koko launcher runs `koko %U`; /usr/local/bin precedes /usr/bin
# in the Plasma session PATH. Scope this layout workaround to Koko alone.
target=/usr/local/bin/koko
if [ "$mode" = plan ]; then
    echo "Preview: install Koko wrapper at $target"
else
    if [ -e "$target" ] && ! grep -q J701F_KOKO_WRAPPER "$target"; then
        echo "Refusing to replace an unrelated $target" >&2
        exit 1
    fi
    install -m 0755 "$here/koko-wrapper" "$target"
fi
