#!/usr/bin/env python3
"""rr6-nx (2026-11-03): pictures and stats of rr6_diag_texture_dump's files (docs/rr6-notes.md; the mechanism is
sasrt-nx's shadow dump, tools/shadow_dump_view.py there).

    python -I tools/texture_dump_view.py <texture_dump folder> [out folder] [--compare <other texture_dump folder>]

Each file is w<window>_f<render frame>_<serial>_s<pixel slot>_<guest address>_<w>x<h>_fmt<plume format>_m<mip>_l<layer>.bin:
one mip level of one layer of a texture the car-paint draw sampled, as the GPU held it, raw texels row by row (the
row pitch stripped): fmt20 R8G8B8A8_UNORM, fmt24 B8G8R8A8_UNORM, fmt10 R16G16B16A16_FLOAT, fmt38 R8G8_UNORM, fmt50
R8_UNORM, fmt34 R32_FLOAT, and the block formats fmt55/56 BC1, fmt58/59 BC2, fmt61/62 BC3, fmt64 BC4, fmt67 BC5
(decoded here; BC5 shown as a normal map with its blue rebuilt).

Writes, per window and texture level (slot, address, size, format, mip), one sheet: a row per frame, the layers side
by side (a cube's six faces), and stats.txt: per file the mean of each channel, the share of texels that are all
zero, the share equal to the first texel, and a hash of the bytes. With --compare, a texture level in both folders by
(slot, address, size, format, mip, layer) is compared file for file in order: equal bytes, or the mean absolute
difference per channel. The emulator's dump of the same scene is the reference: a static texture (the normal map)
must be equal at every level; a render target (the reflection cube) differs by the frame, but black or noise in the
console's shows up in its means, and a level that is right in the emulator and wrong on the console is the fault.
"""
import hashlib
import os
import re
import sys
from collections import defaultdict

import numpy as np
from PIL import Image

NAME = re.compile(r'w(\d+)_f(\d+)_(\d+)_s(\d+)_([0-9A-F]{8})_(\d+)x(\d+)_fmt(\d+)_m(\d+)_l(\d+)\.bin$')

# plume RenderFormat value -> (bytes per texel or per 4x4 block, block, decoder name)
FORMATS = {
    20: (4, 1, 'rgba8'), 24: (4, 1, 'bgra8'), 10: (8, 1, 'rgba16f'), 38: (2, 1, 'rg8'), 50: (1, 1, 'r8'),
    34: (4, 1, 'r32f'), 27: (4, 1, 'rg16'),
    55: (8, 4, 'bc1'), 56: (8, 4, 'bc1'), 58: (16, 4, 'bc2'), 59: (16, 4, 'bc2'), 61: (16, 4, 'bc3'),
    62: (16, 4, 'bc3'), 64: (8, 4, 'bc4'), 67: (16, 4, 'bc5'),
}


