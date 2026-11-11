#!/bin/sh
# Befehl an die OneBlock-Konsole senden, z.B.: oneblock-cmd.sh "say Hallo"
[ -p /run/oneblock/console ] || { echo "Server läuft nicht"; exit 1; }
echo "$*" > /run/oneblock/console
sleep 1; journalctl -u oneblock -n 5 -o cat --no-pager
