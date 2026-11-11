# Entfernt nur defekte Chunk-Einträge aus .mca-Headern (Minecraft generiert sie neu).
import sys, zlib, gzip, struct
for p in sys.argv[1:]:
    d = bytearray(open(p, 'rb').read()); removed = 0
    for i in range(1024):
        off = int.from_bytes(d[i*4:i*4+3], 'big')
        if off == 0: continue
        s = off * 4096
        try:
            ln = struct.unpack('>I', d[s:s+4])[0]; ct = d[s+4]
            raw = bytes(d[s+5:s+4+ln])
            if len(raw) != ln - 1: raise ValueError
            data = zlib.decompress(raw) if ct == 2 else gzip.decompress(raw) if ct == 1 else raw if ct == 3 else None
            if ct & 0x80: continue
            if not data or data[0] != 10: raise ValueError
        except Exception:
            d[i*4:i*4+4] = b'\0\0\0\0'; d[4096+i*4:4096+i*4+4] = b'\0\0\0\0'; removed += 1
    open(p, 'wb').write(d); print(p, 'entfernt:', removed)
