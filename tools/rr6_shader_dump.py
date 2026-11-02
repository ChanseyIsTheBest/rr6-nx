#!/usr/bin/env python3
"""rr6-nx (2026-11-02): writes the shader containers stored in default.xex to out/renut_shader_dump, named by their XXH3 (the hash
Renut looks them up by). XDK 2.0.2135's compiler writes version 0x0E (magic 0x102A0E00, low bit 1 = vertex shader;
XenosRecomp/container_0e.h has the layout), which tools/renut_shader_dump.py (0x11) does not read. The checks are
container_0e.h's IsContainer0E.

Then --scan <file...> looks in the game's data for the same magics, plain, at any byte (the data files may hold more).

  python -I tools/rr6_shader_dump.py --image out/renut_image.bin --out out/renut_shader_dump [--scan D:/ridge racer 6/game/RRM.DAT ...]
"""
import argparse
import os
import re
import struct

import xxhash

MAGIC = re.compile(rb'\x10\x2a(\x0e|\x11)[\x00\x01]')


def containers(data, aligned):
    for m in MAGIC.finditer(data):
        o = m.start()
        if (aligned and o % 4) or o + 0x24 > len(data):
            continue
        version = data[o + 2]
        virt, phys = struct.unpack_from('>II', data, o + 4)
        if version == 0x0E:
            defs, consts, info = struct.unpack_from('>III', data, o + 12)
            ok = 0x18 <= virt < 0x10000 and 0 < phys < 0x100000 and o + virt + phys <= len(data) and \
                defs < virt and consts < virt and 0x18 <= info < virt
        else:
            ct, dt, so = struct.unpack_from('>III', data, o + 0x10)
            ok = 0x24 <= virt < 0x10000 and 0 < phys < 0x100000 and o + virt + phys <= len(data) and \
                ct < virt and dt < virt and 0x24 <= so < virt - 8
        if ok:
            yield o, version, data[o + 3] & 1, data[o:o + virt + phys]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--image', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--scan', nargs='*', default=[])
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    seen = set(f.split('.')[0].upper() for f in os.listdir(a.out))
    image = open(a.image, 'rb').read()
    new = total = vs = ps = 0
    for o, version, is_vs, blob in containers(image, True):
        total += 1
        h = f'{xxhash.xxh3_64_intdigest(blob):016X}'
        vs += is_vs
        ps += not is_vs
        if h not in seen:
            seen.add(h)
            open(os.path.join(a.out, h + '.bin'), 'wb').write(blob)
            new += 1
    print(f'image: {total} containers ({vs} vertex, {ps} pixel), {new} new; {len(seen)} in the dump')
    for path in a.scan:
        size = os.path.getsize(path)
        new = total = 0
        with open(path, 'rb') as f:
            step = 1 << 27
            at = 0
            while at < size:
                f.seek(at)
                data = f.read(step + (1 << 20))
                for o, version, is_vs, blob in containers(data, False):
                    if o >= step:
                        continue
                    total += 1
                    h = f'{xxhash.xxh3_64_intdigest(blob):016X}'
                    if h not in seen:
                        seen.add(h)
                        open(os.path.join(a.out, h + '.bin'), 'wb').write(blob)
                        new += 1
                at += step
        print(f'{os.path.basename(path)}: {total} containers, {new} new; {len(seen)} in the dump')


if __name__ == '__main__':
    main()
