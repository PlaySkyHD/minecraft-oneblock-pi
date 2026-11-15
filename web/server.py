#!/usr/bin/env python3
"""Private, read-only Minecraft statistics website. Filtered game events and read-only position queries."""
import argparse
from collections import deque
from datetime import datetime
import importlib.util
import ipaddress
import json
import logging
import mimetypes
import os
from pathlib import Path
import re
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('minecraft_exporter', ROOT.parent/'exporter/oneblock_exporter.py')
exporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)
LOG = logging.getLogger('minecraft-stats')


class Samples:
    def __init__(self): self.rows = []
    def add(self, name, value, help_text='', mtype='gauge', **labels):
        self.rows.append((name, value, labels))


class History:
    def __init__(self, path):
        self.path = path
        with sqlite3.connect(path) as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE IF NOT EXISTS snapshots (ts INTEGER PRIMARY KEY, players TEXT NOT NULL)')

    def update(self, now, players):
        with sqlite3.connect(self.path, timeout=5) as db:
            last = db.execute('SELECT MAX(ts) FROM snapshots').fetchone()[0]
            if last is None or now-last >= 300:
                db.execute('INSERT INTO snapshots VALUES (?,?)', (now, json.dumps(players)))
                db.execute('DELETE FROM snapshots WHERE ts < ?', (now-90*86400,))

    def views(self, now, players):
        result = {}
        with sqlite3.connect(self.path) as db:
            first = db.execute('SELECT MIN(ts) FROM snapshots').fetchone()[0]
            for key, seconds in [('day',86400),('week',7*86400)]:
                row = db.execute('SELECT ts,players FROM snapshots WHERE ts<=? ORDER BY ts DESC LIMIT 1', (now-seconds,)).fetchone()
                if row is None:
                    row = db.execute('SELECT ts,players FROM snapshots ORDER BY ts LIMIT 1').fetchone()
                then, previous = row if row else (now,'{}')
                baseline = json.loads(previous)
                deltas, resets, unknown = {}, [], []
                for uuid, summary in players.items():
                    if uuid not in baseline:
                        # A player first observed after the baseline has no known
                        # initial balance. Do not count their lifetime total as new.
                        unknown.append(uuid)
                        continue
                    deltas[uuid] = {}
                    for metric,value in summary.items():
                        if metric in ('survival','rest','advancements'):
                            continue
                        old = baseline[uuid].get(metric,0)
                        if value < old:
                            if uuid not in resets: resets.append(uuid)
                            deltas[uuid][metric] = None
                        else: deltas[uuid][metric] = value-old
                result[key] = {'since':then,'complete':then<=now-seconds,'players':deltas,'resets':resets,'unknown':unknown}
            rows = db.execute('SELECT ts,players FROM snapshots WHERE ts>=? ORDER BY ts', (now-7*86400,)).fetchall()
        # Absolute, saved values only. Never invent activity between snapshots.
        result['timeline'] = [{'at':ts,'players':json.loads(data)} for ts,data in rows]
        result['startedAt'] = first or now
        return result


SUMMARY_TOTALS = {'mined':'blocks_mined','crafted':'items_crafted','pickedUp':'items_picked_up',
                  'uses':'item_uses','broken':'items_broken','dropped':'items_dropped'}
SUMMARY_ACTIONS = {'deaths':'deaths','mobKills':'mob_kills','playerKills':'player_kills','jumps':'jump',
                   'bred':'animals_bred','fish':'fish_caught','enchanted':'enchant_item',
                   'trades':'traded_with_villager','slept':'sleep_in_bed','chests':'open_chest'}


