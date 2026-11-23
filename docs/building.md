# Building rr6-nx

You need your own copy of the game: the code generator and the shader tools read it. Nothing made from it is committed
(`.gitignore`): `app/assets`, `app/generated`, `out/`, `app/out/`.

## Tools

Windows; LLVM clang and the Visual Studio Build Tools (CMake and Ninja) for the PC build (`tools/pc_env.bat` names the
paths); devkitA64, libnx and deko3d from [devkitPro](https://devkitpro.org) for the Switch; Python 3 with `xxhash` and
`Pillow`. The deko3d host tools (`out/deko3d_tools`: SPIRV-Cross and the PC uam) come from `tools/deko3d_build_tools.sh`.

## 1. The game

Extract the disc (`tools/extract_iso.py`) and make `app/assets` point at the folder that holds `default.xex`.

## 2. The PC build: code generation and the shader translator

```bat
tools\build_host.bat
tools\build_pc.bat
```

The PC build runs the code generator (`app/renut_manifest.toml`), the post-codegen passes (`tools/post_codegen.py`) and
Renut's XenosRecomp over `out/renut_shader_dump`. Run it with `tools/run_pc.ps1`.

## 3. The shaders

```bash
python -I tools/rr6_shader_dump.py --image out/renut_image.bin --out out/renut_shader_dump
```

This takes the 176 containers stored in `default.xex` (version 0x0E, XDK 2.0.2135). `--scan <file...>` looks for more in
the game's data; none were found in `RRM*.DAT`. Then:

```bat
powershell -File tools\switch_shaders.ps1
python tools\renut_release_shaders.py
```

`switch_shaders.ps1` translates all 176 to GLSL and makes the everyday build's files (`app/out/renut_switch`, every
shader built into the NRO). `renut_release_shaders.py` makes the release build's (`app/out/renut_switch_release`: the
shader table without SPIR-V, and `sd/deko3d_glsl.bin` to put next to the NRO for tests). `BANJO_CENTROID=0` (or
`switch_shaders.ps1 -NoCentroid`) translates without centroid sampling.

## 4. The Switch build

The everyday build (`app/out/switch`, every shader built in, no LTO):

```bat
tools\build_switch.bat
```

The released NRO, in folders of their own (`BUILD_DIR` and `CMAKE_EXTRA` of `tools/build_switch.bat`):

1.0.0 (2026-11-10) and 1.0.1 (2026-11-11) were built this way. Every folder takes `app/out/switch-ult`'s settings (the renut-ultimate shaders:
`-DBANJO_RENUT_SHADER_DIR`, `-DBANJO_RENUT_SHADER_CACHE_CPP` and `-DBANJO_DEKO3D_GLSL_CPP` from
`app/out/renut_switch_ult`, `-DRR6_RENUT_HOOKS=ON`) plus `-DRR6_BUILTIN_CONFIG=ON -DBANJO_SWITCH_SDK_OPT=ON` (the SDK's
runtime and FFmpeg get the PGO and LTO flags too):

1. **Instrumented:** `-DBANJO_PGO=generate` (no LTO needed). Play it: it writes `pgo/banjo_pgo_<N>.stream` next to the
   NRO every 2 minutes, at HOME and at exit (the whole session each time). 1.0.0's profile: a 400 s Ryujinx session
   (boot, menus, a race), Ryubing with the ARMeilleure fix in its `BANJO-NX.md` (2026-11-10). 1.0.1's: a session on
   the console (the PC was busy), on the hybrid-packed game folder: `tools/console_run.py` drove the Single Race route
   (`out/console_tests/m/pgo101_session.txt`), then the user raced; HOME, then the game closed, and the stream fetched
   by ftp. The `.lz4b` reader and its codecs (`rexfilesystem`, `rexblockcodecs`) are outside the LTO and PGO targets:
   every build compiles them the same way.
2. **Merge** on the PC that built it (the streams name its folders): `python tools/pgo_merge.py <folder with the
   streams>` fills `pgo/` (it stops if `pgo/` already has `.gcda` files: move them aside first).
3. **Optimised:** `-DBANJO_PGO=use -DBANJO_SWITCH_LTO=ON -DBANJO_PGO_DIR=<a copy of pgo/ at a path without spaces>`.
   `pgo/` in this repository is the released build's profile. A function changed since the instrumented build keeps no
   profile.

