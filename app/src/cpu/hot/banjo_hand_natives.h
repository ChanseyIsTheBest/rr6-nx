// banjo-nx - hand-written native versions of hot guest functions (CPU enhancements banjo_hand_*).
//
// The localized copies of tools/localize_native.py keep a function's own statements; these replace the statements:
// the XDK C runtime's memcpy and memset and Direct3D's two shader float-constant writers, written from what the
// routines do. They are sa2-nx's natives (app/src/cpu/hot/n_827F05C0.h, n_827EFEA0.h, n_d3d_constants.h, GPL-3.0;
// the memcpy came there from masseffect-nx's n_82AC4AF0.h): tools/crt_signatures.py of sa2-nx finds the same three C
// runtime routines in Banjo's image (unique matches), and the two constant writers are the same instructions with
// the same two offsets. Banjo's own additions are the two writers of Direct3D's state flush (namespace flush below).
// What is different here is how they are used and checked:
//
//   * Each is a template on the store policy of banjo_hot_common.h, so the guard's logged form records what it is
//     about to write like any generated copy (no hand-written list of written ranges).
//   * tools/localize_native.py puts them IN FRONT of the generated copy of the same function wherever that copy is
//     used: as a hook of its own, and inside every other function's copy that contains it (app/src/cpu/hot/hand.txt).
//     Inside a caller's copy the call is inlined: no hook, no hand-over of every register (on the Switch that
//     hand-over is what made copies with real calls slower than their originals).
//   * A native returns false to DECLINE a call it does not cover (nothing written yet): the generated copy of the
//     original then runs, in the same place.
//   * The registers the original leaves behind as scratch (hand.txt gives them per function; tools/localize_native.py
//     takes them from the original's own statements) are NOT reproduced: the natives write no register. Those
//     registers are left out of the guard's register compare for every hook whose copy contains the native. Sound
//     because they are caller-saved scratch of assembly routines and of a callee the callers reach through the
//     normal calling convention: a caller that read one after the call would get a different value, would act on
//     it, and the guard would see that in everything else it compares.
//
// ARM (the A57 is where this has to pay, and sa2-nx's first native Direct3D layer lost there for reasons no PC run
// showed: docs/api-renderer.md of sa2-nx, section 6): nothing here is per thread (no thread_local: a function call on
// the Switch), nothing copies a context, no loop keeps a count where a store could alias it, nothing is byte-swapped
// word by word (the copies are guest order to guest order), and sizes up to 128 bytes (memcpy; 64 for memset) are
// moved with overlapping 16/8/4/2-byte loads and stores without a call into the C library. In a PC run of title,
// menus, intro and gameplay 62 % of the 21.9 million memcpy calls were under 64 bytes and 21 % were 64 to 127; 46 %
// of the memsets were 4 to 7 bytes; 98 % of the 26 million constant uploads were 1 to 7 vectors.
//
// Guest function addresses may be named in this folder only (tools/direct_calls.py and tools/localize_native.py
// read every other source's addresses as hooked functions; these four are hooked, by app/src/cpu/hot/localized.txt).
#pragma once

#include <cmath>
#include <cstdint>
#include <cstring>

#include <rex/ppc/context.h>

#if defined(__aarch64__)
#include <arm_neon.h>
#endif

#include "cpu/banjo_hot_common.h"
#include <rex/ppc/diet_ops.h>  // katamari-nx: rex::ppc::SingleToDoublePure

// katamari-nx: the in-run A/B's target in its off half (renut_engine/gpu/banjo_renut_tuning.cpp).
#include <atomic>
namespace banjo::renut_gpu {
extern std::atomic<int> g_ab_off;
}  // namespace banjo::renut_gpu

