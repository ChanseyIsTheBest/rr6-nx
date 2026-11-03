#!/usr/bin/env python3
"""rr6-nx (2026-11-03): the hot functions of a console rex_profile.log, per thread and in all, named from the ELF of the same
build. tools/switch-cpu-profile.py reads the older [cpu profile] blocks; this log has "N%  pc image+0x... xCOUNT" lines.

  python tools/rex_profile_names.py rex_profile.log rr6-nx.elf [--min-fps 15] [--max-fps 45] [--top 25]

Only windows inside the frame-rate range count, so a race can be read apart from the menus and the loads.
"""
import argparse
import bisect
import collections
import os
import re
import subprocess

head = re.compile(r'^==== ([\d.]+) s \| mode: (\S+) \| game ([\d.]+) fps')
thread = re.compile(r'^-- thread (\d+) "([^"]*)": CPU ([\d.]+)%')
sample = re.compile(r'^\s+[\d.]+%\s+pc image\+0x([0-9a-fA-F]+) x(\d+)')
samples_line = re.compile(r'^\s+(\d+) samples, (\d+)% waiting')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('log')
    ap.add_argument('elf')
    ap.add_argument('--min-fps', type=float, default=15)
    ap.add_argument('--max-fps', type=float, default=45)
    ap.add_argument('--top', type=int, default=25)
    a = ap.parse_args()
    nm = os.path.join(os.environ.get('DEVKITPRO', r'C:\devkitPro'), 'devkitA64', 'bin', 'aarch64-none-elf-nm.exe')
    text = subprocess.run([nm, '--numeric-sort', '--defined-only', a.elf], capture_output=True, text=True, errors='replace', check=True).stdout
    addrs, names = [], []
    for line in text.splitlines():
        f = line.split(None, 2)
        if len(f) == 3 and f[1] in 'tTwW':
            addrs.append(int(f[0], 16))
            names.append(f[2])
    base = addrs[0] & ~0xFFFFF if addrs else 0
    print(f'{len(addrs)} functions, lowest {addrs[0]:#x}')

    def name(off):
        for candidate in (off, off + base):
            i = bisect.bisect_right(addrs, candidate) - 1
            if i >= 0 and candidate - addrs[i] < 0x40000:
                return names[i]
        return f'image+{off:#x}'

    per = collections.defaultdict(collections.Counter)
    every = collections.Counter()
    windows = 0
    keep = False
    cur = None
    waiting = collections.Counter()
    running = collections.Counter()
    for line in open(a.log, encoding='utf-8', errors='replace'):
        m = head.match(line)
        if m:
            keep = a.min_fps <= float(m.group(3)) <= a.max_fps
            windows += keep
            cur = None
            continue
        if not keep:
            continue
        m = thread.match(line)
        if m:
            cur = re.sub(r'[0-9A-F]{8}', '', m.group(2)).strip() or m.group(2)
            continue
        m = samples_line.match(line)
        if m and cur:
            n, w = int(m.group(1)), int(m.group(2))
            waiting[cur] += n * w // 100
            running[cur] += n - n * w // 100
            continue
        m = sample.match(line)
        if m and cur:
            fn = name(int(m.group(1), 16))
            per[cur][fn] += int(m.group(2))
            every[fn] += int(m.group(2))
    total = sum(every.values())
    print(f'{windows} windows between {a.min_fps} and {a.max_fps} fps, {total} samples listed')
    print('all threads:')
    for fn, n in every.most_common(a.top):
        print(f'  {n * 100 / total:5.1f}%  {fn}')
    for t, c in sorted(per.items(), key=lambda kv: -sum(kv[1].values()))[:6]:
        tn = sum(c.values())
        print(f'thread {t}: {tn} listed, running {running[t]}, waiting {waiting[t]}')
        for fn, n in c.most_common(12):
            print(f'  {n * 100 / tn:5.1f}%  {fn}')


if __name__ == '__main__':
    main()
