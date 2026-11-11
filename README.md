# minecraft-oneblock-pi

Skripte, systemd-Units und Monitoring für einen modded Minecraft-Server
(**OneBlock + Create**, NeoForge 1.21.1) auf einem Raspberry Pi 5.

Welt, Spielerdaten und `server.properties` (enthält das RCON-Passwort) sind
**nicht** Teil dieses Repos.

## Aufbau

| Pfad | Inhalt |
|---|---|
| `mods.txt` | Modrinth-Projekte (Slugs). Abhängigkeiten werden automatisch aufgelöst. |
| `scripts/oneblock-mods.py` | Lädt/aktualisiert die Mods (sha512-geprüft), entfernt alte Jars und baut `modpack/OneBlock-Create.mrpack` für die Clients. |
| `scripts/oneblock-start.sh` | Startet NeoForge mit den JVM-Optionen aus `oneblock.env`. |
| `scripts/oneblock-cmd.sh` | Schickt einen Befehl an die Server-Konsole (FIFO `/run/oneblock/console`). |
| `scripts/oneblock-backup.sh` | Backup im laufenden Betrieb (`save-off` → tar.gz → `save-on`), behält die letzten 5. |
| `scripts/checkworld.py` | Prüft jede Region-Datei / jeden Chunk, NBT- und JSON-Dateien einer Welt. |
| `scripts/fixregion.py` | Entfernt nur defekte Chunk-Einträge aus `.mca`-Dateien (Minecraft generiert sie neu). |
| `exporter/oneblock_exporter.py` | Prometheus-Exporter (nur Python-Standardbibliothek). |
| `systemd/` | `oneblock.service`, `oneblock-exporter.service`, `oneblock-backup.{service,timer}` |
| `monitoring/` | Prometheus-Scrape-Config, Alarmregeln und Grafana-Dashboard |
| `install.sh` | Kopiert die Units nach `/etc/systemd/system` und aktiviert sie (sudo). |

Erwartete Verzeichnisse auf dem Pi:

```
/home/nicma/servers/tools      ← dieses Repo
/home/nicma/servers/oneblock   ← Server (Welt, server.properties, mods/, libraries/)
/home/nicma/mc-backup/auto     ← automatische Backups
```

## Einrichtung

```bash
# Mods laden und Client-Modpack bauen
python3 scripts/oneblock-mods.py /home/nicma/servers/oneblock

# Units installieren
sudo ./install.sh
sudo systemctl restart oneblock oneblock-exporter
```

## Monitoring

Der Exporter lauscht auf **Port 9225** (`/metrics`). Er fragt den Server bei jedem
Scrape per RCON ab. Port und Passwort liest er direkt aus `server.properties`, dort muss
gesetzt sein:

```properties
enable-rcon=true
rcon.port=25575
rcon.password=<langes Zufallspasswort>
broadcast-rcon-to-ops=false   # sonst bekommen Ops bei jedem Scrape eine Chat-Meldung
```

### Metriken

| Metrik | Beschreibung |
|---|---|
| `minecraft_up` | 1 wenn der Server per RCON antwortet |
| `minecraft_players_online` / `minecraft_players_max` | Spielerzahl |
| `minecraft_player_online{player}` | 1/0 je Spieler (Whitelist + aktuell online) |
| `minecraft_tps{dimension}` | TPS je Dimension, `dimension="overall"` = gesamt |
| `minecraft_tick_time_ms{dimension}` | Mittlere Tick-Zeit (über 50 ms = Lag) |
| `minecraft_process_resident_memory_bytes` | RAM des Java-Prozesses |
| `minecraft_process_cpu_seconds_total` | CPU-Zeit (mit `rate()` auswerten) |
| `minecraft_process_threads`, `minecraft_process_start_time_seconds` | Threads, Startzeit |
| `minecraft_world_size_bytes{dimension}` | Weltgröße (alle 5 min gemessen) |
| `minecraft_backup_last_timestamp_seconds`, `minecraft_backup_last_size_bytes`, `minecraft_backup_count` | Backups |
| `minecraft_disk_free_bytes` | Freier Platz auf dem Server-Laufwerk |

Test: `python3 exporter/oneblock_exporter.py --once`

### Prometheus und Grafana (auf dem Monitoring-Pi)

1. Den Block aus `monitoring/prometheus-scrape.yml` in `prometheus.yml` unter
   `scrape_configs:` einfügen, `<PI-ADRESSE>` ersetzen, Prometheus neu laden.
2. Optional `monitoring/prometheus-alerts.yml` unter `rule_files:` eintragen.
3. In Grafana: *Dashboards → New → Import* → `monitoring/grafana-dashboard.json`
   hochladen und die Prometheus-Datenquelle auswählen.
