#!/usr/bin/env python3
"""rr6-nx (2026-11-02): takes what belonged to Beautiful Katamari out of the copy of katamari-nx-public. One-off.

 1. Sources no CMake file names (other games' addresses): "Stale mentions" in docs/optimising-functions.md.
 2. The hot lists and natives: emptied, the common code kept (pacman-nx's stripped copies of the same base files).
 3. pgo/, the icon, the forwarder NPDM: removed. Function lists and analysis lists: emptied.
 4. katamari_* file names and identifiers in CMake and the app: rr6_*.

  python tools/rr6_strip_katamari.py
"""
import os
import re
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAC = r'D:\pacman\pacman-nx'

DELETE = """app/src/cpu/banjo_pool_lock.cpp
app/src/cpu/banjo_reverb_native.cpp
app/src/cpu/banjo_xaudio_native.cpp
app/src/cpu/katamari_stage_diag.cpp
app/src/me/banjo_me_hooks.cpp
app/src/native/banjo_d3d_hooks.cpp
app/src/native/banjo_espera_anillo.cpp
app/src/native/banjo_nativo_stubs.cpp
app/src/native/banjo_shader_harvest.cpp
app/src/native/nfsmw_nativo_destinos.cpp
app/src/native/nfsmw_nativo_dibujos.cpp
app/src/native/nfsmw_nativo_ganchos.cpp
app/src/native/nfsmw_nativo_shaders.cpp
app/src/native/nfsmw_nativo_sistema.cpp
app/src/native/nfsmw_nativo_texturas_pool.cpp
app/src/native/nfsmw_shader_library.cpp
app/src/renut_engine/StopNSwap.cpp
app/src/renut_engine/cvar_menu.cpp
app/src/renut_engine/env_map_pool.cpp
app/src/renut_engine/frameHooks.cpp
app/src/renut_engine/frontend_debug_menu.cpp
app/src/renut_engine/hooks.cpp
app/src/renut_engine/shader_dump.cpp
app/src/renut_engine/texture_tools.cpp
app/src/renut_engine/thread_slots.cpp
app/src/renut_engine/title_update.cpp
app/src/renut_engine/townsfolk.cpp
tools/katamari_files.py
tools/katamari_shader_files.py
tools/cpdb.py
tools/forwarder/katamari_forwarder.json
tools/forwarder/katamari_main.npdm
tools/renut_hook_map_katamari.txt
docs/console-rc3-breakdown.md
docs/console-rc4-breakdown.md
docs/console-rc5-breakdown.md
docs/console-rc9-breakdown.md""".split()

# Stripped copies from pacman-nx (same base commit), retargeted to this port's name.
COPY = {
    'app/src/cpu/hot/banjo_hand_natives.h': 'app/src/cpu/hot/banjo_hand_natives.h',
    'app/src/cpu/hot/hand.txt': 'app/src/cpu/hot/hand.txt',
    'app/src/cpu/hot/localized.txt': 'app/src/cpu/hot/localized.txt',
    'app/src/cpu/banjo_hot_guest.cpp': 'app/src/cpu/banjo_hot_guest.cpp',
    'app/src/cpu/banjo_hot_guest.h': 'app/src/cpu/banjo_hot_guest.h',
    'app/config/hot_edges.txt': 'app/config/hot_edges.txt',
    'app/config/hot_functions.txt': 'app/config/hot_functions.txt',
    'app/config/locals_optout.txt': 'app/config/locals_optout.txt',
    'app/config/lr_write_same_choice.json': 'app/config/lr_write_same_choice.json',
    'app/config/r1_local_choice.json': 'app/config/r1_local_choice.json',
    'app/config/renut_crt.toml': 'app/config/renut_crt.toml',
    'app/config/renut_hooks.toml': 'app/config/renut_hooks.toml',
    'app/indirect_promotions.txt': 'app/indirect_promotions.txt',
}

RENAME = {
    'app/katamari_switch.toml': 'app/rr6_switch.toml',
    'app/katamari_switch_defaults.toml': 'app/rr6_switch_defaults.toml',
    'app/src/katamari_keys.cpp': 'app/src/rr6_keys.cpp',
    'app/src/katamari_builtin_config.h.in': 'app/src/rr6_builtin_config.h.in',
    'tools/make_katamari_tomls.py': 'tools/make_rr6_tomls.py',
    'dist/switch/katamari-nx': 'dist/switch/rr6-nx',
    'docs/katamari-notes.md': 'docs/katamari-notes-reference.md',
}