def rgb565(c):
    r = ((c >> 11) & 31).astype(np.uint16)
    g = ((c >> 5) & 63).astype(np.uint16)
    b = (c & 31).astype(np.uint16)
    return np.stack([(r * 255 + 15) // 31, (g * 255 + 31) // 63, (b * 255 + 15) // 31], axis=-1).astype(np.int32)


def bc_colour_blocks(b, one_bit_alpha):
    """b: (n, 8) uint8 -> (n, 16, 4) uint8 (the colour block of BC1, or the lower half of BC2/BC3)."""
    c0 = b[:, 0].astype(np.uint16) | (b[:, 1].astype(np.uint16) << 8)
    c1 = b[:, 2].astype(np.uint16) | (b[:, 3].astype(np.uint16) << 8)
    p0, p1 = rgb565(c0), rgb565(c1)
    four = (c0 > c1) | (not one_bit_alpha)
    p2 = np.where(four[:, None], (2 * p0 + p1) // 3, (p0 + p1) // 2)
    p3 = np.where(four[:, None], (p0 + 2 * p1) // 3, 0)
    palette = np.stack([p0, p1, p2, p3], axis=1).astype(np.uint8)  # (n, 4, 3)
    alpha = np.full((b.shape[0], 4), 255, np.uint8)
    alpha[:, 3] = np.where(four, 255, 0)
    idx = np.stack([(b[:, 4 + y] >> (2 * x)) & 3 for y in range(4) for x in range(4)], axis=1)  # (n, 16)
    rgb = np.take_along_axis(palette, idx[:, :, None], axis=1)
    a = np.take_along_axis(alpha, idx, axis=1)
    return np.concatenate([rgb, a[:, :, None]], axis=2)


def bc_alpha_blocks(b):
    """b: (n, 8) uint8 -> (n, 16) uint8 (BC3's alpha, BC4's red, BC5's red and green)."""
    a0, a1 = b[:, 0].astype(np.int32), b[:, 1].astype(np.int32)
    eight = a0 > a1
    pal = np.zeros((b.shape[0], 8), np.int32)
    pal[:, 0], pal[:, 1] = a0, a1
    for i in range(1, 7):
        pal[:, i + 1] = np.where(eight, ((7 - i) * a0 + i * a1) // 7, ((5 - i) * a0 + i * a1) // 5 if i <= 4 else 0)
    pal[:, 7] = np.where(eight, pal[:, 7], 255)
    pal[:, 6] = np.where(eight, pal[:, 6], 0)
    bits = np.zeros(b.shape[0], np.uint64)
    for i in range(6):
        bits |= b[:, 2 + i].astype(np.uint64) << np.uint64(8 * i)
    idx = np.stack([((bits >> np.uint64(3 * i)) & np.uint64(7)).astype(np.int64) for i in range(16)], axis=1)
    return np.take_along_axis(pal, idx, axis=1).astype(np.uint8)


def blocks_to_image(texels, bw, bh):
    """(bw*bh, 16, c) block texels -> (bh*4, bw*4, c)."""
    c = texels.shape[2]
    return texels.reshape(bh, bw, 4, 4, c).transpose(0, 2, 1, 3, 4).reshape(bh * 4, bw * 4, c)


def load(path, w, h, fmt):
    """The file as (h, w, channels) uint8 (RGBA, or the channels the format has), or a float array; None if cut."""
    if fmt not in FORMATS:
        return None
    size, block, kind = FORMATS[fmt]
    raw = np.fromfile(path, dtype=np.uint8)
    if block == 1:
        if raw.size != w * h * size:
            return None
        if kind == 'rgba8':
            return raw.reshape(h, w, 4)
        if kind == 'bgra8':
            return raw.reshape(h, w, 4)[:, :, [2, 1, 0, 3]]
        if kind == 'rg8':
            return raw.reshape(h, w, 2)
        if kind == 'r8':
            return raw.reshape(h, w, 1)
        if kind == 'rgba16f':
            return raw.view('<f2').reshape(h, w, 4).astype(np.float32)
        if kind == 'r32f':
            return raw.view('<f4').reshape(h, w, 1)
        if kind == 'rg16':
            return (raw.view('<u2').reshape(h, w, 2) >> 8).astype(np.uint8)
        return None
    bw, bh = (w + 3) // 4, (h + 3) // 4
    if raw.size != bw * bh * size:
        return None
    b = raw.reshape(bw * bh, size)
    if kind == 'bc1':
        return blocks_to_image(bc_colour_blocks(b, True), bw, bh)[:h, :w]
    if kind == 'bc2':
        rgba = bc_colour_blocks(b[:, 8:], False)
        a = np.stack([(b[:, 2 * i // 4 + (0 if i % 4 < 2 else 1)] >> (4 * (i % 2))) & 15 for i in range(16)], axis=1)
        rgba[:, :, 3] = (a * 17).astype(np.uint8)
        return blocks_to_image(rgba, bw, bh)[:h, :w]
    if kind == 'bc3':
        rgba = bc_colour_blocks(b[:, 8:], False)
        rgba[:, :, 3] = bc_alpha_blocks(b[:, :8])
        return blocks_to_image(rgba, bw, bh)[:h, :w]
    if kind == 'bc4':
        return blocks_to_image(bc_alpha_blocks(b)[:, :, None], bw, bh)[:h, :w]
    if kind == 'bc5':
        rg = np.stack([bc_alpha_blocks(b[:, :8]), bc_alpha_blocks(b[:, 8:])], axis=2)
        return blocks_to_image(rg, bw, bh)[:h, :w]
    return None


def picture(a):
    """An RGB picture of the texels: RG (a normal map) with the blue rebuilt, single channels grey, floats clipped."""
    if a.dtype != np.uint8:
        return Image.fromarray((np.clip(a[:, :, :3] if a.shape[2] >= 3 else np.repeat(a[:, :, :1], 3, axis=2), 0, 1)
                                * 255).astype(np.uint8), 'RGB')
    if a.shape[2] == 1:
        return Image.fromarray(np.repeat(a, 3, axis=2), 'RGB')
    if a.shape[2] == 2:
        x = a[:, :, 0].astype(np.float32) / 127.5 - 1
        y = a[:, :, 1].astype(np.float32) / 127.5 - 1
        z = np.sqrt(np.clip(1 - x * x - y * y, 0, 1))
        return Image.fromarray(np.stack([a[:, :, 0], a[:, :, 1], ((z * 0.5 + 0.5) * 255).astype(np.uint8)], axis=2), 'RGB')
    return Image.fromarray(np.ascontiguousarray(a[:, :, :3]), 'RGB')


def stats(a):
    f = a.astype(np.float64)
    means = ' '.join('%.4g' % m for m in f.reshape(-1, f.shape[2]).mean(axis=0))
    zero = float(np.mean(np.all(a == 0, axis=2)))
    flat = float(np.mean(np.all(a == a[0, 0], axis=2)))
    return means, zero, flat


def scan(folder):
    """(window, slot, va, w, h, fmt, mip) -> [(frame, serial, layer, name)]."""
    groups = defaultdict(list)
    for name in sorted(os.listdir(folder)):
        m = NAME.match(name)
        if not m:
            continue
        window, frame, serial, slot, va, w, h, fmt, mip, layer = m.groups()
        groups[(int(window), int(slot), va, int(w), int(h), int(fmt), int(mip))].append(
            (int(frame), int(serial), int(layer), name))
    return groups


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    other = sys.argv[sys.argv.index('--compare') + 1] if '--compare' in sys.argv else None
    src = args[0]
    out = args[1] if len(args) > 1 and args[1] != other else os.path.join(src, 'view')
    os.makedirs(out, exist_ok=True)
    groups = scan(src)
    report = open(os.path.join(out, 'stats.txt'), 'w')
    for key, files in sorted(groups.items()):
        window, slot, va, w, h, fmt, mip = key
        frames = sorted({f for f, _, _, _ in files})
        layers = max(l for _, _, l, _ in files) + 1
        scale = min(1.0, 256 / max(w, h))
        tw, th = max(1, int(w * scale)), max(1, int(h * scale))
        sheet = Image.new('RGB', (tw * layers, th * len(frames)), (40, 40, 40))
        for row, frame in enumerate(frames):
            for _, serial, layer, name in sorted(x for x in files if x[0] == frame):
                a = load(os.path.join(src, name), w, h, fmt)
                if a is None:
                    report.write('%s: unreadable (cut short, or a format this viewer has no decoder for)\n' % name)
                    continue
                sheet.paste(picture(a).resize((tw, th)), (layer * tw, row * th))
                means, zero, flat = stats(a)
                digest = hashlib.sha1(np.ascontiguousarray(a).tobytes()).hexdigest()[:12]
                report.write('%s: mean %s, all-zero %.4f, flat %.4f, hash %s\n' % (name, means, zero, flat, digest))
        sheet.save(os.path.join(out, 'w%d_s%d_%s_%dx%d_fmt%d_m%d.png' % (window, slot, va, w, h, fmt, mip)))
    if other:
        report.write('\n== compared with %s (by slot, address, size, format, mip, layer; file for file in order)\n'
                     % other)
        theirs = scan(other)
        mine_by = defaultdict(list)
        for (window, slot, va, w, h, fmt, mip), files in groups.items():
            for frame, serial, layer, name in sorted(files):
                mine_by[(slot, va, w, h, fmt, mip, layer)].append(name)
        theirs_by = defaultdict(list)
        for (window, slot, va, w, h, fmt, mip), files in theirs.items():
            for frame, serial, layer, name in sorted(files):
                theirs_by[(slot, va, w, h, fmt, mip, layer)].append(name)
        # The same texture may sit at another guest address on the other platform (or in another run): a key with no
        # match by address is matched by slot, size, format, level and layer alone, and the report says so.
        def loose(key):
            return key[:1] + key[2:]
        theirs_loose = defaultdict(list)
        for key, names in theirs_by.items():
            theirs_loose[loose(key)].append(key)
        for key in sorted(set(mine_by) | set(theirs_by)):
            slot, va, w, h, fmt, mip, layer = key
            other_key = key
            if key in mine_by and key not in theirs_by:
                candidates = [k for k in theirs_loose.get(loose(key), []) if k not in mine_by]
                if len(candidates) == 1:
                    other_key = candidates[0]
                    report.write('s%d %s %dx%d fmt%d m%d l%d: matched by slot, size, format, level and layer to the '
                                 'other folder\'s %s\n' % (slot, va, w, h, fmt, mip, layer, other_key[1]))
            if key not in mine_by:
                if loose(key) in {loose(k) for k in mine_by}:
                    continue  # matched loosely from this folder's side
                report.write('s%d %s %dx%d fmt%d m%d l%d: only in the other\n' % (slot, va, w, h, fmt, mip, layer))
                continue
            if other_key not in theirs_by:
                report.write('s%d %s %dx%d fmt%d m%d l%d: only in this folder\n' % (slot, va, w, h, fmt, mip, layer))
                continue
            for a_name, b_name in zip(mine_by[key], theirs_by[other_key]):
                a = load(os.path.join(src, a_name), w, h, fmt)
                b = load(os.path.join(other, b_name), w, h, fmt)
                if a is None or b is None:
                    report.write('%s vs %s: unreadable\n' % (a_name, b_name))
                    continue
                if np.array_equal(a, b):
                    report.write('%s vs %s: EQUAL\n' % (a_name, b_name))
                else:
                    d = np.abs(a.astype(np.float64) - b.astype(np.float64)).reshape(-1, a.shape[2]).mean(axis=0)
                    report.write('%s vs %s: mean |diff| %s\n' % (a_name, b_name, ' '.join('%.4g' % x for x in d)))
    report.close()
    print('written to', out)


if __name__ == '__main__':
    main()
