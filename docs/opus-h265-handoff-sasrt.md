# Opus music and H.265 movies: a handoff to sasrt-nx (from rr6-nx, 2026-11-21)

The user asked rr6-nx to help Sonic & All-Stars Racing Transformed convert its audio and videos to H.265 and Opus,
as Ridge Racer 6 and Culdcept Saga did. This is what rr6-nx knows: what SASRT has, what is worth converting, which
pieces to copy, and the traps. rr6-nx's code is **uncommitted** (read it from the working tree).

## What SASRT has (sasrt-nx/assets/game_root, measured 2026-11-21)

| Files | Format | Size | Worth converting? |
|---|---|---|---|
| Data/Movies/credits.usm (4:41), Drifting.usm (1:31), Gameclear.usm (0:15), Logos.usm (0:12) | CRI Sofdec2 USM: MPEG-1 1280x720 29.97-30 fps, ADX 48 kHz stereo (Logos: an audio codec ffprobe does not name) | 619 MB (6.6 min; credits 11.6 Mbit/s, Drifting 15 Mbit/s) | **yes**: about 250 MB at 35 % of the video bitrate (35 % keeps about 41 % of a file); the ADX stays |
| Data/sound/*.pck (Wwise AKPK, big-endian RIFX) | 103 XMA2 sounds (music 44.1-48 kHz stereo, voices 24 kHz mono), about 110 kbit/s on average | 638 MB | **little to gain**: see below |
| the same .pck files | 182 PCM sounds (48 kHz, mostly mono effects) | 24 MB | no |
| Data/GameAssets.M00, Frontend.M00 | the game's packed assets | 3.4 GB | not audio or video |

**The audio is not RR6's case.** RR6's music was raw 16-bit PCM, so Opus cut it by 90 %. SASRT's is XMA2, a
compressed codec at about 110 kbit/s already: Opus at the rate music needs (96-128 kbit/s) saves next to nothing, and
the voices (24 kHz mono) perhaps half, at a second lossy step. Wwise decodes XMA2 through the 360's XMA hardware
(Renut's XMA decoder in the port), so Opus would have to stand in for XMA contexts the game fills from its own
streams: a large job for perhaps 100-200 MB. rr6-nx's advice: leave the audio as it is and do the movies.

## The movies (4 .usm): adapt RR6's path

RR6's idea: NAME.sfd.hevc stands in for NAME.sfd. The game reads a file that is byte for byte the original except each
picture's slice data, which is a 10-byte tag (movie id, display index) and zeros (stored as zero runs, not bytes); the
guest's MPEG-1 decoder skips the macroblocks, and the picture the player hands out is overwritten with the H.265
picture of that index, decoded on NVDEC. Audio, timing and frame buffers stay CRI's. SASRT's video is MPEG-1 too, so
the same trick works; two things differ:

1. **The container is USM** (CRI chunks: CRID, @SFV video, @SFA audio, @CUE, ...), not RR6's MPEG program stream. The
   packer has to find the MPEG-1 elementary stream inside the @SFV chunks' payloads and cut each picture's slices
   there; the tag and the zeros take exactly the slice bytes' place, so every chunk keeps its size and offset.
   rr6-nx's tools/hevc_sfd_pack.py (demux, pictures, the tag, the segment table) is the model; its demux is the part
   to rewrite.
2. **The player is CRI's Sofdec2**, not RR6's MWSFD 3.71f / CRI MPV 1.976: find SASRT's own MPEG-1 slice function (the
   one that reads a slice header and runs the macroblock decoder) and the function that hands out the frame to show.
   RR6's are described in the header comment of rr6-nx/app/src/cpu/rr6_hevc_movies.cpp (what each hook does, the
   reader's GetChunk/UngetChunk peek, the frame buffer layout).

Pieces to copy:
- Format and reader: `rr6-nx/sdk/include/rex/filesystem/sfd_hevc.h`, `sdk/src/filesystem/sfd_hevc.cpp` ("RXSFDH01";
  the segment table works for any container).
- Lookup: `sdk/src/filesystem/devices/host_path_entry.h/.cpp`, `host_path_device.cpp` (the suffix, and AnswerRank:
  NAME.hevc before NAME before NAME.lz4b; the VFS index version 2).
- The hooks: `rr6-nx/app/src/cpu/rr6_hevc_movies.cpp` (the decode at a raised priority, the read-ahead thread, the
  timing lines).
- nxvideo (FFmpeg 7.1 + nvtegra, NVDEC): `rr6-nx/tools/switch/nxvideo/` (copied from culdcept-nx), the
  `RR6_NXVIDEO` block in `rr6-nx/app/CMakeLists.txt`.
- The installer: `rr6-nx-installer/lib/sfdh.js`, `wasm/src/mpeg1/` (FFmpeg 4.4's MPEG-1 decoder in WebAssembly), the
  worker's movies option; the browser encodes the H.265 itself.

## Traps (RR6's console runs, 2026-11-21)

1. **A new REX_HOOK_RAW is not called** until `python tools/direct_calls.py --redo` runs again, and bulk machine
   copies of a caller bypass it too (RR6 turned two off in its Switch defaults).
2. **Raise the thread's priority around nxv_decode** (0x2C; culdcept-nx's `culdcept_movie_decode_priority`, RR6's
   `rr6_hevc_decode_priority`). The game's threads run at 0x3B and Horizon does not time-slice them, so a thread woken
   from NVDEC waits for a core: RR6 went from 12-14 ms a 720p picture to 3.4.
3. **Read the frames ahead on a thread of their own.** On the game's thread, reading each frame from the SD cost RR6
   another 4.6-6.1 ms while the game streamed the movie's audio. RR6's read-ahead (`Prefetch`, `AheadLoop`,
   `StartAhead`, `TakeFrame`) keeps the next 45 frames (1.5 s) in memory: on the console 1,203 of 1,204 frames came
   from it, and a 720p picture took about 5.4 ms on the game's thread in all. **Make it a libnx thread**
   (`threadCreate` at 0x2C, core -2, 256 KB, `threadStart`), not std::thread: a std::thread started from the game's
   thread aborted the process (svcBreak in Ryujinx).
4. **NVDEC: keep the VIC copy and the clock** (nxvideo's defaults; culdcept-nx: the CPU copy cost 18 ms a frame).
5. **Ryujinx has no H.265 NVDEC** (green pictures): test there with the software decoder (`rr6_hevc_nvdec = false`).
6. **An older install's NAME.lz4b shadows a new NAME.hevc** unless the lookup prefers the re-encoded file.
7. Bitrate: 35 % of the original video's (Culdcept's rule). A deblocking filter before the encode was tried in RR6 and
   not kept (H.265's own deblocking does most of it; the browser installer's time matters).

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

For SASRT: the USM keeps its ADX audio and chunk headers the same way, so expect a similar tenth.

Licences: FFmpeg as built with nvtegra is GPL (THIRD_PARTY_NOTICES.md in rr6-nx has the rows); credit culdcept-nx for
nxvideo.
