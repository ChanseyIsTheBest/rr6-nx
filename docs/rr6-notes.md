# Ridge Racer 6 port: notes

This file records the port: what each step found, with its evidence. The project is a copy of katamari-nx
(`D:\beautifulkatamari\katamari-nx-public`, commit `f6c0efcd`, its files and not its history), itself from banjo-nx
(`D:\Banjo kazooie port\banjo-nx`). Both are read-only references. Comments that say "banjo-nx", "katamari-nx", "pacman-nx",
"zuma-nx", "sa2-nx" or "peggle2-nx" record findings from those ports. Where docs differ, katamari-nx's win, then banjo-nx's.
Ridge Racer 6 Recomp by Sirhalo23 (BSD 3-Clause, `D:\ridge racer 6\RidgeRacer6-Recompilation-main`, read, not built) solved this
game's codegen; what is taken from it is named where it is used and its notice is in `THIRD_PARTY_NOTICES.md`.

The request (2026-11-02, from 20:12 AEST): port Ridge Racer 6 to the PC and the Switch with ReXGlue, the Switch the main goal;
work uninterrupted until 06:00 AEST without asking; a package for the console by then.

## Decisions (made without asking, as the request said)

| What | Decision | Why |
|---|---|---|
| Game files | `D:\ridge racer 6\game` (the disc, 45 files, 6.1 GB, by `tools/extract_iso.py`) | the request |
| `app/assets` | a junction to `D:\ridge racer 6\game` | no second copy; git-ignored |
| Internal project name | `renut`, as banjo-nx and katamari-nx | its CMake, post-codegen passes and glue name `renut_*`; the NRO, its title and the SD folder are rr6-nx |
| Bootstrap generator | katamari-nx's built `rexglue.exe` and its two DLLs in `out/bootstrap` | the build needs a generated tree first; the build then uses the generator it builds from `sdk/` |
| Private files | FFmpeg's `config.h`, `avconfig.h`, `ffversion.h` and six `*_list.c`, XenosRecomp's `dxc-bin`, glslangValidator, spirv-cross, uam: copied from `D:\beautifulkatamari\katamari-nx` | the request |
| Sources no CMake file names | removed (`tools/rr6_strip_katamari.py`, the list pacman-nx removed from the same base) | other games' addresses: "Stale mentions" in `docs/optimising-functions.md` |
| Hand-written natives | none, the header holds only the common code | the request: only from a console profile |
| `.ps1` tools | run through the session's `PowerShell` tool (its process has `Bypass`); `powershell -File` from a plain shell is refused by this machine's default policy, and the policy was not changed | "no system setting changes" |

## The game (2026-11-02)

- ISO: XGD2, partition at `0x0FD90000`, 45 files, no directories, 6.05 GB.
- `default.xex` (`tools/xex_info.py`): title **4E4D07D3**, media `03F77EEF`, version 0.0.0.4; base `0x82000000`, entry `0x8224CEF0`, image
  `0x5A0000` (5.9 MB); AES + basic compression. No title update supplied.
- **XDK 2.0.2135**: every static library (XAPILIB, D3D9, D3DX9, XGRAPHC, XBOXKRNL, XNET, XAUD, LIBCPMT, XONLINE, XHV; QFE 1 at most), `xam.xex`
  (116 imports) and `xboxkrnl.exe` (280) at 2.0.2135, minimum 2.0.1861. **The oldest XDK of the table ("XDK versions of our Xbox 360 ports"),
  the same as Zuma's** (zuma-nx), older than Feeding Frenzy's 2571 and Katamari's 5632.
- Sections (PE header in the loaded image):

  | Section | Range | |
  |---|---|---|
  | `.rdata` | `82000400-820A5664` | |
  | `.pdata` | `820A5800-820B4E50` | |
  | `.text` | `820C0000-82330A84` | code |
  | `PSFD00` | `82330C00-823366CC` | code: the Sofdec video decoder |
  | `.data` | `82340000-8255B7D8` | |
  | `.idata`, `.XBLD`, `.reloc` | `82560000-`, `82570000-`, `82570200-8259A528` | |

