#!/usr/bin/env bash
# Tägliches Backup der OneBlock-Welt auf die SD-Karte (läuft auch bei laufendem Server).
set -Eeuo pipefail
SRC=/home/nicma/servers/oneblock
DEST=/home/nicma/mc-backup/auto
KEEP=5
CON=/run/oneblock/console

[ -d "$SRC/world" ] || { echo "FEHLER: $SRC/world fehlt"; exit 1; }
free_kb=$(df --output=avail -k /home/nicma | tail -1)
[ "$free_kb" -gt 1048576 ] || { echo "FEHLER: weniger als 1 GB frei auf der SD-Karte"; exit 1; }

mkdir -p "$DEST"
ts=$(date +%F-%H%M)
out="$DEST/oneblock-$ts.tar.gz"
tmp="$out.part"

running=0
if systemctl is-active -q oneblock && [ -p "$CON" ]; then running=1; fi
send() { timeout 5 sh -c "echo '$1' > '$CON'"; }
cleanup() { rm -f "$tmp"; if [ "$running" = 1 ]; then send "save-on" || true; fi; }
trap cleanup EXIT

if [ "$running" = 1 ]; then
  since=$(date '+%F %T')
  send "save-off"
  send "save-all flush"
  for _ in $(seq 1 120); do
    journalctl -u oneblock --since "$since" -o cat 2>/dev/null | grep -q "Saved the game" && break
    sleep 1
  done
  sleep 2
fi

cd "$SRC"
tar czf "$tmp" world server.properties ops.json whitelist.json usercache.json mods.txt
gzip -t "$tmp"
mv "$tmp" "$out"
if [ "$running" = 1 ]; then send "save-on"; running=0; fi

# Nur die neuesten $KEEP behalten
ls -1t "$DEST"/oneblock-*.tar.gz | tail -n +$((KEEP + 1)) | xargs -r rm -f
echo "Backup OK: $out ($(du -h "$out" | cut -f1))"
