#!/usr/bin/env python3
"""rr6-nx (2026-11-03): the same crop of the reference and of up to two of our captures, side by side, labelled, for the visual difference
list. Captures of a race are not the same frame: for looking, not for a pixel count.

  python tools/three_way.py <out.jpg> <box x0,y0,x1,y1> <scale> label=path [label=path ...]
"""
import sys

from PIL import Image, ImageDraw


def main():
    out, box, scale = sys.argv[1], tuple(int(v) for v in sys.argv[2].split(',')), float(sys.argv[3])
    pairs = [a.split('=', 1) for a in sys.argv[4:]]
    w, h = int((box[2] - box[0]) * scale), int((box[3] - box[1]) * scale)
    sheet = Image.new('RGB', (w * len(pairs), h + 14), (20, 20, 20))
    for i, (label, path) in enumerate(pairs):
        im = Image.open(path).convert('RGB').crop(box).resize((w, h), Image.LANCZOS)
        sheet.paste(im, (i * w, 14))
        ImageDraw.Draw(sheet).text((i * w + 3, 1), label, fill=(255, 255, 0))
    sheet.save(out, quality=92)
    print(out)


if __name__ == '__main__':
    main()
