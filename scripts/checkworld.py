import sys, os, zlib, gzip, json, struct
root = sys.argv[1]; bad = []; nchunks = 0
def nbt_ok(b):
    return len(b) > 3 and b[0] == 10
for dp, _, fs in os.walk(root):
    for f in fs:
        p = os.path.join(dp, f)
        try:
            if f.endswith('.mca'):
                d = open(p, 'rb').read()
                if len(d) == 0: continue
                for i in range(1024):
                    off = int.from_bytes(d[i*4:i*4+3], 'big'); cnt = d[i*4+3]
                    if off == 0: continue
                    s = off * 4096
                    ln = struct.unpack('>I', d[s:s+4])[0]; ct = d[s+4]
                    raw = d[s+5:s+4+ln]
                    if ct & 0x80: continue
                    data = zlib.decompress(raw) if ct == 2 else gzip.decompress(raw) if ct == 1 else raw
                    if not nbt_ok(data): raise ValueError(f'chunk {i} kein NBT')
                    nchunks += 1
            elif f.endswith(('.dat', '.dat_old', '.nbt')):
                b = open(p, 'rb').read()
                if b[:2] == b'\x1f\x8b': b = gzip.decompress(b)
                if b and not nbt_ok(b): raise ValueError('kein NBT')
            elif f.endswith('.json'):
                json.load(open(p))
        except Exception as e:
            bad.append((p, repr(e)[:120]))
print(nchunks, 'Chunks OK')
for b in bad: print('DEFEKT', *b)
print(len(bad), 'defekte Dateien')
