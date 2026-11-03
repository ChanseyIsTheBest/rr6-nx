#!/usr/bin/env python3
"""rr6-nx (2026-11-03): compares the [paint-tex] lines of two renut logs (the console's and the emulator's): for each
texture slot of the car-paint draw, the fetch constant's format and size words (the address words masked) and the hash
of the texture's first 4 KB of guest data. The same words and hashes on both mean the bytes the console's draw fetches
are the emulator's: the fault is in the upload or the sampling. Different ones put it in the game's code or the reads.
  python tools/paint_tex_compare.py CONSOLE.log EMULATOR.log
"""
import re
import sys
from collections import Counter, defaultdict

LINE = re.compile(r'\[paint-tex\] f(\d+) slot (\d+) words ([0-9A-F]{8}) ([0-9A-F]{8}) ([0-9A-F]{8}) ([0-9A-F]{8}) '
                  r'([0-9A-F]{8}) ([0-9A-F]{8}) page ([0-9A-F]+) hash4k ([0-9A-F]{16})')


def read(path):
    """slot -> Counter of (format words without the address bits, hash)."""
    out = defaultdict(Counter)
    for line in open(path, encoding='utf-8', errors='replace'):
        m = LINE.search(line)
        if not m:
            continue
        slot = int(m.group(2))
        w = [int(m.group(i), 16) for i in range(3, 9)]
        # dword 1 holds the base address (low 20 bits are the page); dword 5 the mip address: masked.
        key = (w[0], w[1] & 0xFFF00000, w[2], w[3], w[4], w[5] & 0xFFF00000, m.group(10))
        out[slot][key] += 1
    return out


def main():
    a, b = read(sys.argv[1]), read(sys.argv[2])
    slots = sorted(set(a) | set(b))
    for slot in slots:
        ka, kb = set(a[slot]), set(b[slot])
        same = ka & kb
        print(f'slot {slot}: console {sum(a[slot].values())} lines, {len(ka)} distinct; emulator {sum(b[slot].values())} lines, '
              f'{len(kb)} distinct; {len(same)} in both')
        for k in sorted(ka - kb, key=lambda k: -a[slot][k])[:3]:
            print(f'   console only  x{a[slot][k]:4}: fmt {k[0]:08X} {k[2]:08X} {k[3]:08X} {k[4]:08X} hash {k[6]}')
        for k in sorted(kb - ka, key=lambda k: -b[slot][k])[:3]:
            print(f'   emulator only x{b[slot][k]:4}: fmt {k[0]:08X} {k[2]:08X} {k[3]:08X} {k[4]:08X} hash {k[6]}')
        # the same format words with a different hash: the same texture header, other bytes
        fa = {k[:6]: k[6] for k in ka}
        fb = {k[:6]: k[6] for k in kb}
        for f in set(fa) & set(fb):
            if fa[f] != fb[f]:
                print(f'   SAME WORDS, DIFFERENT BYTES: fmt {f[0]:08X} {f[2]:08X} {f[3]:08X} {f[4]:08X}: console {fa[f]} emulator {fb[f]}')


if __name__ == '__main__':
    main()
