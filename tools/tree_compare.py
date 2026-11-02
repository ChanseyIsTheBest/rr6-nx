#!/usr/bin/env python3
"""rr6-nx (2026-11-03): tree flicker from recordings (banjo_record_s) of a still camera. The still stretch is found in each
recording from the road: a stretch where the road does not change. A recording without one is reported and not measured (the
game's attract demo looks like a race at a glance). In that stretch:
  - jumps: tree pixels changing by over 24 levels a new frame; sway counts too;
  - blips: a pixel jumps for one new frame and comes back; sway at this speed does not;
  - second difference: mean |x(t) - 2 x(t+1) + x(t+2)|, which grows with flicker and hardly with slow movement.
Two runs of the same code show what these figures do by chance: read a change against that.

  python tools/tree_compare.py <seconds> <out.mp4 or -> label=video.mp4 [label=video.mp4 ...]
"""
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

FFMPEG = r'C:\ffmpeg\ffmpeg.exe'
ZOOM = (280, 60, 620, 200)
BOXES = {'trees left': (300, 90, 500, 215), 'trees right': (700, 140, 870, 230), 'trees far left': (0, 60, 200, 200),
         'road (control)': (40, 420, 300, 600)}
ROAD = BOXES['road (control)']


def gray(path, start=0, seconds=None, fps=None):
    args = [FFMPEG, '-loglevel', 'error', '-ss', str(start)]
    if seconds:
        args += ['-t', str(seconds)]
    args += ['-i', path]
    if fps:
        args += ['-vf', f'fps={fps}']
    args += ['-f', 'rawvideo', '-pix_fmt', 'gray', '-']
    p = subprocess.run(args, capture_output=True, check=True)
    return np.frombuffer(p.stdout, dtype=np.uint8).reshape(-1, 720, 1280)


def still_start(path, seconds):
    """The first second from which the road stays still for 'seconds', or None."""
    x0, y0, x1, y1 = ROAD
    f = gray(path, fps=1)[:, y0:y1, x0:x1].astype(np.int16)
    moves = np.abs(f[1:] - f[:-1]).mean(axis=(1, 2))
    run = 0
    for i, m in enumerate(moves):
        run = run + 1 if m < 0.5 else 0
        if run >= seconds:
            return i + 1 - seconds + 1
    return None


def measure(label, path, seconds):
    start = still_start(path, seconds)
    if start is None:
        print(f'{label}: NO STILL STRETCH of {seconds} s: not measured')
        return None
    raw = gray(path, start, seconds).astype(np.int16)
    keep = [0] + [i for i in range(1, len(raw)) if np.abs(raw[i] - raw[i - 1]).mean() > 0.002]
    f = raw[keep]
    per_s = len(f) / seconds
    print(f'{label}: still from {start} s, {len(f)} new of {len(raw)} frames, {per_s:.1f} a second')
    for box, (x0, y0, x1, y1) in BOXES.items():
        part = f[:, y0:y1, x0:x1]
        step = np.abs(part[1:] - part[:-1])
        blip = (np.abs(part[1:-1] - part[:-2]) > 24) & (np.abs(part[1:-1] - part[2:]) > 24) & (np.abs(part[:-2] - part[2:]) <= 6)
        second = np.abs(part[:-2] - 2 * part[1:-1] + part[2:])
        print(f'   {box:16s} jumps {100 * (step > 24).mean():6.3f} % a frame; blips {100 * blip.mean():6.3f} % a frame, '
              f'{100 * blip.mean() * per_s:6.2f} % a second; second difference {second.mean():6.3f}')
    return start


def label_png(path, text, width):
    im = Image.new('RGB', (width, 40), (20, 20, 20))
    try:
        font = ImageFont.truetype(r'C:\Windows\Fonts\arial.ttf', 26)
    except OSError:
        font = ImageFont.load_default()
    ImageDraw.Draw(im).text((10, 5), text, fill=(255, 255, 0), font=font)
    im.save(path)


def main():
    seconds, out = int(sys.argv[1]), sys.argv[2]
    runs = [a.split('=', 1) for a in sys.argv[3:]]
    starts = [measure(label, path, seconds) for label, path in runs]
    if out == '-' or None in starts[:2]:
        return
    x, y, w, h = ZOOM
    crop = f'crop={w}:{h}:{x}:{y},scale={w * 2}:{h * 2}:flags=neighbor'
    args, chain = [], []
    for i, (label, path) in enumerate(runs[:2]):
        png = out + f'.l{i}.png'
        label_png(png, label, w * 2)
        args += ['-ss', str(starts[i]), '-t', str(seconds), '-i', path, '-i', png]
        chain.append(f'[{2 * i}:v]{crop}[v{i}]')
    chain.append('[1:v][v0][3:v][v1]vstack=inputs=4[v]')
    subprocess.run([FFMPEG, '-loglevel', 'error', '-y'] + args + ['-filter_complex', ';'.join(chain), '-map', '[v]', '-r', '60',
                    '-c:v', 'h264_nvenc', '-preset', 'p5', '-rc', 'vbr', '-cq', '21', '-b:v', '0', '-pix_fmt', 'yuv420p', out], check=True)
    for i in range(2):
        os.remove(out + f'.l{i}.png')
    print(out, round(os.path.getsize(out) / 1e6, 1), 'MB')


if __name__ == '__main__':
    main()