Since the base sync (2026-11-22) the Switch build has the machine copies in place (`SASRT_HOT_IN_PLACE` ON, guard forms
OFF), and that form reads its own profile: `pgo-inplace/` (`BANJO_PGO_DIR_IN_PLACE`), not `pgo/` (the 1.0.x profile of
the hooked form). The 2026-11-22 build: `C:\rr6pgo\gen122` (generate, `-DBANJO_PGO_DIR_IN_PLACE=C:/rr6pgo/profile122`),
a 560 s Ryujinx session (`config.toml`'s `input_script = "52:START,84:A,94:A,104:A,122:DOWN,127:DOWN,132:A,142:A,152:A,
162:A,172:A,182:A,192:A,215:A,225:A,235:A,245:A,255:A,265:A,280:RT@240"`, the `game_opus_test` folder for the Opus music
and the H.265 opening, the release DKSH cache; window pictures every 15 s showed World Xplorer's first race, Harborline
765, from about 400 s: a hold such as `RT@240` blocks the presses after it, so the last A must come before it, and the
game takes no input during its movies), `tools/pgo_merge.py C:/rr6pgo/streams122 C:/rr6pgo/profile122
--gen-build C:/rr6pgo/gen122/renut.nro` (403 .gcda, copied to `pgo-inplace/`), then `C:\rr6pgo\lto122` (use + LTO, the
same `BANJO_PGO_DIR_IN_PLACE`).

Since 2026-11-22 (the user: "compile them and extract them in browser like banjo") the released NRO carries no game
shader: rr6-nx-installer makes them from the player's `default.xex` (its `lib/shaders.js`). The release shader table:
`python tools/renut_release_shaders.py --glsl out/deko3d_shaders_ult/glsl_opt --cache
app/out/renut_switch_ult/shader_cache_switch.cpp --out app/out/renut_switch_ult_release` (the table without SPIR-V; its
`sd/deko3d_glsl.bin` is the version 1 package for tests, game data, never distributed). The build: the LTO folder
reconfigured with `-DBANJO_RENUT_SHADER_DIR=app/out/renut_switch_ult_release -DBANJO_RENUT_RELEASE_SHADERS=ON` (no GLSL
package built in; the same PGO profile), `C:\rr6pgo\lto122` on 2026-11-22: `out/final_2026-11-22/rr6-nx_release.nro`.
The installer's `release/variants.txt`: `tools/deko3d_variant_cache.py` with the cache's own arguments (`--generic
--plain-guess app/out/renut_switch_ult/shader_cache_switch.cpp --sasrt-guess --round-guess --earlykill-ab`, the lists
and run-time logs) plus `--export-variants out/browser_shaders/variants.txt --dry-run`; then the installer's
`tools/make_release.py --nro <the NRO>` and `node test/shaders_node.mjs <game> --reference`. After a change to the
translator (`app/thirdparty/reblue-XenosRecomp`) or the Python passes, rebuild the installer's `wasm/renut_hlsl` and run
its `tools/sync_from_base.py --base <rr6-nx>`: its shaders must be this tree's.

Keep the build folders' and the profile's paths free of spaces (GCC's parallel LTO link writes a makefile with them
unquoted; 1.0.0 used `C:\rr6pgo\gen`, `C:\rr6pgo\lto` and `C:\rr6pgo\profile`, 1.0.1 the same names with `101`
added), and never run two of these builds at
once: they share the SDK's archives in `sdk/out/switch-arm64`. Configure with Visual Studio's CMake by its full path: Git
Bash's PATH finds devkitPro's MSYS2 cmake, which damaged a cache once.

With `RR6_BUILTIN_CONFIG=ON` the settings are compiled in: `app/rr6_switch_defaults.toml` (every fixed setting, log_level
"off") and `app/rr6_switch.toml`, the player's `config.toml`, written next to the NRO when there is none. Keys in
`config.toml` override the built-in ones. `tools/make_rr6_builtin.py` makes both from a play toml. With it OFF the NRO
reads `renut.toml` next to it: `dist/switch/rr6-nx`, made by `tools/make_rr6_tomls.py`, has it with `renut_play.toml`
and `renut_ab.toml`. The test runs copy one over it (`tools/run_ryujinx.ps1 -Toml <file>`).

## 5. After a change to the code generator

`rexglue` skips codegen while `app/generated/codegen.stamp` matches its inputs, and those do not include the generator's own
code, so a fixed builder in `sdk/src/codegen` compiles and never reaches the generated code. Use
`tools/build_pc_regen.ps1 -Generator`, then look for the new text in `app/generated`.
