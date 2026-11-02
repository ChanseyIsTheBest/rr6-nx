#!/usr/bin/env python3
"""rr6-nx: two captures side by side, with the absolute difference under them, for the visual difference list in docs/rr6-notes.md.

  python tools/side_by_side.py <reference.png> <ours.png> <out.jpg> [--width 640] [--crop x0,y0,x1,y1]
"""
import argparse

from PIL import Image, ImageChops, ImageDraw


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('reference')
    ap.add_argument('ours')
    ap.add_argument('out')
    ap.add_argument('--width', type=int, default=640)
    ap.add_argument('--crop', default='')
    a = ap.parse_args()
    ref = Image.open(a.reference).convert('RGB')
    our = Image.open(a.ours).convert('RGB')
    if our.size != ref.size:
        our = our.resize(ref.size)
    if a.crop:
        box = tuple(int(v) for v in a.crop.split(','))
        ref, our = ref.crop(box), our.crop(box)
    diff = ImageChops.difference(ref, our)
    bbox = diff.getbbox()
    grey = diff.convert('L')
    changed = sum(grey.histogram()[9:])
    total = grey.size[0] * grey.size[1]
    print(f'{changed} of {total} pixels differ by more than 8 ({100.0 * changed / total:.2f} %), box {bbox}')
    h = a.width * ref.size[1] // ref.size[0]
    sheet = Image.new('RGB', (a.width * 2, h * 2), (20, 20, 20))
    for i, (im, label) in enumerate(((ref, 'reference'), (our, 'ours'), (diff, 'difference'))):
        im = im.resize((a.width, h))
        ImageDraw.Draw(im).text((4, 2), label, fill=(255, 255, 0))
        sheet.paste(im, ((i % 2) * a.width, (i // 2) * h))
    sheet.save(a.out, quality=85)


if __name__ == '__main__':
    main()
