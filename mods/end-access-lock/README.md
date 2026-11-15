# Werkbank End Access Lock

Kleine serverseitige Mod für Minecraft 1.21.1 / NeoForge 21.1.265.
Keine Client-Mod, Pakete oder zusätzlichen Abhängigkeiten.

Solange die Sperre aktiv ist, wird `EntityTravelToDimensionEvent` vor einem
Dimensionswechsel nach `minecraft:the_end` abgebrochen. Das gilt für Spieler
(einschließlich OPs) und andere Entities. Der Nether und die Rückreise aus dem
End bleiben unverändert. Vorhandene End-Daten werden weder entfernt noch
zurückgesetzt. Bereits im End befindliche Spieler werden nicht ausgeworfen.
Teleporter anderer Mods müssen den normalen NeoForge-Dimensionswechsel nutzen.
Direkte administrative `/tp`-Transfers können diesen Portal-Hook umgehen; die
Mod ist eine Portalsperre, kein Entzug von Administratorrechten.

Beim blockierten Versuch sehen Spieler die frei einstellbare Nachricht in der
Actionbar und im Chat. Actionbar maximal alle zwei Sekunden, Chat maximal alle
30 Sekunden pro Spieler; ausgeloggte Spieler werden nicht im Speicher gehalten.

## Konfiguration

`config/end-access-lock.toml`:

```toml
locked = true
message = "Das End ist aktuell noch gesperrt. Wir öffnen es später gemeinsam!"
```

Admin-Befehle (OP-Level 2 oder Serverkonsole):

- `/endlock status` — Status und Nachricht anzeigen.
- `/endlock open` — Zugang freigeben und Einstellung speichern.
- `/endlock close` — Zugang sperren und Einstellung speichern.

Öffnen/Schließen benötigt keinen Minecraft-Neustart. Zur Erstinstallation die
JAR in den Server-Mods-Ordner legen und einmal neu starten. Spieler behalten ihr
bisheriges Client-Modpack.

## Build

```bash
python3 mods/end-access-lock/build.py --server-dir /home/nicma/servers/create
```

Der Build verwendet Java 21 und die bereits installierten NeoForge-/Minecraft-
Bibliotheken. Er lädt nichts herunter und verändert den Server nicht.
Ergebnis: `build/werkbank-end-access-lock-1.0.0.jar`. Build-Dateien werden nicht
ins Repository aufgenommen.

## Validierung

Kompilation gegen die installierte NeoForge-Version. Nach Installation:
Mod-Ladung und `/endlock status` prüfen. Integrationstest am 15.11.2026:
Ein temporäres Endportal wurde ausschließlich in einer zuvor geprüften Luftposition
über dem Weltspawn platziert. Eine markierte Test-Entity blieb nach drei Sekunden
im Portal in der Oberwelt. Portal und Test-Entities wurden anschließend entfernt.
Die Konfiguration wurde mit `/endlock close` gespeichert und der Status erneut
bestätigt. Spieler wurden beim Test nicht teleportiert. Ein separater Direktteleport-
Test bestätigt die oben dokumentierte Einschränkung für administrative Befehle.
