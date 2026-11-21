# Opus music and H.265 movies: a handoff to sa2-nx (from rr6-nx, 2026-11-21)

The user asked rr6-nx to help Sonic Adventure 2 convert its audio and videos to Opus and H.265, as Ridge Racer 6 and
Culdcept Saga did. This is what rr6-nx knows: what SA2 has, which pieces to copy from where, and the traps. The code
named below is on disk; rr6-nx's part is **uncommitted** (read it from the working tree), culdcept-nx's is committed.

## What SA2 has (sa2-nx/assets/game_root, measured 2026-11-21)

| Files | Format | Size | What converting gives |
|---|---|---|---|
| gd/interview.wmv, gd/interview_jp.wmv | WMV3 1920x1080 30 fps, 10 Mbit/s; WMA Pro 48 kHz | 658 MB (interview.wmv 6 min) | the biggest win: about 270 MB (35 % of the video bitrate keeps about 41 % of a file; Culdcept's path) |
| 31 gd/**/*.sfd | CRI Sofdec: MPEG-1 320x240 29.97 fps + two ADX streams (44.1 kHz stereo each) | 405 MB (13.5 min, 4 Mbit/s in all) | about 190 MB: the video (about 3.3 Mbit/s) to 35 %, the two ADX tracks (about 0.7 Mbit/s) stay (RR6's path) |
| 157 gd/ADX/*.ADX | CRI ADX ADPCM, 32 kHz stereo (about 4.5 bits a sample) | 365 MB | **less than RR6 got**: see below |
| gd/event_adx.afs, gd/event_adx_e.afs | AFS archives of ADX voice clips | 146 MB | as the ADX files |
| 283 *.csb | CRI sound banks | 50 MB | not worth it |

**The audio is not RR6's case.** RR6's music was raw 16-bit PCM, so Opus at 128 kbit/s cut it by 90 %. SA2's ADX is
already ADPCM (about 288 kbit/s for 32 kHz stereo), so Opus at 128 kbit/s saves about half (365 + 146 MB to roughly
230 MB), at a second lossy step. And the game decodes ADX itself (CRI's ADX library in guest code), so RR6's .opcm
(which serves the original PCM bytes from Opus) cannot be dropped in: it needs a hook at the guest's ADX decoder that
takes PCM from Opus instead. Measure the gain before building it; the movies come first.

## The movies (31 .sfd): copy RR6's path

RR6's movies are the same library (CRI Sofdec, MWSFD 3.71f / CRI MPV 1.976 in RR6). The idea: NAME.sfd.hevc stands in
for NAME.sfd. The game reads an SFD that is byte for byte the original except each picture's slice data, which is a
10-byte tag (movie id, display index) and zeros; the guest's MPEG-1 decoder skips the macroblocks, and the picture the
player hands out is overwritten with the H.265 picture of that index, decoded on NVDEC. Audio, timing and frame
buffers stay CRI's.

- Format and reader: `rr6-nx/sdk/include/rex/filesystem/sfd_hevc.h`, `sdk/src/filesystem/sfd_hevc.cpp` ("RXSFDH01").
- Lookup: `sdk/src/filesystem/devices/host_path_entry.h/.cpp`, `host_path_device.cpp` (the suffixes, and AnswerRank:
  NAME.hevc before NAME before NAME.lz4b; the VFS index version 2).
- The hooks: `rr6-nx/app/src/cpu/rr6_hevc_movies.cpp` (its header comment lists the CRI functions and offsets RR6
  found: the slice function, mwPlyGetCurFrm, the frame layout, a no-op function). SA2's addresses will differ: find the
  same functions in SA2's code (the CRI MPV slice loop and MWSFD's mwPlyGetCurFrm; the offsets inside CRI's structures
  are the library's, so they likely match if the library version does).
- nxvideo (FFmpeg 7.1 + nvtegra, NVDEC): `rr6-nx/tools/switch/nxvideo/` (copied from culdcept-nx), the
  `RR6_NXVIDEO` block in `rr6-nx/app/CMakeLists.txt`.
- The PC tool: `rr6-nx/tools/hevc_sfd_pack.py` (make, --check; --fraction 0.35, --gop 120, libx265 or hevc_nvenc).
- The installer: `rr6-nx-installer/lib/sfdh.js`, `wasm/src/mpeg1/` (FFmpeg 4.4's MPEG-1 decoder in WebAssembly),
  the worker's movies option. Its output equals the tool's byte for byte given the same H.265 frames.
- 320x240 is small: RR6's 480x272 course previews took 3.7 ms a picture on the console in all (reading, NVDEC and
  the copy, before the priority fix); the software decoder may even do for this size.

## The interviews (2 WMV, 1080p): copy Culdcept's path

culdcept-nx converts its WMV3 movies: `culdcept-nx/app/src/cpu/culdcept_wmv_ffmpeg.cpp` hooks the game's WMV3
decoder (decode, get output, flush, destroy) and gives it H.265 pictures from the installer's file, on NVDEC through
the same nxvideo. Its installer makes the H.265 files. SA2's interviews are 1920x1080: about 2.25 times a 720p picture
for NVDEC and the copy.

## Traps both ports hit

1. **A new REX_HOOK_RAW is not called** until `python tools/direct_calls.py --redo` is run again (the generated code
   calls `__imp__` directly), and **bulk machine copies of a caller** bypass it too (RR6 turned off
   `banjo_cpu_native_sub_822FB638` and `..._82247720` in its Switch defaults).
2. **The decode on the game's thread is slow until its priority is raised.** The game's threads run at 0x3B and
   Horizon does not time-slice them, so a thread woken from NVDEC waits for a core: RR6 12-14 ms a 720p picture,
   3.4 ms at 0x2C (culdcept-nx's `culdcept_movie_decode_priority`, RR6's `rr6_hevc_decode_priority`).
3. **Reading the frames on the game's thread costs as much again** (RR6: 4.6-6.1 ms a picture from the SD while the
   game streams the movie's audio). RR6 reads them ahead on a thread of their own (`Prefetch` / `AheadLoop` /
   `StartAhead` / `TakeFrame` in rr6_hevc_movies.cpp): one thread keeps the next 45 frames (1.5 s) of each open movie
   in memory; the game's thread takes a frame from there and reads it itself only on a miss. On the console
   (2026-11-21 21:52): 1,203 of 1,204 frames from the read-ahead, 0.04 ms to take one; with the priority fix, about
   5.4 ms a 720p picture on the game's thread in all (decode 4.7-5.0 + copy 0.5), from 12-14 at first.
   **Make it a libnx thread** (`threadCreate` at 0x2C, core -2, 256 KB stack, then `threadStart`), **not
   std::thread**: a std::thread started from the game's thread aborted the process (svcBreak in Ryujinx), and
   rr6-nx's masseffect_deferred_recording.cpp had found a pthread made from an SDK thread hung it.
4. **NVDEC: keep the VIC copy and the clock** (nxvideo's defaults; culdcept-nx: the CPU copy cost 18 ms a frame).
5. **Ryujinx has no H.265 NVDEC** (green pictures): test there with the software decoder (`rr6_hevc_nvdec = false`).
6. **An older install's NAME.lz4b shadows a new NAME.hevc** unless the lookup prefers the re-encoded file (AnswerRank).
7. Bitrate: 35 % of the original video's (Culdcept's rule). A deblocking filter before the encode was tried in RR6 and
   not kept (H.265's own deblocking does most of it; `pp=de` smears drawn artwork; the heavy ones add 25-40 min to an
   install in the browser).

Opus, for the audio when it comes: `rr6-nx/sdk/include/rex/filesystem/opus_pcm.h`, `sdk/src/filesystem/opus_pcm.cpp`,
`opus_decoder.cpp` (libopus from devkitPro's portlibs), `tools/opus_pcm_pack.py`, `rr6-nx-installer/lib/opcm.js`.

## Pack the .hevc files as ZXC blocks (rr6-nx, 2026-11-21 evening; the user: "add ZXC packing it's worth it")

The H.265 frames do not compress, but a .hevc keeps the original movie's other bytes as they were (the ADX audio, the
stream headers), and those do: ZXC 7 in 512 KB blocks made RR6's opening.sfd.hevc 10.3 % smaller (82.3 to 73.8 MB) and
course_a1n.sfd.hevc 11.5 % (LZ4 HC 9: 8.9 and 10.9 %), about 100 MB over RR6's movies. Opus files gain nothing (0.3 %).

- **The file:** NAME.hevc.lz4b, the .hevc in the same .lz4b container (version 2, ZXC) the installer already writes for
  every other game file. rr6-nx's installer makes it with lib/lz4b.js pack() on the re-encoded movie (worker.js, the
  `re === 'hevc'` branch); `node test/pack_node.mjs OUT NAME.hevc` makes the same file on a PC.
- **The reader:** `rr6-nx/sdk/include/rex/filesystem/sfd_hevc.h` kPackedSfdHevcSuffix; `sdk/src/filesystem/
  sfd_hevc.cpp` Unpacked() / UnpackedSize(): ReadSfdHevcSize and OpenSfdHevc wrap the file in OpenLz4Blocks when its
  name ends in .lz4b, and so does the second handle the frames are read through (the movie reopens the file by path;
  it has to unpack too), and the table bounds use the unpacked size.
- **The lookup:** `sdk/src/filesystem/devices/host_path_entry.cpp` Create: NAME.hevc.lz4b is the game's NAME (both
  suffixes off) with the movie's size, marked sfd_hevc (not lz4_blocks); `host_path_device.cpp`: AnswerRank gives it a
  re-encoded file's rank, the stat order tries NAME.hevc.lz4b after NAME.hevc, and the directory sweep strips .lz4b and
  then .hevc.
- **The cost:** the .lz4b reader keeps the last block it unpacked, so frames read in order unpack one 512 KB block about
  every dozen frames, on the read-ahead thread, not the game's.
- **Checked (Ryujinx, RR6's opening as opening.sfd.hevc.lz4b):** opened as ZXC (157 blocks), the movie's 1,470 frames
  found, pictures shown through the read-ahead, 0 errors; the PC and Switch builds without warnings. Not yet on the
  console.

For SA2: the .sfd movies keep their two ADX tracks the same way, so expect a similar tenth or more. Culdcept's WMV path stores its files differently: measure them before packing.

Licences: libopus BSD-3; FFmpeg as built with nvtegra is GPL (THIRD_PARTY_NOTICES.md in rr6-nx has the rows); credit
culdcept-nx for nxvideo and the WMV path.
