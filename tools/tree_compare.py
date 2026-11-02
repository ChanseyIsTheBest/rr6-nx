#!/usr/bin/env python3
"""rr6-nx (2026-11-03): tree flicker from recordings (banjo_record_s) of a still camera: frame-to-frame change, and pixels that
blip: jump for one new frame and come back, which sway does not do at this speed. Then a zoomed clip of the first two, one
above the other. Game imagery: stays in out/visual_diffs.

  python tools/tree_compare.py <start_s> <seconds> <out.mp4 or -> label=video.mp4 [label=video.mp4 ...]
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


def frames(path, start, seconds):
    p = subprocess.run([FFMPEG, '-loglevel', 'error', '-ss', str(start), '-t', str(seconds), '-i', path, '-f', 'rawvideo',
                        '-pix_fmt', 'gray', '-'], capture_output=True, check=True)
    all_frames = np.frombuffer(p.stdout, dtype=np.uint8).reshape(-1, 720, 1280).astype(np.int16)
    keep = [0] + [i for i in range(1, len(all_frames)) if np.abs(all_frames[i] - all_frames[i - 1]).mean() > 0.002]
    return all_frames[keep], len(all_frames)


def measure(label, path, start, seconds):
    f, total = frames(path, start, seconds)
    per_s = len(f) / seconds
    print(f'{label}: {len(f)} new of {total} frames, {per_s:.1f} a second')
    for box, (x0, y0, x1, y1) in BOXES.items():
        part = f[:, y0:y1, x0:x1]
        step = np.abs(part[1:] - part[:-1])
        blip = (np.abs(part[1:-1] - part[:-2]) > 24) & (np.abs(part[1:-1] - part[2:]) > 24) & (np.abs(part[:-2] - part[2:]) <= 6)
        print(f'   {box:16s} jumps over 24 levels {100 * (step > 24).mean():6.3f} % a frame, {100 * (step > 24).mean() * per_s:6.2f} % a second; '
              f'blips {100 * blip.mean():6.3f} % a frame, {100 * blip.mean() * per_s:6.2f} % a second')


def label_png(path, text, width):
    im = Image.new('RGB', (width, 40), (20, 20, 20))
    try:
        font = ImageFont.truetype(r'C:\Windows\Fonts\arial.ttf', 26)
    except OSError:
        font = ImageFont.load_default()
    ImageDraw.Draw(im).text((10, 5), text, fill=(255, 255, 0), font=font)
    im.save(path)


def main():
    start, seconds, out = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
    runs = [a.split('=', 1) for a in sys.argv[4:]]
    for label, path in runs:
        measure(label, path, start, seconds)
    if out == '-':
        return
    x, y, w, h = ZOOM
    crop = f'crop={w}:{h}:{x}:{y},scale={w * 2}:{h * 2}:flags=neighbor'
    args, chain = [], []
    for i, (label, path) in enumerate(runs[:2]):
        png = out + f'.l{i}.png'
        label_png(png, label, w * 2)
        args += ['-ss', str(start), '-t', '25', '-i', path, '-i', png]
        chain.append(f'[{2 * i}:v]{crop}[v{i}]')
    chain.append('[1:v][v0][3:v][v1]vstack=inputs=4[v]')
    subprocess.run([FFMPEG, '-loglevel', 'error', '-y'] + args + ['-filter_complex', ';'.join(chain), '-map', '[v]', '-r', '60',
                    '-c:v', 'h264_nvenc', '-preset', 'p5', '-rc', 'vbr', '-cq', '21', '-b:v', '0', '-pix_fmt', 'yuv420p', out], check=True)
    for i in range(2):
        os.remove(out + f'.l{i}.png')
    print(out, round(os.path.getsize(out) / 1e6, 1), 'MB')


if __name__ == '__main__':
    main()
