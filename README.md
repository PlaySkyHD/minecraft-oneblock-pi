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

## Create Survival: Spielerstatistiken ohne Minecraft-Neustart

Der aktive Server liegt inzwischen unter `/home/nicma/servers/create`. Die Units
`create.service` und `create-exporter.service` sind **systemd-Benutzerdienste**.
Der Exporter wird so gestartet (wie in der aktiven Unit):

```bash
python3 -I exporter/oneblock_exporter.py --port 9225 \
  --server-dir /home/nicma/servers/create \
  --backup-dir /home/nicma/mc-backup/create --unit create.service --user-unit
```

Nach Exporter-Aenderungen nur `systemctl --user restart create-exporter` ausfuehren.
Der Minecraft-Dienst braucht weder Neustart noch `/reload`. Der Exporter liest
`world/stats/*.json`, `world/advancements/*.json` und lokale Namenszuordnungen.
Er sendet keine neuen Befehle an Minecraft und erzwingt keine Spielerspeicherung.

### Neue Spieler-Metriken

Alle Spielerwerte haben `player` (letzter bekannter Name) und `uuid` als Labels.
Sie beziehen sich auf die **aktuelle Welt**, nicht auf die archivierte OneBlock-Welt.

- `minecraft_player_blocks_mined_total`, `items_crafted_total`, `item_uses_total`,
  `items_broken_total`, `items_picked_up_total`, `items_dropped_total`,
  `entities_killed_total`, `deaths_to_entities_total` (jeweils mit Praefix
  `minecraft_player_`): Gesamtzahlen je Kategorie.
- `minecraft_player_statistic_events_total{category,statistic}`: alle einzelnen
  Block-, Item- und Wesen-Statistiken einschliesslich Mod-IDs. Kategorien sind
  `minecraft:mined`, `crafted`, `used`, `broken`, `picked_up`, `dropped`, `killed`
  und `killed_by` (jeweils mit Namespace).
- `minecraft_player_actions_total{action}`: alle gespeicherten sonstigen
  Zaehlstatistiken. Unter anderem Tode, Mob-/Spieler-Kills, Spruenge, Tierzucht,
  Fischen, Verzaubern, Schlafen, Handel, Kisten und Werkbanknutzung. Mod-Aktionen
  wie `waystones:waystone_activated` werden ebenfalls erfasst.
- `minecraft_player_distance_meters_total{mode}`: Gehen, Sprinten, Schleichen,
  Schwimmen, Wasserlaufen, Tauchen, Klettern, Fallen, Flug, Elytra und Fahrzeuge.
  Zentimeter werden in Meter umgerechnet.
- `minecraft_player_on_foot_meters_total`: Gehen + Sprinten + Schleichen.
- `minecraft_player_time_seconds_total{activity}`: Spielzeit inklusive AFK,
  gesamte Weltzeit und Schleichzeit; Ticks / 20. Die Arten nicht addieren.
- `minecraft_player_time_since_death_seconds`, `minecraft_player_time_since_rest_seconds`:
  Spielzeit seit Tod bzw. Schlaf, kein Echtzeit-Timer fuer Offline-Spieler.
- `minecraft_player_damage_health_points_total{kind}`: ausgeteilter, erhaltener,
  absorbierter, abgewehrter und widerstandener Schaden; 2 Lebenspunkte = 1 Herz.
- `minecraft_player_advancements_completed`,
  `minecraft_player_advancement_completed{advancement}`: Fortschritte insgesamt
  und einzeln, inklusive Mod-Fortschritte, ohne Rezeptfreischaltungen.
- `minecraft_player_recipe_advancements_completed`: abgeschlossene Rezept-
  Fortschritte; ein Fortschritt kann mehrere Rezepte freischalten.
- `minecraft_player_statistics_saved_timestamp_seconds`: Datei-Aenderungszeit,
  **nicht** letzte Anmeldung. Offline-Spieler haben naturgemaess alte Dateien.