- Data: `RRM.DAT`, `RRM2.DAT`, `RRM3.DAT` (3.2 GB), `.sfd` Sofdec videos (`course_*`, `ending*`, `auroravision`), no other code module.
- DLC (`D:\ridge racer 6\Ridge_Racer_6\Ridge Racer 6`, 77 LIVE packages, content type 2, title 4E4D07D3, 1.9 GB): 41 music packs, the largest 68.9 MB; 36 car unlock keys of
  57 KB each.

## Code generation (2026-11-02)

- Config: `app/renut_config.toml`, katamari-nx's keys. Every address from Recomp's manifest was checked against this image
  (`tools/rr6_check_manifest.py`) and is in `app/config/renut_funcs.toml`:
  - the 7 tail-call targets: each follows a function's terminator, each has its `b` from the thunk named (`0x8232C810`, `0x8215841C`, ...); two are also in data;
  - the 36 pointer-only functions: each follows a terminator; 18 are built by `lis/addi` (`0x82162440-0x82162550`, no data word), 18 are stored in data at the address the manifest says;
  - setjmp `0x8230E2F0`: `stfd f14,0(r3)` at `+0x1C`, the image's only one, after a hook word check; longjmp `0x8230E1D0`: `lfd f14,0(r7)` at `+0x3C`, the only one.
  - All 43 stand: no address of theirs was wrong for this image.