class Snapshot:
    def __init__(self, server_dir, state_dir, exporter_url):
        self.reader = exporter.PlayerStatistics(str(server_dir))
        self.history = History(state_dir/'history.sqlite3')
        self.exporter_url = exporter_url
        self.lock = threading.Lock()
        self.cached = None
        self.cached_at = 0

    def live(self):
        try:
            with urlopen(self.exporter_url, timeout=3) as response:
                content = response.read(4*1024*1024).decode('utf-8')
            def scalar(name):
                match = re.search(r'^'+re.escape(name)+r' ([0-9.eE+-]+)$',content,re.M)
                return float(match[1]) if match else None
            tps = re.search(r'^minecraft_tps\{dimension="overall"\} ([0-9.]+)$',content,re.M)
            online = set()
            for name,value in re.findall(r'^minecraft_player_online\{player="([A-Za-z0-9_]+)"\} ([01])$',content,re.M):
                if value=='1': online.add(name)
            return {'available':True,'up':scalar('minecraft_up')==1,'online':online,
                    'tps':float(tps[1]) if tps else None,'onlineCount':scalar('minecraft_players_online')}
        except (OSError,ValueError):
            return {'available':False,'up':None,'online':set(),'tps':None,'onlineCount':None}

    def get(self):
        with self.lock:
            now = int(time.time())
            if self.cached and now-self.cached_at < 20:
                return self.cached
            samples = Samples()
            self.reader.collect(samples)
            names = self.reader.names()
            index = {}
            for name,value,labels in samples.rows:
                uuid = labels.get('uuid')
                if uuid: index.setdefault(uuid,[]).append((name,value,labels))
            live = self.live()
            players, summaries = [], {}
            for uuid,(stats,saved_at) in self.reader.cache.items():
                rows = index.get(uuid,[])
                if not rows: continue
                def get(name,**selectors):
                    return next((v for n,v,l in rows if n==name and all(l.get(k)==val for k,val in selectors.items())),0)
                summary = {key:get('minecraft_player_'+suffix+'_total') for key,suffix in SUMMARY_TOTALS.items()}
                summary.update({key:get('minecraft_player_actions_total',action='minecraft:'+action) for key,action in SUMMARY_ACTIONS.items()})
                summary.update(playSeconds=get('minecraft_player_time_seconds_total',activity='play_time'),
                    walkMeters=get('minecraft_player_on_foot_meters_total'),
                    survival=get('minecraft_player_time_since_death_seconds'),rest=get('minecraft_player_time_since_rest_seconds'),
                    damageDealt=get('minecraft_player_damage_health_points_total',kind='damage_dealt'),
                    damageTaken=get('minecraft_player_damage_health_points_total',kind='damage_taken'),
                    advancements=get('minecraft_player_advancements_completed'))
                player_name = names.get(uuid,uuid)
                players.append({'uuid':uuid,'name':player_name,
                    'online':player_name in live['online'] if live['available'] and live['up'] else None,
                    'savedAt':saved_at,'readSuccess':bool(get('minecraft_player_statistics_read_success')),
                    'summary':summary,'statistics':stats,
                    'movement':{l['mode']:v for n,v,l in rows if n=='minecraft_player_distance_meters_total'},
                    'advancements':[{'id':l['advancement'],'done':bool(v)} for n,v,l in rows if n=='minecraft_player_advancement_completed']})
                summaries[uuid]=summary
            players.sort(key=lambda p:p['summary']['mined'],reverse=True)
            self.history.update(now,summaries)
            history = self.history.views(now,summaries)
            errors = next((value for name,value,l in samples.rows if name=='minecraft_statistics_read_errors'),0)
            self.cached = {'generatedAt':now,'server':{'name':'Create Survival','minecraft':'1.21.1','create':'6.0.10',
                'online':live['up'],'statusAvailable':live['available'],'tps':live['tps'],'onlineCount':live['onlineCount']},
                'players':players,'history':history,'readErrors':errors,
                'note':'Statistiken werden beim regulären Speichern durch Minecraft aktualisiert. Spielzeit enthält AFK-Zeit.'}
            self.cached_at = now
            return self.cached


