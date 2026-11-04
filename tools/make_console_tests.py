import os, subprocess, sys
R = r'D:/ridge racer 6/rr6-nx/'
base = R + 'dist/switch/rr6-nx/renut.toml'
out = R + 'out/console_tests/'
os.makedirs(out, exist_ok=True)
tests = {
    'test1_all_suspects_off': ['rr6_user_clip_plane=false', 'banjo_cpu_native_bulk=false', 'banjo_deko3d_uam_uniform_branches=false', 'rr6_frames_ahead=0'],
    'test2_clip_plane_off': ['rr6_user_clip_plane=false'],
    'test3_copies_off': ['banjo_cpu_native_bulk=false'],
    'test4_uniform_branches_off': ['banjo_deko3d_uam_uniform_branches=false'],
    'test5_frames_ahead_0': ['rr6_frames_ahead=0'],
    # 2026-11-03 evening: the GPU ordering the emulator cannot show (sasrt-nx's console A/Bs for a fault of this class).
    'test6_gpu_waits': ['banjo_deko3d_read_wait=true', 'banjo_deko3d_write_wait=true', 'banjo_deko3d_clear_wait=true'],
    'test7_gpu_all_safe': ['banjo_deko3d_read_wait=true', 'banjo_deko3d_write_wait=true', 'banjo_deko3d_clear_wait=true',
                           'banjo_deko3d_zcull=false', 'banjo_deko3d_depth_compression=false', 'banjo_deko3d_barrier_merge=false',
                           'banjo_deko3d_barrier_lean=false', 'banjo_renut_upload_cached=false', 'rr6_frames_ahead=0'],
    'test8_full_barriers': ['banjo_deko3d_full_barriers=true', 'banjo_deko3d_clear_wait=true'],
    # 2026-11-03 night: the textures the car-paint draw samples, copied out of the console's GPU (tools/texture_dump_view.py).
    'test9_texture_dump': ['rr6_diag_texture_dump="120,40,6,2"'],
    # 2026-11-04: hardware colour compression off (Ryujinx ignores it; deko3d's swapchain keeps its own).
    'test10_no_color_compression': ['banjo_deko3d_color_compression=false'],
    # 2026-11-04: every shader optimisation off: the VS-output pruning (an input the pixel shader reads but the pruned
    # vertex shader no longer writes is garbage on the hardware and zero in Ryujinx) and uam's passes. Shaders recompile.
    'test11_no_shader_opts': ['banjo_deko3d_vs_outputs=false', 'banjo_deko3d_uam_prmt=false', 'banjo_deko3d_uam_gvn=false',
                              'banjo_deko3d_uam_uniform_branches=false', 'banjo_deko3d_uam_wide_rows=false'],
    # 2026-11-04: every texture any draw samples, 150 a window, one frame a window: the scenery, sky, cables, tower video.
    'test12_texture_dump_all': ['rr6_diag_texture_dump="60,30,5,1"', 'rr6_diag_texture_dump_all=150'],
    # 2026-11-04 07:15 (the user's ask): every switch at once plus the whole-frame dump. Not test 2 (the clip plane off makes
    # the car matte by design, so the chrome could not be judged). Slow: full barriers, waits, copies off, shaders recompiled.
    'test13_everything': ['banjo_cpu_native_bulk=false', 'rr6_frames_ahead=0',
                          'banjo_deko3d_read_wait=true', 'banjo_deko3d_write_wait=true', 'banjo_deko3d_clear_wait=true',
                          'banjo_deko3d_zcull=false', 'banjo_deko3d_depth_compression=false', 'banjo_deko3d_barrier_merge=false',
                          'banjo_deko3d_barrier_lean=false', 'banjo_renut_upload_cached=false', 'banjo_deko3d_full_barriers=true',
                          'banjo_deko3d_color_compression=false', 'banjo_deko3d_vs_outputs=false', 'banjo_deko3d_uam_prmt=false',
                          'banjo_deko3d_uam_gvn=false', 'banjo_deko3d_uam_uniform_branches=false', 'banjo_deko3d_uam_wide_rows=false',
                          'rr6_diag_texture_dump="90,40,4,1"', 'rr6_diag_texture_dump_all=150',
                          'banjo_renut_whole_buffers=false'],  # 09:40: test 14 joined (not 15: the range path needs restart too)
    # 2026-11-04 07:55: the intro's cables and palm fronds as ribbons across the sky on the console (shot 07:43) are strips
    # joined across their cuts: the whole-buffer path sends the game's 16-bit indices with 0xFFFF cuts to the GPU under
    # primitive restart, which the hardware honours by the restart register and Ryujinx by the index type. Test 14 takes
    # every draw through the range path (the CPU keeps the cuts: rr6_strip_markers); test 15 is the control, restart off.
    'test14_range_path': ['banjo_renut_whole_buffers=false'],
    'test15_no_strip_restart': ['banjo_deko3d_strip_restart=false'],
    # 2026-11-04 10:50: the restart index itself (Ryujinx ignores the register, the hardware compares it).
    'test16_restart_all_ones': ['banjo_deko3d_restart_index=1'],
    'test17_restart_ffff': ['banjo_deko3d_restart_index=2'],
}
# 2026-11-04 11:10 (the user: always everything at once): the two all-in-one tomls. The restart index register holds one
# value, so the two values are two runs; each carries every other switch of test 13 and the whole-frame dump from 90 s.
tests['all_A_everything_restart_ffffffff'] = tests['test13_everything'] + ['banjo_deko3d_restart_index=1']
tests['all_B_everything_restart_ffff'] = tests['test13_everything'] + ['banjo_deko3d_restart_index=2']
for name, keys in tests.items():
    p = subprocess.run([sys.executable, '-I', R + 'tools/make_emu_toml.py', base, out + name + '.toml'] + keys, capture_output=True, text=True)
    print(name, p.returncode, p.stdout.strip()[:90], p.stderr.strip()[:160])
    text = open(out + name + '.toml', encoding='utf-8').read()
    for k in keys:
        key, value = k.split('=')
        lines = [l for l in text.splitlines() if l.startswith(key + ' ') or l.startswith(key + '=')]
        print('   ', lines[:2], 'ok' if len(lines) == 1 and lines[0].split('=')[1].split('#')[0].strip() == value else 'CHECK')
