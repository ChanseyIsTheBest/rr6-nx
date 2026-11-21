// rr6-nx (2026-11-21, the user: "rencoding audio as opus and videos as h.265 copy what culdcept saga does"): Ridge Racer
// 6's movies (CRI Sofdec: .sfd files, MPEG-1 video and ADX audio, played by MWSFD 3.71f / CRI MPV 1.976 in the game's
// own code, on a thread of its own) shown from H.265 on the Switch's NVDEC instead of decoded as MPEG-1 by the guest. As
// culdcept-nx does for its WMV movies (app/src/cpu/culdcept_wmv_ffmpeg.cpp, and its nxvideo, tools/switch/nxvideo;
// credit culdcept-nx), but the SFD is kept byte for byte: NAME.hevc (rex/filesystem/sfd_hevc.h) shows the game the .sfd
// with each picture's slice data zero but for a tag (the movie and the picture's display index) after its first slice
// header.
//
// Found in the game's code (2026-11-21):
//   sub_822F6298(mpv, reader, frame)  CRI MPV's decode of one picture: frame (16 words) copied to mpv+624, then
//                                     sub_822FB878 the output planes at mpv+688: Cb, Cr, Y, the chroma pitch (u16 at
//                                     +700) and the luma pitch (u16 at +702); sub_822FB638 its slices
//   sub_822FB638(mpv, reader)         the slice loop: each slice start code to sub_822FB420, until mpv+852 (the last
//                                     macroblock done) reaches mpv+864 (the picture's last)
//   sub_822FB420(mpv, reader)         one slice: the reader's bytes (CRI's stream joint: vtable +24 GetChunk into
//                                     mpv+5384, the address, and mpv+5388, the length; +28 UngetChunk, +32 PutChunk)
//                                     from the slice start code, the slice header, then the picture type's
//                                     macroblock decoder through mpv+732 (sub_82330C00 I, sub_82331850 P, sub_823311E0
//                                     B: bulk machine copies here, so they are not hooked themselves)
//   sub_822DCD80(ply, frm)            mwPlyGetCurFrm: the frame to show, frm+0 its buffer (Y, then Cb, then Cr: the
//                                     layout of sub_822E27D0), +12 / +16 its width and height; sub_82247720 (the game's
//                                     movie textures) copies each plane's rows out of it
//   sub_822E1D80                      a function that only returns
//
// The hooks: (1) sub_822FB420: when the slice header is followed by a tag, mpv+732 is pointed at sub_822E1D80 (no
// macroblocks decoded), the tag is written into the picture's Y plane, and mpv+852 set to the picture's last macroblock
// (the slice loop ends: the rest of the picture is zero, which the next start code search skips); (2) sub_822DCD80: a
// frame whose Y plane starts with a tag gets the H.265 picture of that display index written over it. Frame buffers,
// timing, the order of pictures and the audio stay CRI's.
#include <fmt/format.h>
#include <rex/cvar.h>
#include <rex/filesystem/sfd_hevc.h>
#include <rex/hook.h>
#include <rex/logging.h>
#include <rex/ppc/func.h>
#include <rex/system/xmemory.h>

#include <algorithm>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <cstring>
#include <map>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

#if RR6_NXVIDEO
#include <switch.h>  // svcGetThreadPriority / svcSetThreadPriority (rr6_hevc_decode_priority)

#include "nxvideo.h"
#endif

REXCVAR_DEFINE_BOOL(rr6_hevc_movies, true, "RR6",
                    "The movies the installer made H.265 (NAME.hevc beside the game files) shown from H.265 on the "
                    "Switch's video hardware; false: their tags are not looked for (such a movie then shows nothing)")
    .lifecycle(rex::cvar::Lifecycle::kInitOnly);
// rr6-nx (2026-11-21): Ryujinx opens nvtegra's NVDEC for H.265 but emulates no H.265 decoding; tests in it use false.
REXCVAR_DEFINE_BOOL(rr6_hevc_nvdec, true, "RR6",
                    "The H.265 movies on the Switch's video hardware (NVDEC); false: FFmpeg's software decoder (slow: for "
                    "an emulator, which has no H.265 NVDEC)")
    .lifecycle(rex::cvar::Lifecycle::kInitOnly);
