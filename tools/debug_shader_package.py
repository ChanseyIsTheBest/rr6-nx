#!/usr/bin/env python3
"""rr6-nx (2026-11-05): a shader package whose pixel shaders paint what they compute, to read the console's GPU. The NRO
prefers a deko3d_glsl.bin beside itself, so no rebuild is needed; delete the file to go back. Variants are compiled on
the console and cached by their text, so the normal shaders' cache entries stay valid.

    python tools/debug_shader_package.py OUTDIR [--mode which]

--mode which: each of the 13 cube-sampling shaders outputs a solid colour of its own (COLOURS: read the car's colour to
name its shader); every other pixel shader marks magenta, in every third band of 24 pixels, where its output alpha is
below 0.5, so a surface that passes the alpha test with low alpha shows. Post-processing keeps alpha 1, so stays clean.
--mode noclip: no vertex shader writes gl_ClipDistance (the clipper then has only the frustum to cut against).
--mode clip1: they write gl_ClipDistance[0] = 1.0: the output is there, and never clips.
--mode clip4: gl_ClipDistance has 4 elements: [0] the game's plane, the others 1.0 (a defined value for each of the vec4's).
--mode clip8: the same with all 8 (the clipper then reads no unwritten output, whichever of them it has enabled).
The GLSL comes from out/deko3d_shaders/glsl_opt, which is game data: this stays on the build machine and the user's card.
"""
import argparse
import os
import shutil
import subprocess
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
SRC = os.path.join(ROOT, 'out', 'deko3d_shaders', 'glsl_opt')
COLOURS = {
    '03232386464D9DB7': (1, 0, 0), '08C9D7D372A22B5E': (0, 1, 0), '1665925ABA65650D': (0, 0, 1),
    '22A0920B4D109C62': (1, 1, 0), '34D14F18E9D49E45': (1, 0, 1), '501A2B6A5237BC99': (0, 1, 1),
    '51E8275A885F7995': (1, 0.5, 0), '80391EE201BC4392': (0.5, 0, 1), '81B184F7D71B86A1': (0, 1, 0.5),
    '9445DA8C3B064B31': (1, 0, 0.5), 'A17B08137F6A4732': (0.5, 1, 0), 'C1136A7A769975C5': (0, 0.5, 1),
    'C657E51C7D437604': (1, 1, 1),
}
LOW_ALPHA = ('    if (int(gl_FragCoord.x / 24.0) % 3 == 1 && out_var_SV_Target0.a < 0.5) '
             '{ out_var_SV_Target0 = vec4(1.0, 0.0, 1.0, 1.0); }\n')


def patch_noclip(name, text):
    if not name.startswith('vs_') or 'gl_ClipDistance' not in text:
        return text, False
    lines = [l for l in text.split('\n') if 'gl_ClipDistance' not in l]
    return '\n'.join(lines), True


def patch_clip_const(name, text):
    if not name.startswith('vs_') or 'gl_ClipDistance' not in text:
        return text, False
    lines = ['    gl_ClipDistance[0u] = 1.0;' if 'gl_ClipDistance[0u] =' in l else l for l in text.split('\n')]
    return '\n'.join(lines), True


def patch_clip_n(name, text, count):
    if not name.startswith('vs_') or 'gl_ClipDistance' not in text:
        return text, False
    text = text.replace('out float gl_ClipDistance[1];', 'out float gl_ClipDistance[%d];' % count)
    lines = []
    for l in text.split('\n'):
        lines.append(l)
        if 'gl_ClipDistance[0u] =' in l:
            lines += ['    gl_ClipDistance[%du] = 1.0;' % i for i in range(1, count)]
    return '\n'.join(lines), True


def patch_clip_four(name, text):
    return patch_clip_n(name, text, 4)


def patch_clip_eight(name, text):
    return patch_clip_n(name, text, 8)


def patch(name, text):
    if not name.startswith('ps_') or 'out_var_SV_Target0' not in text:
        return text, False
    end = text.rstrip().rfind('}')
    if end < 0:
        return text, False
    colour = COLOURS.get(name[3:19])
    if colour:
        add = '    out_var_SV_Target0 = vec4(%.1f, %.1f, %.1f, 1.0);\n' % colour
    else:
        add = LOW_ALPHA
    return text[:end] + add + text[end:], True


def main():
    a = argparse.ArgumentParser()
    a.add_argument('out')
    a.add_argument('--mode', default='which')
    args = a.parse_args()
    glsl = os.path.join(args.out, 'glsl')
    shutil.rmtree(args.out, ignore_errors=True)
    os.makedirs(glsl)
    patched = 0
    for name in sorted(os.listdir(SRC)):
        source = open(os.path.join(SRC, name), encoding='utf-8').read()
        patcher = {'noclip': patch_noclip, 'clip1': patch_clip_const, 'clip4': patch_clip_four, 'clip8': patch_clip_eight}.get(args.mode, patch)
        text, did = patcher(name, source)
        patched += did
        open(os.path.join(glsl, name), 'w', encoding='utf-8', newline='\n').write(text)
    print('patched', patched, 'shaders; colours found:', sum(os.path.exists(os.path.join(SRC, 'ps_%s.glsl' % h)) for h in COLOURS))
    subprocess.check_call([sys.executable, os.path.join(ROOT, 'tools', 'deko3d_shader_package.py'), '--glsl', glsl, '--out', args.out])
    print(os.path.join(args.out, 'deko3d_glsl.bin'), os.path.getsize(os.path.join(args.out, 'deko3d_glsl.bin')), 'bytes')


if __name__ == '__main__':
    main()
