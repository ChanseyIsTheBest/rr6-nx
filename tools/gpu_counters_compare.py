#!/usr/bin/env python3
"""rr6-nx (2026-11-05): the samples each draw passed on the console against the emulator, in the same flyover frame ([gpuctr] lines; Ryujinx
reports samples passed only). Draws are paired by shaders and index count, in order. A draw that passes far fewer on the console is one
whose triangles are lost there.

  python tools/gpu_counters_compare.py <console log> <emulator log>            the frames' sizes
  python tools/gpu_counters_compare.py <console log> <emulator log> F1 F2      the draws of those two frames
"""
import collections
import re
import sys

LINE = re.compile(r"\[gpuctr\] f(\d+) d(\d+) vs ([0-9A-F]{16}) ps ([0-9A-F]{16}) w (\d+) prim (\d+) n (\d+) inst (\d+) \| in (\d+) vs (\d+) clipin (\d+) clipout (\d+) frag (\d+) pass (\d+)")


def load(path):
    frames = collections.OrderedDict()
    for line in open(path, encoding="utf-8", errors="replace"):
        m = LINE.search(line)
        if m and m.group(5) == "1440":
            g = m.groups()
            frames.setdefault(int(g[0]), []).append((g[2][:8], g[3][:8], int(g[6]), int(g[8]), int(g[11]), int(g[12]), int(g[13]), int(g[1])))
    return frames


def main():
    a, b = load(sys.argv[1]), load(sys.argv[2])
    if len(sys.argv) < 5:
        for name, frames in (("console", a), ("emulator", b)):
            print(name, [(f, len(r), sum(x[6] for x in r)) for f, r in frames.items() if len(r) > 20][:40])
        return
    fa, fb = int(sys.argv[3]), int(sys.argv[4])
    ra, rb = a[fa], b[fb]
    print(f"console f{fa}: {len(ra)} draws, {sum(x[6] for x in ra)} samples passed; emulator f{fb}: {len(rb)} draws, {sum(x[6] for x in rb)}")
    queue = collections.defaultdict(list)
    for x in rb:
        queue[x[:3]].append(x)
    rows = []
    unmatched = []
    for x in ra:
        q = queue.get(x[:3])
        if q:
            rows.append((x, q.pop(0)))
        else:
            unmatched.append(x)
    left = [x for q in queue.values() for x in q]
    print(f"paired {len(rows)}; only console {len(unmatched)} ({sum(x[6] for x in unmatched)} samples); only emulator {len(left)} ({sum(x[6] for x in left)} samples)")
    rows.sort(key=lambda p: p[0][6] - p[1][6])
    print("console draw d, vs, ps, n, assembled, clip out, fragments, passed | emulator passed")
    for x, y in rows[:24]:
        print(f"  d{x[7]} {x[0]} {x[1]} n {x[2]} in {x[3]} clipout {x[4]} frag {x[5]} pass {x[6]} | emu pass {y[6]}")
    print("largest gains on the console")
    for x, y in rows[-8:]:
        print(f"  d{x[7]} {x[0]} {x[1]} n {x[2]} in {x[3]} clipout {x[4]} frag {x[5]} pass {x[6]} | emu pass {y[6]}")
    print("only emulator, largest")
    for x in sorted(left, key=lambda x: -x[6])[:12]:
        print(" ", x)


if __name__ == "__main__":
    main()
