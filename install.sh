#!/bin/sh
# Installiert/aktualisiert die systemd-Units aus diesem Repo. Mit sudo ausführen.
set -e
cd "$(dirname "$0")/systemd"
cp oneblock.service oneblock-backup.service oneblock-backup.timer oneblock-exporter.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable oneblock.service oneblock-backup.timer oneblock-exporter.service
echo "Installiert. Neustart des Servers (übernimmt Änderungen): sudo systemctl restart oneblock"