class LiveFeed:
    """Bounded, filtered game feed. Never expose raw log lines or commands."""
    LINE = re.compile(r'^\[(\d{2}[A-Za-z]{3}\d{4} \d{2}:\d{2}:\d{2}\.\d+)\] \[Server thread/INFO\] \[net\.minecraft\.server\.(?:MinecraftServer|dedicated\.DedicatedServer)/?\]: (.*)$')
    NAME = r'[A-Za-z0-9_]{1,16}'

    def __init__(self, path):
        self.path = path
        self.events = deque(maxlen=250)
        self.lock = threading.Lock()
        self.identity = None
        self.offset = 0
        self.pending = b''
        self.sequence = 0

    @classmethod
    def parse(cls, line):
        match = cls.LINE.fullmatch(line)
        if not match: return None
        stamp, message = match.groups()
        message = re.sub(r'§.', '', message)
        kind, player, text = None, None, None
        chat = re.fullmatch(r'(?:\[Not Secure\] )?<('+cls.NAME+r')> (.*)', message)
        join = re.fullmatch(r'('+cls.NAME+r') (joined|left) the game', message)
        advancement = re.fullmatch(r'('+cls.NAME+r') has (?:made the advancement|completed the challenge|reached the goal) \[(.*)\]', message)
        death = re.fullmatch(r'('+cls.NAME+r') ((?:was |fell |hit the ground |drowned|blew up|burned |went up |tried to |walked |starved |suffocated |froze |experienced |discovered |didn.t want |withered |died|got |left the confines |was poked).*?)', message)
        if chat: kind, player, text = 'chat', chat[1], chat[2]
        elif join: kind, player, text = join[2], join[1], 'ist beigetreten' if join[2]=='joined' else 'hat den Server verlassen'
        elif advancement: kind, player, text = 'advancement', advancement[1], advancement[2]
        elif death: kind, player, text = 'death', death[1], death[2]
        elif message.startswith('Done ('): kind, text = 'server', 'Server gestartet'
        elif message=='Stopping server': kind, text = 'server', 'Server wird gestoppt'
        if kind is None: return None
        try: ts = datetime.strptime(stamp, '%d%b%Y %H:%M:%S.%f').timestamp()
        except ValueError: return None
        return {'at':ts, 'type':kind, 'player':player, 'text':text[:2000]}

    def get(self):
        with self.lock:
            try:
                # fstat the opened file so rotation between stat/open cannot skip data.
                with self.path.open('rb') as log:
                    stat = os.fstat(log.fileno())
                    identity = (stat.st_dev, stat.st_ino)
                    if identity != self.identity or stat.st_size < self.offset:
                        self.identity = identity
                        self.offset = max(0, stat.st_size-1024*1024)
                        self.pending = b''
                        if self.offset:
                            log.seek(self.offset); log.readline(); self.offset = log.tell()
                    log.seek(self.offset)
                    data = log.read(1024*1024)
                    self.offset = log.tell()
                lines = (self.pending+data).split(b'\n')
                self.pending = lines.pop()[-16384:]
                for line in lines:
                    event = self.parse(line.decode('utf-8', 'replace').rstrip('\r'))
                    if event:
                        self.sequence += 1
                        event['id'] = self.sequence
                        self.events.append(event)
                return {'available':True, 'generatedAt':int(time.time()), 'events':list(self.events)}
            except OSError:
                return {'available':False, 'generatedAt':int(time.time()), 'events':list(self.events)}


class Positions:
    """Only fixed, read-only RCON commands; no browser-supplied commands."""
    def __init__(self, server_dir):
        self.server_dir = server_dir
        self.lock = threading.Lock()
        self.cached = None
        self.cached_at = 0

    @staticmethod
    def parse_position(text):
        match = re.search(r'has the following entity data: \[([^\]]+)\]', text)
        if not match: raise ValueError('Position nicht verfügbar')
        values = [float(v.strip().rstrip('dDfF')) for v in match[1].split(',')]
        if len(values)!=3 or any(not (-32000000<v<32000000) for v in values):
            raise ValueError('Ungültige Position')
        return dict(zip(('x','y','z'), values))

    def get(self):
        with self.lock:
            now = time.time()
            if self.cached is not None and now-self.cached_at<10: return self.cached
            connection = None
            players, missing = [], []
            try:
                props = exporter.read_properties(str(self.server_dir/'server.properties'))
                if props.get('enable-rcon')!='true': raise ValueError('RCON deaktiviert')
                connection = exporter.Rcon('127.0.0.1', int(props.get('rcon.port','25575')), props.get('rcon.password',''), timeout=2)
                listing = exporter.LIST_RE.search(connection.command('list'))
                if not listing: raise ValueError('Spielerliste nicht verfügbar')
                names = [n.strip() for n in listing[3].split(',') if n.strip()]
                for name in names[:20]:
                    if not re.fullmatch(r'[A-Za-z0-9_]{1,16}', name): continue
                    try:
                        pos = self.parse_position(connection.command('data get entity '+name+' Pos'))
                        dim = connection.command('data get entity '+name+' Dimension')
                        dimension = re.search(r'has the following entity data: "([a-z0-9_.-]+:[a-z0-9_./-]+)"', dim)
                        if not dimension: raise ValueError('Dimension nicht verfügbar')
                        players.append(dict(name=name, dimension=dimension[1], **pos))
                    except ValueError:
                        missing.append(name)
                self.cached = {'available':True, 'generatedAt':int(now), 'players':players, 'missing':missing, 'onlineCount':int(listing[1]), 'limited':len(names)>20}
            except (OSError, ValueError, exporter.RconError):
                self.cached = {'available':False, 'generatedAt':int(now), 'players':[], 'missing':[], 'onlineCount':None, 'limited':False}
            finally:
                if connection: connection.close()
            self.cached_at = now
            return self.cached


