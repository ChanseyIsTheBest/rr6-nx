#!/usr/bin/env python3
"""rr6-nx (2026-11-03): the race HUD's lap clock from each capture of a run, on one sheet, each labelled with the capture's real time, to
measure game speed against real time when frames run late.

  python tools/lap_clock_sheet.py <folder> <out.jpg> [--first N] [--last N] [--box 960,150,1280,235] [--cols 5]
"""
import argparse
import glob
import os
import re

from PIL import Image, ImageDraw


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('folder')
    ap.add_argument('out')
    ap.add_argument('--first', type=int, default=0)
    ap.add_argument('--last', type=int, default=0)
    ap.add_argument('--box', default='960,150,1280,235')
    ap.add_argument('--cols', type=int, default=5)
    a = ap.parse_args()
    box = tuple(int(v) for v in a.box.split(','))
    files = sorted(glob.glob(os.path.join(a.folder, '**', '*.png'), recursive=True), key=os.path.basename)
    files = files[a.first:] if not a.last else files[a.first:a.last]
    w, h = box[2] - box[0], box[3] - box[1]
    rows = (len(files) + a.cols - 1) // a.cols
    sheet = Image.new('RGB', (a.cols * w, rows * (h + 14)), (20, 20, 20))
    for i, f in enumerate(files):
        im = Image.open(f).convert('RGB').crop(box)
        x, y = (i % a.cols) * w, (i // a.cols) * (h + 14)
        sheet.paste(im, (x, y + 14))
        m = re.search(r'_(\d+s)\.png$', f)
        ImageDraw.Draw(sheet).text((x + 2, y + 1), m.group(1) if m else os.path.basename(f), fill=(255, 255, 0))
    sheet.save(a.out, quality=90)
    print(a.out, len(files), 'captures')


if __name__ == '__main__':
    main()
