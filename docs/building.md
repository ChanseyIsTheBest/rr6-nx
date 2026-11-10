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

1.0.0 was built this way (2026-11-10). Every folder takes `app/out/switch-ult`'s settings (the renut-ultimate shaders:
`-DBANJO_RENUT_SHADER_DIR`, `-DBANJO_RENUT_SHADER_CACHE_CPP` and `-DBANJO_DEKO3D_GLSL_CPP` from
`app/out/renut_switch_ult`, `-DRR6_RENUT_HOOKS=ON`) plus `-DRR6_BUILTIN_CONFIG=ON -DBANJO_SWITCH_SDK_OPT=ON` (the SDK's
runtime and FFmpeg get the PGO and LTO flags too):

1. **Instrumented:** `-DBANJO_PGO=generate` (no LTO needed). Play it: it writes `pgo/banjo_pgo_<N>.stream` next to the
   NRO every 2 minutes, at HOME and at exit (the whole session each time). 1.0.0's profile: a 400 s Ryujinx session
   (boot, menus, a race), Ryubing with the ARMeilleure fix in its `BANJO-NX.md` (2026-11-10).
2. **Merge** on the PC that built it (the streams name its folders): `python tools/pgo_merge.py <folder with the
   streams>` fills `pgo/` (it stops if `pgo/` already has `.gcda` files: move them aside first).
3. **Optimised:** `-DBANJO_PGO=use -DBANJO_SWITCH_LTO=ON -DBANJO_PGO_DIR=<a copy of pgo/ at a path without spaces>`.
   `pgo/` in this repository is the released build's profile. A function changed since the instrumented build keeps no
   profile.

Keep the build folders' and the profile's paths free of spaces (GCC's parallel LTO link writes a makefile with them
unquoted; 1.0.0 used `C:\rr6pgo\gen`, `C:\rr6pgo\lto` and `C:\rr6pgo\profile`), and never run two of these builds at
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
