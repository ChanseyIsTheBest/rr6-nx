// rr6-nx (2026-11-04): a probe of the console's GPU through deko3d, for the questions the emulator cannot answer
// (Ryujinx is lenient where the hardware is strict). Each experiment draws into an offscreen image, reads the pixels
// back with the copy engine and judges them on the device; the verdicts go to the screen (the libnx console, no
// swapchain) and to sdmc:/gpuprobe.txt. Built from devkitPro's deko3d examples (SampleFramework, zlib licence).
//
//   1. Strip cuts: a 16-bit index buffer with a 0xFFFF cut between two quads, drawn as one triangle strip under a
//      restart index of 0xFFFF, of 0xFFFFFFFF, and with restart off; the same with 32-bit indices and a 0xFFFFFFFF cut.
//      A honoured cut leaves the gap between the quads black; a cut drawn as vertex 65535 or joined fills it.
//   2. Hardware colour compression: a gradient drawn into a compressed render target, read back four ways: the copy
//      engine straight from it (dkCmdBufCopyImageToBuffer), through a copy-engine image copy into a plain image,
//      through a 2D-engine blit into a plain image, and the same gradient drawn into an uncompressed target (the
//      control). The renderer resolves and dumps with the first two; the emulator has no compression at all.
#include <switch.h>
#include <deko3d.hpp>
#include <cstdarg>
#include <cstdio>
#include <cstring>
#include <cstdint>
#include <cmath>
#include <optional>
#include <vector>
#include <string>

#include "SampleFramework/CMemPool.h"
#include "SampleFramework/CShader.h"

namespace {

constexpr uint32_t W = 64, H = 64;

struct Vertex { float position[3]; float color[3]; };

constexpr std::array VertexAttribState = {
    DkVtxAttribState{0, 0, offsetof(Vertex, position), DkVtxAttribSize_3x32, DkVtxAttribType_Float, 0},
    DkVtxAttribState{0, 0, offsetof(Vertex, color), DkVtxAttribSize_3x32, DkVtxAttribType_Float, 0},
};
constexpr std::array VertexBufferState = {DkVtxBufferState{sizeof(Vertex), 0}};

FILE *g_out = nullptr;
int g_failed = 0, g_passed = 0;

void say(const char *fmt, ...) {
    char line[512];
    va_list va;
    va_start(va, fmt);
    vsnprintf(line, sizeof line, fmt, va);
    va_end(va);
    printf("%s\n", line);
    if (g_out) { fprintf(g_out, "%s\n", line); fflush(g_out); }
    consoleUpdate(nullptr);
}

void verdict(const char *name, bool pass, const char *detail) {
    (pass ? g_passed : g_failed)++;
    say("%s  %s  %s", pass ? "PASS" : "FAIL", name, detail);
}

struct Probe {
    dk::UniqueDevice device;
    dk::UniqueQueue queue;
    std::optional<CMemPool> pool_images, pool_code, pool_data;
    dk::UniqueCmdBuf cmdbuf;
    CShader vsh, fsh;
    CMemPool::Handle readback;  // W*H*4 bytes, CPU-visible
    std::string last_error;

    static void debugCallback(void *, const char *context, DkResult result, const char *message) {
        say("deko3d says (%s, result %d): %s", context ? context : "", int(result), message ? message : "");
    }

    bool init() {
        device = dk::DeviceMaker{}.setCbDebug(debugCallback).create();
        queue = dk::QueueMaker{device}.setFlags(DkQueueFlags_Graphics).create();
        pool_images.emplace(device, DkMemBlockFlags_GpuCached | DkMemBlockFlags_Image, 8 * 1024 * 1024);
        pool_code.emplace(device, DkMemBlockFlags_CpuUncached | DkMemBlockFlags_GpuCached | DkMemBlockFlags_Code, 128 * 1024);
        pool_data.emplace(device, DkMemBlockFlags_CpuUncached | DkMemBlockFlags_GpuCached, 2 * 1024 * 1024);
        cmdbuf = dk::CmdBufMaker{device}.create();
        CMemPool::Handle cmdmem = pool_data->allocate(256 * 1024);
        cmdbuf.addMemory(cmdmem.getMemBlock(), cmdmem.getOffset(), cmdmem.getSize());
        vsh.load(*pool_code, "romfs:/shaders/probe_vsh.dksh");
        fsh.load(*pool_code, "romfs:/shaders/probe_fsh.dksh");
        readback = pool_data->allocate(W * H * 4, 256);
        return true;
    }

