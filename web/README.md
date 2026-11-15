# Die Werkbank

Private, deutschsprachige Statistik-Webseite für Create Survival. Sie läuft separat
von Minecraft und benötigt keine Mod, keinen Minecraft-Neustart und kein `/reload`.

## Zugriff

Auf dem aktuellen Pi:

- Heimnetz: **http://192.168.178.134:8088/**
- Tailscale: **http://100.87.4.65:8088/**

Der installierte Dienst bindet an `0.0.0.0:8088` (alle IPv4-Schnittstellen).
Die LAN-Adresse wird per DHCP vergeben und kann sich ändern.
Die Anwendung hat keinen zusätzlichen Login; Geräte im Heimnetz können sie direkt öffnen.
Für Tailscale brauchen Mitspieler eine passende Freigabe/ACL für dieses Gerät und
TCP-Port 8088. Minecraft-Freigaben für Port 25567 erlauben diesen Port nicht automatisch.
Es wurden keine Router-Portfreigaben, Tailscale-ACLs oder Funnel-Einstellungen verändert.

## Ansichten

- Übersicht mit Welt-Gesamtwerten, Online-Spielern, Rangliste und Rekorden.
- Ranglisten mit Suche, Statistik-Auswahl, Sortierung und CSV-Download.
- Spielerprofile mit Produktion, Kampf, Bewegung und einzelnen Fortschritten.
- Zwei Spieler nebeneinander vergleichen.
- Alle gespeicherten Einzelwerte nach Block-/Item-/Wesen-ID durchsuchen.
- Gesamtwerte seit Weltstart sowie beobachtete Zuwächse über 24 Stunden/7 Tage.

Es gibt keine erfundenen Wochenwerte: Historie wird ab Installation alle fünf
Minuten in SQLite gespeichert, auch ohne geöffnete Browser. Vorherige Zeiträume
werden als unvollständig gekennzeichnet. Neue Spieler ohne Vergleichswert und
zurückgesetzte Zähler werden nicht mit einem erfundenen Zuwachs verrechnet.
Die Originalstatistiken werden beim normalen Minecraft-Speichern aktualisiert.
Spielzeit enthält AFK-Zeit; Item-Benutzungen sind keine exakten Blockplatzierungen.
Die Vorschau für jeden Bewegungs-/Fortschrittswert folgt den Exporter-Definitionen.

## Betrieb

Nur Python-Standardbibliothek, keine npm-Abhängigkeiten oder Build-Schritte.

```bash
python3 -I web/server.py --bind 0.0.0.0 --port 8088
systemctl --user status minecraft-stats-web
journalctl --user -u minecraft-stats-web -f
```

Installationsvorlage: `systemd/minecraft-stats-web.service` nach
`~/.config/systemd/user/` kopieren, Pfade/IP ggf. anpassen und dann:

```bash
systemctl --user daemon-reload
systemctl --user enable --now minecraft-stats-web
```

Der Nutzer `nicma` hat Linger aktiviert, damit der Dienst ohne Anmeldung startet.
Der Dienst benötigt beim Start keine bereits zugewiesene Tailscale-Adresse. Nur diesen Webdienst nach Änderungen an `web/server.py` neu starten.
Statische Dateien werden ohne Dienstneustart ausgeliefert.

Die Anwendung liest gespeicherte Weltstatistiken über die vorhandene
`PlayerStatistics`-Klasse und den bestehenden Exporter unter
`http://127.0.0.1:9225/metrics` für den Live-Status. Sie sendet selbst keine
RCON-Befehle und schreibt nicht in den Minecraft-Ordner. Snapshot-Antworten werden
20 Sekunden gecacht, der Browser aktualisiert alle 30 Sekunden.

Verlauf und gecachte Avatare liegen in
`~/.local/share/minecraft-stats/` (nicht im Repo, Zugriffsmodus 0700).
SQLite-Snapshots werden 90 Tage aufbewahrt. Vor einem Umzug des Webdienstes diese
Daten separat sichern; die Minecraft-Welt-Backups enthalten sie nicht.
Für eine konsistente laufende Sicherung kann `sqlite3.Connection.backup()`
verwendet werden. Aktuelle Spielerdaten und Avatare nicht ins öffentliche Repo laden.

Fonts werden lokal ausgeliefert, kein Tracking, keine Browser-Anfragen an CDNs.
Avatare der aktuellen Spieler wurden einmalig von mc-heads.net gecacht.
Für neue Spieler kann eine PNG-Datei unter
`~/.local/share/minecraft-stats/avatars/<uuid>.png` abgelegt werden; ohne Datei
erscheint ein lokaler, deterministischer Pixel-Avatar. Auf Wunsch lassen sich
Avatare später erneut herunterladen. Der Webdienst ruft den Avatar-Anbieter
nicht automatisch auf.

## Tests

```bash
python3 -m unittest discover -s web/tests -v
```

Geprüft werden echte Einheitenumrechnungen, unbekannter Live-Status,
Historienbeginn, neue Spieler, Counter-Resets, Persistenz, UTF-8 und die
Allowlist der HTTP-Routen. Kein Zugriff auf Konfigurationen oder Quellcode
über den Webserver. Manuell im gemeinsamen Browser: Desktop und iPhone-Breite,
Ranglistenfilter, Suche, Profile, Vergleich, Detailkategorien und CSV-Download.

## Gestaltung und Quellen

Designrecherche und eigene Gestaltung: `DESIGN.md`.
Eigene SVG-Illustrationen und Icons. Space Grotesk und DM Sans werden unter der
SIL Open Font License mitgeliefert, Lizenztexte liegen in `static/fonts/`.
Es wurden keine externen Website-Layouts oder Minecraft-Texturen kopiert.
