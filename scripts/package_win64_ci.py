"""Stage the actual MinGW x64 game runtime and verify its PE import closure."""
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

build, output = map(Path, sys.argv[1:])
source = Path(__file__).resolve().parents[1]
output.mkdir(parents=True, exist_ok=False)
objdump = 'x86_64-w64-mingw32-objdump'

# These are supplied by Windows. Any other unresolved import fails packaging.
system_dlls = set('''advapi32 avrt bcrypt cfgmgr32 comctl32 comdlg32 crypt32
    d3d11 d3d12 d3d9 dcomp dbghelp dnsapi dsound dwmapi dxgi dxguid gdi32
    hid imm32 iphlpapi kernel32 ksuser mpr msvcrt mswsock ncrypt netapi32
    normaliz ntdll ole32 oleaut32 opengl32 powrprof propsys psapi rpcrt4
    secur32 setupapi shell32 shlwapi user32 userenv usp10 uxtheme version
    winhttp wininet winmm winspool wintrust ws2_32 wtsapi32'''.split())
search = {}
# Prioritize the top-level DLLs staged by the platform's POST_BUILD commands.
for root in [build, Path('/usr/x86_64-w64-mingw32'),
             Path('/usr/lib/gcc/x86_64-w64-mingw32')]:
    for path in sorted(root.rglob('*.dll'), key=lambda p: (len(p.parts), str(p))):
        search.setdefault(path.name.lower(), path)

# GNS is loaded by name at runtime, so an EXE import scan alone misses it.
pending = []
for name in ['openjkdf2-64.exe', 'OpenAL32.dll', 'libGameNetworkingSockets.dll']:
    path = build / name
    if not path.is_file():
        raise RuntimeError(f'Missing required game output: {path}')
    pending.append(path)
seen = set()
imports = []
while pending:
    path = pending.pop(0)
    if path.name.lower() in seen:
        continue
    seen.add(path.name.lower())
    header = subprocess.check_output([objdump, '-f', str(path)], text=True)
    if 'file format pei-x86-64' not in header:
        raise RuntimeError(f'Not a Windows x64 PE file: {path}')
    shutil.copy2(path, output / path.name)
    pe = subprocess.check_output([objdump, '-p', str(path)], text=True)
    for dll in re.findall(r'DLL Name:\s*(\S+)', pe):
        key = dll.lower()
        imports.append(f'{path.name} -> {dll}')
        if key.removesuffix('.dll') in system_dlls or key.startswith(('api-ms-win-', 'ext-ms-win-')):
            continue
        if key not in search:
            raise RuntimeError(f'Unresolved runtime dependency: {path.name} -> {dll}')
        pending.append(search[key])

for name in ['README.md', 'LICENSE.md']:
    shutil.copy2(source / name, output / name)
# UI/shaders/certificates are embedded by CMake; original GOB/music/video data
# is deliberately not bundled. Preserve dependency license notices separately.
licenses = output / 'licenses'
for root in [source / 'lib', source / 'src/external', source / '3rdparty']:
    for path in root.rglob('*'):
        if path.is_file() and path.name.lower().startswith(('license', 'copying', 'copyright')):
            destination = licenses / path.relative_to(source)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
(output / 'START-HERE.txt').write_text(
    'OpenJKDF2 Windows x64 (Debug, with audio, PhysFS and GNS networking)\n'
    'Extract ALL files next to your licensed Jedi Knight: Dark Forces II game data,\n'
    'then run openjkdf2-64.exe. See README.md for the game data directory layout.\n'
    'Keep all bundled DLLs beside the executable; no separate SDL install is needed.\n'
    'Original game assets are not included. Gameplay requires your own copy.\n'
    f'Source: https://github.com/{os.environ.get("GITHUB_REPOSITORY", "shinyquagsire23/OpenJKDF2")}\n'
    f'Commit: {os.environ.get("GITHUB_SHA", "unknown")}\n', encoding='utf-8')
(output / 'DEPENDENCIES.txt').write_text('\n'.join(sorted(imports)) + '\n', encoding='utf-8')
manifest = []
for path in sorted(output.rglob('*')):
    if path.is_file():
        manifest.append(f'{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(output).as_posix()}')
(output / 'SHA256SUMS.txt').write_text('\n'.join(manifest) + '\n', encoding='utf-8')
print('Packaged runtime: ' + ', '.join(sorted(seen)))