REXCVAR_DEFINE_BOOL(rr6_hevc_log, false, "RR6",
                    "One [hevc] line every 300 pictures shown from H.265: the time reading, decoding and copying, and "
                    "nxvideo's own steps and clocks")
    .lifecycle(rex::cvar::Lifecycle::kInitOnly);
// rr6-nx (2026-11-21, the console test: the user saw slight stutter in the opening; 12-14 ms a 720p picture where the
// console's NVDEC benchmark takes 4.5): as culdcept-nx found (culdcept_movie_decode_priority, 2026-11-20), the decode
// waits on the hardware on the game's own thread, which runs at the lowest priority (0x3B); woken, it waits for a core
// behind the game's other threads, which Horizon does not time-slice. nxv_decode runs at this priority instead (above
// the game's threads) and the thread's own is put back after.
REXCVAR_DEFINE_INT32(rr6_hevc_decode_priority, 0x2C, "RR6",
                     "The thread's priority while it waits for an H.265 picture on NVDEC (0x1C-0x3B, lower runs first; "
                     "the game's threads 0x3B); 0 = the thread's own")
    .range(0, 0x3B)
    .lifecycle(rex::cvar::Lifecycle::kInitOnly);

REX_EXTERN(__imp__sub_822FB420);  // CRI MPV: one slice (mpv, reader)
REX_EXTERN(__imp__sub_822DCD80);  // MWSFD: mwPlyGetCurFrm (ply, frm)