- `minecraft_player_statistics_read_success`, `minecraft_player_advancements_read_success`,
  `minecraft_statistics_read_errors`, `minecraft_statistics_directory_accessible`,
  `minecraft_statistics_players`: Zustand der Dateiauswertung.

Statistiken werden erst beim regulaeren Speichern/Logout aktuell. Eine gerade
unvollstaendig geschriebene Statistikdatei ersetzt keinen gueltigen Stand: bis zum
naechsten erfolgreichen Lesen bleibt der letzte gute Snapshot sichtbar und
`statistics_read_success` ist 0. Ohne vorherigen Snapshot wird kein erfundener
Nullstand ausgegeben. Fehler einer Datei blockieren die anderen Spieler nicht.

**Grenzen:** Item-Benutzungen sind keine genaue Blockplatzierungszahl. Aufheben
kann denselben Gegenstand mehrfach zaehlen, Crafting zaehlt Ausgabemengen.
Maschinen-Abbau wird nicht automatisch einem Spieler zugerechnet. Aktuelle XP,
Inventare, Level und Gesundheit werden nicht aus den Statistikdateien abgeleitet.
Spielzeit ist keine exakte aktive Spielzeit. Alte Welt-Backups koennen Zaehler
zuruecksetzen; Prometheus behandelt dies bei `increase()` als Counter-Reset.
Mod-Aktionen ohne bekannte Einheit werden als ihre gespeicherten Zaehler exportiert.

### Dashboard aktualisieren

`monitoring/grafana-dashboard.json` enthaelt weiterhin die UID
`minecraft-oneblock`, damit das bestehende Dashboard beim Import ersetzt werden
kann. Der Titel lautet nun **Minecraft Create – Server & Spieler**. Die bisherigen
Serverpanels bleiben erhalten. Hinzu kommen Spieler-/Serverfilter, Ranglisten,
Bewegungsarten, Aktionen, Fortschritte, Detailtabellen und Zeitraum-Zuwaechse.

Auf dem **Monitoring-Server** bzw. im Grafana-Browser:

1. Dashboards > New > Import, JSON hochladen und Prometheus-Datenquelle waehlen.
2. Bestehendes Dashboard mit dieser UID aktualisieren; bei Bedarf zuvor dessen
   angepasste Version aus Grafana exportieren.
3. Job und Server auswaehlen. Scrape-Ziel bleibt `100.87.4.65:9225`.

Der normale Prometheus-Scrape sammelt die neuen Metriken automatisch, sofern keine
`metric_relabel_configs` oder `sample_limit` diese ausschliessen. Erfasst werden
aktuell ca. 2.700 Samples (ca. 440 kB) pro Scrape fuer fuenf Spieler; der Aufwand
waechst mit Spielern und verschiedenen Block-/Item-/Wesen-IDs. Bei einem eigenen
Sample-Limit entsprechende Reserve einplanen.

Gesamtwerte sind aus den vorhandenen Dateien sofort verfuegbar. Zeitreihen und
Zuwaechse entstehen erst ab der ersten Erfassung; historische Zeitpunkte lassen
sich aus den Dateien nicht rekonstruieren. Sehr kurze Zeitfenster haben ggf. noch
keine zwei Scrapes und zeigen dann keinen Zuwachs.

Der Dashboard-Generator ist `python3 monitoring/build_player_dashboard.py`.
Tests: `python3 -m unittest discover -s tests -v`.

## Private Webseite für Mitspieler

**Die Werkbank:** `http://100.87.4.65:8088/` (nur über Tailscale).
Ranglisten, Spielerprofile, Vergleich, Einzelstatistiken und CSV-Export.
Eigener systemd-Benutzerdienst: `minecraft-stats-web.service`.
Minecraft muss dafür nicht neu gestartet werden. Installation, Datenhaltung und
Tests sind in [`web/README.md`](web/README.md) beschrieben.