- **PSFD00 is covered:** the generated `REX_CODE_BASE / SIZE` is `0x820C0000 + 0x2766CC = 0x823366CC`, the end of PSFD00; its functions are generated (`sub_82330C00` ...). The tools take the range from the generated tree or `--code 820C0000:823366CC`.
- **The two function-pointer tail calls** (Recomp's `dispatch_fixes.cpp`): `indirect_calls = [0x8217C960, 0x8217D2B0]`, the base's key, in place of their hand-corrected functions. Checked: both end `lwz; rlwinm r10,r10,2; lwzx r11,r10,r11; mtctr r11; bctr` through `0x8236D1E8` / `0x8236D1B0`, six entries each, all function starts. `switch_check.py` confirms them as indirect calls; so are their four siblings (`0x8217C400`, `0x8217D280`, `0x8217D2D0`, `0x8217D300`), which the generator needs no help with.
- **Pointer sweep** (`tools/pointer_fixpoint.py`, 6,069 gaps, 7 candidates): 2 accepted, fixpoint in pass 2. `0x8224C544` then went out (below), `0x8227DEB0` (6 instructions, built at `0x8227DEE8`) stays.
- **Gap sweep** (`tools/gap_sweep.py`): 57 accepted of 310, fixpoint. 54 of them are a lone `blr` after a `bctr` (dead code nothing points at): removed. The other four shapes went too, with `tools/override_labels_check.py`: `0x8224C544` (SEH scope label, reached by branches of its parent), `0x822DB6C8`, `0x822DB770`, `0x82318720`, `0x8231AEE4` (an instruction runs into each: funclet and epilogue tails). So the sweeps add **one function** beyond Recomp's 43.
- **Wide scan** (`tools/wide_pointer_scan.py`): 9 hits, none a missing function: the entry point and `__except` labels in `.pdata`, the FPR save / restore helpers (named), and three import thunks (`0x82330634` is `__imp__KeTlsGetValue`, the C runtime's table of them: registered by the generator).
- **Jump tables** (`tools/switch_check.py --code 820C0000:823366CC`): 119 switches, 193 indirect; truncated 0, wrong targets 0, missed 0, switches at a call through a function table 0. No bound in the code: 5 (the four function-pointer tables, right as indirect calls; `sub_82311AE0`, a half table with 8 cases). Odd shapes: 5, all generated as indirect calls.
- **Register diet** (all on, `non_volatile_as_local_keep = ["v64-v127"]` from the start, katamari-nx's rc3 finding). `tools/non_argument_audit.py --noreturn=8230E1D0`: ENTRY 264 (the save / restore helpers, kept by name; MSVC unwind funclets), RET 1 (`sub_8231B1E8` with `sub_8231B2B0`), HANDOVER 0: 48 functions kept (`tools/diet_keep_list.py`). `tools/read_before_write.py` on code generated WITH the options: setjmp's callers' `env.*` copies (handled by the generator), setjmp itself, and `sub_8231BA74`, a data word (a pointer, `0x8231BAA0`) decoded as `lwz r17,-17760(r17)`, never run. **No `share_registers` needed.**

## Game fixes (Recomp's, checked against the base)

| Their fix | Base | Here |
|---|---|---|
| `XGetLanguage` from `user_language` | has it (`xam_info.cpp`) | nothing to do |
| `XMASetLoopData` read its 12-byte argument as a whole context | **does not have it**: the same code as stock v0.10.0 (the request expected it there; what is in the code wins) | fixed in the SDK (`xboxkrnl_audio_xma.cpp`), their word-by-word atomic update, with their notice |
| Save error code: a missing content open as `ERROR_FUNCTION_FAILED` | no | `app/src/rr6_game_fixes.cpp`, hooks at `sub_82247E10`, `sub_82247F80` |
| Thumbnail not stored in the save folder | no | the same file, `rr6_save_thumbnail` (false), hook at `sub_82247E40` |
| FP state on host threads (`host_thread_fixes.cpp`, `fp_guard.cpp`) | the guest threads only | the same file, PC only: hooks at `sub_822AA050`, `sub_8225A590`, the vectored handler |
| DLC installer with checks of its own | the SDK's `InstallContent` | not taken: the packages are the user's own; the installer now walks into subfolders so it can be pointed at them where they lie |
| `depth_bias_fix`, `lod_bias_fix`, launcher, achievements, widescreen, overlays, statistics | - | left out (see "Visual issues" for the two renderer questions) |

## Unlock keys

`rr6_dlc_unlock_keys` (false, the user's decision): the 36 keys stay out of the game's content list by their display names (`app/src/renut_engine/dlc_install.cpp`, the SDK's `dlc_hidden`, katamari-nx's mechanism). The music packs always show.

## Renut at XDK 2.0.2135 (2026-11-02)

katamari-nx's Renut stands at XDK 2.0.5632 (`docs/from-katamari/katamari-notes-reference.md`), N&B's layout with its zones moved. This game's XDK is far older; zuma-nx
(`D:\peggle 2\zuma-nx`) runs Renut on the same XDK but its game uses a fraction of Direct3D (no index buffers, render targets, depth or resolves).

**Measured:**

- `tools/d3d_propagate.py` pairs: Zuma 1,862, Katamari 1,139, Feeding Frenzy 1,082, N&B 117. The Direct3D library is `0x8224E000-0x82264000`.
- `tools/rr6_d3d_api.py`: the game's code calls 70 of its functions (`out/renut_map/rr6_d3d_api.txt`).
- `tools/d3d_device_layout.py`, Zuma -> this game: delta 0 at `0x0-0x494`, `0x2880-0x2930`, `0x2B38-0x3C04`, `0x3C98-0x3D0C`, `0x4FD0-0x5060`: the same layout.
- `tools/rr6_device_census.py`: 129 functions outside the library load the device pointer `0x824F0378` and touch it directly:
  - reads of the state tables, at `+0x60` (setters, row 10 at +0x88 ...) and `+0x1E4` (sampler setters);
  - **writes of float constants inline**, `stfs` at `+0x780...` (vertex) and `+0x1780...` (pixel), N&B's places, followed by the dirty mask: `ld r11,8(r10); or; std r11,8(r10)` with `r10 = device + 16`. So XDK 2135 keeps its masks at **+16 (vertex), +24 (pixel)**; N&B's are at +0 and +8.
  - XDK 2135's `EndVertices` (`sub_82254080`) has the ring at +0, and `sub_8224E4C8` / `sub_8224E610` (SetVertex/PixelShaderConstantF) are ordinary guest functions writing the same fields.
- Headers: a resource head of 12 bytes (Common with the count in its low byte, the type in bits 16-18, a bind count in bits 19-23; fence +4; flush +8). Texture 40 bytes with its fetch constant at +16; surface 64 bytes (the same six words, its texture at +44, SurfaceInfo +48, Color/DepthInfo +52, HiControl +56); vertex buffer 20 bytes (fetch at +12), index buffer 20 bytes (address +12, size +16; Format 0 = 16-bit, 1 = 32-bit).
- No code outside the library builds a `0x0101xxxx` / `0x0102xxxx` Common: vertex and index buffers only come from the Create calls.
- Shaders: **version 0x0E containers** (magic `0x102A0E00/01`): 244 in `default.xex` (122 + 122), 176 unique by XXH3 (`tools/rr6_shader_dump.py`); none in plain form in `RRM*.DAT`.

**Design** (`tools/renut_hook_remap_rr6.py`, `tools/rr6_renut_port.py`):

- Renut's device stays Katamari's layout where only Renut reads it, with the **head moved to where this XDK's inline code writes**: ring +0, count +12, masks +16, tables +0x60 / +0x1E4 / +0x234 / +0x3B8.
- zuma-nx's split: the game's textures, surfaces and volumes stay **the game's own XDK 2135 objects** (its loaders and D3DX read them; its Create, GetSurfaceLevel, GetDesc, AddRef, Release, GetType run on them). Renut gets a **shadow** in N&B's layout: a texture's copy of the fetch constant; a surface's Renut record, made at `CreateSurface` with the game's EDRAM base. New here: surfaces (Zuma had none), the bind counts this XDK's setters keep (an object released while bound lives until unbound), index buffers.
- Renut's own objects: vertex and index buffers, shaders, declarations, automatic surfaces.
- States: rows 0-56 are N&B's, row 57 a state N&B lacks (kept on the host), N&B's 57-95 are rows 58-96, 96-100 are not in this XDK; N&B's order of defaults kept (Zuma's list).

## Renut bugs at this XDK, found entering the race (2026-11-02)

- **Record heap corrupted (`o1heapAllocate` crash, about 240 s in).** The XDK 2135 setters keep a bind count on what they hold. `Rr6Rebind` unbound the old object before the native setter ran, and the native setter fences what it replaces (`TagResourceFence`, header +8). When that unbind was the last reference, the fence landed in a freed record: the BE word 0x0000E2FC at user +8 is a free-list link read as the host pointer 0xFCE20000. Found by giving each record its own pages, read-only once freed. Fixed by unbinding after the native setter, in every setter and in both shader setters.
- **Index buffer Unlock.** `sub_82254EB8` ran XDK 2135 header code on Renut's header: hooked.
- **Clear over a larger colour target.** A clear with 0x3F on a 1440x800 colour with 1280x720 depth made an invalid Vulkan framebuffer. `ClearTargets` splits it when the depth is smaller.

## Visual differences against the reference (emulated GPU, Direct3D 12)

Reference: `out/pc_runs/emu4`. Ours: `out/pc_runs/renut*`. `tools/side_by_side.py` makes the comparison.

| # | Where | Difference | Why | Status |
|---|---|---|---|---|
| 1 | Race | Scene cut on the right and at the bottom on Direct3D 12 (88.9 % x 90 %); device lost on Vulkan | The race draws a 1440x800 colour target over a depth surface made 1280x720. RB_SURFACE_INFO's pitch is shared, so that is legal on the console; a host framebuffer cuts to the smaller or is invalid | Fixed by `rr6_depth_covers_colour` (no in-run A/B: off loses the device on Vulkan; runs only when targets change) |
| 2 | Car select | Car body black, logos included; interior draws | Under investigation. Not the exponent adjust (the counter never fires), not the PS constant location (0x1780 matches) | Open |

## Recompiler bugs found by other ports (2026-11-02)

Both are in `sdk/src/codegen/builders/vector.cpp`, both are a destination that is also a source, overwritten before it is read.

- `vpkuhus` / `vpkuwus`: now built through `vTemp`. This game has neither (0 in the generated code).
- `vpkd3d128` types 3, 4, 5: read a scoped copy when the destination is the source; other uses generate the same code as before. This game has 3 uses, 1 aliased: `vpkd3d128 v0,v0,5,2,2` in `sub_82266768`, called through `sub_82266958` from 3 sites. The sign of a negative element 0 was lost. **The reference has the same generated code, so it cannot show this difference**: the fix is checked by reading the code, not against the reference.

The other piecewise builders in that file were read and are safe: `vsubsws`, `vrlw`, `vsrab`, `vsrb`, `vsraw`, `vsrw`, `vlogefp` work element by element, and `vupkd3d128` reads each source before what overlaps it is written. Other builder files were not audited.

## Enhancements against banjo-nx's reference (2026-11-02, read from the sources; `tools/enhancement_gap.py`, `tools/enhancement_state.py`)

260 keys in the reference, 245 defined here. Of the table's 139 rows, 136 ship the reference's value here.

- **SLOWER ON THE CONSOLE, all off:** `banjo_renut_replay_lookahead`, `banjo_renut_shadow_sort`, `banjo_renut_texture_slot_skip`, `banjo_renut_inline_line_compare`.
- **Differs:** `banjo_native_reverb` is off here (true in the reference). It is listed under game code as native code, N&B's.
- **Absent, in the table:** `banjo_renut_check_worker`, `banjo_gpu_fetch_spec` (the reference's case is tessellated draws' fetch types). Neither has been measured on this game.
- **Absent, outside the table:** the `banjo_cpu_native_*` natives (`constants_ps`, `constants_vs`, `flush_constants`, `flush_registers`, `memcpy`, `memset`, `xaudio_src_m03`), the `banjo_ring_prover*` keys, `banjo_pool_lock`, `banjo_renut_check_worker_core`.

This is the keys' presence and values, not a measurement. Each key's in-run A/B and verify run on this game is still to do.

**Package defaults changed from Katamari:** `banjo_renut_render_height_docked` is 720, not 1080: pixel-identical is the default here and 1080 was the user's decision for Katamari. `configs/renut_1080_docked.toml` has it. `RR6_BUILTIN_CONFIG` is OFF, so the NRO reads `renut.toml`, as the package needs.

## The main thread's spin (2026-11-02, PC profile, `out/pc_runs/renut19/pc_profile.log`)

`sub_82144DA0` takes 91 % of the main thread's samples in the race, and that is waiting, not work: it loops on the word at `0x824D4F30` until another thread sets it to 1, calling an optional callback each time round, then adds 1 to it atomically. A profile must not read this as a hot function. On the Switch this loop keeps a core busy while it waits. Replacing it with a real wait would change no picture but touches the game's timing, so it is **a decision for the user, not made here**.

## Census for the renderer guide's section 2 (2026-11-02, PC, Vulkan, `out/pc_runs/renut18`; the race's picture was still wrong in this run, so these are counts, not costs)

| Question | This game | Banjo, for scale |
|---|---|---|
| Where draws come from | 100 % direct calls: 229,379 immediate, 0 replayed from recorded command buffers in the 10 s measured | 98.5 % recorded |
| Draws a frame | about 413 in that 10 s of race (229,377 draws, 555 frames) | |
| Shadow or depth-only | 2,755 depth-only draws in that 10 s, about 5 a frame, all with alpha test or alpha to coverage | about 2,200 a frame |
| Render targets | 8, 20 MB, at 1x | |
| Textures | 831 to 858, 83 to 91 MB, of which 8 resolve targets 22 MB | |
| Vertex and index copies | stream cache 17 to 18 MB in a 32 MB pool, about 1,100 streams | |
| Shaders | all 176 in the image, none found in `RRM*.DAT`; 103 vertex, 73 pixel | |

**Consequence:** the record-time items of the guide's sections 4.5 to 4.7 serve recorded command buffers, and this game records none, so they should do little here. To be measured with their A/B targets, not assumed.

**Not measured yet:** resources by creation call or built by the game (`UnleashedCensusOn`), setters or inline writes (the tags census), memexport pending per draw, threads on the emulator.

## Hypothesis under test: the black car at car select (2026-11-03)

The reference's translator gives every multiply Shader Model 3's rule, zero times anything is zero, even NaN (`dxbc_translator_alu.cpp`, `kMul`, `kMad`). XenosRecomp emits a plain multiply. At car select the pixel bank's `c21` and `c22` are NaN, and those are `FogPhaseY` and `FogPhaseZ`. The vertex shader 877AAC07400C0F33 multiplies its own constants of those names into the fog terms, and the paint shader ends `r0.xyz = r1.xyz * r3.xyz + r4.xyz` with those terms in r3 and r4. A NaN there comes out black. In the race those constants are finite and the same paint draws correctly. **Not yet proved:** the vertex bank's values have not been read, and no fix has been tried.

**Proved (2026-11-03, renut27):** with `RR6_NAN_ZERO` zeroing registers 21 and 22 at upload, the car at car select draws textured and matches the reference (`out/pc_runs/renut27/captura_014_0211s.png`, `out/pc_runs/emu4/captura_014_0210s.png`). Both banks' c21 and c22 are NaN there, and the fog colours and coefficient are 0. Its texture memory holds data. The cause is Shader Model 3's multiply (0 x NaN = 0), which the reference has and XenosRecomp lacks.