namespace banjo::hand {

// The natives' own keys (banjo_hot_guest.cpp), each read once: 0 not read yet, 1 off, 2 on.
// katamari-nx: kMatCopy / kMatMul / kMatTranslation are Beautiful Katamari's (the end of this file); kMemset serves its
// C runtime memset too. N&B's other natives stay for reference: hand.txt does not list them here, so they never compile.
// rr6-nx (2026-11-08): the first four, from the console profile of 2026-11-05 (hand.txt): banjo-nx's memcpy native for
// this game's C runtime memcpy, and three routines of the game's matrix library (the end of this file).
enum : uint32_t {
  kMemcpy = 0,
  kMatMul = 1,
  kMatTranspose = 2,
  kVecMat = 3,
  kNatives = 4
};
extern uint8_t g_state[kNatives];
uint8_t Init(uint32_t which);
[[gnu::always_inline]] inline bool On(uint32_t which) {
  const uint8_t state = g_state[which];
  if (state == 2) [[likely]] return true;
  return state == 0 && Init(which) == 2;
}

namespace detail {

// 16 bytes through a register (any alignment; one NEON load or store on the A57).
struct B16 {
  uint8_t b[16];
};
[[gnu::always_inline]] inline B16 L16(const uint8_t* p) {
  B16 v;
  std::memcpy(v.b, p, 16);
  return v;
}
[[gnu::always_inline]] inline void S16(uint8_t* p, const B16& v) { std::memcpy(p, v.b, 16); }

// 1 <= n <= 64; all loads before all stores (memmove semantics for dst <= src overlap).
[[gnu::always_inline]] inline void CopySmall(uint8_t* d, const uint8_t* s, uint32_t n) {
  if (n >= 16) {
    if (n > 32) {
      const B16 a = L16(s), b = L16(s + 16), c = L16(s + n - 32), e = L16(s + n - 16);
      S16(d, a);
      S16(d + 16, b);
      S16(d + n - 32, c);
      S16(d + n - 16, e);
    } else {
      const B16 a = L16(s), e = L16(s + n - 16);
      S16(d, a);
      S16(d + n - 16, e);
    }
  } else if (n >= 8) {
    uint64_t a, e;
    std::memcpy(&a, s, 8);
    std::memcpy(&e, s + n - 8, 8);
    std::memcpy(d, &a, 8);
    std::memcpy(d + n - 8, &e, 8);
  } else if (n >= 4) {
    uint32_t a, e;
    std::memcpy(&a, s, 4);
    std::memcpy(&e, s + n - 4, 4);
    std::memcpy(d, &a, 4);
    std::memcpy(d + n - 4, &e, 4);
  } else if (n >= 2) {
    uint16_t a, e;
    std::memcpy(&a, s, 2);
    std::memcpy(&e, s + n - 2, 2);
    std::memcpy(d, &a, 2);
    std::memcpy(d + n - 2, &e, 2);
  } else {
    *d = *s;
  }
}

// 64 < n <= 128; all loads before all stores. (Banjo's calls: a fifth are 64 to 127 bytes.)
[[gnu::always_inline]] inline void CopyMedium(uint8_t* d, const uint8_t* s, uint32_t n) {
  const B16 a = L16(s), b = L16(s + 16), c = L16(s + 32), e = L16(s + 48);
  const B16 f = L16(s + n - 64), g = L16(s + n - 48), h = L16(s + n - 32), i = L16(s + n - 16);
  S16(d, a);
  S16(d + 16, b);
  S16(d + 32, c);
  S16(d + 48, e);
  S16(d + n - 64, f);
  S16(d + n - 48, g);
  S16(d + n - 32, h);
  S16(d + n - 16, i);
}

// 1 <= n <= 64, every byte = v.
[[gnu::always_inline]] inline void FillSmall(uint8_t* d, uint8_t v, uint32_t n) {
  if (n >= 16) {
    B16 x;
    std::memset(x.b, v, 16);
    S16(d, x);
    S16(d + n - 16, x);
    if (n > 32) {
      S16(d + 16, x);
      S16(d + n - 32, x);
    }
  } else {
    const uint64_t x = uint64_t(v) * 0x0101010101010101ull;
    if (n >= 8) {
      std::memcpy(d, &x, 8);
      std::memcpy(d + n - 8, &x, 8);
    } else if (n >= 4) {
      std::memcpy(d, &x, 4);
      std::memcpy(d + n - 4, &x, 4);
    } else if (n >= 2) {
      std::memcpy(d, &x, 2);
      std::memcpy(d + n - 2, &x, 2);
    } else {
      *d = v;
    }
  }
}

// [a, a + n) is one stretch of host memory: it does not wrap around 4 GB and (on hosts with the physical-view
// offset) does not cross its boundary. n >= 1.
[[gnu::always_inline]] inline bool Straight(uint32_t a, uint32_t n) {
  if (uint64_t(a) + n > 0x100000000ull) return false;
  return ::banjo::hot::PhysOff(a) == ::banjo::hot::PhysOff(a + n - 1u);
}

}  // namespace detail

// ---------------------------------------------------------------------------------------------------------------------
// rr6-nx (2026-11-08): Ridge Racer 6's hand-written natives. The evidence is the console profile of 2026-11-05 16:28
// (the build of 16:17, handheld, sampling on; out/console_runs/sd_last_2026-11-05, read with that build's ELF), the
// race's 27 ten-second windows; hand.txt has each line's figures.
// ---------------------------------------------------------------------------------------------------------------------

// sub_82309770 - the game's XDK C runtime memcpy (XDK 2.0.2135): r3 = dst, r4 = src, r5 = n; returns r3 as it came.
// The same contract as N&B's and Katamari's (banjo-nx's native, sa2-nx's), read from its 264 instructions: `std
// r3,-8(r1)` first and `ld r3,-8(r1)` at each of its three returns; a byte head up to 8-byte destination alignment
// (or the whole copy when it is shorter), then by the source's alignment 128-byte blocks, doublewords, words or
// bytes (the unaligned-source blocks build words from four bytes), every unit's loads ahead of its stores and the
// units upward, so for dst <= src the result is memmove's; sizes and addresses their 32-bit parts (cmplw, rlwinm,
// bdnz on ctr's low word); dcbt / dcbtst are hints and there is no dcbz; nothing read or written outside the two
// ranges. The block loops' unreachable `b .` (the prefetch counter cannot run out first: 128 * blocks >= n - 127)
// changes nothing. Declined: a forward overlap (dst > src, dst - src < n: the original smears), ranges that wrap,
// a destination over the save slot. Scratch not reproduced (hand.txt exact=r3): r0, r4-r12, ctr, cr0/1/6/7, xer.
namespace n_82309770 {

template <class S>
[[gnu::always_inline]] inline bool Native(PPCContext& __restrict ctx, uint8_t* base, [[maybe_unused]] S& s) {
  if (!On(kMemcpy)) [[unlikely]] return false;
  const uint32_t dst = ctx.r3.u32, src = ctx.r4.u32, n = ctx.r5.u32, slot = ctx.r1.u32 - 8u;
  s.Hand(kMemcpy, n);
  if (n) {
    if (uint32_t(dst - src - 1u) < n - 1u) [[unlikely]] return false;  // dst > src, dst - src < n
    if (!detail::Straight(dst, n) || !detail::Straight(src, n)) [[unlikely]] return false;
    if (uint64_t(uint32_t(slot + 7u - dst)) < uint64_t(n) + 7u) [[unlikely]] return false;  // dst covers the slot
  }
  if (!s.Note(slot, 8)) [[unlikely]] return true;
  const uint64_t saved = __builtin_bswap64(ctx.r3.u64);
  std::memcpy(::banjo::hot::Raw(base, slot), &saved, 8);
  if (n == 0) return true;
  if (!s.Note(dst, n)) [[unlikely]] return true;
  ::banjo::hot::Card(base, dst, n);
  uint8_t* d = ::banjo::hot::Raw(base, dst);
  const uint8_t* p = ::banjo::hot::Raw(base, src);
  if (n <= 64) {
    detail::CopySmall(d, p, n);
  } else if (n <= 128) {
    detail::CopyMedium(d, p, n);
  } else if (uint32_t(src - dst) < n) {
    std::memmove(d, p, n);  // dst < src (or equal), overlapping: the forward copy is memmove
  } else {
    std::memcpy(d, p, n);
  }
  return true;
}

}  // namespace n_82309770

// The game's matrix library takes its matrices BY VALUE: each routine below copies its 64-byte matrix operands into
// the red zone under r1 with eight ld / std, then reads them back with lvx. On the A57 such a 16-byte load of what
// 8-byte stores wrote just before is not forwarded: it waits for the stores to reach the cache, four times per
// matrix. The natives make the same red-zone stores (the guest sees them) and take the vectors from the operands
// themselves, then run the generated statements in their order: vmrghw vD,vA,vB = unpackhi_epi32(vB, vA) and vmrglw
// = unpacklo_epi32(vB, vA) in the generated code's register layout, vmsum4fp128 = simde_mm_dp_ps(.., 0xFF) with the
// flush mode on, as the generated code computes them. Each writes every register its original writes back with the
// value it leaves (hand.txt exact= lists them all: the guard compares everything). Declined: r1 not 16-aligned (the
// lvx would read other bytes), an operand over the red zone (the copies would change it before it is read), ranges
// that wrap.
namespace rr6 {

[[gnu::always_inline]] inline simde__m128i Reverse16(simde__m128i v) {
  return simde_mm_shuffle_epi8(v, simde_mm_set_epi8(0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15));
}
// A guest vector into the generated code's register layout (lvx: REX_BSWAP128 of the 16 bytes), and back (stvx).
[[gnu::always_inline]] inline simde__m128i LoadV(const uint8_t* p) {
  return Reverse16(simde_mm_loadu_si128(reinterpret_cast<const simde__m128i*>(p)));
}
[[gnu::always_inline]] inline void StoreV(uint8_t* p, simde__m128i v) {
  simde_mm_storeu_si128(reinterpret_cast<simde__m128i*>(p), Reverse16(v));
}
[[gnu::always_inline]] inline simde__m128i Dp(simde__m128i a, simde__m128i b) {
  return simde_mm_castps_si128(simde_mm_dp_ps(simde_mm_castsi128_ps(a), simde_mm_castsi128_ps(b), 0xFF));
}
[[gnu::always_inline]] inline simde__m128i Hi(simde__m128i b, simde__m128i a) { return simde_mm_unpackhi_epi32(b, a); }
[[gnu::always_inline]] inline simde__m128i Lo(simde__m128i b, simde__m128i a) { return simde_mm_unpacklo_epi32(b, a); }
[[gnu::always_inline]] inline void PutV(PPCVRegister& r, simde__m128i v) {
  simde_mm_store_si128(reinterpret_cast<simde__m128i*>(r.u8), v);
}
// [a, a + an) and [b, b + bn) share no byte.
[[gnu::always_inline]] inline bool Apart(uint32_t a, uint32_t an, uint32_t b, uint32_t bn) {
  return uint64_t(a) + an <= b || uint64_t(b) + bn <= a;
}

}  // namespace rr6

// sub_820E33B0 - 4x4 matrix product: r3 = out (rows stored with stvx), r4 = A, r5 = B (any alignment). 77
// instructions: B copied to r1-128 and A to r1-64, B transposed from its reloads, sixteen vmsum4fp128 with A's
// rows, the four rows stored to out, out+16, out+48, out+32 in that order. Inlined into 47 copies, among them those of
// the drawing thread's sub_82218290 (camera matrices and their shader constants: six products) and sub_820E6658 (three
// rotations, each multiplied in). All loads come before the first store to out: in-place calls are fine. Written back
// as the original leaves them: r5 (+ 64), r9 (r3 + 48), r10 (r3 + 32), v0-v13; r11, ctr and v26-v31 are locals of
// the generated function.
namespace n_820E33B0 {

template <class S>
[[gnu::always_inline]] inline bool Native(PPCContext& __restrict ctx, uint8_t* base, S& s) {
  if (!On(kMatMul)) [[unlikely]] return false;
  const uint32_t sp = ctx.r1.u32, a = ctx.r4.u32, b = ctx.r5.u32, out = ctx.r3.u32 & ~15u, red = sp - 128u;
  if (sp & 15u) [[unlikely]] return false;
  if (!detail::Straight(red, 128) || !detail::Straight(a, 64) || !detail::Straight(b, 64) ||
      !detail::Straight(out, 64)) [[unlikely]]
    return false;
  if (!rr6::Apart(a, 64, red, 128) || !rr6::Apart(b, 64, red, 128)) [[unlikely]] return false;
  s.Hand(kMatMul, 64);
  const uint8_t* pa = ::banjo::hot::Raw(base, a);
  const uint8_t* pb = ::banjo::hot::Raw(base, b);
  // The by-value copies: B at r1-128, A at r1-64.
  if (!s.Note(red, 128)) [[unlikely]] return true;
  ::banjo::hot::Card(base, red, 128);
  uint8_t* r = ::banjo::hot::Raw(base, red);
  std::memcpy(r, pb, 64);
  std::memcpy(r + 64, pa, 64);
  using namespace rr6;
  simde__m128i v0 = LoadV(pb + 32);   // lvx v0, r1-96
  simde__m128i v11 = LoadV(pb);       // lvx v11, r1-128
  simde__m128i v13 = Hi(v0, v11);     // vmrghw v13,v11,v0
  v11 = Lo(v0, v11);                  // vmrglw v11,v11,v0
  simde__m128i v9 = LoadV(pb + 48);   // lvx v9, r1-80
  simde__m128i v8 = LoadV(pb + 16);   // lvx v8, r1-112
  simde__m128i v12 = Hi(v9, v8);      // vmrghw v12,v8,v9
  simde__m128i v7 = Lo(v9, v8);       // vmrglw v7,v8,v9
  simde__m128i v10 = LoadV(pa);       // lvx v10, r1-64
  v0 = Hi(v12, v13);                  // vmrghw v0,v13,v12
  v13 = Lo(v12, v13);                 // vmrglw v13,v13,v12
  v12 = Hi(v7, v11);                  // vmrghw v12,v11,v7
  v11 = Lo(v7, v11);                  // vmrglw v11,v11,v7
  v9 = LoadV(pa + 16);                // lvx v9, r1-48
  ctx.fpscr.enableFlushMode();
  v7 = Dp(v10, v0);
  simde__m128i v3 = Dp(v10, v12);
  simde__m128i v2 = Dp(v10, v11);
  simde__m128i v6 = Dp(v10, v13);
  v10 = LoadV(pa + 48);               // lvx v10, r1-16
  simde__m128i v5 = Dp(v9, v0);
  v8 = LoadV(pa + 32);                // lvx v8, r1-32
  simde__m128i v4 = Dp(v9, v13);
  simde__m128i v1 = Dp(v9, v12);
  v9 = Dp(v9, v11);
  const simde__m128i v30 = Dp(v8, v12);
  const simde__m128i v28 = Dp(v10, v0);
  v12 = Dp(v10, v12);
  const simde__m128i v31 = Dp(v8, v0);
  const simde__m128i v29 = Dp(v8, v13);
  const simde__m128i v27 = Dp(v10, v13);
  const simde__m128i v26 = Dp(v10, v11);
  v8 = Dp(v8, v11);
  v0 = Hi(v3, v7);                    // vmrghw v0,v7,v3
  v13 = Hi(v2, v6);                   // vmrghw v13,v6,v2
  v11 = Hi(v1, v5);                   // vmrghw v11,v5,v1
  v10 = Hi(v9, v4);                   // vmrghw v10,v4,v9
  v0 = Hi(v13, v0);                   // vmrghw v0,v0,v13
  v13 = Hi(v12, v28);                 // vmrghw v13,v28,v12
  v12 = Hi(v10, v11);                 // vmrghw v12,v11,v10
  v9 = Hi(v30, v31);                  // vmrghw v9,v31,v30
  v11 = Hi(v26, v27);                 // vmrghw v11,v27,v26
  v8 = Hi(v8, v29);                   // vmrghw v8,v29,v8
  const simde__m128i row0 = v0;       // stvx v0, r3
  v0 = Hi(v11, v13);                  // vmrghw v0,v13,v11
  v10 = Hi(v8, v9);                   // vmrghw v10,v9,v8
  if (!s.Note(out, 64)) [[unlikely]] return true;
  ::banjo::hot::Card(base, out, 64);
  uint8_t* d = ::banjo::hot::Raw(base, out);
  StoreV(d, row0);
  StoreV(d + 16, v12);
  StoreV(d + 48, v0);
  StoreV(d + 32, v10);
  ctx.r5.s64 = ctx.r5.s64 + 64;
  ctx.r9.s64 = ctx.r3.s64 + 48;
  ctx.r10.s64 = ctx.r3.s64 + 32;
  PutV(ctx.v0, v0);
  PutV(ctx.v1, v1);
  PutV(ctx.v2, v2);
  PutV(ctx.v3, v3);
  PutV(ctx.v4, v4);
  PutV(ctx.v5, v5);
  PutV(ctx.v6, v6);
  PutV(ctx.v7, v7);
  PutV(ctx.v8, v8);
  PutV(ctx.v9, v9);
  PutV(ctx.v10, v10);
  PutV(ctx.v11, v11);
  PutV(ctx.v12, v12);
  PutV(ctx.v13, v13);
  return true;
}

}  // namespace n_820E33B0

// sub_82153688 - 4x4 matrix transpose: r3 = out (stvx), r4 = M (any alignment). 33 instructions: M copied to r1-64,
// reloaded, transposed with vmrghw / vmrglw, the four rows stored to out .. out+48. Seven calls in sub_82218290 (the
// camera's matrices into its shader-constant block). No float arithmetic, so the flush mode is not touched. Written
// back as the original leaves them: r9 (r3 + 48), r10 (r3 + 32), v0, v9-v13; r11 and ctr are locals.
namespace n_82153688 {

template <class S>
[[gnu::always_inline]] inline bool Native(PPCContext& __restrict ctx, uint8_t* base, S& s) {
  if (!On(kMatTranspose)) [[unlikely]] return false;
  const uint32_t sp = ctx.r1.u32, m = ctx.r4.u32, out = ctx.r3.u32 & ~15u, red = sp - 64u;
  if (sp & 15u) [[unlikely]] return false;
  if (!detail::Straight(red, 64) || !detail::Straight(m, 64) || !detail::Straight(out, 64)) [[unlikely]] return false;
  if (!rr6::Apart(m, 64, red, 64)) [[unlikely]] return false;
  s.Hand(kMatTranspose, 64);
  const uint8_t* pm = ::banjo::hot::Raw(base, m);
  if (!s.Note(red, 64)) [[unlikely]] return true;
  ::banjo::hot::Card(base, red, 64);
  std::memcpy(::banjo::hot::Raw(base, red), pm, 64);
  using namespace rr6;
  simde__m128i v12 = LoadV(pm + 32);  // lvx v12, r1-32
  simde__m128i v10 = LoadV(pm + 48);  // lvx v10, r1-16
  simde__m128i v9 = LoadV(pm + 16);   // lvx v9, r1-48
  simde__m128i v13 = Hi(v10, v9);     // vmrghw v13,v9,v10
  simde__m128i v11 = LoadV(pm);       // lvx v11, r1-64
  simde__m128i v0 = Hi(v12, v11);     // vmrghw v0,v11,v12
  v12 = Lo(v12, v11);                 // vmrglw v12,v11,v12
  v11 = Lo(v10, v9);                  // vmrglw v11,v9,v10
  v10 = Hi(v13, v0);                  // vmrghw v10,v0,v13
  v0 = Lo(v13, v0);                   // vmrglw v0,v0,v13
  v13 = Hi(v11, v12);                 // vmrghw v13,v12,v11
  v12 = Lo(v11, v12);                 // vmrglw v12,v12,v11
  if (!s.Note(out, 64)) [[unlikely]] return true;
  ::banjo::hot::Card(base, out, 64);
  uint8_t* d = ::banjo::hot::Raw(base, out);
  StoreV(d, v10);
  StoreV(d + 16, v0);
  StoreV(d + 32, v13);
  StoreV(d + 48, v12);
  ctx.r9.s64 = ctx.r3.s64 + 48;
  ctx.r10.s64 = ctx.r3.s64 + 32;
  PutV(ctx.v0, v0);
  PutV(ctx.v9, v9);
  PutV(ctx.v10, v10);
  PutV(ctx.v11, v11);
  PutV(ctx.v12, v12);
  PutV(ctx.v13, v13);
  return true;
}

}  // namespace n_82153688

// sub_8213EAB0 - a vector by a 4x4 matrix: r3 = out (stvx), r4 = the vector (lvx), r5 = M (any alignment). 35
// instructions: M copied to r1-64, the vector loaded, M transposed from its reloads, four vmsum4fp128, the result
// merged and stored. Four calls in sub_82218290. Written back as the original leaves them: r9 (the last doubleword
// copied, M's bytes 56-63 as the ld read them), r10 (r1: the copy's end), v0, v8-v13; r11 and ctr are locals.
namespace n_8213EAB0 {

template <class S>
[[gnu::always_inline]] inline bool Native(PPCContext& __restrict ctx, uint8_t* base, S& s) {
  if (!On(kVecMat)) [[unlikely]] return false;
  const uint32_t sp = ctx.r1.u32, vec = ctx.r4.u32 & ~15u, m = ctx.r5.u32, out = ctx.r3.u32 & ~15u, red = sp - 64u;
  if (sp & 15u) [[unlikely]] return false;
  if (!detail::Straight(red, 64) || !detail::Straight(m, 64) || !detail::Straight(vec, 16) ||
      !detail::Straight(out, 16)) [[unlikely]]
    return false;
  if (!rr6::Apart(m, 64, red, 64) || !rr6::Apart(vec, 16, red, 64)) [[unlikely]] return false;
  s.Hand(kVecMat, 16);
  const uint8_t* pm = ::banjo::hot::Raw(base, m);
  if (!s.Note(red, 64)) [[unlikely]] return true;
  ::banjo::hot::Card(base, red, 64);
  std::memcpy(::banjo::hot::Raw(base, red), pm, 64);
  uint64_t last;
  std::memcpy(&last, pm + 56, 8);
  using namespace rr6;
  simde__m128i v0 = LoadV(::banjo::hot::Raw(base, vec));  // lvx v0, r4
  simde__m128i v11 = LoadV(pm + 32);  // lvx v11, r1-32
  simde__m128i v10 = LoadV(pm);       // lvx v10, r1-64
  simde__m128i v13 = Hi(v11, v10);    // vmrghw v13,v10,v11
  v11 = Lo(v11, v10);                 // vmrglw v11,v10,v11
  simde__m128i v9 = LoadV(pm + 48);   // lvx v9, r1-16
  simde__m128i v8 = LoadV(pm + 16);   // lvx v8, r1-48
  simde__m128i v12 = Hi(v9, v8);      // vmrghw v12,v8,v9
  v10 = Lo(v9, v8);                   // vmrglw v10,v8,v9
  v9 = Hi(v12, v13);                  // vmrghw v9,v13,v12
  v13 = Lo(v12, v13);                 // vmrglw v13,v13,v12
  v12 = Hi(v10, v11);                 // vmrghw v12,v11,v10
  v11 = Lo(v10, v11);                 // vmrglw v11,v11,v10
  ctx.fpscr.enableFlushMode();
  v10 = Dp(v0, v9);
  v13 = Dp(v0, v13);
  v12 = Dp(v0, v12);
  v0 = Dp(v0, v11);
  v12 = Hi(v12, v10);                 // vmrghw v12,v10,v12
  v0 = Hi(v0, v13);                   // vmrghw v0,v13,v0
  v0 = Hi(v0, v12);                   // vmrghw v0,v12,v0
  if (!s.Note(out, 16)) [[unlikely]] return true;
  ::banjo::hot::Card(base, out, 16);
  StoreV(::banjo::hot::Raw(base, out), v0);
  ctx.r9.u64 = __builtin_bswap64(last);
  ctx.r10.s64 = ctx.r1.s64;
  PutV(ctx.v0, v0);
  PutV(ctx.v8, v8);
  PutV(ctx.v9, v9);
  PutV(ctx.v10, v10);
  PutV(ctx.v11, v11);
  PutV(ctx.v12, v12);
  PutV(ctx.v13, v13);
  return true;
}

}  // namespace n_8213EAB0

}  // namespace banjo::hand
