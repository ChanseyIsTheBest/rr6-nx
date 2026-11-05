#!/usr/bin/env python3
"""rr6-nx (2026-11-05): compares the [geom] lines (rr6_diag_geometry_frames) of two runs. A mesh is its shader, primitive, index
count, the hash of its guest indices and, per stream, the stride, the vertex count and the hash of its converted vertices: bytes
that do not depend on where the run allocated them. A mesh of the first run the second never drew, with the same indices and shader
in the second, is data that differs.

  python tools/compare_geom.py <console log> <reference log> [--frames]
"""
import collections
import re
import sys

GEOM = re.compile(r"\[geom\] f(\d+) vs ([0-9A-F]{16}) prim (\d+) n (\d+) start (\d+) base (-?\d+) is32 (\d) lo (\d+) hi (\d+) "
                  r"resets (\d+) guest ([0-9A-F]{16}) host (\d+) (\d) ([0-9A-F]{16}) first (\d+) range (\d+) whole (\d)(.*)$")
STREAM = re.compile(r"\| s(\d+) stride (\d+) host (\d+) vertices (\d+) count (\d+) endian (\d+) ([0-9A-F]{16})")


def read(path):
    meshes = {}
    frames = collections.Counter()
    for line in open(path, encoding="utf-8", errors="replace"):
        m = GEOM.search(line)
        if not m:
            continue
        frame, vs, prim, n, start, base, is32, lo, hi, resets, guest, host_n, host_size, host_hash, first, rng, whole, rest = m.groups()
        streams = tuple((s[0], s[1], s[4], s[6]) for s in STREAM.findall(rest))
        key = (vs, prim, n, guest, streams)
        frames[frame] += 1
        e = meshes.setdefault(key, dict(count=0, whole=0, resets=resets, hi=hi, lo=lo, first_frame=frame, range=rng, host=(host_n, host_size, host_hash)))
        e["count"] += 1
        e["whole"] += int(whole)
    return meshes, frames


def main():
    a, a_frames = read(sys.argv[1])
    b, b_frames = read(sys.argv[2])
    print(f"first:  {len(a)} meshes in {len(a_frames)} frames ({sum(a_frames.values())} lines)")
    print(f"second: {len(b)} meshes in {len(b_frames)} frames ({sum(b_frames.values())} lines)")
    b_keys = set(b)
    b_index = collections.defaultdict(list)
    for k in b:
        b_index[(k[0], k[1], k[2], k[3])].append(k)
    same = [k for k in a if k in b_keys]
    print(f"in both: {len(same)} ({100 * len(same) / max(1, len(a)):.1f} % of the first's)")
    other = [k for k in a if k not in b_keys]
    idx_match = [k for k in other if (k[0], k[1], k[2], k[3]) in b_index]
    print(f"only in the first: {len(other)}; of those with the same indices and shader in the second (vertices differ): {len(idx_match)}")
    shown = 0
    for k in idx_match:
        if shown >= 30:
            break
        shown += 1
        print(" VERTICES DIFFER vs", k[0], "prim", k[1], "n", k[2], "guest", k[3])
        print("   first ", k[4])
        for o in b_index[(k[0], k[1], k[2], k[3])][:2]:
            print("   second", o[4])
    no_idx = [k for k in other if (k[0], k[1], k[2], k[3]) not in b_index]
    by_vs = collections.Counter(k[0] for k in no_idx)
    print(f"no draw in the second with these indices: {len(no_idx)}; by vertex shader: {by_vs.most_common(12)}")
    b_host = collections.defaultdict(set)
    for k, e in b.items():
        b_host[(k[0], k[1], k[2], k[3])].add(e["host"])
    diff_host = [(k, a[k]["host"], b_host[(k[0], k[1], k[2], k[3])]) for k in same if a[k]["host"] not in b_host[(k[0], k[1], k[2], k[3])]]
    print(f"same mesh, different host indices: {len(diff_host)}")
    for k, ha, hb in diff_host[:10]:
        print("  vs", k[0], "n", k[2], ha, hb)


if __name__ == "__main__":
    main()
