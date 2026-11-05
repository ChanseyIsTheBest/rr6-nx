# Ridge Racer 6 port: where it stands (2026-11-04, paused by the user for about a month)

**Use this package:** `builds/2026-11-04_1102_restart_index_tests17` (NRO 2C47F586EBCF). Everything is committed; nothing is pushed.

## Working

PC (Direct3D 12) and the emulator (deko3d) boot and race. The console boots and races too, with the visual faults below. Fixed for
good: the wedges and torn meshes of the first console run (strip markers, the range path).

## Still wrong, on the console only

Harborline's intro: bridge cables and palm fronds as long ribbons and dark blocks. The race: the chrome car, the black tower
screen, hard rectangles in the sky, a translucent block by the rock wall, noise blocks.

## Ruled out, by two console runs of test 13 with the logs proving the switches took effect

The machine copies, the frame ahead, GPU ordering (every barrier a full wait), Zcull, depth compression, barrier merging, the
cached upload ring, hardware colour compression, the vertex-output pruning and uam's optional passes (compiled on the console:
`deko3d_shaders_f158.bin`), both geometry paths, and the point-sprite layout (a real bug, fixed, but it did not change these). The
game's paint constants and its livery, normal map and 512x512 texture bytes match the emulator's on the console. deko3d's debug
library refuses nothing in a whole run (emu57).

## Not known yet

- **Never run on the console:** the 1102 NRO, the restart-index switch, `gpuprobe.nro`, `tools/switch_remote.py`, and the texture
  dump itself (its first window was later than both runs lasted). So what the GPU holds on the console is still unseen.
- That the ribbons are strips joined across their cuts is an inference from how they look. Both paths show them, so the cause may
  not be the cuts.
- Best guesses, unproven: the restart index for the ribbons; the reflection cube's contents for the car.

## Pick up here

1. `gpuprobe.nro` (in the package; `GPUPROBE_README.txt` says how to read it). A couple of minutes, and it answers independently
   of the game whether the GPU honours a strip cut.
2. `tests/all_A_everything_restart_ffffffff.toml`, then `all_B_everything_restart_ffff.toml`, copied over the SD's `renut.toml`.
   The race starts about 75 s after launch; stay in it until 3 min 30 s after launch so all four dump windows come. Bring back
   `logs/`, `texture_dump/` and shots of the intro's cables and of the car. Delete nothing. The user wants every switch in one toml.
3. `python tools/texture_dump_view.py <console texture_dump> <out folder> --compare out/emu_runs/emu52/texture_dump` (same course,
   deko3d). A texture with no equal twin is the lead. The cube is RGBA8 on the Switch tomls and 16-bit on the PC, so compare it
   with the emulator's, not the PC's.

Optional: sys-botbase and an ftp sysmodule on the console would let these runs be driven from the PC (`tools/switch_remote.py`,
written but never connected to anything). The install steps given to the user came from memory, not from the current releases:
check each project's README first. On the user's console sys-botbase stops the boot with 2021-0003 (0x615; 2026-11-05): `sm::ResultOutOfSessions`, a process asked for a service whose session limit was reached (`sm_service_manager.cpp`, `GetServiceHandle`). Still failing with minimal sysmodules. Its `__appInit` waits 20 s, then opens sm, pm:dmnt, ldr:dmnt, pm:info, sockets, caps:sc and vi, with `fatalThrow` on any failure, so it is probably crashing itself on one of them; which one is not known. `ldr:dmnt` has the lowest limit visible (3; `pm:dmnt` and `pm:info` have 16), the others are closed Nintendo modules. The report in `atmosphere/fatal_reports/` names the process, not the service: a build logging each init would. Not needed for the tests: they run by hand.

## Follow-ups, none urgent

- Indexed literal arrays (vivapinata-nx cc502f76): no detection in this recompiler; the check needs the shader caches regenerated.
- The reference recorded at the game's anisotropy (`--anisotropic_override=-1`): ours is captured (`out/pc_runs/aniso_ours`); the
  reference run makes no captures, and the recorder for its videos was not found.
- kameo-nx's NaN-constant flush (77622770) as a general rule; this port does it for the fog phase only.
- Console performance at stock clocks: the recent 60 fps figures were at CPU 2397, GPU 1305.6 MHz.
- Decisions left to the user: the 140 never-compared machine copies, hand natives for the wait spin and the audio functions.

## Only on this disk (`out/` is ignored by git, nothing is pushed)

The references (`out/emu_runs/emu52`, `emu53`, `out/pc_runs/pcdump6`, `pcdump8`) and the console runs (`out/console_runs`). Rebuild
the test tomls with `python -I tools/make_console_tests.py`. gpuprobe needs a path without spaces and the devkitPro shell: copy
`tools/gpuprobe` somewhere spaceless and run `make` there.
