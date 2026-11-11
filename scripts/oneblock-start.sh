#!/usr/bin/env bash
# Wird von oneblock.service gestartet (NeoForge, Server auf der SD-Karte).
set -Eeuo pipefail
cd /home/nicma/servers/oneblock
exec "${JAVA_BIN:?}" \
  "-Xms${MC_MIN_RAM:-1G}" "-Xmx${MC_MAX_RAM:-4G}" \
  -XX:+UseG1GC -XX:+ParallelRefProcEnabled -XX:MaxGCPauseMillis=200 \
  -XX:+DisableExplicitGC -XX:+AlwaysPreTouch \
  @libraries/net/neoforged/neoforge/21.1.265/unix_args.txt nogui
