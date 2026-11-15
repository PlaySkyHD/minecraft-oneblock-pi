#!/usr/bin/env python3
"""Build against the already installed Minecraft/NeoForge jars; no downloads."""
import argparse
from pathlib import Path
import shutil
import subprocess
import zipfile

root = Path(__file__).resolve().parent
p = argparse.ArgumentParser()
p.add_argument('--server-dir', type=Path, default=Path('/home/nicma/servers/create'))
a = p.parse_args()
java_home = Path('/usr/lib/jvm/java-21-openjdk-arm64')
libraries = a.server_dir/'libraries'
patched = libraries/'net/neoforged/neoforge/21.1.265/neoforge-21.1.265-server.jar'
assert patched.is_file(), 'Installed NeoForge 21.1.265 server jar is required'
classpath = ':'.join(str(x) for x in [patched, *sorted(libraries.rglob('*.jar'))])
build = root/'build'
if build.exists(): shutil.rmtree(build)
classes = build/'classes'
classes.mkdir(parents=True)
subprocess.run([str(java_home/'bin/javac'), '--release', '21', '-encoding', 'UTF-8', '-proc:none', '-cp', classpath,
                '-d', str(classes), *map(str, (root/'src/main/java').rglob('*.java'))], check=True)
out = build/'werkbank-end-access-lock-1.0.0.jar'
with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as jar:
    for base in [classes, root/'src/main/resources']:
        for file in sorted(base.rglob('*')):
            if file.is_file(): jar.write(file, str(file.relative_to(base)))
print(out)
