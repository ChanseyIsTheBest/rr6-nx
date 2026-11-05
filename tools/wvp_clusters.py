#!/usr/bin/env python3
"""rr6-nx (2026-11-05): per logged frame, the [wvp] lines (rr6_diag_geometry_frames) grouped by matrix: how many main-target draws used
each world-view-projection and which vertex shaders. A static mesh in the wrong place has either another matrix than its neighbours
or the same one; this shows which.

  python tools/wvp_clusters.py <log> [first frame] [last frame]
"""
import collections
import re
import sys

LINE = re.compile(r"^\[([^\]]+)\].*\[wvp\] f(\d+) vs ([0-9A-F]{16}) (.*)$")


def main():
    path = sys.argv[1]
    lo = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    hi = int(sys.argv[3]) if len(sys.argv) > 3 else 1 << 60
    frames = collections.OrderedDict()
    for line in open(path, encoding="utf-8", errors="replace"):
        m = LINE.match(line)
        if not m:
            continue
        f = int(m.group(2))
        if not lo <= f <= hi:
            continue
        nums = tuple(float(x) for x in m.group(4).replace("|", " ").split())
        frames.setdefault(f, dict(time=m.group(1), rows=[]))["rows"].append((m.group(3), nums))
    for f, d in frames.items():
        groups = collections.defaultdict(list)
        for vs, nums in d["rows"]:
            groups[tuple(round(x, 2) for x in nums)].append(vs)
        print(f"f{f} {d['time'][11:23]}: {len(d['rows'])} draws, {len(groups)} matrices")
        top = sorted(groups.items(), key=lambda kv: -len(kv[1]))
        for key, vss in top[:6]:
            c = collections.Counter(vss)
            biggest = max(abs(x) for x in key)
            print(f"   {len(vss):4d} draws, |max| {biggest:10.2f}, row3 {key[12:16]}, vs {[v[:8] for v, _ in c.most_common(3)]}")
        odd = [(k, v) for k, v in top if max(abs(x) for x in k) > 1e5]
        if odd:
            print(f"   {sum(len(v) for _, v in odd)} draws with a value over 1e5")


if __name__ == "__main__":
    main()