namespace {

constexpr uint32_t kNoOpFunction = 0x822E1D80;

uint8_t* Host(uint8_t* base, uint32_t a) { return rex::memory::GuestPtr(base, a); }
uint32_t Ld32(uint8_t* base, uint32_t a) {
  const uint8_t* p = Host(base, a);
  return (uint32_t(p[0]) << 24) | (uint32_t(p[1]) << 16) | (uint32_t(p[2]) << 8) | p[3];
}
uint16_t Ld16(uint8_t* base, uint32_t a) {
  const uint8_t* p = Host(base, a);
  return uint16_t((p[0] << 8) | p[1]);
}
void St32(uint8_t* base, uint32_t a, uint32_t v) {
  uint8_t* p = Host(base, a);
  p[0] = uint8_t(v >> 24);
  p[1] = uint8_t(v >> 16);
  p[2] = uint8_t(v >> 8);
  p[3] = uint8_t(v);
}

std::atomic<uint64_t> g_tagged_slices{0}, g_shown{0}, g_missing{0}, g_cut_tags{0};
// A tag whose display index could not be read (rr6-nx's slice hook): the frame after the last one shown.
constexpr uint32_t kIndexUnknown = 0x1FFFFF;
// The H.265 movie each CRI MPV decoder (its handle) last decoded a tagged picture of.
std::mutex g_mpv_mutex;
std::map<uint32_t, uint32_t> g_mpv_movie;

// The Sofdec frame buffer's planes for a w x h picture (sub_822E27D0): Y pitch the width rounded to 16 then to 128,
// round_up(h, 16) rows; then Cb and Cr, pitch half the 16-rounded width rounded to 128, half the rows.
struct Planes {
  uint32_t y, cb, cr, y_pitch, c_pitch;
};
Planes SofdecPlanes(uint32_t buf, uint32_t w, uint32_t h) {
  const uint32_t w16 = (w + 15) & ~15u, h16 = (h + 15) & ~15u;
  Planes p;
  p.y_pitch = (w16 + 127) & ~127u;
  p.c_pitch = ((w16 / 2) + 127) & ~127u;
  p.y = buf;
  p.cb = buf + p.y_pitch * h16;
  p.cr = p.cb + p.c_pitch * (h16 / 2);
  return p;
}

#if RR6_NXVIDEO
// rr6-nx (2026-11-21, the console's second test: with the decode at 3.4 ms, reading each frame's bytes from the SD on
// the game's thread cost 4.6-6.1 ms a picture, while the game streams the movie's audio from the same card): the
// frames a movie will ask for next are read by a thread of their own, kAhead of them ahead of the decoder. The game's
// thread takes a frame from there, and reads it from the SD itself only when the read-ahead has not got it yet.
constexpr int64_t kAhead = 45;  // 1.5 s at 30 frames a second

struct Prefetch {
  std::shared_ptr<const rex::filesystem::SfdHevcMovie> movie;
  std::mutex m;
  int64_t want = 0;  // the first frame the decoder still needs
  std::map<uint32_t, std::vector<uint8_t>> ready;
  uint64_t hits = 0, misses = 0;
};

std::mutex g_ahead_mutex;
std::condition_variable g_ahead_cv;
std::vector<std::weak_ptr<Prefetch>> g_ahead;

// The read-ahead thread: the first frame missing from any open movie's window, read, then the next.
void AheadLoop() {
  std::vector<uint8_t> bytes;
  for (;;) {
    std::shared_ptr<Prefetch> job;
    uint32_t frame = 0;
    {
      std::unique_lock<std::mutex> lock(g_ahead_mutex);
      for (;;) {
        g_ahead.erase(std::remove_if(g_ahead.begin(), g_ahead.end(), [](const auto& w) { return w.expired(); }),
                      g_ahead.end());
        for (const auto& w : g_ahead) {
          auto p = w.lock();
          if (!p) continue;
          std::lock_guard<std::mutex> pl(p->m);
          const int64_t end = std::min<int64_t>(p->want + kAhead, int64_t(p->movie->frames.size()));
          for (int64_t f = std::max<int64_t>(p->want, 0); f < end; ++f) {
            if (!p->ready.count(uint32_t(f))) {
              job = std::move(p);
              frame = uint32_t(f);
              break;
            }
          }
          if (job) break;
        }
        if (job) break;
        g_ahead_cv.wait_for(lock, std::chrono::milliseconds(50));
      }
    }
    if (!job->movie->ReadFrame(frame, &bytes)) {
      std::this_thread::sleep_for(std::chrono::milliseconds(20));  // read again later rather than spin on a failure
      continue;
    }
    std::lock_guard<std::mutex> pl(job->m);
    if (int64_t(frame) >= job->want && int64_t(frame) < job->want + kAhead) job->ready[frame].swap(bytes);
  }
}

// The read-ahead thread, once: a libnx thread, not std::thread (Ryujinx, 2026-11-21: a std::thread started from the
// game's thread here aborted the process; masseffect_deferred_recording.cpp found a pthread made from an SDK thread hung
// it). Above the game's threads (0x3B, which Horizon does not time-slice: at their priority it could wait for a core as
// long as they keep it); it only reads, a frame at a time. Null (each frame read on the game's thread, as before) if it
// did not start.
std::shared_ptr<Prefetch> StartAhead(std::shared_ptr<const rex::filesystem::SfdHevcMovie> movie) {
  static const bool running = [] {
    static Thread thread;
    const int prio = REXCVAR_GET(rr6_hevc_decode_priority);
    const bool ok = R_SUCCEEDED(threadCreate(&thread, [](void*) { AheadLoop(); }, nullptr, nullptr, 256 * 1024,
                                             prio > 0 ? prio : 0x2C, -2)) &&
                    R_SUCCEEDED(threadStart(&thread));
    if (!ok) REXLOG_WARN("[hevc] the read-ahead thread did not start: the frames are read on the game's thread");
    return ok;
  }();
  if (!running) return nullptr;
  auto p = std::make_shared<Prefetch>();
  p->movie = std::move(movie);
  {
    std::lock_guard<std::mutex> lock(g_ahead_mutex);
    g_ahead.push_back(p);
  }
  g_ahead_cv.notify_one();
  return p;
}

// Frame `f`'s bytes into `out`: from the read-ahead when it has them, else read here. The window moves to f + 1.
bool TakeFrame(Prefetch& p, uint32_t f, std::vector<uint8_t>* out) {
  bool hit = false;
  {
    std::lock_guard<std::mutex> lock(p.m);
    p.want = int64_t(f) + 1;
    auto it = p.ready.find(f);
    if (it != p.ready.end()) {
      out->swap(it->second);
      hit = true;
    }
    // frames behind the decoder, or past the window after a jump back, are not needed
    for (auto i = p.ready.begin(); i != p.ready.end();) {
      if (int64_t(i->first) < p.want || int64_t(i->first) >= p.want + kAhead)
        i = p.ready.erase(i);
      else
        ++i;
    }
    ++(hit ? p.hits : p.misses);
  }
  g_ahead_cv.notify_one();
  return hit || p.movie->ReadFrame(f, out);
}

// One open movie's decoder, by the movie's id.
struct Decoder {
  std::shared_ptr<const rex::filesystem::SfdHevcMovie> movie;
  std::shared_ptr<Prefetch> ahead;
  NxvDecoder* d = nullptr;
  int64_t next = 0;  // the next frame nxv_decode would give
  std::vector<uint8_t> bytes;
  std::chrono::steady_clock::time_point used;
  double decode_ms = 0, copy_ms = 0;
  double read_ms = 0, nxv_ms = 0;  // of decode_ms: the frames' bytes taken (or read), and nxv_decode
  uint64_t frames = 0;
};

// nxv_decode at rr6_hevc_decode_priority (see the cvar), timed into dc.nxv_ms.
int DecodeRaised(Decoder& dc, NxvPicture* pic) {
  static const int boost = REXCVAR_GET(rr6_hevc_decode_priority);
  s32 own = 0;
  const bool raised = boost > 0 && R_SUCCEEDED(svcGetThreadPriority(&own, CUR_THREAD_HANDLE)) && own > boost &&
                      R_SUCCEEDED(svcSetThreadPriority(CUR_THREAD_HANDLE, u32(boost)));
  const auto t0 = std::chrono::steady_clock::now();
  const int r = nxv_decode(dc.d, dc.bytes.data(), int(dc.bytes.size()), pic);
  dc.nxv_ms += std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
  if (raised) svcSetThreadPriority(CUR_THREAD_HANDLE, u32(own));
  return r;
}

// nxvideo's own steps since its last call (then cleared), as culdcept-nx's [wmv] nxvideo line.
void NxvLine(Decoder& dc) {
  NxvStats st;
  nxv_stats(dc.d, &st);
  if (!st.frames) return;
  const double n = double(st.frames);
  REXLOG_INFO("[hevc] {}: nxvideo a picture ({}): send {:.2f} ms, receive {:.2f} ms, transfer {:.2f} ms; NVDEC {} MHz "
              "(DFS's start {} MHz, put back {} times), VIC {} MHz; copied out by the VIC {}, by the CPU {}",
              dc.movie->name, st.frames, st.send_ms / n, st.receive_ms / n, st.transfer_ms / n, st.nvdec_hz / 1000000,
              st.nvdec_max_hz / 1000000, st.restores, st.vic_hz / 1000000, st.vic_frames, st.cpu_frames);
}
std::mutex g_mutex;
std::map<uint32_t, Decoder> g_decoders;

void CloseIdle() {
  const auto now = std::chrono::steady_clock::now();
  for (auto it = g_decoders.begin(); it != g_decoders.end();) {
    if (now - it->second.used > std::chrono::seconds(15)) {
      if (it->second.d) nxv_close(it->second.d);
      it = g_decoders.erase(it);
    } else {
      ++it;
    }
  }
}

// Frame `index` of the movie into `pic`: decoded in order from the last one, or from the keyframe at or before it.
bool DecodeTo(Decoder& dc, uint32_t index, NxvPicture* pic) {
  const auto& frames = dc.movie->frames;
  if (index >= frames.size()) return false;
  if (!dc.d) {
    char why[256] = {};
    static const bool hw = REXCVAR_GET(rr6_hevc_nvdec);
    dc.d = nxv_open(NXV_HEVC, nullptr, 0, int(dc.movie->width), int(dc.movie->height), hw ? 1 : 0, why, sizeof(why));
    REXLOG_INFO("[hevc] {}: {}", dc.movie->name, dc.d ? why : "the H.265 decoder did not open");
    if (!dc.d) return false;
    dc.next = 0;
  }
  if (int64_t(index) < dc.next || int64_t(index) > dc.next + 120) {
    int64_t k = index;
    while (k > 0 && !frames[size_t(k)].keyframe) --k;
    if (!(int64_t(index) >= dc.next && k <= dc.next)) {
      nxv_flush(dc.d);
      dc.next = k;
    }
  }
  bool got = false;
  while (dc.next <= int64_t(index)) {
    const uint32_t f = uint32_t(dc.next++);
    const auto t0 = std::chrono::steady_clock::now();
    if (!(dc.ahead ? TakeFrame(*dc.ahead, f, &dc.bytes) : dc.movie->ReadFrame(f, &dc.bytes))) return false;
    dc.read_ms += std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
    const int r = DecodeRaised(dc, pic);
    got = r == 1 && f == index;
    if (r < 0) {
      REXLOG_WARN("[hevc] {}: frame {} did not decode", dc.movie->name, f);
      return false;
    }
  }
  return got;
}

void WritePicture(uint8_t* base, const NxvPicture& pic, const Planes& pl, uint32_t w, uint32_t h) {
  const uint32_t fw = std::min<uint32_t>(w, uint32_t(pic.width)), fh = std::min<uint32_t>(h, uint32_t(pic.height));
  for (uint32_t y = 0; y < fh; ++y)
    std::memcpy(Host(base, pl.y + y * pl.y_pitch), pic.data[0] + size_t(y) * size_t(pic.linesize[0]), fw);
  const uint32_t cw = fw / 2, ch = fh / 2;
  for (uint32_t y = 0; y < ch; ++y) {
    uint8_t* u = Host(base, pl.cb + y * pl.c_pitch);
    uint8_t* v = Host(base, pl.cr + y * pl.c_pitch);
    if (pic.nv12) {
      const uint8_t* s = pic.data[1] + size_t(y) * size_t(pic.linesize[1]);
      for (uint32_t x = 0; x < cw; ++x) {
        u[x] = s[2 * x];
        v[x] = s[2 * x + 1];
      }
    } else {
      std::memcpy(u, pic.data[1] + size_t(y) * size_t(pic.linesize[1]), cw);
      std::memcpy(v, pic.data[2] + size_t(y) * size_t(pic.linesize[2]), cw);
    }
  }
  rex::memory::MarkStoreCardsAt(base, pl.y, pl.y_pitch * ((h + 15) & ~15u));
  rex::memory::MarkStoreCardsAt(base, pl.cb, pl.c_pitch * ((h + 15) & ~15u));
}
#endif

}  // namespace

