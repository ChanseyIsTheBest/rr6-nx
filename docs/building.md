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

1. **Instrumented:** `-DBANJO_PGO=generate -DBANJO_SWITCH_LTO=ON`. Play it: it writes `pgo/banjo_pgo_<N>.stream` next to
   the NRO every 2 minutes, at HOME and at exit.
2. **Merge** on the PC that built it (the streams name its folders): `python tools/pgo_merge.py <folder with the
   streams>` fills `pgo/` (it stops if `pgo/` already has `.gcda` files: move them aside first).
3. **Optimised:** `-DBANJO_PGO=use -DBANJO_SWITCH_LTO=ON -DBANJO_RENUT_RELEASE_SHADERS=ON`. It carries no game shader and
   reads `deko3d_glsl.bin` beside itself. `pgo/` in this repository is the released build's profile. A function changed
   since the instrumented build keeps no profile.

Keep the temporary folder's path free of spaces (GCC's parallel LTO link writes a makefile with it unquoted), and never
run two of these builds at once: they share the SDK's archives in `sdk/out/switch-arm64`.

The NRO reads `renut.toml` next to it (`RR6_BUILTIN_CONFIG` is OFF in this port): `dist/switch/rr6-nx`, made by
`tools/make_rr6_tomls.py`, has it with `renut_play.toml`, `renut_ab.toml` and `configs/`. The test runs copy one over it
(`tools/run_ryujinx.ps1 -Toml <file>`).

## 5. After a change to the code generator

`rexglue` skips codegen while `app/generated/codegen.stamp` matches its inputs, and those do not include the generator's own
code, so a fixed builder in `sdk/src/codegen` compiles and never reaches the generated code. Use
`tools/build_pc_regen.ps1 -Generator`, then look for the new text in `app/generated`.
