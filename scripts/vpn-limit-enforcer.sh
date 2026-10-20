#!/bin/bash
LIMITS_DIR="/etc/UDPCustom/limits"
LOG="/var/log/vpn-device-limit.log"
NOW=$(date +%s)

for f in /tmp/limit_exceeded_*; do
    [ -e "$f" ] || continue
    USER_NAME=$(basename "$f" | sed 's/limit_exceeded_//')
    START_TS=$(cat "$f" 2>/dev/null)
    [ -z "$START_TS" ] && continue
    
    DIFF=$((NOW - START_TS))
    if [ "$DIFF" -ge 60 ]; then
        LIMIT=$(cat "$LIMITS_DIR/$USER_NAME" 2>/dev/null || echo 3)
        PIDS=($(pgrep -u "$USER_NAME" -f "sshd-session:" 2>/dev/null))
        COUNT=${#PIDS[@]}
        
        if [ "$COUNT" -gt "$LIMIT" ]; then
            # Сортируем PID по времени запуска (от старых к новым)
            SORTED=($(for pid in "${PIDS[@]}"; do echo "$(stat -c %Y /proc/$pid 2>/dev/null || echo 0) $pid"; done | sort -n | awk '{print $2}'))
            KILL_COUNT=$((COUNT - LIMIT))
            
            for ((i=0; i<KILL_COUNT; i++)); do
                IDX=$(( ${#SORTED[@]} - 1 - i ))
                kill -9 "${SORTED[$IDX]}" 2>/dev/null
                echo "[$(date '+%F %T')] [KILL] user=$USER_NAME pid=${SORTED[$IDX]} reason=grace_expired" >> "$LOG"
            done
        fi
        rm -f "$f"
    fi
done
