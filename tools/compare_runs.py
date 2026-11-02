#!/usr/bin/env python3
"""rr6-nx (2026-11-03): two runs' captures in two columns, the reference on the left. The pairs are chosen by hand as first:second capture
numbers, because a route reaches a screen at different times in different runs.

  python tools/compare_runs.py <reference folder> <our folder> <out.jpg> <pairs, e.g. 1:1,5:6> [--width 480] [--cols 2]
"""
import argparse
import glob
import os
import re

from PIL import Image, ImageDraw


def by_number(folder):
    found = {}
    for f in glob.glob(os.path.join(folder, '**', '*.png'), recursive=True):
        m = re.search(r'captura_(\d+)_', os.path.basename(f))
        if m:
            found[int(m.group(1))] = f
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('reference')
    ap.add_argument('ours')
    ap.add_argument('out')
    ap.add_argument('pairs')
    ap.add_argument('--width', type=int, default=480)
    ap.add_argument('--cols', type=int, default=2, help='pairs across')
    a = ap.parse_args()
    ref, our = by_number(a.reference), by_number(a.ours)
    pairs = [tuple(int(v) for v in p.split(':')) for p in a.pairs.split(',')]
    h = a.width * 9 // 16
    rows = (len(pairs) + a.cols - 1) // a.cols
    sheet = Image.new('RGB', (a.cols * 2 * a.width, rows * h), (20, 20, 20))
    for i, (r, o) in enumerate(pairs):
        for k, (files, n, label) in enumerate(((ref, r, 'ref'), (our, o, 'ours'))):
            if n not in files:
                continue
            im = Image.open(files[n]).convert('RGB').resize((a.width, h))
            ImageDraw.Draw(im).text((3, 1), f'{label} {n}', fill=(255, 255, 0))
            sheet.paste(im, ((i % a.cols) * 2 * a.width + k * a.width, (i // a.cols) * h))
    sheet.save(a.out, quality=85)
    print(a.out, len(pairs), 'pairs')


if __name__ == '__main__':
    main()
