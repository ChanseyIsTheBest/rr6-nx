#!/usr/bin/env python3
"""rr6-nx (2026-11-02): which guest functions still run XDK 2135's ring code on Renut's device.

Renut's device has this XDK's layout only at its head (the ring, the masks, the tables, the constants). Past the constants it is
N&B's, so the game's own ring helpers read other fields there: sub_8225B828 (BlockUntilIdle) spins on device+0x28FC, which on
Renut's device is a render state. A function that reaches them and is not hooked is a bug waiting for the right value.

Walks the generated code: the helpers given, then whoever calls them, upward, stopping at a hooked function (the hook replaces it).
Prints each unhooked function in the D3D library that reaches a helper, and who outside the library calls it.

  python -I tools/rr6_ring_callers.py [--helpers 8225B5E0,8225B038,8225B4A0,8225B828]
"""
import argparse
import collections
import glob
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEN = os.path.join(ROOT, 'app', 'generated')
HOOKS = os.path.join(ROOT, 'app', 'src', 'renut_engine', 'gpu', 'd3d', 'hooks')
LIB_LO, LIB_HI = 0x8224E000, 0x82264000
DEF = re.compile(r'^(?:DEFINE_REX_FUNC|PPC_FUNC_IMPL|PPC_WEAK_FUNC)\((?:__imp__)?sub_([0-9A-F]{8})\)')
CALL = re.compile(r'\b(?:__imp__)?sub_([0-9A-F]{8})\(ctx')
HOOK = re.compile(r'BANJO_RENUT_HOOK(?:_RAW)?\(sub_([0-9A-F]{8})')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--helpers', default='8225B5E0,8225B038,8225B4A0,8225B828')
    a = ap.parse_args()
    helpers = {int(x, 16) for x in a.helpers.split(',')}

    hooked = set()
    for path in glob.glob(os.path.join(HOOKS, '*.cpp')):
        for line in open(path, encoding='utf-8', errors='replace'):
            m = HOOK.search(line)
            if m:
                hooked.add(int(m.group(1), 16))

    callers = collections.defaultdict(set)  # callee -> callers
    for path in glob.glob(os.path.join(GEN, 'renut_recomp.*.cpp')):
        current = None
        for line in open(path, encoding='utf-8', errors='replace'):
            m = DEF.match(line)
            if m:
                current = int(m.group(1), 16)
                continue
            if current is None or 'sub_' not in line or line.lstrip().startswith('//'):
                continue
            for m in CALL.finditer(line):
                callee = int(m.group(1), 16)
                if callee != current:
                    callers[callee].add(current)

    print(f'{len(hooked)} hooked functions; {len(callers)} functions with callers')
    reach = {}  # function -> the helper it reaches first
    work = collections.deque((h, h) for h in helpers)
    while work:
        fn, helper = work.popleft()
        if fn in reach:
            continue
        reach[fn] = helper
        if fn in hooked:
            continue  # the hook replaces it: nothing above reaches the helper through here
        for caller in callers.get(fn, ()):
            work.append((caller, helper))

    in_lib = sorted(f for f in reach if LIB_LO <= f < LIB_HI and f not in hooked)
    print(f'\nUnhooked functions in the D3D library that reach a helper: {len(in_lib)}')
    for f in in_lib:
        outside = sorted(c for c in callers.get(f, ()) if not LIB_LO <= c < LIB_HI)
        inside = sorted(c for c in callers.get(f, ()) if LIB_LO <= c < LIB_HI)
        print(f'  sub_{f:08X} via {reach[f]:08X}: {len(outside)} game callers {[hex(c) for c in outside[:4]]}, '
              f'{len(inside)} library callers {[hex(c) for c in inside[:4]]}')
    game = sorted(f for f in reach if not LIB_LO <= f < LIB_HI and f not in hooked)
    print(f'\nGame functions above them: {len(game)}')
    print('Hooked functions that stopped the walk:', ', '.join(f'{f:08X}' for f in sorted(reach) if f in hooked))


if __name__ == '__main__':
    main()