    struct Image {
        CMemPool::Handle mem;
        dk::Image image;
    };

    Image makeImage(uint32_t flags, DkImageFormat format = DkImageFormat_RGBA8_Unorm) {
        dk::ImageLayout layout;
        dk::ImageLayoutMaker{device}.setFlags(flags).setFormat(format).setDimensions(W, H).initialize(layout);
        Image out;
        out.mem = pool_images->allocate(layout.getSize(), layout.getAlignment());
        out.image.initialize(layout, out.mem.getMemBlock(), out.mem.getOffset());
        return out;
    }

    void bindState(dk::Image &target) {
        dk::ImageView view{target};
        cmdbuf.bindRenderTargets(&view);
        cmdbuf.setViewports(0, {{0.0f, 0.0f, float(W), float(H), 0.0f, 1.0f}});
        cmdbuf.setScissors(0, {{0, 0, W, H}});
        cmdbuf.clearColor(0, DkColorMask_RGBA, 0.0f, 0.0f, 0.0f, 1.0f);
        dk::RasterizerState rasterizerState;
        rasterizerState.setCullMode(DkFace_None);
        dk::ColorState colorState;
        dk::ColorWriteState colorWriteState;
        cmdbuf.bindShaders(DkStageFlag_GraphicsMask, {vsh, fsh});
        cmdbuf.bindRasterizerState(rasterizerState);
        cmdbuf.bindColorState(colorState);
        cmdbuf.bindColorWriteState(colorWriteState);
        cmdbuf.bindVtxAttribState(VertexAttribState);
        cmdbuf.bindVtxBufferState(VertexBufferState);
    }

    // The target's pixels into 'readback' (the copy engine), the queue idle after.
    void copyOut(dk::Image &source) {
        dk::ImageView view{source};
        DkImageRect rect{0, 0, 0, W, H, 1};
        DkCopyBuf dst{readback.getGpuAddr(), W * 4, H};
        cmdbuf.barrier(DkBarrier_Full, DkInvalidateFlags_Image);
        cmdbuf.copyImageToBuffer(view, rect, dst);
        cmdbuf.barrier(DkBarrier_Full, DkInvalidateFlags_L2Cache);
    }

    void run() {
        queue.submitCommands(cmdbuf.finishList());
        queue.waitIdle();
    }

    const uint8_t *pixels() const { return static_cast<const uint8_t *>(readback.getCpuAddr()); }
    uint32_t px(uint32_t x, uint32_t y) const {
        const uint8_t *p = pixels() + (y * W + x) * 4;
        return p[0] | (p[1] << 8) | (p[2] << 16) | (p[3] << 24);
    }

