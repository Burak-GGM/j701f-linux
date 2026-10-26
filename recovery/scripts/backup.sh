#!/bin/sh
# Written by Claude 2026-10-10. Backup of settings and chosen directories for
# the recovery (roadmap R.6).
#
#   backup.sh create ROOT DEST [PATH...]   archive PATHs (relative to ROOT) into DEST
#   backup.sh verify ARCHIVE               compare the archive with its recorded hash, list it
#   backup.sh restore ARCHIVE SCRATCH      unpack into an EMPTY directory, never over data
#
# ROOT is where the installed system is mounted (read-only is enough). Default
# paths: etc, the user's .config and .local/share. "restore" refuses a target
# that is not empty: putting files back over a live system is a manual step on
# purpose (owner's rule: nothing here may overwrite the installed system).
set -eu
say() { echo "backup: $*"; }
die() { say "REFUSED: $*"; exit 1; }
sha() { sha256sum "$1" | cut -d' ' -f1; }

cmd=${1:-}
case "$cmd" in
create)
    root=${2:-}; dest=${3:-}
    [ -d "$root" ] || die "no such root directory: $root"
    [ -d "$dest" ] || die "no such destination directory: $dest"
    shift 3
    [ $# -gt 0 ] || set -- etc home/burak-alpine/.config home/burak-alpine/.local/share
    list=
    for p in "$@"; do
        case "$p" in /*|*..*) die "paths must be relative to the root and must not contain '..': $p";; esac
        [ -e "$root/$p" ] && list="$list $p" || say "skipping missing $p"
    done
    [ -n "$list" ] || die "nothing to back up"
    name=j701f-backup-$(date -u +%Y%m%d-%H%M%S).tar.gz
    # shellcheck disable=SC2086
    tar -C "$root" -czf "$dest/$name.part" $list
    mv "$dest/$name.part" "$dest/$name"
    sha "$dest/$name" > "$dest/$name.sha256"
    sync
    say "CREATED $dest/$name ($(wc -c < "$dest/$name") bytes)"
    ;;
verify)
    a=${2:-}
    [ -f "$a" ] && [ -f "$a.sha256" ] || die "archive or its .sha256 file is missing"
    [ "$(sha "$a")" = "$(cat "$a.sha256")" ] || { say "HASH MISMATCH"; exit 1; }
    n=$(tar -tzf "$a" | wc -l)
    say "VERIFIED $a: $n entries"
    ;;
restore)
    a=${2:-}; scratch=${3:-}
    [ -f "$a" ] && [ -f "$a.sha256" ] || die "archive or its .sha256 file is missing"
    [ "$(sha "$a")" = "$(cat "$a.sha256")" ] || die "archive does not match its recorded hash"
    [ -d "$scratch" ] || die "no such directory: $scratch"
    [ -z "$(ls -A "$scratch")" ] || die "target directory is not empty"
    tar -C "$scratch" -xzf "$a"
    sync
    say "RESTORED into $scratch"
    ;;
*)
    echo "usage: backup.sh create ROOT DEST [PATH...] | verify ARCHIVE | restore ARCHIVE EMPTY_DIR" >&2
    exit 2
    ;;
esac
