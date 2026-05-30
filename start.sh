#!/bin/bash
# JT-for-SC : lance le proxy calendrier + ouvre la page
cd "$(dirname "$0")"

# Tue tout process existant sur le port 5000
fuser -k 5000/tcp 2>/dev/null
sleep 1

# Lance le proxy en background
./.venv-proxy/bin/python proxy_calendar.py &
PROXY_PID=$!

# Attend que le proxy soit prêt
for i in $(seq 1 10); do
  curl -s http://127.0.0.1:5000/calendar > /dev/null 2>&1 && break
  sleep 1
done

echo "[INFO] Proxy prêt → http://127.0.0.1:5000"
echo "[INFO] Ctrl+C pour arrêter"

# Ouvre Firefox
firefox http://127.0.0.1:5000 2>/dev/null &

# Attend que l'utilisateur fasse Ctrl+C
trap "kill $PROXY_PID 2>/dev/null; exit 0" INT TERM
wait $PROXY_PID
