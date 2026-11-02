#!/usr/bin/env python3
"""rr6-nx (2026-11-03): two clips from two recordings of the same stretch (banjo_record_s), for looking at the trees, and how
much the trees change from one frame to the next in each. Game imagery: stays in out/visual_diffs, never committed.

  python tools/tree_video.py <ours.mp4> <reference.mp4> <out folder>
"""
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

FFMPEG = r'C:\ffmpeg\ffmpeg.exe'
STILL_FROM, STILL_LENGTH = 6, 25   # seconds: the car braked, nothing but the trees should move
DRIVE_FROM, DRIVE_LENGTH = 42, 30  # seconds: moving off, past the trees
ZOOM = (280, 60, 620, 200)         # x, y, width, height in the 1280 x 720 picture
BOXES = {'trees left': (300, 90, 500, 215), 'trees right': (700, 140, 870, 230), 'trees far left': (0, 60, 200, 200),
         'road (control)': (40, 420, 300, 600)}


def label(path, text, width, height=40):
    im = Image.new('RGB', (width, height), (20, 20, 20))
    try:
        font = ImageFont.truetype(r'C:\Windows\Fonts\arial.ttf', 26)
    except OSError:
        font = ImageFont.load_default()
    ImageDraw.Draw(im).text((10, 5), text, fill=(255, 255, 0), font=font)
    im.save(path)


def encode(args, out):
    subprocess.run([FFMPEG, '-loglevel', 'error', '-y'] + args +
                   ['-c:v', 'h264_nvenc', '-preset', 'p5', '-rc', 'vbr', '-cq', '21', '-b:v', '0', '-pix_fmt', 'yuv420p', out],
                   check=True)
    print(out, round(os.path.getsize(out) / 1e6, 1), 'MB')


def frames(path, start, seconds):
    """Grey frames, each new one only (a late capture repeats the last frame in the recording)."""
    w, h = 1280, 720
    p = subprocess.run([FFMPEG, '-loglevel', 'error', '-ss', str(start), '-t', str(seconds), '-i', path, '-f', 'rawvideo',
                        '-pix_fmt', 'gray', '-'], capture_output=True, check=True)
    all_frames = np.frombuffer(p.stdout, dtype=np.uint8).reshape(-1, h, w).astype(np.int16)
    keep = [0] + [i for i in range(1, len(all_frames)) if np.abs(all_frames[i] - all_frames[i - 1]).mean() > 0.002]
    return all_frames[keep], len(all_frames)


def measure(name, path):
    f, total = frames(path, STILL_FROM + 5, 8)
    print(f'{name}: {total} frames, {len(f)} of them new')
    for box, (x0, y0, x1, y1) in BOXES.items():
        part = f[:, y0:y1, x0:x1]
        step = np.abs(part[1:] - part[:-1])
        print(f'   {box:16s} mean change a frame {step.mean():6.2f}; pixels jumping over 24 levels a frame '
              f'{100 * (step > 24).mean():6.2f} %')


def main():
    ours, ref, out = sys.argv[1:4]
    os.makedirs(out, exist_ok=True)
    x, y, w, h = ZOOM
    label(os.path.join(out, 'l_ours.png'), 'OURS (Renut, Direct3D 12, shipped settings)', w * 2)
    label(os.path.join(out, 'l_ref.png'), 'REFERENCE (emulated GPU)', w * 2)
    label(os.path.join(out, 'l_both.png'), 'LEFT: ours    RIGHT: reference', 2560)
    crop = f'crop={w}:{h}:{x}:{y},scale={w * 2}:{h * 2}:flags=neighbor'
    encode(['-ss', str(STILL_FROM), '-t', str(STILL_LENGTH), '-i', ours, '-ss', str(STILL_FROM), '-t', str(STILL_LENGTH), '-i', ref,
            '-i', os.path.join(out, 'l_ours.png'), '-i', os.path.join(out, 'l_ref.png'),
            '-filter_complex', f'[0:v]{crop}[a];[1:v]{crop}[b];[2:v][a][3:v][b]vstack=inputs=4[v]', '-map', '[v]', '-r', '60'],
           os.path.join(out, 'trees_1_still_zoom_ours_top_reference_bottom.mp4'))
    encode(['-ss', str(DRIVE_FROM), '-t', str(DRIVE_LENGTH), '-i', ours, '-ss', str(DRIVE_FROM), '-t', str(DRIVE_LENGTH), '-i', ref,
            '-i', os.path.join(out, 'l_both.png'),
            '-filter_complex', '[0:v][1:v]hstack[h];[2:v][h]vstack[v]', '-map', '[v]', '-r', '60'],
           os.path.join(out, 'trees_2_driving_ours_left_reference_right.mp4'))
    measure('ours', ours)
    measure('reference', ref)


if __name__ == '__main__':
    main()