def handler(snapshot,state_dir,feed=None,positions=None):
    class Handler(BaseHTTPRequestHandler):
        def reply(self,code,data,content_type='application/json; charset=utf-8',cache='no-store'):
            self.send_response(code)
            self.send_header('Content-Type',content_type)
            self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control',cache)
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            if self.command!='HEAD': self.wfile.write(data)
        def do_HEAD(self): self.do_GET()
        def do_GET(self):
            path=urlsplit(self.path).path
            try:
                if path=='/api/stats':
                    data=json.dumps(snapshot.get(),ensure_ascii=False,allow_nan=False).encode()
                    return self.reply(200,data)
                if path=='/api/live' and feed is not None:
                    return self.reply(200,json.dumps(feed.get(),ensure_ascii=False,allow_nan=False).encode())
                if path=='/api/positions' and positions is not None:
                    return self.reply(200,json.dumps(positions.get(),ensure_ascii=False,allow_nan=False).encode())
                if path=='/healthz': return self.reply(200,b'{"ok":true}')
                # Exact static paths only; world data/config are never served.
                if path in ('/','/index.html'): file=ROOT/'static/index.html'
                elif path in ('/app.js','/styles.css','/world.svg','/favicon.svg'):
                    file=ROOT/'static'/path[1:]
                elif re.fullmatch(r'/fonts/[a-zA-Z0-9_-]+\.woff2',path): file=ROOT/'static'/path[1:]
                elif re.fullmatch(r'/avatars/[0-9a-f-]{36}\.png',path): file=state_dir/path[1:]
                else: return self.reply(404,b'{"error":"Nicht gefunden"}')
                if not file.is_file(): return self.reply(404,b'{"error":"Nicht gefunden"}')
                content_type=mimetypes.guess_type(file.name)[0] or 'application/octet-stream'
                if content_type.startswith(('text/','application/javascript')): content_type+='; charset=utf-8'
                return self.reply(200,file.read_bytes(),content_type,'public, max-age=3600' if file.suffix in ('.png','.woff2') else 'no-cache')
            except (OSError,ValueError,sqlite3.Error):
                LOG.exception('Statistics request failed')
                self.reply(503,json.dumps({'error':'Statistiken sind gerade nicht verfügbar. Bitte später erneut laden.'},ensure_ascii=False).encode())
        def log_message(self,fmt,*args): LOG.info(fmt,*args)
    return Handler


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bind',default='100.87.4.65')
    p.add_argument('--port',type=int,default=8088)
    p.add_argument('--server-dir',type=Path,default=Path('/home/nicma/servers/create'))
    p.add_argument('--state-dir',type=Path,default=Path.home()/'.local/share/minecraft-stats')
    p.add_argument('--exporter-url',default='http://127.0.0.1:9225/metrics')
    a=p.parse_args()
    address=ipaddress.ip_address(a.bind)
    allowed_networks = ('127.0.0.0/8', '10.0.0.0/8', '172.16.0.0/12',
                        '192.168.0.0/16', '100.64.0.0/10')
    if str(address) != '0.0.0.0' and not any(
            address in ipaddress.ip_network(network) for network in allowed_networks):
        p.error('--bind muss 0.0.0.0 oder eine lokale, private oder Tailscale-IPv4-Adresse sein')
    a.state_dir.mkdir(parents=True,exist_ok=True)
    os.chmod(a.state_dir,0o700)
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    snapshot=Snapshot(a.server_dir,a.state_dir,a.exporter_url)
    snapshot.get()
    def record_periodically():
        while True:
            time.sleep(60)
            try:
                snapshot.get()
            except (OSError, ValueError, sqlite3.Error):
                LOG.exception('Background statistics collection failed')
    threading.Thread(target=record_periodically, daemon=True).start()
    server=ThreadingHTTPServer((a.bind,a.port),handler(snapshot,a.state_dir,LiveFeed(a.server_dir/'logs/latest.log'),Positions(a.server_dir)))
    LOG.info('Minecraft-Statistiken: http://%s:%s',a.bind,a.port)
    server.serve_forever()

if __name__=='__main__': main()
