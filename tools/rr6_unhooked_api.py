#!/usr/bin/env python3
"""rr6-nx (2026-11-02): the D3D library functions this game's code calls directly, and whether Renut replaces each.

A function left to the game runs XDK 2135's code on Renut's device, whose layout matches this XDK only at its head. That is right
for pure header work on the game's own objects (zuma-nx's split) and wrong for anything reading device fields past the constants.
Prints each unhooked one with the device offsets it reads or writes through its first argument, so the wrong ones stand out.

  python -I tools/rr6_unhooked_api.py
"""
import collections
import glob
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEN = os.path.join(ROOT, 'app', 'generated')
HOOKS = os.path.join(ROOT, 'app', 'src', 'renut_engine', 'gpu', 'd3d', 'hooks')
LIB_LO, LIB_HI = 0x8224E000, 0x82264000
CONSTANTS_END = 0x2820  # past here Renut's device is N&B's layout, not this XDK's
DEF = re.compile(r'^(?:DEFINE_REX_FUNC|PPC_FUNC_IMPL|PPC_WEAK_FUNC)\((?:__imp__)?sub_([0-9A-F]{8})\)')
CALL = re.compile(r'\b(?:__imp__)?sub_([0-9A-F]{8})\(ctx')
HOOK = re.compile(r'BANJO_RENUT_HOOK(?:_RAW|_SHARED)?\(sub_([0-9A-F]{8})')
MEM = re.compile(r'//\s+(?:lwz|stw|lbz|stb|lhz|sth|ld|std|lwzx|stwx)\s+r\d+,(-?\d+)\(r(\d+)\)')


def main():
    hooked = set()
    names = {}
    for path in glob.glob(os.path.join(HOOKS, '*.cpp')):
        for line in open(path, encoding='utf-8', errors='replace'):
            m = HOOK.search(line)
            if m:
                hooked.add(int(m.group(1), 16))
    callers = collections.defaultdict(set)
    high = collections.defaultdict(set)  # function -> offsets past the constants it touches, by any register
    for path in glob.glob(os.path.join(GEN, 'renut_recomp.*.cpp')):
        current = None
        for line in open(path, encoding='utf-8', errors='replace'):
            m = DEF.match(line)
            if m:
                current = int(m.group(1), 16)
                continue
            if current is None:
                continue
            if LIB_LO <= current < LIB_HI:
                m = MEM.search(line)
                if m and int(m.group(1)) >= CONSTANTS_END:
                    high[current].add(int(m.group(1)))
            if line.lstrip().startswith('//'):
                continue
            for m in CALL.finditer(line):
                callee = int(m.group(1), 16)
                if callee != current:
                    callers[callee].add(current)

    entries = sorted(f for f, c in callers.items() if LIB_LO <= f < LIB_HI and any(not LIB_LO <= x < LIB_HI for x in c))
    print(f'{len(entries)} library functions called from game code; {sum(1 for f in entries if f in hooked)} hooked')

    def reach(root):
        seen, work = set(), [root]
        while work:
            f = work.pop()
            if f in seen or f in hooked:
                continue
            seen.add(f)
            work.extend(g for g, c in callers.items() if f in c and LIB_LO <= g < LIB_HI)
        return seen

    for f in entries:
        if f in hooked:
            continue
        below = reach(f)
        offsets = sorted(set().union(*(high[x] for x in below))) if below else []
        game = sorted(c for c in callers[f] if not LIB_LO <= c < LIB_HI)
        mark = 'DEVICE? ' if offsets else 'header  '
        print(f'{mark} sub_{f:08X}: {len(game)} game callers, {len(below)} functions below, past-constants offsets '
              f'{[hex(o) for o in offsets[:8]]}{"..." if len(offsets) > 8 else ""}')


if __name__ == '__main__':
    main()
