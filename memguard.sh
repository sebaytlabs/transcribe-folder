#!/usr/bin/env bash
# Pause a long job when the computer runs low on memory, and resume it when memory is back. Linux, systemd.
#   memguard.sh UNIT [LOW_MB] [HIGH_MB]          e.g.  memguard.sh transcribe 300 1700
# Every 20 s: if free memory (MemAvailable) stays under LOW_MB for a full minute, stop the user unit UNIT;
# when free memory is back over HIGH_MB, start it again. The job must be resumable (transcribe.py is).
# The gap between LOW and HIGH stops it flapping on and off. Exits when the unit finishes on its own.
# Log: memguard.log next to this script.
set -u
UNIT=${1:?usage: memguard.sh UNIT [LOW_MB] [HIGH_MB]}
LOW_MB=${2:-300}
HIGH_MB=${3:-1700}
LOG="$(cd "$(dirname "$0")" && pwd)/memguard.log"
paused=0 low=0
while true; do
  avail=$(awk '/MemAvailable/ {print int($2/1024)}' /proc/meminfo)
  if systemctl --user is-active -q "$UNIT"; then
    if [ "$avail" -lt "$LOW_MB" ]; then low=$((low + 1)); else low=0; fi
    if [ "$low" -ge 3 ]; then
      echo "$(date '+%F %T') free ${avail}MB < ${LOW_MB}MB for 1 min: pausing $UNIT" >> "$LOG"
      systemctl --user stop "$UNIT"; paused=1; low=0
    fi
  elif [ "$paused" = 1 ]; then
    if [ "$avail" -gt "$HIGH_MB" ]; then
      echo "$(date '+%F %T') free ${avail}MB: resuming $UNIT" >> "$LOG"
      systemctl --user reset-failed "$UNIT" 2>/dev/null
      systemctl --user start "$UNIT"; paused=0
    fi
  else
    echo "$(date '+%F %T') $UNIT is not running and wasn't paused by me: done" >> "$LOG"
    exit 0
  fi
  sleep 20
done
