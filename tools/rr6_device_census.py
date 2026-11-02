#!/usr/bin/env python3
"""rr6-nx (2026-11-02): which fields of the Direct3D device the game's own code touches, outside the Direct3D library.

Follows registers through a function: from a load of the device pointer's global (0x824F0378, Ridge Racer 6 Recomp's notes),
a D-form use of that register gives an offset. Copies by mr are followed; a call forgets the volatile registers. Printed
per offset with the sites and whether each site reads or writes, so what the game inlines from XDK 2.0.2135's headers is
known before Renut's device layout is chosen. Also prints a summary line for each function of the Direct3D library that the
game calls: instruction count, the displacements it uses, immediates, calls (feedingfrenzy-nx's out/ff_d3d_api_summary.txt).

  python -I tools/rr6_device_census.py
"""
import os
import re
import struct
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from d3d_propagate import starts_of, TGT_CODE, ROOT  # noqa: E402

B = 0x82000000
DEV = 0x824F0378
LIB = (0x8224E000, 0x82264000)
img = open(os.path.join(ROOT, 'out', 'renut_image.bin'), 'rb').read()
starts = starts_of(os.path.join(ROOT, 'app', 'generated'))


def w(a):
    return struct.unpack_from('>I', img, a - B)[0]


LOADS = {32: 'lwz', 33: 'lwzu', 34: 'lbz', 35: 'lbzu', 40: 'lhz', 41: 'lhzu', 42: 'lha', 43: 'lhau', 48: 'lfs', 49: 'lfsu', 50: 'lfd', 51: 'lfdu'}
STORES = {36: 'stw', 37: 'stwu', 38: 'stb', 39: 'stbu', 44: 'sth', 45: 'sthu', 52: 'stfs', 53: 'stfsu', 54: 'stfd', 55: 'stfdu'}


def census():
    sites = defaultdict(list)
    fns = 0
    for i, s in enumerate(starts):
        if LIB[0] <= s < LIB[1]:
            continue
        e = starts[i + 1] if i + 1 < len(starts) else s + 4
        dev = set()
        his = {}
        touched = False
        for a in range(s, min(e, s + 0x8000), 4):
            x = w(a)
            op = x >> 26
            rd, ra, simm = (x >> 21) & 31, (x >> 16) & 31, x & 0xFFFF
            sv = simm - 0x10000 if simm & 0x8000 else simm
            if op == 15 and ra == 0:  # lis
                his[rd] = (simm << 16) & 0xFFFFFFFF
                dev.discard(rd)
                continue
            if op == 18:  # b / bl
                if x & 1:
                    for r in list(dev):
                        if r <= 12:
                            dev.discard(r)
                    his = {r: v for r, v in his.items() if r > 12}
                continue
            if op == 32 and ra in his and ((his[ra] + sv) & 0xFFFFFFFF) == DEV:
                dev.add(rd)
                touched = True
                continue
            if op == 31 and ((x >> 1) & 0x3FF) == 444 and (x >> 11) & 31 == rd and rd in dev:  # mr
                dev.add(ra)
                continue
            if op in LOADS and ra in dev:
                sites[sv].append((a, LOADS[op], s))
                if rd in dev:
                    dev.discard(rd)
                continue
            if op in STORES and ra in dev:
                sites[sv].append((a, STORES[op], s))
                continue
            if op in LOADS or op == 14:
                if rd in dev:
                    dev.discard(rd)
                his.pop(rd, None)
            if op == 31 and rd in dev and ((x >> 1) & 0x3FF) in (23, 87, 266, 40):
                dev.discard(rd)
        fns += touched
    print(f'{fns} functions outside the library load the device pointer; offsets used directly:')
    for off in sorted(sites):
        c = Counter(k for _, k, _ in sites[off])
        ex = sites[off][0]
        print(f'  +{off:#07x} ({off:6d}) {sum(c.values()):5d} sites {dict(c)} e.g. {ex[0]:08X} in sub_{ex[2]:08X}')


def summary(names):
    for a in names:
        i = starts.index(a)
        e = starts[i + 1]
        n = (e - a) // 4
        rd, wr, imm, calls = [], [], [], []
        for k in range(a, e, 4):
            x = w(k)
            op = x >> 26
            ra, simm = (x >> 16) & 31, x & 0xFFFF
            sv = simm - 0x10000 if simm & 0x8000 else simm
            if op in LOADS or op == 58:
                if ra != 1 and sv >= 0:
                    rd.append(f'{LOADS.get(op, "ld")}+{sv}')
            elif op in STORES or op == 62:
                if ra != 1 and sv >= 0:
                    wr.append(f'{STORES.get(op, "std")}+{sv}')
            elif op == 14 and ra == 0:
                imm.append(str(sv))
            elif op == 15 and ra == 0:
                imm.append(f'lis{simm:04X}')
            elif op == 18 and x & 1:
                d = x & 0x03FFFFFC
                if d & 0x02000000:
                    d -= 0x04000000
                calls.append(f'{(k + d) & 0xFFFFFFFF:08X}')
        print(f'{a:08X}: {n} ins; R {" ".join(dict.fromkeys(rd))[:150]}; W {" ".join(dict.fromkeys(wr))[:120]}; imm {" ".join(dict.fromkeys(imm))[:70]}; calls {" ".join(dict.fromkeys(calls))[:90]}')


if __name__ == '__main__':
    census()
    want = [int(x, 16) for x in '8224E4C8 8224E610 8224E758 8224ED60 8224EDA0 82251158 822528B0 82252A18 82252AD8 82252AE0 82252AE8 82252CB8 82253E00 82254080 822540A0 82254368 82254D90 82254DA0 82254E50 82254EB8 82257488 822576D0 82257798 82257818 82257860 822579C0 82257C78 82257FE0 82258980 82263CE0 82263D28 82263D58 82263DB8 82263E74'.split()]
    summary(want)
