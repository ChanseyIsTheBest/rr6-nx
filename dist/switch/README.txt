rr6-nx: Ridge Racer 6 (Xbox 360, title 4E4D07D3) on the Nintendo Switch
======================================================================

A ReXGlue static recompilation, started from katamari-nx: its SDK fork, its post-codegen CPU passes and reNut's
Direct3D-level renderer on plume's deko3d back end (no NVK, no PM4 ring, no EDRAM model). Your own game files are needed;
nothing of the game is in this package except the recompiled code.

Credits: Ridge Racer 6 Recomp by Sirhalo23 (BSD 3-Clause; its codegen work and its notes on this game), reNut's renderer by
masterspike52 (its author permits its reuse in these ports), katamari-nx, banjo-nx, sa2-nx, NetherSX2_nx by NaGaa95 (the
four-core layout, MIT), battd_nx (the GPU arena), bejeweled3-nx and the Zuma ports (Renut at this XDK, the hot-function
method). GPL-3.0 where the sources are.

SD card layout
--------------
sdmc:/switch/rr6-nx/rr6-nx.nro           the program
sdmc:/switch/rr6-nx/renut.toml           settings (copy one of the tomls below over it)
sdmc:/switch/rr6-nx/deko3d_shaders.bin   the prebuilt shader cache: without it shaders compile while you play
sdmc:/switch/rr6-nx/game_root/           the disc's files: default.xex and the rest (extract your ISO; the ISO is not read)
sdmc:/switch/rr6-nx/dlc/                 the DLC packages, as they come (Xbox 360 LIVE files, content type 2), in any
                                         folders under it. Installed at the first start: their contents are extracted
                                         next to your saves, about 1.9 GB for all 77. The 41 music packs show in the game
                                         as "Disc 4: Player Disc". The 36 car unlock keys install but stay hidden from
                                         the game unless rr6_dlc_unlock_keys = true in renut.toml (your decision).

The tomls
---------
renut.toml        the shipped settings: Renut on deko3d, 720 lines handheld and docked (the Xbox 360's own), the game's own
                  MSAA, no dynamic resolution, every exact enhancement on, the items measured SLOWER ON THE CONSOLE in
                  banjo-nx off, logs and diagnostics on.
renut_play.toml   the same with the render-thread diagnostics off (for playing).
renut_ab.toml     the same with an in-run A/B list, 30 s halves, target 1 as the do-nothing control (a Vulkan-only key). Stay
                  in one place for 10+ minutes; the log's "[renut A/B]" lines give each target.
configs/          options one key away from renut.toml. renut_1080_docked.toml and renut_648_864.toml change the picture,
                  for you to decide on. renut_verify.toml turns every verify mode on and is slow.

Profiling
---------
The ELF (rr6-nx.elf) and the source snapshot (source_<commit>.tgz) are the ones this NRO was built from: a console profile
maps to source lines with them. switch_profile_stacks = true (on in renut.toml) samples every thread; the log is
logs/rex_profile.log next to the NRO. Play the scene you care about for a few minutes and send that log with this ELF.

This port's own keys
--------------------
rr6_depth_covers_colour  a depth target smaller than its colour target grows to fit (the race needs it). No A/B: off is broken.
rr6_fog_nan_zero         NaN fog constants read as 0, as the console's multiply treats them (A/B 71).
rr6_depth_bias           the game's depth bias reaches the GPU, as dynamic state (A/B 72).
rr6_alpha_near_one       the foliage's alpha test of >= 1 with an epsilon: the tree flicker (A/B 74).
rr6_fetch_over_pointer   a draw after SetTexture(NULL) samples what the fetch constant holds: the bloom (A/B 75).
rr6_user_clip_plane      the game's clip plane reaches the reflection-map shaders: the car's reflections (A/B 76).
rr6_strip_markers        a strip's 0xFFFF restart markers kept out of the vertex range: the wedges and torn meshes (A/B 77).
rr6_frames_ahead         1: the game runs a frame ahead of the render thread (0: it waits each frame; console test 5).
rr6_diag_render_delay_ms, rr6_diag_camera, rr6_diag_geometry_frames, rr6_diag_paint_frames, rr6_diag_texture_dump: diagnostics
                         (PACKAGE_NOTES.txt; the dump is console test 9).
rr6_dlc_unlock_keys      false: the 36 car unlock keys stay hidden.
banjo_renut_game_gamma   the display's gamma ramp, as the reference applies it (A/B 73): on; off is brighter in the darks.
banjo_deko3d_read_wait, _write_wait, _clear_wait, _full_barriers: console tests 6-8 for the chrome car (off by default).
banjo_deko3d_color_compression  colour targets' hardware compression (on); off is console test 10.

Machine copies of hot functions: banjo_cpu_native_bulk, A/B 70. A guard compares a copy with the generated original now and
then (banjo_hot_guard_calls / _period); a difference switches that copy off and logs "[hot] DIFFERENCE".