// (1) One slice: a tagged one decodes no macroblocks and ends the picture.
REX_HOOK_RAW(sub_822FB420) {
  static const bool on = REXCVAR_GET(rr6_hevc_movies);
  if (!on) {
    __imp__sub_822FB420(ctx, base);
    return;
  }
  const uint32_t mpv = ctx.r3.u32, reader = ctx.r4.u32, r1 = ctx.r1.u32;
  // A look at the slice's bytes as the slice decoder's own first call takes them: the reader (CRI's stream joint) hands
  // out its data lane's bytes from the start code on (vtable +24, GetChunk(sj, 1, 0x7FFFFFFF, &chunk): mpv+5384 the
  // address, mpv+5388 the length), and they are given back as they were (+28, UngetChunk(sj, 1, &chunk)), as the slice
  // loop sub_822FB638 does for its own look.
  bool tagged = false;
  if (reader) {
    const uint32_t vtable = Ld32(base, reader);
    PPCFunc* get = rex::runtime::ResolveIndirectFunction(Ld32(base, vtable + 24));
    PPCFunc* unget = rex::runtime::ResolveIndirectFunction(Ld32(base, vtable + 28));
    if (get && unget) {
      ctx.r1.u64 = r1 - 128;
      ctx.r3.u64 = reader;
      ctx.r4.u64 = 1;
      ctx.r5.u64 = 0x7FFFFFFF;
      ctx.r6.u64 = mpv + 5384;
      get(ctx, base);
      const uint32_t p = Ld32(base, mpv + 5384), len = Ld32(base, mpv + 5388);
      static const bool diag = REXCVAR_GET(rr6_hevc_log);
      static std::atomic<int> shown_peeks{0};
      if (diag && p && shown_peeks.fetch_add(1, std::memory_order_relaxed) < 6) {
        const uint8_t* q = Host(base, p);
        REXLOG_INFO("[hevc] slice hook: mpv {:08X}, reader {:08X} (GetChunk {:08X}, UngetChunk {:08X}), chunk {:08X} length {}, "
                    "bytes {:02X} {:02X} {:02X} {:02X} {:02X} {:02X} {:02X} {:02X} {:02X} {:02X}",
                    mpv, reader, Ld32(base, vtable + 24), Ld32(base, vtable + 28), p, len, q[0], q[1], q[2], q[3], q[4],
                    q[5], q[6], q[7], q[8], q[9]);
        if (shown_peeks.load(std::memory_order_relaxed) == 1) {
          std::string words;
          for (uint32_t k = 0; k < 64; k += 4) words += fmt::format(" {:08X}", Ld32(base, reader + k));
          REXLOG_INFO("[hevc] the reader's first 64 bytes:{}", words);
        }
      }
      const uint8_t* s = p ? Host(base, p) : nullptr;
      uint8_t head[4 + 8 + rex::filesystem::kSfdHevcTagBytes] = {};
      const uint32_t have = s ? std::min<uint32_t>(len, uint32_t(sizeof(head))) : 0;
      if (have) std::memcpy(head, s, have);
      ctx.r1.u64 = r1 - 128;
      ctx.r3.u64 = reader;
      ctx.r4.u64 = 1;
      ctx.r5.u64 = mpv + 5384;
      unget(ctx, base);
      ctx.r1.u64 = r1;
      s = head;
      uint8_t tag[rex::filesystem::kSfdHevcTagBytes];
      if (have >= 4 && s[0] == 0 && s[1] == 0 && s[2] == 1 && s[3] >= 0x01 && s[3] <= 0xAF) {
        for (uint32_t off = 4; off <= 8 && off + rex::filesystem::kSfdHevcTagBytes <= have && !tagged; ++off) {
          uint32_t id, index;
          if (rex::filesystem::ParseSfdHevcTag(s + off, &id, &index)) {
            tagged = true;
            std::memcpy(tag, s + off, sizeof(tag));
            std::lock_guard<std::mutex> lock(g_mpv_mutex);
            g_mpv_movie[mpv] = id;
          }
        }
        // The chunk ends before the tag. The ring's wrap cannot do it: the reader is CRI's SJRBF (GetChunk sub_8231D4C8:
        // object +28 the buffer, +32 its size, +36 an extra area after it, 2 KB for the movies, +24 the data's position,
        // +12 how much there is) and hands out data contiguously as far as the extra area's end, which PutChunk
        // (sub_8231D668) keeps a copy of the buffer's first bytes in; MPV decodes a picture only when it is all in the
        // buffer. A safety net all the same (counted in the [hevc] line): a decoder that is playing an H.265 movie still
        // decodes no macroblocks, and the picture gets the movie's tag with no display index (the frame after the last
        // one shown).
        if (!tagged && have < sizeof(head)) {
          std::lock_guard<std::mutex> lock(g_mpv_mutex);
          auto it = g_mpv_movie.find(mpv);
          if (it != g_mpv_movie.end()) {
            tagged = true;
            rex::filesystem::MakeSfdHevcTag(it->second, kIndexUnknown, tag);
            g_cut_tags.fetch_add(1, std::memory_order_relaxed);
          }
        }
        if (tagged) {
          // The tag into the picture's Y plane (mpv+696), where mwPlyGetCurFrm finds it when the game shows it.
          const uint32_t y = Ld32(base, mpv + 696);
          if (y) {
            std::memcpy(Host(base, y), tag, sizeof(tag));
            rex::memory::MarkStoreCardsAt(base, y, sizeof(tag));
          }
        }
      }
    }
  }
  ctx.r3.u64 = mpv;
  ctx.r4.u64 = reader;
  if (tagged) {
    St32(base, mpv + 732, kNoOpFunction);  // the picture type's macroblock decoder: none (set again each picture)
    g_tagged_slices.fetch_add(1, std::memory_order_relaxed);
  }
  __imp__sub_822FB420(ctx, base);
  if (tagged) St32(base, mpv + 852, Ld32(base, mpv + 864));  // every macroblock done: the slice loop ends
}

