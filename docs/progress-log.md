# Progress log

The work in order; each line a step finished. `docs/rr6-notes.md` has the evidence.

- 2026-11-02 20:12 Inputs checked; docs read in the given order.
- 20:16 Disc extracted; XDK 2.0.2135 (the oldest of the table, the same as Zuma).
- 20:20 rr6-nx from katamari-nx-public f6c0efcd; Katamari content out.
- 20:25 Codegen: Recomp manifest checked against the image, sweeps, jump tables, register diet audited.
- 21:32 PC: the emulated GPU (D3D12, RTX 3060) boots to the first race, no CPU, kernel or file-system fix beyond the function list and the save fixes.
- 21:50 PC: Renut on Vulkan draws logos, loader, intro, title and menus at 60 fps (render thread about 0.8 ms, GPU 1 to 1.5 ms).
- 22:16 Device lost fixed: a clear over a colour target larger than its depth target made an invalid framebuffer.
- 22:32 Heap corruption entering the race fixed: the XDK 2135 setters released the old resource before the native setter fenced it (found with a temporary page guard on the record heap).
- 22:38 Race entry: a second Vulkan device lost, about 247 s into the run, under investigation.
- 22:58 Race targets understood: 1440x800 colour over a depth surface made 1280x720, legal on the console. `rr6_depth_covers_colour` grows the host depth once (black bars on D3D12, device lost on Vulkan).
- 23:00 Codegen: vpkuhus / vpkuwus built through v_temp (a destination that is also a source was overwritten before it was read; the Pac-Man port's report, relayed by the user). This game has neither instruction: 0 in the generated code, 0 in an image scan.
- 23:05 Vulkan: no device lost in the race (55 to 59 fps, no Vulkan errors in stderr), but race geometry is garbage on Vulkan only; correct on D3D12. Under investigation. Ruled out by reading the code: primitive restart (same on both), a stale vertex stride (the layout is in the pipeline key).
- 23:06 Codegen: vpkd3d128 types 3, 4 and 5 read the source after writing the destination when they are one register (reported by the Pac-Man and Halo 3 ports). This game has one such use, `vpkd3d128 v0,v0,5,2,2` in sub_82266768, a float32-to-float16 array converter: a negative element 0 lost its sign. Fixed with a scoped copy; the emulated-GPU reference runs the same generated code, so it had the bug too.
- 23:10 The first regeneration after the vpkd3d128 fix did NOT carry it: `vPackSrc` is absent from the generated code, though the new rexglue.exe holds the string. Cause not known yet (the build rule orders the generator before codegen, so a stale generator is not the obvious answer). To test: run the generator by hand and read its output before the passes.
- 23:12 Why the vpkd3d128 fix did not land: rexglue skips codegen while `generated/codegen.stamp` matches, and its fingerprint leaves out the generator's own code (stamp dated 20:34). `tools/build_pc_regen.ps1 -Generator` removes it and checks that a new one was written. Warned the other ports through the Pac-Man session.