    // ---- experiment 1: strip cuts -------------------------------------------------------------------------------
    // Two quads, x in [-0.9, -0.3] and [0.3, 0.9], y in [-0.6, 0.6], as one strip with a cut between them. The gap
    // x in [-0.2, 0.2] stays black when the cut is honoured.
    void stripCut(const char *name, bool wide, bool enable, uint32_t restartIndex) {
        const Vertex verts[8] = {
            {{-0.9f, -0.6f, 0}, {1, 1, 1}}, {{-0.9f, 0.6f, 0}, {1, 1, 1}}, {{-0.3f, -0.6f, 0}, {1, 1, 1}}, {{-0.3f, 0.6f, 0}, {1, 1, 1}},
            {{0.3f, -0.6f, 0}, {1, 1, 1}}, {{0.3f, 0.6f, 0}, {1, 1, 1}}, {{0.9f, -0.6f, 0}, {1, 1, 1}}, {{0.9f, 0.6f, 0}, {1, 1, 1}},
        };
        CMemPool::Handle vb = pool_data->allocate(sizeof verts, 16);
        memcpy(vb.getCpuAddr(), verts, sizeof verts);
        CMemPool::Handle ib = pool_data->allocate(9 * 4, 16);
        if (wide) {
            const uint32_t idx[9] = {0, 1, 2, 3, 0xFFFFFFFFu, 4, 5, 6, 7};
            memcpy(ib.getCpuAddr(), idx, sizeof idx);
        } else {
            const uint16_t idx[9] = {0, 1, 2, 3, 0xFFFFu, 4, 5, 6, 7};
            memcpy(ib.getCpuAddr(), idx, sizeof idx);
        }
        Image target = makeImage(DkImageFlags_UsageRender | DkImageFlags_Usage2DEngine);
        bindState(target.image);
        cmdbuf.bindVtxBuffer(0, vb.getGpuAddr(), vb.getSize());
        cmdbuf.bindIdxBuffer(wide ? DkIdxFormat_Uint32 : DkIdxFormat_Uint16, ib.getGpuAddr());
        cmdbuf.setPrimitiveRestart(enable, restartIndex);
        cmdbuf.drawIndexed(DkPrimitive_TriangleStrip, 9, 1, 0, 0, 0);
        copyOut(target.image);
        run();
        // The gap: columns 26..37 (x in [-0.19, 0.16]) at rows 20..43; the quads: column 8 and column 55 at row 32.
        uint32_t gapWhite = 0, gapTotal = 0;
        for (uint32_t y = 20; y < 44; ++y)
            for (uint32_t x = 26; x < 38; ++x, ++gapTotal)
                gapWhite += (px(x, y) & 0xFFFFFF) != 0;
        const bool leftDrawn = (px(8, 32) & 0xFFFFFF) == 0xFFFFFF, rightDrawn = (px(55, 32) & 0xFFFFFF) == 0xFFFFFF;
        char detail[200];
        snprintf(detail, sizeof detail, "quads drawn %d/%d, gap pixels lit %u of %u%s", leftDrawn, rightDrawn, gapWhite, gapTotal,
                 !enable ? " (restart off: the control; lit means the cut was drawn)" : "");
        verdict(name, leftDrawn && rightDrawn && (enable ? gapWhite == 0 : true), detail);
        vb.destroy();
        ib.destroy();
        target.mem.destroy();
    }

    // ---- experiment 2: compression and the copy paths -----------------------------------------------------------
    // A full-screen quad with red = x and green = y, drawn into 'target', read back along 'how'.
    void drawGradient(dk::Image &target) {
        const Vertex verts[4] = {
            {{-1, -1, 0}, {0, 0, 0}}, {{-1, 1, 0}, {0, 1, 0}}, {{1, -1, 0}, {1, 0, 0}}, {{1, 1, 0}, {1, 1, 0}},
        };
        CMemPool::Handle vb = pool_data->allocate(sizeof verts, 16);
        memcpy(vb.getCpuAddr(), verts, sizeof verts);
        bindState(target);
        cmdbuf.bindVtxBuffer(0, vb.getGpuAddr(), vb.getSize());
        cmdbuf.setPrimitiveRestart(false, 0);
        cmdbuf.draw(DkPrimitive_TriangleStrip, 4, 1, 0, 0);
        cmdbuf.barrier(DkBarrier_Full, DkInvalidateFlags_Image);
        run();
        vb.destroy();
    }

    // The read-back pixels against the gradient: the mean error over a grid and the worst pixel.
    void judgeGradient(const char *name) {
        double sum = 0;
        uint32_t worst = 0, n = 0, worstX = 0, worstY = 0;
        for (uint32_t y = 2; y < H; y += 6)
            for (uint32_t x = 2; x < W; x += 6, ++n) {
                const uint8_t *p = pixels() + (y * W + x) * 4;
                // The origin is the upper left for deko3d's default; the gradient's green rises with clip-space y, so
                // row 0 (top) is green 1. Either origin is accepted: the row is judged against both and the better taken.
                const int er = std::abs(int(p[0]) - int(std::lround((x + 0.5) / W * 255.0)));
                const int egA = std::abs(int(p[1]) - int(std::lround((1.0 - (y + 0.5) / H) * 255.0)));
                const int egB = std::abs(int(p[1]) - int(std::lround((y + 0.5) / H * 255.0)));
                const uint32_t e = uint32_t(er + std::min(egA, egB) + std::abs(int(p[2]) - 0));
                sum += e;
                if (e > worst) { worst = e; worstX = x; worstY = y; }
            }
        char detail[200];
        const uint8_t *w = pixels() + (worstY * W + worstX) * 4;
        snprintf(detail, sizeof detail, "mean error %.2f, worst %u at (%u,%u) = %02X %02X %02X %02X", sum / n, worst, worstX, worstY,
                 w[0], w[1], w[2], w[3]);
        verdict(name, worst <= 12, detail);
    }

