#!/usr/bin/env python3
"""rr6-nx (2026-11-05): checks a run's [readcrc] lines (rr6_diag_read_crc) against the game's files on the PC: every read the game
made on the console is read again from the PC's copy and its CRC-32 compared, so the card's bytes and the console's read path
are checked for exactly what the game loaded.

  python tools/check_read_crc.py <log> [<game folder>]
"""
import collections
import os
import re
import sys
import zlib

LINE = re.compile(r"\[readcrc\] (.+) (\d+) (\d+) ([0-9A-F]{8})\s*$")


def main():
    log = sys.argv[1]
    root = sys.argv[2] if len(sys.argv) > 2 else r"D:\ridge racer 6\game"
    reads = 0
    bytes_checked = 0
    bad = []
    skipped = collections.Counter()
    per_file = collections.Counter()
    handles = {}
    for line in open(log, encoding="utf-8", errors="replace"):
        m = LINE.search(line)
        if not m:
            continue
        name = m.group(1).replace("\\", "/").split("/")[-1]
        offset, size, crc = int(m.group(2)), int(m.group(3)), int(m.group(4), 16)
        path = os.path.join(root, name)
        if not os.path.exists(path):
            skipped[name] += 1
            continue
        f = handles.get(name) or open(path, "rb")
        handles[name] = f
        f.seek(offset)
        data = f.read(size)
        reads += 1
        bytes_checked += size
        per_file[name] += size
        if len(data) != size or zlib.crc32(data) != crc:
            bad.append((name, offset, size, crc, zlib.crc32(data), len(data)))
    print(f"{reads} reads, {bytes_checked / 1e6:.1f} MB checked; {len(bad)} differ")
    for name, n in per_file.most_common():
        print(f"  {name}: {n / 1e6:.1f} MB")
    for name, n in skipped.most_common():
        print(f"  not on the PC: {name}: {n} reads")
    for b in bad[:40]:
        print("DIFFERS", b)


if __name__ == "__main__":
    main()