# Build and app text. Comments that record a katamari-nx finding keep the name.
SUBS = [
    (r'KATAMARI_BUILTIN_TEXT', 'RR6_BUILTIN_TEXT'),
    (r'KATAMARI_PLAYER_TEXT', 'RR6_PLAYER_TEXT'),
    (r'KATAMARI_BUILTIN_CONFIG', 'RR6_BUILTIN_CONFIG'),
    (r'kKatamariBuiltInConfig', 'kRr6BuiltInConfig'),
    (r'kKatamariPlayerConfig', 'kRr6PlayerConfig'),
    (r'katamari_builtin_config', 'rr6_builtin_config'),
    (r'katamari_switch_defaults', 'rr6_switch_defaults'),
    (r'katamari_switch\.toml', 'rr6_switch.toml'),
    (r'src/katamari_keys\.cpp', 'src/rr6_keys.cpp'),
    (r'/switch/katamari-nx/', '/switch/rr6-nx/'),
    (r'katamari-nx\.nro', 'rr6-nx.nro'),
    (r'"Beautiful Katamari"', '"Ridge Racer 6"'),
    (r'katamari\.toml', 'rr6.toml'),
    (r'tools/switch/icon/katamari_icon\.jpg', 'tools/switch/icon/rr6_icon.jpg'),
    (r'/switch/katamari_nx/', '/switch/rr6_nx/'),
]
SUB_FILES = ['app/CMakeLists.txt', 'app/src/renut_app.h', 'app/src/rr6_keys.cpp', 'app/src/rr6_builtin_config.h.in',
             'app/src/renut_engine/dlc_install.cpp', 'app/src/renut_engine/gpu/banjo_renut_deko3d.cpp',
             'app/cmake/banjo_renut_gpu.cmake', 'app/rr6_switch.toml', 'app/rr6_switch_defaults.toml',
             'tools/run_ryujinx.ps1', 'tools/run_ryujinx_rdc.ps1', 'tools/run_pc.ps1', 'tools/run_pc_verify.ps1',
             'tools/run_pc_renut.ps1', 'tools/package_switch.ps1', 'tools/gate_ryujinx.ps1', 'tools/build_switch_release.bat',
             'tools/make_rr6_tomls.py', 'tools/make_test_toml.py', 'tools/build_pc.bat']


def main():
    for rel in DELETE:
        p = os.path.join(ROOT, rel)
        if os.path.exists(p):
            os.remove(p)
    for src, dst in COPY.items():
        shutil.copyfile(os.path.join(PAC, src), os.path.join(ROOT, dst))
        p = os.path.join(ROOT, dst)
        t = open(p, encoding='utf-8', errors='surrogateescape', newline='').read()
        t = t.replace('pacman-nx', 'rr6-nx')
        open(p, 'w', encoding='utf-8', errors='surrogateescape', newline='').write(t)
    open(os.path.join(ROOT, 'app/src/cpu/hot/localized_bulk.txt'), 'w', newline='\n').write(
        '# rr6-nx: machine copies by tools/switch_hot_bulk.py --merge (docs/optimising-functions.md).\n')
    # pgo/: the released NRO's profile of another game.
    pgo = os.path.join(ROOT, 'pgo')
    if os.path.isdir(pgo):
        shutil.rmtree(pgo)
    icon = os.path.join(ROOT, 'tools/switch/icon/katamari_icon.jpg')
    if os.path.exists(icon):
        os.remove(icon)
    for a, b in RENAME.items():
        pa, pb = os.path.join(ROOT, a), os.path.join(ROOT, b)
        if os.path.exists(pa):
            shutil.move(pa, pb)
    for rel in SUB_FILES:
        p = os.path.join(ROOT, rel)
        if not os.path.exists(p):
            continue
        t = open(p, encoding='utf-8', errors='surrogateescape', newline='').read()
        n = t
        for a, b in SUBS:
            n = re.sub(a, b, n)
        if n != t:
            open(p, 'w', encoding='utf-8', errors='surrogateescape', newline='').write(n)
    print('done')


if __name__ == '__main__':
    main()
