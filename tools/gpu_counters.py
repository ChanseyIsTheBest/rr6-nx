#!/usr/bin/env python3
"""rr6-nx (2026-11-05): summary of a run's [gpuctr] lines (rr6_diag_gpu_counters), per frame: the scene target's draws, with what the GPU
did with their primitives. With a [geom] log of the same run or an emulator's, the expected triangle count (n minus markers).

  python tools/gpu_counters.py <log> [frame]
"""
import collections
import re
import sys

LINE = re.compile(r"\[gpuctr\] f(\d+) d(\d+) vs ([0-9A-F]{16}) ps ([0-9A-F]{16}) w (\d+) prim (\d+) n (\d+) inst (\d+) \| in (\d+) vs (\d+) clipin (\d+) clipout (\d+) frag (\d+) pass (\d+)")


def main():
    frames = collections.OrderedDict()
    for line in open(sys.argv[1], encoding="utf-8", errors="replace"):
        m = LINE.search(line)
        if m:
            g = m.groups()
            frames.setdefault(int(g[0]), []).append(dict(d=int(g[1]), vs=g[2][:8], ps=g[3][:8], w=int(g[4]), prim=int(g[5]), n=int(g[6]), inst=int(g[7]),
                                                         inp=int(g[8]), vsi=int(g[9]), ci=int(g[10]), co=int(g[11]), frag=int(g[12]), passed=int(g[13])))
    want = int(sys.argv[2]) if len(sys.argv) > 2 else None
    for f, rows in frames.items():
        if want is not None and f != want:
            continue
        main_rows = [r for r in rows if r["w"] == 1440]
        if not main_rows:
            continue
        lost_clip = [r for r in main_rows if r["ci"] and r["co"] < r["ci"]]
        nofrag = [r for r in main_rows if r["co"] and not r["frag"]]
        zero_in = [r for r in main_rows if r["n"] >= 3 and not r["inp"]]
        print(f"f{f}: {len(main_rows)} scene draws; tris in {sum(r['inp'] for r in main_rows)}, clip in {sum(r['ci'] for r in main_rows)}, clip out "
              f"{sum(r['co'] for r in main_rows)}, fragments {sum(r['frag'] for r in main_rows)}; draws assembling none {len(zero_in)}, "
              f"losing some in the clipper {len(lost_clip)}, shading nothing {len(nofrag)}")
        if want is not None:
            for r in main_rows:
                print("  ", r)


if __name__ == "__main__":
    main()
