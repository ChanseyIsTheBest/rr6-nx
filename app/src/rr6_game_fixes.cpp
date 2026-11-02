// rr6-nx: Ridge Racer 6's game fixes (docs/rr6-notes.md, "Game fixes"). Taken from Ridge Racer 6 Recomp by Sirhalo23
// (src/save_fixes.cpp, src/host_thread_fixes.cpp, src/fp_guard.cpp); BSD 3-Clause, notice in THIRD_PARTY_NOTICES.md.
// Each address was checked against this image: XContentCreate 0x82247E10 and XContentSetThumbnail 0x82247E40 are the import
// thunks' wrappers (`b 0x8232FEB4`, `b 0x8232FEE4`), XGetOverlappedResult 0x82247F80 reads the overlapped at r3.
//
// Save data. The game's save library understands exactly one failure from XContentCreate(OPEN_EXISTING):
// ERROR_FUNCTION_FAILED (0x65B), "no save yet"; anything else means a broken storage device and it never creates a save.
// The SDK completes a missing content open with ERROR_PATH_NOT_FOUND. And the SDK stores the save's thumbnail as
// __thumbnail.png inside the save's folder; the game takes the first file it lists there as its save data, so a
// thumbnail listed first reads as "Game Data is corrupted". rr6_save_thumbnail = true restores the SDK's behaviour.
//
// PC only: the audio worker and the graphics interrupt thread are host threads whose guest FP control word was never
// seeded; the first flush-mode toggle then unmasks every SSE exception (0xC000008F in the audio mixer). The Switch's
// exception enable bits are 0 and it needs neither (as zuma-nx found).

#include <cstdint>
#include <mutex>
#include <unordered_set>

#include <rex/cvar.h>
#include <rex/hook.h>
#include <rex/logging.h>

REXCVAR_DEFINE_BOOL(rr6_save_thumbnail, false, "RR6",
                    "Store the save's thumbnail picture in the save folder, as the SDK does by default. Off: the game can "
                    "mistake the picture for its save data and report the save as corrupted.");

REX_EXTERN(__imp__sub_82247E10);
REX_EXTERN(__imp__sub_82247F80);
REX_EXTERN(__imp__sub_82247E40);

namespace {
constexpr uint32_t kErrorFileNotFound = 2;
constexpr uint32_t kErrorPathNotFound = 3;
constexpr uint32_t kErrorIoIncomplete = 0x3E4;
constexpr uint32_t kErrorFunctionFailed = 0x65B;
std::mutex g_mutex;
std::unordered_set<uint32_t> g_content_opens;  // guest XOVERLAPPED addresses awaiting a result
}  // namespace

// XContentCreate(user, root_name, XCONTENT_DATA*, flags, disposition*, license_mask*, XOVERLAPPED*)
REX_HOOK_RAW(sub_82247E10) {
  if (const uint32_t overlapped = ctx.r9.u32) {
    std::lock_guard<std::mutex> lock(g_mutex);
    g_content_opens.insert(overlapped);
  }
  __imp__sub_82247E10(ctx, base);
}

// XGetOverlappedResult(XOVERLAPPED*, result*, wait)
REX_HOOK_RAW(sub_82247F80) {
  const uint32_t overlapped = ctx.r3.u32;
  __imp__sub_82247F80(ctx, base);
  const uint32_t result = ctx.r3.u32;
  if (result == kErrorIoIncomplete || !overlapped) {
    return;  // still running
  }
  {
    std::lock_guard<std::mutex> lock(g_mutex);
    if (g_content_opens.erase(overlapped) == 0) {
      return;  // not a content open
    }
  }
  if (result == kErrorFileNotFound || result == kErrorPathNotFound) {
    REXLOG_INFO("[save] content open: not found ({}): reporting ERROR_FUNCTION_FAILED ('no save data yet')", result);
    *reinterpret_cast<rex::be<uint32_t>*>(base + overlapped) = kErrorFunctionFailed;  // XOVERLAPPED.InternalLow
    ctx.r3.u64 = kErrorFunctionFailed;
  }
}

// XContentSetThumbnail(user, XCONTENT_DATA*, image*, image_size, XOVERLAPPED*). Only the plain synchronous form is
// answered here (the only form this game uses).
REX_HOOK_RAW(sub_82247E40) {
  if (!REXCVAR_GET(rr6_save_thumbnail) && !ctx.r7.u32) {
    ctx.r3.u64 = 0;  // ERROR_SUCCESS
    return;
  }
  __imp__sub_82247E40(ctx, base);
}

#if !defined(__SWITCH__)
REX_EXTERN(__imp__sub_822AA050);
REX_EXTERN(__imp__sub_8225A590);

// XAudio render-driver callback (registered through XAudioRegisterRenderDriverClient).
REX_HOOK_RAW(sub_822AA050) {
  ctx.fpscr.InitHost();
  __imp__sub_822AA050(ctx, base);
}

// Graphics interrupt callback (registered through VdSetGraphicsInterruptCallback).
REX_HOOK_RAW(sub_8225A590) {
  ctx.fpscr.InitHost();
  __imp__sub_8225A590(ctx, base);
}
#endif

#ifdef _WIN32
// Safety net for the same problem elsewhere: masks the exceptions again and resumes instead of letting the process die.
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>

#include <atomic>

namespace {
std::atomic<unsigned> g_fp_hits{0};

LONG CALLBACK FpGuard(EXCEPTION_POINTERS* info) {
  const DWORD code = info->ExceptionRecord->ExceptionCode;
  const bool is_fp = (code >= 0xC000008Du && code <= 0xC0000093u) || code == 0xC00002B4u || code == 0xC00002B5u;
  if (!is_fp) {
    return EXCEPTION_CONTINUE_SEARCH;
  }
  CONTEXT* c = info->ContextRecord;
  const DWORD kMaskAll = 0x1F80u;
  if ((c->MxCsr & kMaskAll) == kMaskAll) {
    return EXCEPTION_CONTINUE_SEARCH;  // exceptions already masked: not this problem
  }
  const DWORD before = c->MxCsr;
  c->MxCsr = (c->MxCsr | kMaskAll) & ~0x3Fu;
  c->FltSave.MxCsr = c->MxCsr;
  if (g_fp_hits.fetch_add(1) < 16) {
    REXLOG_ERROR("[fp guard] code {:08X} at {} thread {} mxcsr {:08X}", static_cast<unsigned>(code),
                 static_cast<void*>(info->ExceptionRecord->ExceptionAddress), static_cast<unsigned>(GetCurrentThreadId()),
                 static_cast<unsigned>(before));
  }
  return EXCEPTION_CONTINUE_EXECUTION;
}

struct FpGuardInstaller {
  FpGuardInstaller() { AddVectoredExceptionHandler(1, FpGuard); }
} g_fp_guard_installer;
}  // namespace
#endif  // _WIN32
