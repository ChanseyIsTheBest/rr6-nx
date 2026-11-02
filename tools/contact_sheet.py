#!/usr/bin/env python3
"""rr6-nx: a contact sheet of a run's captures, for looking at a run in one image.

  python tools/contact_sheet.py <folder> <out.jpg> [--cols 3] [--width 480] [--first N] [--last N]
"""
import argparse
import glob
import os

from PIL import Image, ImageDraw


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('folder')
    ap.add_argument('out')
    ap.add_argument('--cols', type=int, default=3)
    ap.add_argument('--width', type=int, default=480)
    ap.add_argument('--first', type=int, default=0)
    ap.add_argument('--last', type=int, default=0)
    a = ap.parse_args()
    files = sorted(glob.glob(os.path.join(a.folder, '**', '*.png'), recursive=True), key=os.path.basename)
    files = files[a.first:] if not a.last else files[a.first:a.last]
    if not files:
        print('no captures')
        return
    h = a.width * 9 // 16
    rows = (len(files) + a.cols - 1) // a.cols
    sheet = Image.new('RGB', (a.cols * a.width, rows * h), (20, 20, 20))
    for i, f in enumerate(files):
        im = Image.open(f).convert('RGB').resize((a.width, h))
        d = ImageDraw.Draw(im)
        d.rectangle((0, 0, a.width, 12), fill=(0, 0, 0))
        d.text((2, 0), os.path.basename(f)[8:-4], fill=(255, 255, 0))
        sheet.paste(im, ((i % a.cols) * a.width, (i // a.cols) * h))
    sheet.save(a.out, quality=80)
    print(a.out, len(files), 'captures')


if __name__ == '__main__':
    main()
