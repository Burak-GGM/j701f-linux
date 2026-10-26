#!/bin/bash
# Written by Claude 2026-10-10. Coordination helper for two assistants (Claude
# and ChatGPT Codex) working in this repository at the same time. No daemon and
# no interrupts: locks are directories (mkdir is atomic), messages are files.
# Rules and conventions: docs/coordination/README.md
#
#   tools/coord.sh status
#   tools/coord.sh lock   NAME WHO "purpose" [minutes]   # NAME: phone | kbuild | <anything>
#   tools/coord.sh unlock NAME WHO
#   tools/coord.sh wait   NAME WHO "purpose" [minutes] [max_wait_min]   # poll until free, then lock
#   tools/coord.sh say    FROM TO "text"                 # TO: claude | codex | all
#   tools/coord.sh inbox  WHO                            # print unread messages for WHO, mark them read
#   tools/coord.sh claim  WHO "what I am working on"     # append to the board
#   tools/coord.sh done   WHO "what I finished"
set -euo pipefail
cd "$(dirname "$0")/.."
L=build/coord/locks; M=docs/coordination/messages; B=docs/coordination/BOARD.md
mkdir -p "$L" "$M"
now() { date +%s; }
stamp() { date '+%Y-%m-%d %H:%M:%S'; }
age_min() { echo $(( ( $(now) - $(cat "$1/time") ) / 60 )); }
show() { for d in "$L"/*/; do [ -d "$d" ] || continue; n=$(basename "$d")
    echo "LOCK $n: owner=$(cat "$d/owner") age=$(age_min "$d")min ttl=$(cat "$d/ttl")min purpose=$(cat "$d/purpose")"; done; }
take() { # NAME WHO PURPOSE TTL
    local d="$L/$1"
    if mkdir "$d" 2>/dev/null; then
        echo "$2" > "$d/owner"; now > "$d/time"; echo "${4:-30}" > "$d/ttl"; echo "$3" > "$d/purpose"
        echo "LOCKED $1 for $2 (${4:-30} min): $3"; return 0
    fi
    local o; o=$(cat "$d/owner" 2>/dev/null || echo '?')
    if [ "$o" = "$2" ]; then now > "$d/time"; echo "$3" > "$d/purpose"; echo "${4:-30}" > "$d/ttl"; echo "RENEWED $1 for $2: $3"; return 0; fi
    if [ "$(age_min "$d")" -ge "$(cat "$d/ttl")" ]; then
        echo "STALE lock $1 (owner $o, $(age_min "$d") min old, ttl $(cat "$d/ttl")): taking it over" >&2
        echo "[$(stamp)] $2 took over the stale '$1' lock from $o (purpose was: $(cat "$d/purpose"))" >> "$B"
        rm -rf "$d"; take "$@"; return $?
    fi
    echo "BUSY $1: owner=$o age=$(age_min "$d")min purpose=$(cat "$d/purpose")"; return 1
}
case "${1:-status}" in
status) show; echo "--- board (last 12 lines)"; tail -12 "$B" 2>/dev/null || true
        echo "--- unread: claude=$(grep -L 'read-by: claude' "$M"/*-to-claude-*.md "$M"/*-to-all-*.md 2>/dev/null | wc -l) codex=$(grep -L 'read-by: codex' "$M"/*-to-codex-*.md "$M"/*-to-all-*.md 2>/dev/null | wc -l)" ;;
lock)   take "${2:?name}" "${3:?who}" "${4:?purpose}" "${5:-30}" ;;
unlock) d="$L/${2:?name}"; [ -d "$d" ] || { echo "not locked"; exit 0; }
        [ "$(cat "$d/owner")" = "${3:?who}" ] || { echo "REFUSED: $2 is held by $(cat "$d/owner")"; exit 1; }
        rm -rf "$d"; echo "UNLOCKED $2" ;;
wait)   end=$(( $(now) + ${6:-60} * 60 ))
        until take "${2:?name}" "${3:?who}" "${4:?purpose}" "${5:-30}" >/dev/null 2>&1; do
            [ "$(now)" -lt "$end" ] || { echo "TIMEOUT waiting for $2"; show; exit 1; }; sleep 20; done
        echo "LOCKED $2 for $3: $4" ;;
say)    f="$M/$(date +%Y%m%d-%H%M%S)-${2:?from}-to-${3:?to}-$$.md"
        printf 'from: %s\nto: %s\ntime: %s\n\n%s\n' "$2" "$3" "$(stamp)" "${4:?text}" > "$f"; echo "SENT $f" ;;
inbox)  w="${2:?who}"; n=0
        for f in "$M"/*-to-"$w"-*.md "$M"/*-to-all-*.md; do [ -f "$f" ] || continue
            grep -q "read-by: $w" "$f" && continue
            case "$f" in *"-$w-to-"*) continue ;; esac     # my own broadcast
            echo "=== $f"; cat "$f"; echo; printf 'read-by: %s (%s)\n' "$w" "$(stamp)" >> "$f"; n=$((n+1)); done
        echo "($n new message(s) for $w)" ;;
claim)  echo "[$(stamp)] ${2:?who} WORKING ON: ${3:?what}" >> "$B"; echo ok ;;
done)   echo "[$(stamp)] ${2:?who} DONE: ${3:?what}" >> "$B"; echo ok ;;
*)      sed -n 2,16p "$0"; exit 2 ;;
esac