    void compression() {
        // (a) the copy engine straight from the compressed target
        {
            Image rt = makeImage(DkImageFlags_UsageRender | DkImageFlags_HwCompression | DkImageFlags_Usage2DEngine);
            drawGradient(rt.image);
            copyOut(rt.image);
            run();
            judgeGradient("compressed target, copy engine readback");
            // (b) copy-engine image copy into a plain image, then readback
            Image plain = makeImage(DkImageFlags_Usage2DEngine);
            {
                dk::ImageView sv{rt.image}, dv{plain.image};
                DkImageRect rect{0, 0, 0, W, H, 1};
                cmdbuf.barrier(DkBarrier_Full, DkInvalidateFlags_Image);
                cmdbuf.copyImage(sv, rect, dv, rect);
                cmdbuf.barrier(DkBarrier_Full, DkInvalidateFlags_Image);
            }
            copyOut(plain.image);
            run();
            judgeGradient("compressed target, dkCmdBufCopyImage to a plain image");
            // (c) 2D-engine blit into a plain image, then readback
            Image plain2 = makeImage(DkImageFlags_Usage2DEngine);
            {
                dk::ImageView sv{rt.image}, dv{plain2.image};
                DkImageRect rect{0, 0, 0, W, H, 1};
                cmdbuf.barrier(DkBarrier_Full, DkInvalidateFlags_Image);
                cmdbuf.blitImage(sv, rect, dv, rect, 0, 0);
                cmdbuf.barrier(DkBarrier_Full, DkInvalidateFlags_Image);
            }
            copyOut(plain2.image);
            run();
            judgeGradient("compressed target, dkCmdBufBlitImage (2D engine) to a plain image");
            plain2.mem.destroy();
            plain.mem.destroy();
            rt.mem.destroy();
        }
        // (d) the control: an uncompressed target
        {
            Image rt = makeImage(DkImageFlags_UsageRender | DkImageFlags_Usage2DEngine);
            drawGradient(rt.image);
            copyOut(rt.image);
            run();
            judgeGradient("uncompressed target, copy engine readback (control)");
            rt.mem.destroy();
        }
    }
};

}  // namespace

int main(int, char **) {
    consoleInit(nullptr);
    padConfigureInput(1, HidNpadStyleSet_NpadStandard);
    PadState pad;
    padInitializeDefault(&pad);  // romfs and the socket come from SampleFramework/startup.cpp's userAppInit
    g_out = fopen("sdmc:/gpuprobe.txt", "w");
    say("RR6 GPU probe (deko3d, 2026-11-04). Results also in sdmc:/gpuprobe.txt. Press + to exit.");
    {
        Probe p;
        p.init();
        say("-- strip cuts (one strip, two quads, a cut between them)");
        p.stripCut("16-bit indices, cut 0xFFFF, restart index 0xFFFF", false, true, 0xFFFFu);
        p.stripCut("16-bit indices, cut 0xFFFF, restart index 0xFFFFFFFF", false, true, 0xFFFFFFFFu);
        p.stripCut("16-bit indices, cut 0xFFFF, restart OFF", false, false, 0);
        p.stripCut("32-bit indices, cut 0xFFFFFFFF, restart index 0xFFFFFFFF", true, true, 0xFFFFFFFFu);
        p.stripCut("32-bit indices, cut 0xFFFFFFFF, restart index 0xFFFF", true, true, 0xFFFFu);
        say("-- hardware colour compression and the copy paths (a gradient read back)");
        p.compression();
        say("-- %d passed, %d failed", g_passed, g_failed);
        p.queue.waitIdle();
    }
    if (g_out) fclose(g_out);
    while (appletMainLoop()) {
        padUpdate(&pad);
        if (padGetButtonsDown(&pad) & HidNpadButton_Plus) break;
        consoleUpdate(nullptr);
    }
    consoleExit(nullptr);
    return 0;
}
