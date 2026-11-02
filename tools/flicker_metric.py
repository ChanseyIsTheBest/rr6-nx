#!/usr/bin/env python3
"""rr6-nx (2026-11-03): how much a part of the picture flickers, from a burst of captures (run_pc.ps1 -Every 2 -Max 200).

A pixel "blips" when it jumps away for one capture and comes back: a to b by more than --jump levels, b to c by as much,
and a and c within a quarter of that. A camera creeping along does not do that; a flicker does. Captures are not the same
frames from run to run, so compare the shares between runs over the same stretch, with a control part of the picture.

  python tools/flicker_metric.py <from_s> <to_s> <folder> [<folder> ...] [--jump 24]
"""
import argparse
import glob
import os

import numpy as np
from PIL import Image

BOXES = {
    'trees left': (300, 90, 500, 215),
    'trees right': (700, 140, 870, 230),
    'trees far left': (0, 60, 200, 200),
    'road (control)': (40, 420, 300, 600),
    'white tiles (control)': (560, 60, 700, 130),
}


def seconds(path):
    return int(os.path.basename(path).split('_')[2][:4])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('start', type=int)
    ap.add_argument('end', type=int)
    ap.add_argument('folders', nargs='+')
    ap.add_argument('--jump', type=int, default=24)
    a = ap.parse_args()
    for folder in a.folders:
        files = [f for f in sorted(glob.glob(os.path.join(folder, '*.png'))) if a.start <= seconds(f) <= a.end]
        images = [np.asarray(Image.open(f).convert('L')).astype(int) for f in files]
        print(f'{folder}: {len(files)} captures, {a.start} to {a.end} s')
        for name, (x0, y0, x1, y1) in BOXES.items():
            shares = []
            for p, q, r in zip(images, images[1:], images[2:]):
                p, q, r = p[y0:y1, x0:x1], q[y0:y1, x0:x1], r[y0:y1, x0:x1]
                blip = (np.abs(q - p) > a.jump) & (np.abs(q - r) > a.jump) & (np.abs(p - r) <= a.jump // 4)
                shares.append(blip.mean())
            print(f'   {name:24s} {100 * float(np.mean(shares)):6.3f} % of pixels blip per capture')


if __name__ == '__main__':
    main()