// (2) The frame to show: a tagged one gets its H.265 picture.
REX_HOOK_RAW(sub_822DCD80) {
  const uint32_t frm = ctx.r4.u32;
  __imp__sub_822DCD80(ctx, base);
  static const bool on = REXCVAR_GET(rr6_hevc_movies);
  if (!on || !frm) return;
  const uint32_t buf = Ld32(base, frm + 0);
  if (!buf) return;
  uint32_t id, index;
  static const bool diag = REXCVAR_GET(rr6_hevc_log);
  static std::atomic<int> shown_frames{0};
  if (diag && shown_frames.fetch_add(1, std::memory_order_relaxed) < 4) {
    const uint8_t* q = Host(base, buf);
    REXLOG_INFO("[hevc] mwPlyGetCurFrm: buffer {:08X} {}x{}, first bytes {:02X} {:02X} {:02X} {:02X} {:02X}; {} slices "
                "skipped so far",
                buf, Ld32(base, frm + 12), Ld32(base, frm + 16), q[0], q[1], q[2], q[3], q[4],
                g_tagged_slices.load(std::memory_order_relaxed));
  }
  if (!rex::filesystem::ParseSfdHevcTag(Host(base, buf), &id, &index)) return;
  const uint32_t w = Ld32(base, frm + 12), h = Ld32(base, frm + 16);
  if (!w || !h || w > 4096 || h > 4096) return;
  const Planes pl = SofdecPlanes(buf, w, h);
#if RR6_NXVIDEO
  std::lock_guard<std::mutex> lock(g_mutex);
  auto it = g_decoders.find(id);
  if (it == g_decoders.end()) {
    CloseIdle();
    auto movie = rex::filesystem::FindSfdHevcMovie(id);
    if (!movie) {
      if (g_missing.fetch_add(1, std::memory_order_relaxed) < 4)
        REXLOG_WARN("[hevc] a tagged picture of movie id {} that is not open", id);
      return;
    }
    it = g_decoders.emplace(id, Decoder{}).first;
    it->second.ahead = StartAhead(movie);
    it->second.movie = std::move(movie);
  }
  Decoder& dc = it->second;
  dc.used = std::chrono::steady_clock::now();
  if (index == kIndexUnknown) {
    index = uint32_t(dc.next);  // a tag cut short by the reader's ring buffer: the frame after the last one
    if (index >= dc.movie->frames.size()) return;
  }
  const auto t0 = std::chrono::steady_clock::now();
  NxvPicture pic{};
  if (!DecodeTo(dc, index, &pic)) return;
  const auto t1 = std::chrono::steady_clock::now();
  WritePicture(base, pic, pl, w, h);
  const auto t2 = std::chrono::steady_clock::now();
  dc.decode_ms += std::chrono::duration<double, std::milli>(t1 - t0).count();
  dc.copy_ms += std::chrono::duration<double, std::milli>(t2 - t1).count();
  ++dc.frames;
  const uint64_t shown = g_shown.fetch_add(1, std::memory_order_relaxed) + 1;
  static const bool log = REXCVAR_GET(rr6_hevc_log);
  if (shown == 1 || (log && dc.frames % 300 == 0)) {
    uint64_t hits = 0, misses = 0;
    if (dc.ahead) {
      std::lock_guard<std::mutex> pl(dc.ahead->m);
      hits = dc.ahead->hits;
      misses = dc.ahead->misses;
    }
    REXLOG_INFO("[hevc] {}: picture {} of {} shown from H.265 ({}x{}); {} pictures, {:.2f} ms decoding ({:.2f} taking "
                "the frames: {} from the read-ahead, {} read here; {:.2f} in nxv_decode) and {:.2f} ms copying a "
                "picture; {} slices skipped in all ({} tags cut short by the reader's ring buffer)",
                dc.movie->name, index, dc.movie->frames.size(), w, h, dc.frames, dc.decode_ms / double(dc.frames),
                dc.read_ms / double(dc.frames), hits, misses, dc.nxv_ms / double(dc.frames),
                dc.copy_ms / double(dc.frames), g_tagged_slices.load(std::memory_order_relaxed),
                g_cut_tags.load(std::memory_order_relaxed));
    if (log) NxvLine(dc);
  }
#else
  (void)pl;
  (void)index;
  if (g_missing.fetch_add(1, std::memory_order_relaxed) == 0)
    REXLOG_WARN("[hevc] movie id {}: an H.265 movie, and this build has no H.265 decoder (the Switch's nxvideo)", id);
#endif
}
