#!/usr/bin/env python3
"""rr6-nx (2026-11-03): a temporary build that records which generated functions run, so that machine copies are made only
of those (tools/bulk_batch.py --only). Compiling a copy of everything takes more memory than this PC has spare, and a copy
that a run never reaches cannot be verified and is dropped anyway (tools/verified_copies.py).

With --on (RR6_COVERAGE=1 in the environment of the build, tools/post_codegen.py) the pch's DEFINE_REX_FUNC also writes a
function's name to out/rr6_coverage.txt the first time it runs. Without it the block is taken out again: the generated
header outlives a build, and this must never reach a real one. PC build only (clang's form of the macro).

Run such a build with --banjo_cpu_native_bulk=false: a copy that answers a call hides what it calls from the list.

  python tools/pch_coverage.py app/generated/renut_pch.h [--on]
"""
import re
import sys

BEGIN = '// RR6_COVERAGE begin'
END = '// RR6_COVERAGE end'
BLOCK = BEGIN + r''' (tools/pch_coverage.py: a temporary build, never shipped)
#include <atomic>
#include <cstdio>
inline void rr6_coverage_hit(const char* name) {
  static FILE* f = std::fopen("D:/ridge racer 6/rr6-nx/out/rr6_coverage.txt", "w");
  if (f) {
    std::fputs(name, f);
    std::fputc('\n', f);
    std::fflush(f);
  }
}
#undef DEFINE_REX_FUNC
#define DEFINE_REX_FUNC(name)                                                                       \
  extern "C" void __imp__##name(PPCContext& __restrict, uint8_t*);                                  \
  __attribute__((weak, noinline)) extern "C" void name(PPCContext& __restrict ctx, uint8_t* base) { \
    [[clang::musttail]] return __imp__##name(ctx, base);                                            \
  }                                                                                                 \
  static void rr6_body_##name(PPCContext& __restrict ctx, uint8_t* base);                           \
  extern "C" void __imp__##name(PPCContext& __restrict ctx, uint8_t* base) {                        \
    static std::atomic_flag once = ATOMIC_FLAG_INIT;                                                \
    if (!once.test_and_set(std::memory_order_relaxed)) rr6_coverage_hit(#name);                     \
    [[clang::musttail]] return rr6_body_##name(ctx, base);                                          \
  }                                                                                                 \
  static void rr6_body_##name([[maybe_unused]] PPCContext& __restrict ctx, uint8_t* base)
''' + END + '\n'


def main():
    path = sys.argv[1]
    on = '--on' in sys.argv[2:]
    text = open(path, encoding='utf-8', newline='').read()
    clean = re.sub(re.escape(BEGIN) + r'.*?' + re.escape(END) + r'\r?\n', '', text, flags=re.S)
    wanted = clean + BLOCK if on else clean
    if wanted != text:
        open(path, 'w', encoding='utf-8', newline='').write(wanted)
    print(f'pch_coverage: {"on" if on else "off"} in {path}{"" if wanted != text else " (unchanged)"}')


if __name__ == '__main__':
    main()
