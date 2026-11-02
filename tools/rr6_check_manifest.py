#!/usr/bin/env python3
"""rr6-nx (2026-11-02): checks Ridge Racer 6 Recomp's manifest against this image rather than trusting it, and prints the
image's PE sections (the PSFD00 code section of the Sofdec decoder among them).

For each address of config/renut_funcs.toml: is it in a code section, does the word decode as code (not padding), what
precedes it, and is it where the manifest's evidence says (a pointer in data, a `b` from the named thunk). setjmp and
longjmp by shape (`stfd f14,0(r3)` and `lfd f14,0(r7)`). The two indirect tail calls: the bctr, the table's base built
by lis/addi, and every table entry a registered function start or in code.

  python -I tools/rr6_check_manifest.py
"""
import os
import re
import struct

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = 0x82000000
IMG = open(os.path.join(ROOT, 'out', 'renut_image.bin'), 'rb').read()


def w(a):
    return struct.unpack_from('>I', IMG, a - BASE)[0]


def sections():
    e = struct.unpack_from('<I', IMG, 0x3C)[0]
    assert IMG[e:e + 4] == b'PE\0\0'
    nsec = struct.unpack_from('<H', IMG, e + 6)[0]
    opt = struct.unpack_from('<H', IMG, e + 20)[0]
    o = e + 24 + opt
    out = []
    for i in range(nsec):
        name = IMG[o:o + 8].split(b'\0')[0].decode(errors='replace')
        vsize, va, rsize, raw = struct.unpack_from('<IIII', IMG, o + 8)
        ch = struct.unpack_from('<I', IMG, o + 36)[0]
        out.append((name, BASE + va, vsize, ch))
        o += 40
    return out


def main():
    sec = sections()
    print('PE sections:')
    for name, va, vs, ch in sec:
        print(f'  {name:10s} {va:08X}-{va + vs:08X} {vs:9d} bytes  {"CODE " if ch & 0x20 else ""}{"X " if ch & 0x20000000 else ""}{ch:08X}')
    code = [(va, va + vs) for n, va, vs, ch in sec if ch & 0x20]
    in_code = lambda a: any(lo <= a < hi for lo, hi in code)
    gen = open(os.path.join(ROOT, 'app', 'generated', 'renut_config.h'), errors='replace').read() if os.path.exists(os.path.join(ROOT, 'app', 'generated', 'renut_config.h')) else ''
    m = re.findall(r'REX_CODE_(?:BASE|SIZE)\s+(0x[0-9A-Fa-f]+)', gen)
    print('generated code range macros:', m)

    # setjmp / longjmp by shape over all code.
    sj, lj = [], []
    for lo, hi in code:
        for a in range(lo, hi, 4):
            x = w(a)
            if x == 0xD9C30000:  # stfd f14,0(r3)
                sj.append(a)
            if x == 0xC9C70000:  # lfd f14,0(r7)
                lj.append(a)
    print('stfd f14,0(r3) at', [hex(a) for a in sj], '| lfd f14,0(r7) at', [hex(a) for a in lj])

    funcs = open(os.path.join(ROOT, 'app', 'config', 'renut_funcs.toml')).read()
    addrs = [int(x, 16) for x in re.findall(r'^"0x([0-9A-Fa-f]{8})"', funcs, re.M)]
    bad = 0
    for a in addrs:
        problems = []
        if not in_code(a):
            problems.append('not in code')
        x = w(a)
        if x == 0 or x == 0x60000000:
            problems.append('padding word')
        prev = w(a - 4)
        ends = prev in (0x4E800020, 0x4E800420, 0) or (prev >> 26 == 18 and not prev & 1)
        # A pointer to it somewhere, or a branch to it?
        be = struct.pack('>I', a)
        ptrs = []
        i = IMG.find(be)
        while i != -1 and len(ptrs) < 4:
            if i % 4 == 0:
                ptrs.append(BASE + i)
            i = IMG.find(be, i + 1)
        branches = []
        for lo, hi in code:
            for s in range(max(lo, a - 0x2000000), min(hi, a + 0x2000000), 4):
                y = w(s)
                if y >> 26 == 18:
                    d = y & 0x03FFFFFC
                    if d & 0x02000000:
                        d -= 0x04000000
                    if ((s + d) & 0xFFFFFFFF) == a and not y & 2:
                        branches.append(s)
                        if len(branches) > 3:
                            break
            if len(branches) > 3:
                break
        ok = (not problems) and ends
        bad += 0 if ok else 1
        print(f'{a:08X} {"ok " if ok else "CHECK"} word {x:08X} prev {prev:08X} {"prev ends" if ends else "prev runs on"} data ptrs {[hex(p) for p in ptrs]} branches {[hex(p) for p in branches]} {problems}')
    print(f'{len(addrs)} addresses, {bad} to check by hand')

    for label, bctr, table in (('sub_8217C938', 0x8217C960, 0x8236D1E8), ('sub_8217D288', 0x8217D2B0, 0x8236D1B0)):
        words = [f'{w(bctr - 4 * k):08X}' for k in range(4, -1, -1)]
        ents = [w(table + 4 * k) for k in range(6)]
        print(f'{label}: bctr at {bctr:08X} (last words {" ".join(words)}), table {table:08X}: {[hex(e) for e in ents]} all in code: {all(in_code(e) for e in ents)}')


if __name__ == '__main__':
    main()
