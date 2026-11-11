#!/usr/bin/env python3
# Lädt die Mods aus mods.txt (Modrinth) für NeoForge 1.21.1 inkl. Abhängigkeiten,
# prüft sha512, entfernt veraltete Jars und erzeugt modpack/OneBlock-Create.mrpack.
import json, os, sys, hashlib, urllib.request, urllib.parse, zipfile
SERVER = sys.argv[1] if len(sys.argv) > 1 else '/home/nicma/servers/oneblock'
GAME, LOADER = '1.21.1', 'neoforge'
UA = {'User-Agent': 'nicma-pi/oneblock-mods'}
API = 'https://api.modrinth.com/v2'
def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r: return json.load(r)
def latest(pid):
    q = urllib.parse.urlencode({'loaders': json.dumps([LOADER]), 'game_versions': json.dumps([GAME])})
    vs = get(f'{API}/project/{pid}/version?{q}')
    if not vs: raise SystemExit(f'Keine Version für {pid}')
    rel = [v for v in vs if v['version_type'] == 'release'] or vs
    return sorted(rel, key=lambda v: v['date_published'], reverse=True)[0]
slugs = [l.strip() for l in open(os.path.join(SERVER, 'mods.txt')) if l.strip() and not l.startswith('#')]
todo, seen, entries = list(slugs), {}, []
while todo:
    s = todo.pop(0)
    p = get(f'{API}/project/{s}')
    if p['id'] in seen: continue
    v = latest(p['id']); seen[p['id']] = v
    f = next(x for x in v['files'] if x['primary']) if any(x['primary'] for x in v['files']) else v['files'][0]
    entries.append((p, v, f))
    for d in v['dependencies']:
        if d['dependency_type'] == 'required' and d.get('project_id') and d['project_id'] not in seen: todo.append(d['project_id'])
mods = os.path.join(SERVER, 'mods'); os.makedirs(mods, exist_ok=True)
want = set()
for p, v, f in entries:
    server_ok = p['server_side'] != 'unsupported'
    print(f"{'S+C' if server_ok else '  C'}  {f['filename']}")
    if not server_ok: continue
    want.add(f['filename']); dst = os.path.join(mods, f['filename'])
    if os.path.exists(dst) and hashlib.sha512(open(dst,'rb').read()).hexdigest() == f['hashes']['sha512']: continue
    with urllib.request.urlopen(urllib.request.Request(f['url'], headers=UA), timeout=120) as r: data = r.read()
    if hashlib.sha512(data).hexdigest() != f['hashes']['sha512']: raise SystemExit(f'Hash falsch: {f["filename"]}')
    open(dst, 'wb').write(data)
for x in os.listdir(mods):
    if x.endswith('.jar') and x not in want: os.remove(os.path.join(mods, x)); print('entfernt', x)
os.makedirs(os.path.join(SERVER, 'modpack'), exist_ok=True)
idx = {'formatVersion': 1, 'game': 'minecraft', 'versionId': '1.0', 'name': 'OneBlock + Create',
       'dependencies': {'minecraft': GAME, 'neoforge': '21.1.265'},
       'files': [{'path': f'mods/{f["filename"]}', 'hashes': {'sha1': f['hashes']['sha1'], 'sha512': f['hashes']['sha512']},
                  'env': {'client': 'required', 'server': 'unsupported' if p['server_side'] == 'unsupported' else 'required'},
                  'downloads': [f['url']], 'fileSize': f['size']} for p, v, f in entries]}
with zipfile.ZipFile(os.path.join(SERVER, 'modpack', 'OneBlock-Create.mrpack'), 'w', zipfile.ZIP_DEFLATED) as z:
    z.writestr('modrinth.index.json', json.dumps(idx, indent=1))
print(len(entries), 'Dateien im Modpack,', len(want), 'auf dem Server')
