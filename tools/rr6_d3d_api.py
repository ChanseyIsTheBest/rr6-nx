#!/usr/bin/env python3
"""rr6-nx (2026-11-02): this game's Direct3D library: its range (the Zuma pairs of Zuma's library 0x82121000-0x8213B000, XDK
2.0.2135 like this game), and which of its functions the game's own code calls (zuma-nx's out/zuma_d3d_api.txt method),
named by what the pairs and the hook tables know: Zuma's hook table, Katamari's and N&B's hook lines.

  python -I tools/rr6_d3d_api.py [--lo 0x... --hi 0x...]
Writes out/renut_map/rr6_d3d_api.txt.
"""
import argparse
import json
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from d3d_propagate import starts_of, TGT_CODE, ROOT  # noqa: E402

B = 0x82000000
MAP = os.path.join(ROOT, 'out', 'renut_map')
KAT_HOOKS = r'D:\beautifulkatamari\katamari-nx\app\src\renut_engine\gpu\d3d\hooks'
ZUMA_HOOKS = r'D:\peggle 2\zuma-nx\out\renut_map\zuma_hooks.txt'
ZUMA_API = r'D:\peggle 2\zuma-nx\out\zuma_d3d_api.txt'
LINE = re.compile(r'BANJO_RENUT_(?:UNHOOKED_)?HOOK(?:_RAW)?(?:_SHARED)?\(\s*sub_([0-9A-F]{8})[^;]*\)?[^/]*//\s*(\w+)')


def load(name):
    p = os.path.join(MAP, name)
    return {k: v['nights'] for k, v in json.load(open(p)).items()} if os.path.exists(p) else {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--lo', default='')
    ap.add_argument('--hi', default='')
    a = ap.parse_args()
    z, k, n, f = load('zuma_to_rr6.json'), load('kat_to_rr6.json'), load('nb_to_rr6.json'), load('ff1_to_rr6.json')
    lib = [int(v, 16) for kk, v in z.items() if 0x82121000 <= int(kk, 16) < 0x8213B000]
    lib.sort()
    print(f'{len(lib)} Zuma library pairs: {lib[0]:08X} .. {lib[-1]:08X}, middle 90 % {lib[len(lib) // 20]:08X} .. {lib[-len(lib) // 20]:08X}')
    lo = int(a.lo, 16) if a.lo else lib[len(lib) // 50] & ~0xFFF
    hi = int(a.hi, 16) if a.hi else (lib[-len(lib) // 50] | 0xFFF) + 1
    names = {}
    # Zuma's hooks by Zuma's address
    if os.path.exists(ZUMA_HOOKS):
        for line in open(ZUMA_HOOKS, encoding='utf-8', errors='replace'):
            p = line.split()
            if len(p) >= 2 and re.fullmatch('[0-9A-F]{8}', p[0]) and p[0] in z:
                names.setdefault(z[p[0]], p[1])
    for fn in os.listdir(KAT_HOOKS):
        for line in open(os.path.join(KAT_HOOKS, fn), encoding='utf-8', errors='replace'):
            m = LINE.search(line)
            if not m:
                continue
            if m.group(1) in k:
                names.setdefault(k[m.group(1)], m.group(2))
            mm = re.search(r'N&B sub_([0-9A-F]{8})', line)
            if mm and mm.group(1) in n:
                names.setdefault(n[mm.group(1)], m.group(2))
    img = open(os.path.join(ROOT, 'out', 'renut_image.bin'), 'rb').read()
    starts = starts_of(os.path.join(ROOT, 'app', 'generated'))
    lib_funcs = [s for s in starts if lo <= s < hi]
    print(f'library {lo:08X}-{hi:08X}: {len(lib_funcs)} functions, {len(names)} named')
    calls = {}
    for addr in range(TGT_CODE[0], TGT_CODE[1], 4):
        w = struct.unpack_from('>I', img, addr - B)[0]
        if w >> 26 != 18:
            continue
        d = w & 0x03FFFFFC
        if d & 0x02000000:
            d -= 0x04000000
        t = (addr + d) & 0xFFFFFFFF
        if lo <= t < hi and not lo <= addr < hi:
            calls.setdefault(t, []).append(addr)
    # data references: vtables or the state table
    out = [f'{len(calls)} functions of {lo:08X}-{hi:08X} called from outside', '']
    for t in sorted(calls):
        nm = names.get(f'{t:08X}', '?')
        out.append(f'sub_{t:08X} {len(calls[t]):5d} sites  {nm}')
    txt = '\n'.join(out) + '\n'
    open(os.path.join(MAP, 'rr6_d3d_api.txt'), 'w').write(txt)
    print(txt)


if __name__ == '__main__':
    main()
