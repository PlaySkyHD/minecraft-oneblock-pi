#!/usr/bin/env python3
"""Prometheus-Exporter für den OneBlock-Minecraft-Server (NeoForge).

Holt die Daten bei jedem Scrape:
  * über RCON: Spieler online (`list`), TPS / Tick-Zeit je Dimension (`neoforge tps`)
  * aus /proc: Speicher (RSS), CPU-Zeit, Threads und Startzeit des Java-Prozesses
  * aus dem Dateisystem: Weltgröße und Alter / Größe des letzten Backups

RCON-Port und -Passwort werden direkt aus server.properties gelesen, damit das
Passwort nur an einer Stelle liegt. Nur Python-Standardbibliothek.
"""
import argparse
import json
import os
import re
import socket
import struct
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ---------------------------------------------------------------- RCON


class RconError(Exception):
    pass


class Rcon:
    LOGIN, COMMAND = 3, 2

    def __init__(self, host, port, password, timeout=5.0):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.settimeout(timeout)
        self._id = 0
        rid, _ = self._request(self.LOGIN, password)
        if rid == -1:
            raise RconError("RCON-Login fehlgeschlagen (Passwort falsch?)")

    def _recv_exact(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise RconError("RCON-Verbindung geschlossen")
            buf += chunk
        return buf

    def _read_packet(self):
        (length,) = struct.unpack("<i", self._recv_exact(4))
        data = self._recv_exact(length)
        rid, _ptype = struct.unpack("<ii", data[:8])
        return rid, data[8:-2].decode("utf-8", "replace")

    def _send(self, ptype, body):
        self._id += 1
        payload = struct.pack("<ii", self._id, ptype) + body.encode("utf-8") + b"\0\0"
        self.sock.sendall(struct.pack("<i", len(payload)) + payload)
        return self._id

    def _request(self, ptype, body):
        rid = self._send(ptype, body)
        return self._read_packet()

    def command(self, cmd):
        # Antworten > 4 KB kommen in mehreren Paketen. Ein leeres Folge-Paket
        # (ungültiger Typ) markiert das Ende, weil der Server es danach beantwortet.
        rid = self._send(self.COMMAND, cmd)
        marker = self._send(0xC8, "")
        parts = []
        while True:
            got, text = self._read_packet()
            if got == rid:
                parts.append(text)
            elif got == marker:
                break
        return "".join(parts)

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


# ---------------------------------------------------------------- Parser

COLOR = re.compile("\u00a7.")
LIST_RE = re.compile(r"There are (\d+) of a max of (\d+) players online:?\s*(.*)", re.S)
# NeoForge 1.21.1:      "Overworld: 20.000 TPS (0.237 ms/tick)"
# Älteres Forge-Format: "minecraft:overworld: Mean tick time: 0.237 ms. Mean TPS: 20.000"
TPS_RE = re.compile(r"^(?P<dim>.+?):\s*(?P<tps>[\d.,]+)\s*TPS\s*\((?P<mspt>[\d.,]+)\s*ms/tick\)", re.M)
TPS_OLD_RE = re.compile(
    r"^(?P<dim>.+?)\s*:\s*Mean tick time:\s*(?P<mspt>[\d.,]+)\s*ms\.?\s*Mean TPS:\s*(?P<tps>[\d.,]+)", re.M
)
DIM_NAMES = {"overworld": "minecraft:overworld", "the nether": "minecraft:the_nether",
             "the end": "minecraft:the_end", "overall": "overall"}


def parse_list(text):
    m = LIST_RE.search(COLOR.sub("", text))
    if not m:
        return None
    names = [n.strip() for n in m.group(3).split(",") if n.strip()]
    return int(m.group(1)), int(m.group(2)), names


def parse_tps(text):
    text = COLOR.sub("", text)
    out = []
    for m in list(TPS_RE.finditer(text)) or list(TPS_OLD_RE.finditer(text)):
        dim = m.group("dim").strip()
        dim = DIM_NAMES.get(dim.lower(), dim)
        out.append((dim, float(m.group("mspt").replace(",", ".")), float(m.group("tps").replace(",", "."))))
    return out


def read_properties(path):
    props = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                props[k.strip()] = v.strip()
    return props


# ---------------------------------------------------------------- Metriken


class Metrics:
    """Sammelt Samples und gibt sie gruppiert je Metrik aus (Prometheus-Textformat)."""

    def __init__(self):
        self.families = {}

    def add(self, name, value, help_text, mtype="gauge", **labels):
        fam = self.families.setdefault(name, (help_text, mtype, []))
        if labels:
            lab = ",".join(f'{k}="{_esc(v)}"' for k, v in sorted(labels.items()))
            fam[2].append(f"{name}{{{lab}}} {value}")
        else:
            fam[2].append(f"{name} {value}")

    def render(self):
        lines = []
        for name, (help_text, mtype, samples) in self.families.items():
            lines += [f"# HELP {name} {help_text}", f"# TYPE {name} {mtype}", *samples]
        return "\n".join(lines) + "\n"


def _esc(v):
    return str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


CLK_TCK = os.sysconf("SC_CLK_TCK")
PAGE = os.sysconf("SC_PAGE_SIZE")


def main_pid(unit):
    try:
        out = subprocess.run(
            ["systemctl", "show", "-p", "MainPID", "--value", unit],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        pid = int(out or 0)
        return pid or None
    except (ValueError, subprocess.SubprocessError, OSError):
        return None


def proc_stats(pid):
    with open(f"/proc/{pid}/stat") as f:
        fields = f.read().rsplit(")", 1)[1].split()
    # Felder ab Index 3 der Manpage; nach dem Split ist Feld 3 an Position 0
    utime, stime = int(fields[11]), int(fields[12])
    threads, starttime, rss_pages = int(fields[17]), int(fields[19]), int(fields[21])
    with open("/proc/stat") as f:
        btime = next(int(l.split()[1]) for l in f if l.startswith("btime"))
    return {
        "cpu": (utime + stime) / CLK_TCK,
        "threads": threads,
        "start": btime + starttime / CLK_TCK,
        "rss": rss_pages * PAGE,
    }


def dir_size(path):
    total = 0
    for dp, _, files in os.walk(path):
        for name in files:
            try:
                total += os.lstat(os.path.join(dp, name)).st_size
            except OSError:
                pass
    return total


class Collector:
    def __init__(self, args):
        self.args = args
        self.lock = threading.Lock()
        self._world_cache = (0.0, {})

    def world_sizes(self):
        ts, cache = self._world_cache
        if time.time() - ts < self.args.world_size_interval:
            return cache
        world = os.path.join(self.args.server_dir, "world")
        sizes = {}
        if os.path.isdir(world):
            sizes["overworld"] = dir_size(os.path.join(world, "region"))
            for dim, sub in (("the_nether", "DIM-1"), ("the_end", "DIM1")):
                p = os.path.join(world, sub)
                if os.path.isdir(p):
                    sizes[dim] = dir_size(p)
            sizes["total"] = dir_size(world)
        self._world_cache = (time.time(), sizes)
        return sizes

    def whitelist(self):
        try:
            with open(os.path.join(self.args.server_dir, "whitelist.json"), encoding="utf-8") as f:
                return sorted({e["name"] for e in json.load(f) if "name" in e})
        except (OSError, ValueError):
            return []

    def collect(self):
        m = Metrics()
        t0 = time.time()
        a = self.args

        # --- RCON
        up = 0
        try:
            props = read_properties(os.path.join(a.server_dir, "server.properties"))
            if props.get("enable-rcon") != "true":
                raise RconError("enable-rcon=false in server.properties")
            r = Rcon(a.rcon_host, int(props.get("rcon.port", "25575")), props.get("rcon.password", ""))
            try:
                lst = parse_list(r.command("list"))
                tps = parse_tps(r.command("neoforge tps"))
            finally:
                r.close()
            up = 1
            if lst:
                online, maximum, names = lst
                m.add("minecraft_players_online", online, "Anzahl Spieler online")
                m.add("minecraft_players_max", maximum, "Maximale Spielerzahl")
                known = set(self.whitelist()) | set(names)
                for name in sorted(known):
                    m.add("minecraft_player_online", int(name in names),
                          "1 wenn der Spieler online ist", player=name)
            for dim, mspt, tps_v in tps:
                m.add("minecraft_tps", tps_v, "Ticks pro Sekunde (Soll: 20)", dimension=dim)
                m.add("minecraft_tick_time_ms", mspt, "Mittlere Tick-Zeit in ms (Limit: 50)", dimension=dim)
        except (OSError, RconError, ValueError, struct.error) as e:
            m.add("minecraft_rcon_error", 1, "1 wenn die RCON-Abfrage fehlgeschlagen ist", reason=type(e).__name__)
        m.add("minecraft_up", up, "1 wenn der Server per RCON antwortet")

        # --- Prozess
        pid = main_pid(a.unit)
        m.add("minecraft_process_running", int(bool(pid)), "1 wenn der systemd-Dienst einen Prozess hat")
        if pid:
            try:
                s = proc_stats(pid)
                m.add("minecraft_process_resident_memory_bytes", s["rss"], "RSS des Java-Prozesses")
                m.add("minecraft_process_cpu_seconds_total", round(s["cpu"], 2), "CPU-Zeit des Java-Prozesses", "counter")
                m.add("minecraft_process_threads", s["threads"], "Threads des Java-Prozesses")
                m.add("minecraft_process_start_time_seconds", round(s["start"], 1), "Startzeit (Unix-Zeit)")
            except (OSError, ValueError, IndexError, StopIteration):
                pass

        # --- Welt
        for dim, size in self.world_sizes().items():
            m.add("minecraft_world_size_bytes", size, "Größe der Welt auf der Platte", dimension=dim)

        # --- Backups
        try:
            files = [os.path.join(a.backup_dir, f) for f in os.listdir(a.backup_dir)
                     if f.endswith(".tar.gz")]
        except OSError:
            files = []
        m.add("minecraft_backup_count", len(files), "Anzahl vorhandener Backups")
        if files:
            newest = max(files, key=os.path.getmtime)
            m.add("minecraft_backup_last_timestamp_seconds", round(os.path.getmtime(newest)),
                  "Zeitpunkt des letzten Backups (Unix-Zeit)")
            m.add("minecraft_backup_last_size_bytes", os.path.getsize(newest), "Größe des letzten Backups")

        try:
            st = os.statvfs(a.server_dir)
            m.add("minecraft_disk_free_bytes", st.f_bavail * st.f_frsize, "Freier Platz auf dem Server-Laufwerk")
        except OSError:
            pass

        m.add("minecraft_exporter_scrape_duration_seconds", round(time.time() - t0, 4), "Dauer des Scrapes")
        return m.render()


def make_handler(collector):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.split("?")[0] == "/metrics":
                with collector.lock:
                    body = collector.collect().encode("utf-8")
                ctype = "text/plain; version=0.0.4; charset=utf-8"
            elif self.path == "/":
                body = b'<a href="/metrics">/metrics</a>\n'
                ctype = "text/html"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    return Handler


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--listen", default="0.0.0.0")
    p.add_argument("--port", type=int, default=9225)
    p.add_argument("--server-dir", default="/home/nicma/servers/oneblock")
    p.add_argument("--backup-dir", default="/home/nicma/mc-backup/auto")
    p.add_argument("--unit", default="oneblock.service")
    p.add_argument("--rcon-host", default="127.0.0.1")
    p.add_argument("--world-size-interval", type=int, default=300, help="Sekunden zwischen Weltgrößen-Messungen")
    p.add_argument("--once", action="store_true", help="Metriken einmal ausgeben und beenden")
    args = p.parse_args()
    collector = Collector(args)
    if args.once:
        print(collector.collect(), end="")
        return
    ThreadingHTTPServer((args.listen, args.port), make_handler(collector)).serve_forever()


if __name__ == "__main__":
    main()
