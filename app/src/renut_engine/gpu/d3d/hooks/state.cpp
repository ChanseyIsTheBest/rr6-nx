/**
 * @file    gpu/d3d/hooks/state.cpp
 * @brief   N&B's D3D state calls, hooked with the native ports (d3d_native.h).
 *
 * The render and sampler state setters are the ones N&B's state tables name
 * (D3D::InitializeApiState puts them into every device's dispatch table,
 * which the game's inline SetRenderState / SetSamplerState call through).
 * The rest are D3DDevice_Set* and the CDevice internals that write the ring.
 */
#include <cstring>

#include <rex/hook.h>

#include "renut_engine/gpu/banjo_renut_select.h"
#include <rex/types.h>

#include "renut_engine/gpu/d3d/d3d_native.h"
#include "renut_engine/gpu/guest/guest_memory.h"

using namespace renut::gpu;

namespace {

template <u32 State>
void SetRenderStateHook(u32 device, u32 value) {
  native::SetRenderState(native::DeviceAt(device), State, value);
}

template <u32 State>
void SetSamplerStateHook(u32 device, u32 sampler, u32 value) {
  native::SetSamplerState(native::DeviceAt(device), sampler, State, value);
}

template <u32 State>
u32 GetRenderStateHook(u32 device) {
  return native::GetRenderState(native::DeviceAt(device), State);
}

template <u32 State>
u32 GetSamplerStateHook(u32 device, u32 sampler) {
  return native::GetSamplerState(native::DeviceAt(device), sampler, State);
}

// The device's AddRef of a resource it hands out (D3DResource_AddRef,
// resource.cpp).
u32 AddRefResource(u32 resource) {
  return native::AddRefResource(resource);
}

// rr6-nx (2026-11-02): XDK 2.0.2135's setters take the game's own objects and keep a binding on them (hooks/resource.cpp, "XDK
// 2.0.2135's own objects"). Renut's state code sees the object's shadow. What each slot holds as the game knows it is kept
// here: one title device in this game (1 CreateDevice call site).
constexpr u32 kRr6Samplers = 26, kRr6Streams = 16, kRr6Targets = 4;
u32 g_rr6_textures[kRr6Samplers] = {}, g_rr6_streams[kRr6Streams] = {}, g_rr6_targets[kRr6Targets] = {};
u32 g_rr6_depth = 0, g_rr6_indices = 0, g_rr6_declaration = 0;

// Binds the new, unbinds the old.
inline void Rr6Rebind(u32 &slot, u32 value) {
  if (slot == value)
    return;
  native::Rr6Bind(value);
  const u32 old = slot;
  slot = value;
  native::Rr6Unbind(old);
}

void Rr6SetTexture(u32 device, u32 sampler, u32 texture) {
  if (sampler < kRr6Samplers)
    Rr6Rebind(g_rr6_textures[sampler], texture);
  native::SetTexture(native::DeviceAt(device), sampler, native::Rr6TextureShadow(texture));
}
void Rr6SetRenderTarget(u32 device, u32 index, u32 surface) {
  const u32 shadow = native::Rr6SurfaceShadow(surface);
  if (index < kRr6Targets)
    Rr6Rebind(g_rr6_targets[index], surface);
  native::SetRenderTarget(native::DeviceAt(device), index, shadow);
}
void Rr6SetDepthStencil(u32 device, u32 surface) {
  const u32 shadow = native::Rr6SurfaceShadow(surface);
  Rr6Rebind(g_rr6_depth, surface);
  native::SetDepthStencilSurface(native::DeviceAt(device), shadow);
}
u32 Rr6GetRenderTarget(u32 device, u32 index) {
  const native::Device d = native::DeviceAt(device);
  const u32 shadow = d && index < 4 ? d.W(native::off::RenderTargets + index * 4) : 0;
  const u32 surface = shadow ? native::Rr6SurfaceGuest(shadow) : 0;
  if (surface)
    native::Rr6AddRefAny(surface);
  return surface;
}
u32 Rr6GetDepthStencil(u32 device) {
  const native::Device d = native::DeviceAt(device);
  const u32 shadow = d ? d.W(native::off::DepthStencil) : 0;
  const u32 surface = shadow ? native::Rr6SurfaceGuest(shadow) : 0;
  if (surface)
    native::Rr6AddRefAny(surface);
  return surface;
}
void Rr6SetStreamSource(u32 device, u32 stream, u32 vertex_buffer, u32 offset, u32 stride) {
  if (stream < kRr6Streams)
    Rr6Rebind(g_rr6_streams[stream], vertex_buffer);
  native::SetStreamSource(native::DeviceAt(device), stream, vertex_buffer, offset, stride);
}
void Rr6SetIndices(u32 device, u32 index_buffer) {
  Rr6Rebind(g_rr6_indices, index_buffer);
  native::SetIndices(native::DeviceAt(device), index_buffer);
}
void Rr6SetVertexDeclaration(u32 device, u32 declaration) {
  Rr6Rebind(g_rr6_declaration, declaration);
  native::SetVertexDeclaration(native::DeviceAt(device), declaration);
}

// XDK 2135's render state 57 (between ColorWriteEnable3 and TessellationMode), which N&B's order does not have: its setter
// stores the value in four device words where Renut's device has its own fields, so it is kept here (zuma-nx's).
u32 g_rr6_render_state57 = 0;
void Rr6SetRenderState57(u32 /*device*/, u32 value) {
  g_rr6_render_state57 = value;
}
u32 Rr6GetRenderState57(u32 /*device*/) {
  return g_rr6_render_state57;
}

// D3DSurface *GetRenderTarget(D3DDevice*, DWORD Index) [0x82636ED0]
u32 D3DDevice_GetRenderTarget_hook(u32 device, u32 index) {
  const native::Device d = native::DeviceAt(device);
  const u32 surface = d && index < 4 ? d.W(native::off::RenderTargets + index * 4) : 0;
  if (surface)
    AddRefResource(surface);
  return surface;
}

// D3DSurface *GetDepthStencilSurface(D3DDevice*) [0x82636F10]
u32 D3DDevice_GetDepthStencilSurface_hook(u32 device) {
  const native::Device d = native::DeviceAt(device);
  const u32 surface = d ? d.W(native::off::DepthStencil) : 0;
  if (surface)
    AddRefResource(surface);
  return surface;
}

// D3DVertexBuffer *GetStreamSource(D3DDevice*, UINT StreamNumber,
//     UINT *pOffsetInBytes, UINT *pStride) [0x82636E40]: the offset is the
// stream's fetch constant address less the buffer's.
u32 D3DDevice_GetStreamSource_hook(u32 device, u32 stream, mapped_u32 offset, mapped_u32 stride) {
  const native::Device d = native::DeviceAt(device);
  if (!d || stream >= 16)
    return 0;
  const u32 buffer = d.W(native::off::StreamSources + stream * 4);
  u32 bytes = 0;
  if (buffer) {
    const u32 fetch = d.W(native::off::TextureFetch + (95 - stream) * 8);
    bytes = fetch - native::GpuAddress(GuestPtr<const be_u32>(buffer)[6]);
    AddRefResource(buffer);
  }
  if (offset)
    *offset = bytes;
  if (stride)
    *stride = u32(d.B(native::off::StreamStrides + stream)) << 2;
  return buffer;
}

// void D3DDevice_GetViewport(D3DDevice*, D3DVIEWPORT9*) [0x82244B18]
void D3DDevice_GetViewport_hook(u32 device, mapped_u32 viewport) {
  const native::Device d = native::DeviceAt(device);
  if (!d || !viewport)
    return;
  for (u32 i = 0; i < 4; ++i)  // fctidz, the low word
    viewport[i] = u32(native::TruncateToI64(d.F(0x3160 + i * 4)));  // katamari-nx: 0x3170->0x3160
  viewport[4] = d.W(0x3170);  // katamari-nx: 0x3180->0x3170
  viewport[5] = d.W(0x3174);  // katamari-nx: 0x3184->0x3174
}

// void D3DDevice_SetClipPlane(D3DDevice*, DWORD Index, const float *pPlane) [0x826370E8]
void D3DDevice_SetClipPlane_hook(u32 device, u32 index, mapped_u32 plane) {
  native::Device d = native::DeviceAt(device);
  if (!d || !plane || index >= 6)
    return;
  for (u32 i = 0; i < 4; ++i)
    d.SetW(0x2820 + index * 16 + i * 4, plane[i]);
  d.Dirty(4, u64(1) << (54 - index));
}

// void D3DDevice_SetVertexFetchConstant(D3DDevice*, UINT VertexFetchRegister,
//     D3DVertexBuffer*, UINT Offset) [0x82637138]: a vertex fetch slot of the
// 3 in a fetch constant, made a vertex fetch constant first.
void D3DDevice_SetVertexFetchConstant_hook(u32 device, u32 reg, u32 vertex_buffer, u32 offset) {
  native::Device d = native::DeviceAt(device);
  const auto *vb = vertex_buffer ? GuestPtr<const be_u32>(vertex_buffer) : nullptr;
  if (!d || !vb || reg > 0x5F)
    return;
  const u32 slot = (0x5F - reg) / 3;
  const u32 part = (0x5F - reg) - slot * 3;
  const u32 constant = native::off::TextureFetch + slot * 24;
  const u32 type = d.W(constant) & 3;
  if (type == 0 || type == 2)
    std::memset(d.bytes + constant, 0, 24);
  d.TouchRange(constant, 24);  // banjo-nx (2026-10-26, banjo_renut_tags)
  d.SetW(constant, native::Insert(d.W(constant), 1, 0, 2));
  d.Dirty(3, u64(1) << (31 - slot));
  d.SetW(constant + part * 8, native::GpuAddress(u32(vb[6]) + offset));
  d.SetW(constant + part * 8 + 4, native::Insert(u32(vb[7]) - offset, 1, 28, 2));
}

// The boolean and integer shader constants (D3DDevice_Set{Vertex,Pixel}
// ShaderConstant{B,I}): bits from 0x2780 (vertex) / 0x2790 (pixel), a word
// of x, y, z bytes each from 0x27A0 / 0x27E0.
void SetShaderConstantsB(u32 device, u32 base, u32 start, mapped_u32 data, u32 count) {
  native::Device d = native::DeviceAt(device);
  if (!d || !data)
    return;
  for (u32 i = 0; i < count; ++i, ++start) {
    const u32 word = base + (start >> 5) * 4;
    const u32 bit = 1u << (start & 31);
    d.SetW(word, (d.W(word) & ~bit) | ((u32(data[i]) & 1) << (start & 31)));
  }
  d.Dirty(4, u64(1) << 56);
}

void SetShaderConstantsI(u32 device, u32 base, u32 start, mapped_u32 data, u32 count) {
  native::Device d = native::DeviceAt(device);
  if (!d || !data)
    return;
  for (u32 i = 0; i < count; ++i) {
    const u32 x = u32(data[i * 4]) & 0xFF, y = u32(data[i * 4 + 1]) & 0xFF;
    const u32 z = u32(data[i * 4 + 2]) & 0xFF;
    d.SetW(base + (start + i) * 4, (z << 16) | (y << 8) | x);
  }
  d.Dirty(4, u64(1) << 56);
}

// void D3DDevice_SetVertexShaderConstantB(D3DDevice*, UINT StartRegister,
//     const BOOL*, UINT BoolCount) [0x821F0B40], and the others alike.
void D3DDevice_SetVertexShaderConstantB_hook(u32 device, u32 start, mapped_u32 data, u32 count) {
  SetShaderConstantsB(device, 0x2780, start, data, count);
}
void D3DDevice_SetPixelShaderConstantB_hook(u32 device, u32 start, mapped_u32 data, u32 count) {
  SetShaderConstantsB(device, 0x2790, start, data, count);
}
void D3DDevice_SetVertexShaderConstantI_hook(u32 device, u32 start, mapped_u32 data, u32 count) {
  SetShaderConstantsI(device, 0x27A0, start, data, count);
}
void D3DDevice_SetPixelShaderConstantI_hook(u32 device, u32 start, mapped_u32 data, u32 count) {
  SetShaderConstantsI(device, 0x27E0, start, data, count);
}

// void D3DDevice_EndIndexedVertices(D3DDevice*) [0x8263ED90]: the inline end
// of BeginIndexedVertices, back to the ring pointer it saved.
void D3DDevice_EndIndexedVertices_hook(u32 device) {
  native::Device d = native::DeviceAt(device);
  if (d)
    d.SetW(native::off::Ring, d.W(0x3474));  // katamari-nx: 0x3484->0x3474
}

// void D3DDevice_SetTexture(D3DDevice*, DWORD Sampler, D3DBaseTexture*,
//     UINT64 PendingMask3) [0x821FE558]; the mask is the sampler's fetch
// constant bit, which the port derives from Sampler.
void D3DDevice_SetTexture_hook(u32 device, u32 sampler, u32 texture) {
  native::SetTexture(native::DeviceAt(device), sampler, texture);
}

// void D3DDevice_SetStreamSource(D3DDevice*, UINT StreamNumber, D3DVertexBuffer*,
//     UINT OffsetInBytes, UINT Stride, UINT64 PendingMask3) [0x821F9438]
void D3DDevice_SetStreamSource_hook(u32 device, u32 stream, u32 vertex_buffer, u32 offset,
                                    u32 stride) {
  native::SetStreamSource(native::DeviceAt(device), stream, vertex_buffer, offset, stride);
}

// void D3DDevice_SetIndices(D3DDevice*, D3DIndexBuffer*) [0x821DE438]
void D3DDevice_SetIndices_hook(u32 device, u32 index_buffer) {
  native::SetIndices(native::DeviceAt(device), index_buffer);
}

// void D3DDevice_SetVertexDeclaration(D3DDevice*, D3DVertexDeclaration*) [0x821D5060]
void D3DDevice_SetVertexDeclaration_hook(u32 device, u32 declaration) {
  native::SetVertexDeclaration(native::DeviceAt(device), declaration);
}

// void D3DDevice_SetViewport(D3DDevice*, const D3DVIEWPORT9*) [0x821F2090]
void D3DDevice_SetViewport_hook(u32 device, u32 viewport) {
  native::SetViewport(native::DeviceAt(device), viewport);
}

// void D3D::SetViewport(D3DDevice*, float X, float Y, float Width, float Height,
//     float MinZ, float MaxZ) [0x821F2110]
void D3D_SetViewport_hook(u32 device, float x, float y, float width, float height, float min_z,
                          float max_z) {
  native::SetViewport(native::DeviceAt(device), x, y, width, height, min_z, max_z);
}

// void D3DDevice_SetScissorRect(D3DDevice*, const RECT*) [0x821F2368]
void D3DDevice_SetScissorRect_hook(u32 device, mapped_u32 rect) {
  if (!rect)
    return;
  native::SetScissorRect(native::DeviceAt(device), i32(u32(rect[0])), i32(u32(rect[1])),
                         i32(u32(rect[2])), i32(u32(rect[3])));
}

// void D3D::SetSurfaceClip(CDevice*, int, int, int, int) [0x821F2460]: the
// window scissor and per-tile clip packets, nothing else.
void D3D_SetSurfaceClip_hook(u32 /*device*/, u32, u32, u32, u32) {}

// void D3DDevice_SetRenderTarget(D3DDevice*, DWORD Index, D3DSurface*) [0x82248BD0]
void D3DDevice_SetRenderTarget_hook(u32 device, u32 index, u32 surface) {
  native::SetRenderTarget(native::DeviceAt(device), index, surface);
}

// void D3DDevice_SetDepthStencilSurface(D3DDevice*, D3DSurface*) [0x82248FB0]
void D3DDevice_SetDepthStencilSurface_hook(u32 device, u32 surface) {
  native::SetDepthStencilSurface(native::DeviceAt(device), surface);
}

// void D3D::SetSurfaceInfo(CDevice*, D3DSurface*) [0x82248F20]
void D3D_SetSurfaceInfo_hook(u32 device, u32 surface) {
  native::SetSurfaceInfo(native::DeviceAt(device), surface);
}

// void D3DDevice_SetPredication(D3DDevice*, DWORD PredicationMask) [0x821F9A48]
void D3DDevice_SetPredication_hook(u32 device, u32 mask) {
  native::SetPredication(native::DeviceAt(device), mask);
}

// void D3DDevice_SetCommandBufferPredication(D3DDevice*, DWORD TilePredication,
//     DWORD RunPredication) [0x826411C0]
void D3DDevice_SetCommandBufferPredication_hook(u32 device, u32 tile_predication,
                                                u32 run_predication) {
  native::SetCommandBufferPredication(native::DeviceAt(device), tile_predication,
                                      run_predication);
}

// void D3DDevice_SetShaderGPRAllocation(D3DDevice*, DWORD Flags,
//     DWORD VertexShaderCount, DWORD PixelShaderCount) [0x821EFD38]
void D3DDevice_SetShaderGPRAllocation_hook(u32 device, u32 flags, u32 vertex_count,
                                           u32 pixel_count) {
  native::SetShaderGPRAllocation(native::DeviceAt(device), flags, vertex_count, pixel_count);
}

// void D3D::CleanupGprAllocationSetup(CDevice*) [0x82637208]
void D3D_CleanupGprAllocationSetup_hook(u32 device) {
  native::CleanupGprAllocationSetup(native::DeviceAt(device));
}

// void D3DDevice_SetScreenExtentQueryMode(D3DDevice*, D3DSCREENEXTENTQUERYMODE)
// [0x826414C0]
void D3DDevice_SetScreenExtentQueryMode_hook(u32 device, u32 mode) {
  native::SetScreenExtentQueryMode(native::DeviceAt(device), mode);
}

// void D3DDevice_UnsetAll(D3DDevice*) [0x82634C10]
void D3DDevice_UnsetAll_hook(u32 device) {
  native::UnsetAll(native::DeviceAt(device));
}

// void D3D::ResetAllState(CDevice*, BOOL) [0x82255C98]
void D3D_ResetAllState_hook(u32 device, u32 /*skip_packets*/) {
  native::ResetAllState(native::DeviceAt(device));
}

// void D3D::InvalidateConstants(D3DDevice*) [0x82634B90]
void D3D_InvalidateConstants_hook(u32 device) {
  native::InvalidateConstants(native::DeviceAt(device));
}

// void D3DDevice_BlockUntilIdle(D3DDevice*) [0x82640010] (IDA: the second
// D3D::InvalidateConstants): waits for the device's current fence (N&B calls
// it before releasing a device).
void D3DDevice_BlockUntilIdle_hook(u32 device) {
  native::InvalidateConstantsAndWait(native::DeviceAt(device));
}

} // namespace

// Render states, by their index in N&B's table (off_82E506F0).
BANJO_RENUT_HOOK(sub_82255838, SetRenderStateHook<10>);  // D3DDevice_SetRenderState_ZEnable  // rr6-nx: the game's state table; Katamari 824DC2F8
BANJO_RENUT_HOOK(sub_822558C0, SetRenderStateHook<11>);  // D3DDevice_SetRenderState_ZFunc  // rr6-nx: the game's state table; Katamari 824DC368
BANJO_RENUT_HOOK(sub_82255888, SetRenderStateHook<12>);  // D3DDevice_SetRenderState_ZWriteEnable  // rr6-nx: the game's state table; Katamari 824DC338
BANJO_RENUT_HOOK(sub_82255180, SetRenderStateHook<13>);  // D3DDevice_SetRenderState_FillMode  // rr6-nx: the game's state table; Katamari 824DBBD8
BANJO_RENUT_HOOK(sub_82255148, SetRenderStateHook<14>);  // D3DDevice_SetRenderState_CullMode  // rr6-nx: the game's state table; Katamari 824DBBA8
BANJO_RENUT_HOOK(sub_82255200, SetRenderStateHook<15>);  // D3DDevice_SetRenderState_AlphaBlendEnable  // rr6-nx: the game's state table; Katamari 824DBC40
BANJO_RENUT_HOOK(sub_822555D0, SetRenderStateHook<16>);  // D3DDevice_SetRenderState_SeparateAlphaBlendEnable  // rr6-nx: the game's state table; Katamari 824DBFD0
BANJO_RENUT_HOOK(sub_82255718, SetRenderStateHook<17>);  // D3DDevice_SetRenderState_BlendFactor  // rr6-nx: the game's state table; Katamari 824DC100
BANJO_RENUT_HOOK(sub_82255338, SetRenderStateHook<18>);  // D3DDevice_SetRenderState_SrcBlend  // rr6-nx: the game's state table; Katamari 824DBD60
BANJO_RENUT_HOOK(sub_822553D0, SetRenderStateHook<19>);  // D3DDevice_SetRenderState_DestBlend  // rr6-nx: the game's state table; Katamari 824DBDF0
BANJO_RENUT_HOOK(sub_822552A0, SetRenderStateHook<20>);  // D3DDevice_SetRenderState_BlendOp  // rr6-nx: the game's state table; Katamari 824DBCD0
BANJO_RENUT_HOOK(sub_822554E0, SetRenderStateHook<21>);  // D3DDevice_SetRenderState_SrcBlendAlpha  // rr6-nx: the game's state table; Katamari 824DBEF0
BANJO_RENUT_HOOK(sub_82255558, SetRenderStateHook<22>);  // D3DDevice_SetRenderState_DestBlendAlpha  // rr6-nx: the game's state table; Katamari 824DBF60
BANJO_RENUT_HOOK(sub_82255468, SetRenderStateHook<23>);  // D3DDevice_SetRenderState_BlendOpAlpha  // rr6-nx: the game's state table; Katamari 824DBE80
BANJO_RENUT_HOOK(sub_822551B8, SetRenderStateHook<24>);  // D3DDevice_SetRenderState_AlphaTestEnable  // rr6-nx: the game's state table; Katamari 824DBC08
BANJO_RENUT_HOOK(sub_82255670, SetRenderStateHook<25>);  // D3DDevice_SetRenderState_AlphaRef  // rr6-nx: the game's state table; Katamari 824DC068
BANJO_RENUT_HOOK(sub_822556E0, SetRenderStateHook<26>);  // D3DDevice_SetRenderState_AlphaFunc  // rr6-nx: the game's state table; Katamari 824DC0D0
BANJO_RENUT_HOOK(sub_82255908, SetRenderStateHook<27>);  // D3DDevice_SetRenderState_StencilEnable  // rr6-nx: the game's state table; Katamari 824DC3A0
BANJO_RENUT_HOOK(sub_82255958, SetRenderStateHook<28>);  // D3DDevice_SetRenderState_TwoSidedStencilMode  // rr6-nx: the game's state table; Katamari 824DC3E0
BANJO_RENUT_HOOK(sub_822559D8, SetRenderStateHook<29>);  // D3DDevice_SetRenderState_StencilFail  // rr6-nx: the game's state table; Katamari 824DC448
BANJO_RENUT_HOOK(sub_82255A20, SetRenderStateHook<30>);  // D3DDevice_SetRenderState_StencilZFail  // rr6-nx: the game's state table; Katamari 824DC480
BANJO_RENUT_HOOK(sub_82255A68, SetRenderStateHook<31>);  // D3DDevice_SetRenderState_StencilPass  // rr6-nx: the game's state table; Katamari 824DC4B8
BANJO_RENUT_HOOK(sub_822559A0, SetRenderStateHook<32>);  // D3DDevice_SetRenderState_StencilFunc  // rr6-nx: the game's state table; Katamari 824DC418
BANJO_RENUT_HOOK(sub_82255BA0, SetRenderStateHook<33>);  // D3DDevice_SetRenderState_StencilRef  // rr6-nx: the game's state table; Katamari 824DC5B8
BANJO_RENUT_HOOK(sub_82255BC8, SetRenderStateHook<34>);  // D3DDevice_SetRenderState_StencilMask  // rr6-nx: the game's state table; Katamari 824DC5D8
BANJO_RENUT_HOOK(sub_82255BF0, SetRenderStateHook<35>);  // D3DDevice_SetRenderState_StencilWriteMask  // rr6-nx: the game's state table; Katamari 824DC5F8
BANJO_RENUT_HOOK(sub_82255AD8, SetRenderStateHook<36>);  // D3DDevice_SetRenderState_CCWStencilFail  // rr6-nx: the game's state table; Katamari 824DC518
BANJO_RENUT_HOOK(sub_82255B20, SetRenderStateHook<37>);  // D3DDevice_SetRenderState_CCWStencilZFail  // rr6-nx: the game's state table; Katamari 824DC550
BANJO_RENUT_HOOK(sub_82255B68, SetRenderStateHook<38>);  // D3DDevice_SetRenderState_CCWStencilPass  // rr6-nx: the game's state table; Katamari 824DC588
BANJO_RENUT_HOOK(sub_82255AA0, SetRenderStateHook<39>);  // D3DDevice_SetRenderState_CCWStencilFunc  // rr6-nx: the game's state table; Katamari 824DC4E8
BANJO_RENUT_HOOK(sub_82255C18, SetRenderStateHook<40>);  // D3DDevice_SetRenderState_CCWStencilRef  // rr6-nx: the game's state table; Katamari 824DC618
BANJO_RENUT_HOOK(sub_82255C40, SetRenderStateHook<41>);  // D3DDevice_SetRenderState_CCWStencilMask  // rr6-nx: the game's state table; Katamari 824DC638
BANJO_RENUT_HOOK(sub_82255C68, SetRenderStateHook<42>);  // D3DDevice_SetRenderState_CCWStencilWriteMask  // rr6-nx: the game's state table; Katamari 824DC658
BANJO_RENUT_HOOK(sub_82255C90, SetRenderStateHook<43>);  // D3DDevice_SetRenderState_ClipPlaneEnable  // rr6-nx: the game's state table; Katamari 824DC678
BANJO_RENUT_HOOK(sub_82255FD8, SetRenderStateHook<44>);  // D3DDevice_SetRenderState_PointSize  // rr6-nx: the game's state table; Katamari 824DC9A0
BANJO_RENUT_HOOK(sub_82256030, SetRenderStateHook<45>);  // D3DDevice_SetRenderState_PointSizeMin  // rr6-nx: the game's state table; Katamari 824DCA00
BANJO_RENUT_HOOK(sub_82255FC8, SetRenderStateHook<46>);  // D3DDevice_SetRenderState_PointSpriteEnable  // rr6-nx: the game's state table; Katamari 824DC990
BANJO_RENUT_HOOK(sub_82256080, SetRenderStateHook<47>);  // D3DDevice_SetRenderState_PointSizeMax  // rr6-nx: the game's state table; Katamari 824DCA58
BANJO_RENUT_HOOK(sub_82255E40, SetRenderStateHook<48>);  // D3DDevice_SetRenderState_MultiSampleAntiAlias  // rr6-nx: the game's state table; Katamari 824DC840
BANJO_RENUT_HOOK(sub_82255E78, SetRenderStateHook<49>);  // D3DDevice_SetRenderState_MultiSampleMask  // rr6-nx: the game's state table; Katamari 824DC870
BANJO_RENUT_HOOK(sub_82257C68, SetRenderStateHook<50>);  // D3DDevice_SetRenderState_ScissorTestEnable  // rr6-nx: the game's state table; Katamari 824DE720
BANJO_RENUT_HOOK(sub_82255CD8, SetRenderStateHook<51>);  // D3DDevice_SetRenderState_SlopeScaleDepthBias  // rr6-nx: the game's state table; Katamari 824DC6D0
BANJO_RENUT_HOOK(sub_82255D98, SetRenderStateHook<52>);  // D3DDevice_SetRenderState_DepthBias  // rr6-nx: the game's state table; Katamari 824DC798
BANJO_RENUT_HOOK(sub_82255EA8, SetRenderStateHook<53>);  // D3DDevice_SetRenderState_ColorWriteEnable  // rr6-nx: the game's state table; Katamari 824DC890
BANJO_RENUT_HOOK(sub_82255EF0, SetRenderStateHook<54>);  // D3DDevice_SetRenderState_ColorWriteEnable1  // rr6-nx: the game's state table; Katamari 824DC8D0
BANJO_RENUT_HOOK(sub_82255F38, SetRenderStateHook<55>);  // D3DDevice_SetRenderState_ColorWriteEnable2  // rr6-nx: the game's state table; Katamari 824DC910
BANJO_RENUT_HOOK(sub_82255F80, SetRenderStateHook<56>);  // D3DDevice_SetRenderState_ColorWriteEnable3  // rr6-nx: the game's state table; Katamari 824DC950
BANJO_RENUT_HOOK(sub_82256820, SetRenderStateHook<57>);  // D3DDevice_SetRenderState_TessellationMode  // rr6-nx: the game's state table; Katamari 824DD190
BANJO_RENUT_HOOK(sub_822567C0, SetRenderStateHook<58>);  // D3DDevice_SetRenderState_MinTessellationLevel  // rr6-nx: the game's state table; Katamari 824DD120
BANJO_RENUT_HOOK(sub_822567F0, SetRenderStateHook<59>);  // D3DDevice_SetRenderState_MaxTessellationLevel  // rr6-nx: the game's state table; Katamari 824DD158
BANJO_RENUT_HOOK(sub_822560D0, SetRenderStateHook<60>);  // D3DDevice_SetRenderState_Wrap0  // rr6-nx: the game's state table; Katamari 824DCAB0
BANJO_RENUT_HOOK(sub_82256100, SetRenderStateHook<61>);  // D3DDevice_SetRenderState_Wrap1  // rr6-nx: the game's state table; Katamari 824DCAD0
BANJO_RENUT_HOOK(sub_82256130, SetRenderStateHook<62>);  // D3DDevice_SetRenderState_Wrap2  // rr6-nx: the game's state table; Katamari 824DCAF8
BANJO_RENUT_HOOK(sub_82256160, SetRenderStateHook<63>);  // D3DDevice_SetRenderState_Wrap3  // rr6-nx: the game's state table; Katamari 824DCB20
BANJO_RENUT_HOOK(sub_82256190, SetRenderStateHook<64>);  // D3DDevice_SetRenderState_Wrap4  // rr6-nx: the game's state table; Katamari 824DCB48
BANJO_RENUT_HOOK(sub_822561C0, SetRenderStateHook<65>);  // D3DDevice_SetRenderState_Wrap5  // rr6-nx: the game's state table; Katamari 824DCB70
BANJO_RENUT_HOOK(sub_822561F0, SetRenderStateHook<66>);  // D3DDevice_SetRenderState_Wrap6  // rr6-nx: the game's state table; Katamari 824DCB98
BANJO_RENUT_HOOK(sub_82256220, SetRenderStateHook<67>);  // D3DDevice_SetRenderState_Wrap7  // rr6-nx: the game's state table; Katamari 824DCBC0
BANJO_RENUT_HOOK(sub_82256248, SetRenderStateHook<68>);  // D3DDevice_SetRenderState_Wrap8  // rr6-nx: the game's state table; Katamari 824DCBE0
BANJO_RENUT_HOOK(sub_82256278, SetRenderStateHook<69>);  // D3DDevice_SetRenderState_Wrap9  // rr6-nx: the game's state table; Katamari 824DCC00
BANJO_RENUT_HOOK(sub_822562A8, SetRenderStateHook<70>);  // D3DDevice_SetRenderState_Wrap10  // rr6-nx: the game's state table; Katamari 824DCC28
BANJO_RENUT_HOOK(sub_822562D8, SetRenderStateHook<71>);  // D3DDevice_SetRenderState_Wrap11  // rr6-nx: the game's state table; Katamari 824DCC50
BANJO_RENUT_HOOK(sub_82256308, SetRenderStateHook<72>);  // D3DDevice_SetRenderState_Wrap12  // rr6-nx: the game's state table; Katamari 824DCC78
BANJO_RENUT_HOOK(sub_82256338, SetRenderStateHook<73>);  // D3DDevice_SetRenderState_Wrap13  // rr6-nx: the game's state table; Katamari 824DCCA0
BANJO_RENUT_HOOK(sub_82256368, SetRenderStateHook<74>);  // D3DDevice_SetRenderState_Wrap14  // rr6-nx: the game's state table; Katamari 824DCCC8
BANJO_RENUT_HOOK(sub_82256398, SetRenderStateHook<75>);  // D3DDevice_SetRenderState_Wrap15  // rr6-nx: the game's state table; Katamari 824DCCF0
BANJO_RENUT_HOOK(sub_82256480, SetRenderStateHook<76>);  // D3DDevice_SetRenderState_ViewportEnable  // rr6-nx: the game's state table; Katamari 824DCE10
BANJO_RENUT_HOOK(sub_822564E0, SetRenderStateHook<77>);  // D3DDevice_SetRenderState_HighPrecisionBlendEnable  // rr6-nx: the game's state table; Katamari 824DCE60
BANJO_RENUT_HOOK(sub_82256598, SetRenderStateHook<78>);  // D3DDevice_SetRenderState_HighPrecisionBlendEnable1  // rr6-nx: the game's state table; Katamari 824DCF10
BANJO_RENUT_HOOK(sub_82256650, SetRenderStateHook<79>);  // D3DDevice_SetRenderState_HighPrecisionBlendEnable2  // rr6-nx: the game's state table; Katamari 824DCFC0
BANJO_RENUT_HOOK(sub_82256708, SetRenderStateHook<80>);  // D3DDevice_SetRenderState_HighPrecisionBlendEnable3  // rr6-nx: the game's state table; Katamari 824DD070
BANJO_RENUT_HOOK(sub_82256850, SetRenderStateHook<81>);  // D3DDevice_SetRenderState_HalfPixelOffset  // rr6-nx: the game's state table; Katamari 824DD1C8
BANJO_RENUT_HOOK(sub_82256888, SetRenderStateHook<82>);  // D3DDevice_SetRenderState_PrimitiveResetEnable  // rr6-nx: the game's state table; Katamari 824DD200
BANJO_RENUT_HOOK(sub_822568C0, SetRenderStateHook<83>);  // D3DDevice_SetRenderState_PrimitiveResetIndex  // rr6-nx: the game's state table; Katamari 824DD230
BANJO_RENUT_HOOK(sub_822568E8, SetRenderStateHook<84>);  // D3DDevice_SetRenderState_AlphaToMaskEnable  // rr6-nx: the game's state table; Katamari 824DD258
BANJO_RENUT_HOOK(sub_82256920, SetRenderStateHook<85>);  // D3DDevice_SetRenderState_AlphaToMaskOffsets  // rr6-nx: the game's state table; Katamari 824DD288
BANJO_RENUT_HOOK(sub_82256960, SetRenderStateHook<86>);  // D3DDevice_SetRenderState_GuardBand_X  // rr6-nx: the game's state table; Katamari 824DD2C0
BANJO_RENUT_HOOK(sub_82256990, SetRenderStateHook<87>);  // D3DDevice_SetRenderState_GuardBand_Y  // rr6-nx: the game's state table; Katamari 824DD2F0
BANJO_RENUT_HOOK(sub_822569C0, SetRenderStateHook<88>);  // D3DDevice_SetRenderState_DiscardBand_X  // rr6-nx: the game's state table; Katamari 824DD320
BANJO_RENUT_HOOK(sub_822569F0, SetRenderStateHook<89>);  // D3DDevice_SetRenderState_DiscardBand_Y  // rr6-nx: the game's state table; Katamari 824DD348
BANJO_RENUT_HOOK(sub_82256A20, SetRenderStateHook<90>);  // D3DDevice_SetRenderState_HiStencilEnable  // rr6-nx: the game's state table; Katamari 824DD410
BANJO_RENUT_HOOK(sub_82256A58, SetRenderStateHook<91>);  // D3DDevice_SetRenderState_HiStencilWriteEnable  // rr6-nx: the game's state table; Katamari 824DD440
BANJO_RENUT_HOOK(sub_82256A90, SetRenderStateHook<92>);  // D3DDevice_SetRenderState_HiStencilFunc  // rr6-nx: the game's state table; Katamari 824DD470
BANJO_RENUT_HOOK(sub_82256AC8, SetRenderStateHook<93>);  // D3DDevice_SetRenderState_HiStencilRef  // rr6-nx: the game's state table; Katamari 824DD4A0
BANJO_RENUT_HOOK(sub_82256AF0, SetRenderStateHook<94>);  // D3DDevice_SetRenderState_PresentInterval  // rr6-nx: the game's state table; Katamari 824DD4C0
BANJO_RENUT_HOOK(sub_82256B00, SetRenderStateHook<95>);  // D3DDevice_SetRenderState_PresentImmediateThreshold  // rr6-nx: the game's state table; Katamari 824DD4D0
BANJO_RENUT_UNHOOKED_HOOK(unlinked_824DD378, SetRenderStateHook<96>);  // D3DDevice_SetRenderState_HiZEnable  // rr6-nx: not hooked in this XDK; Katamari 824DD378
BANJO_RENUT_UNHOOKED_HOOK(unlinked_824DD3A8, SetRenderStateHook<97>);  // D3DDevice_SetRenderState_HiZWriteEnable  // rr6-nx: not hooked in this XDK; Katamari 824DD3A8
BANJO_RENUT_UNHOOKED_HOOK(unlinked_824DC220, SetRenderStateHook<98>);  // D3DDevice_SetRenderState_LastPixel  // rr6-nx: not hooked in this XDK; Katamari 824DC220
BANJO_RENUT_UNHOOKED_HOOK(unlinked_824DC258, SetRenderStateHook<99>);  // D3DDevice_SetRenderState_LineWidth  // rr6-nx: not hooked in this XDK; Katamari 824DC258
BANJO_RENUT_UNHOOKED_HOOK(unlinked_824DC2C8, SetRenderStateHook<100>);  // D3DDevice_SetRenderState_Buffer2Frames  // rr6-nx: not hooked in this XDK; Katamari 824DC2C8

// Sampler states, by their index in N&B's table (off_82E50BD0).
BANJO_RENUT_HOOK(sub_82257110, SetSamplerStateHook<0>);  // D3DDevice_SetSamplerState_AddressU  // rr6-nx: the game's state table; Katamari 824DDC30
BANJO_RENUT_HOOK(sub_82257160, SetSamplerStateHook<1>);  // D3DDevice_SetSamplerState_AddressV  // rr6-nx: the game's state table; Katamari 824DDC80
BANJO_RENUT_HOOK(sub_822571B0, SetSamplerStateHook<2>);  // D3DDevice_SetSamplerState_AddressW  // rr6-nx: the game's state table; Katamari 824DDCD0
BANJO_RENUT_HOOK(sub_822570A0, SetSamplerStateHook<3>);  // D3DDevice_SetSamplerState_BorderColor  // rr6-nx: the game's state table; Katamari 824DDBC0
BANJO_RENUT_HOOK(sub_82256C30, SetSamplerStateHook<4>);  // D3DDevice_SetSamplerState_MagFilter  // rr6-nx: the game's state table; Katamari 824DD680
BANJO_RENUT_HOOK(sub_82256B20, SetSamplerStateHook<5>);  // D3DDevice_SetSamplerState_MinFilter  // rr6-nx: the game's state table; Katamari 824DD4F0
BANJO_RENUT_HOOK(sub_82256D38, SetSamplerStateHook<6>);  // D3DDevice_SetSamplerState_MipFilter  // rr6-nx: the game's state table; Katamari 824DD810
BANJO_RENUT_HOOK(sub_82256F00, SetSamplerStateHook<7>);  // D3DDevice_SetSamplerState_MipMapLodBias  // rr6-nx: the game's state table; Katamari 824DDA20
BANJO_RENUT_HOOK(sub_82256FA0, SetSamplerStateHook<8>);  // D3DDevice_SetSamplerState_MaxMipLevel  // rr6-nx: the game's state table; Katamari 824DDAC0
BANJO_RENUT_HOOK(sub_82256DE0, SetSamplerStateHook<9>);  // D3DDevice_SetSamplerState_MaxAnisotropy  // rr6-nx: the game's state table; Katamari 824DD900
BANJO_RENUT_HOOK(sub_82256CF0, SetSamplerStateHook<10>);  // D3DDevice_SetSamplerState_MagFilterZ  // rr6-nx: the game's state table; Katamari 824DD778
BANJO_RENUT_HOOK(sub_82256BE0, SetSamplerStateHook<11>);  // D3DDevice_SetSamplerState_MinFilterZ  // rr6-nx: the game's state table; Katamari 824DD5E8
BANJO_RENUT_HOOK(sub_82256D90, SetSamplerStateHook<12>);  // D3DDevice_SetSamplerState_SeparateZFilterEnable  // rr6-nx: the game's state table; Katamari 824DD868
BANJO_RENUT_HOOK(sub_82257020, SetSamplerStateHook<13>);  // D3DDevice_SetSamplerState_MinMipLevel  // rr6-nx: the game's state table; Katamari 824DDB40
BANJO_RENUT_HOOK(sub_82257200, SetSamplerStateHook<14>);  // D3DDevice_SetSamplerState_TrilinearThreshold  // rr6-nx: the game's state table; Katamari 824DDD20
BANJO_RENUT_HOOK(sub_82256E58, SetSamplerStateHook<15>);  // D3DDevice_SetSamplerState_AnisotropyBias  // rr6-nx: the game's state table; Katamari 824DD978
BANJO_RENUT_HOOK(sub_82257258, SetSamplerStateHook<16>);  // D3DDevice_SetSamplerState_HGradientExpBias  // rr6-nx: the game's state table; Katamari 824DDD78
BANJO_RENUT_HOOK(sub_822572B0, SetSamplerStateHook<17>);  // D3DDevice_SetSamplerState_VGradientExpBias  // rr6-nx: the game's state table; Katamari 824DDDD0
BANJO_RENUT_HOOK(sub_82257308, SetSamplerStateHook<18>);  // D3DDevice_SetSamplerState_WhiteBorderColorW  // rr6-nx: the game's state table; Katamari 824DDE28
BANJO_RENUT_HOOK(sub_82257360, SetSamplerStateHook<19>);  // D3DDevice_SetSamplerState_PointBorderEnable  // rr6-nx: the game's state table; Katamari 824DDE80

BANJO_RENUT_HOOK(sub_822530A8, Rr6SetTexture);  // D3DDevice_SetTexture  // rr6-nx: Zuma pair of sub_8212A900; 51 sites; the game's texture, on its shadow; Katamari 824D2640
BANJO_RENUT_UNHOOKED_HOOK(unlinked_824A3D40, D3DDevice_SetTexture_hook);  // D3DDevice_SetTexture_Inline  // rr6-nx: not hooked in this XDK; Katamari 824A3D40
BANJO_RENUT_HOOK(sub_822576F8, Rr6SetStreamSource);  // D3DDevice_SetStreamSource  // rr6-nx: Zuma pair; 11 sites; keeps a reference, as this XDK does; Katamari 824DDFE0
BANJO_RENUT_HOOK(sub_82257798, Rr6SetIndices);  // D3DDevice_SetIndices  // rr6-nx: stored at +12532, the old released; 7 sites; Katamari 824DE188
BANJO_RENUT_HOOK(sub_8224F018, Rr6SetVertexDeclaration);  // D3DDevice_SetVertexDeclaration  // rr6-nx: Zuma pair; 47 sites; keeps a reference; Katamari 824D4B48
BANJO_RENUT_HOOK(sub_82257488, D3DDevice_SetViewport_hook);  // D3DDevice_SetViewport  // rr6-nx: writes the 6 words at +12808 and the viewport floats; 3 sites; Katamari 824DE730
BANJO_RENUT_UNHOOKED_HOOK(unlinked_824DE4B8, D3D_SetViewport_hook);  // D3D_SetViewport  // rr6-nx: not hooked in this XDK; Katamari 824DE4B8
BANJO_RENUT_UNHOOKED_HOOK(unlinked_824DDEE0, D3DDevice_SetScissorRect_hook);  // D3DDevice_SetScissorRect  // rr6-nx: not hooked in this XDK; Katamari 824DDEE0
BANJO_RENUT_UNHOOKED_HOOK(unlinked_824DB8C8, D3D_SetSurfaceClip_hook);  // D3D_SetSurfaceClip  // rr6-nx: not hooked in this XDK; Katamari 824DB8C8
BANJO_RENUT_HOOK(sub_82257C78, Rr6SetRenderTarget);  // D3DDevice_SetRenderTarget  // rr6-nx: (dev, index, surface); 7 sites; the bind count in Common, on the surface's shadow; Katamari 824DE868
BANJO_RENUT_HOOK(sub_82257FE0, Rr6SetDepthStencil);  // D3DDevice_SetDepthStencilSurface  // rr6-nx: (dev, surface); 11 sites; Katamari 824DEBD0
BANJO_RENUT_UNHOOKED_HOOK(unlinked_824DE7D0, D3D_SetSurfaceInfo_hook);  // D3D_SetSurfaceInfo  // rr6-nx: not hooked in this XDK; Katamari 824DE7D0
BANJO_RENUT_UNHOOKED_HOOK(unlinked_824EFA58, D3DDevice_SetPredication_hook);  // D3DDevice_SetPredication  // rr6-nx: not hooked in this XDK; Katamari 824EFA58
BANJO_RENUT_UNHOOKED_HOOK_SHARED(unlinked_826411C0, D3DDevice_SetCommandBufferPredication_hook);  // D3DDevice_SetCommandBufferPredication  // rr6-nx: not hooked in this XDK; Katamari 826411C0
BANJO_RENUT_HOOK(sub_8224EDA0, D3DDevice_SetShaderGPRAllocation_hook);  // D3DDevice_SetShaderGPRAllocation  // rr6-nx: Feeding Frenzy pair of sub_820B6258, register 0x0D00 (imm 3328); 3 sites; Katamari 824D4CD8
BANJO_RENUT_UNHOOKED_HOOK(unlinked_824D3FE0, D3D_CleanupGprAllocationSetup_hook);  // D3D_CleanupGprAllocationSetup  // rr6-nx: not hooked in this XDK; Katamari 824D3FE0
BANJO_RENUT_UNHOOKED_HOOK(unlinked_824E67C8, D3DDevice_SetScreenExtentQueryMode_hook);  // D3DDevice_SetScreenExtentQueryMode  // rr6-nx: not hooked in this XDK; Katamari 824E67C8
BANJO_RENUT_UNHOOKED_HOOK(unlinked_824D0488, D3DDevice_UnsetAll_hook);  // D3DDevice_UnsetAll  // rr6-nx: not hooked in this XDK; Katamari 824D0488
BANJO_RENUT_UNHOOKED_HOOK(unlinked_824DE3C0, D3D_ResetAllState_hook);  // D3D_ResetAllState  // rr6-nx: not hooked in this XDK; Katamari 824DE3C0
BANJO_RENUT_UNHOOKED_HOOK_SHARED(unlinked_82634B90, D3D_InvalidateConstants_hook);  // D3D_InvalidateConstants  // rr6-nx: not hooked in this XDK; Katamari 82634B90
BANJO_RENUT_UNHOOKED_HOOK(unlinked_824E0518, D3DDevice_BlockUntilIdle_hook);  // D3DDevice_BlockUntilIdle  // rr6-nx: not hooked in this XDK; Katamari 824E0518
// Through a thunk (j_D3DDevice_SetRenderTarget 0x82636EC8).
BANJO_RENUT_UNHOOKED_HOOK(unlinked_82636EC8, D3DDevice_SetRenderTarget_hook);  // D3DDevice_SetRenderTarget_Thunk  // rr6-nx: not hooked in this XDK; Katamari 82636EC8
BANJO_RENUT_HOOK(sub_82257818, Rr6GetRenderTarget);  // D3DDevice_GetRenderTarget  // rr6-nx: 18 instructions, AddRef; the game's surface back from its shadow; Katamari 82636ED0
BANJO_RENUT_HOOK(sub_82257860, Rr6GetDepthStencil);  // D3DDevice_GetDepthStencilSurface  // rr6-nx: +12552, AddRef; Katamari 82636F10
BANJO_RENUT_UNHOOKED_HOOK(unlinked_82636E40, D3DDevice_GetStreamSource_hook);  // D3DDevice_GetStreamSource  // rr6-nx: not hooked in this XDK; Katamari 82636E40
BANJO_RENUT_HOOK(sub_822576D0, D3DDevice_GetViewport_hook);  // D3DDevice_GetViewport  // rr6-nx: copies 6 words from +12808; 6 sites; Katamari 82244B18
BANJO_RENUT_HOOK(sub_822579C0, D3DDevice_SetClipPlane_hook);  // D3DDevice_SetClipPlane  // rr6-nx: four floats at register 1480; 1 site; Katamari 826370E8
BANJO_RENUT_UNHOOKED_HOOK(unlinked_82637138, D3DDevice_SetVertexFetchConstant_hook);  // D3DDevice_SetVertexFetchConstant  // rr6-nx: not hooked in this XDK; Katamari 82637138
BANJO_RENUT_UNHOOKED_HOOK(unlinked_824D4470, D3DDevice_SetVertexShaderConstantB_hook);  // D3DDevice_SetVertexShaderConstantB  // rr6-nx: not hooked in this XDK; Katamari 824D4470
BANJO_RENUT_UNHOOKED_HOOK(unlinked_824D44D0, D3DDevice_SetPixelShaderConstantB_hook);  // D3DDevice_SetPixelShaderConstantB  // rr6-nx: not hooked in this XDK; Katamari 824D44D0
BANJO_RENUT_UNHOOKED_HOOK(unlinked_826374B0, D3DDevice_SetVertexShaderConstantI_hook);  // D3DDevice_SetVertexShaderConstantI  // rr6-nx: not hooked in this XDK; Katamari 826374B0
BANJO_RENUT_UNHOOKED_HOOK(unlinked_82637500, D3DDevice_SetPixelShaderConstantI_hook);  // D3DDevice_SetPixelShaderConstantI  // rr6-nx: not hooked in this XDK; Katamari 82637500
BANJO_RENUT_UNHOOKED_HOOK(unlinked_8263ED90, D3DDevice_EndIndexedVertices_hook);  // D3DDevice_EndIndexedVertices  // rr6-nx: not hooked in this XDK; Katamari 8263ED90

// Render state getters, by their index in N&B's table (off_82E506F0, field 0).
BANJO_RENUT_HOOK(sub_82255880, GetRenderStateHook<10>);  // D3DDevice_GetRenderState_ZEnable  // rr6-nx: the game's state table; Katamari 824DC330
BANJO_RENUT_HOOK(sub_822558F8, GetRenderStateHook<11>);  // D3DDevice_GetRenderState_ZFunc  // rr6-nx: the game's state table; Katamari 824DC390
BANJO_RENUT_HOOK(sub_822558B0, GetRenderStateHook<12>);  // D3DDevice_GetRenderState_ZWriteEnable  // rr6-nx: the game's state table; Katamari 824DC358
BANJO_RENUT_HOOK(sub_822551A8, GetRenderStateHook<13>);  // D3DDevice_GetRenderState_FillMode  // rr6-nx: the game's state table; Katamari 824DBBF8
BANJO_RENUT_HOOK(sub_82255170, GetRenderStateHook<14>);  // D3DDevice_GetRenderState_CullMode  // rr6-nx: the game's state table; Katamari 824DBBC8
BANJO_RENUT_HOOK(sub_82255290, GetRenderStateHook<15>);  // D3DDevice_GetRenderState_AlphaBlendEnable  // rr6-nx: the game's state table; Katamari 824DBCC0
BANJO_RENUT_HOOK(sub_82255660, GetRenderStateHook<16>);  // D3DDevice_GetRenderState_SeparateAlphaBlendEnable  // rr6-nx: the game's state table; Katamari 824DC058
BANJO_RENUT_HOOK(sub_822557B8, GetRenderStateHook<17>);  // D3DDevice_GetRenderState_BlendFactor  // rr6-nx: the game's state table; Katamari 824DC1A0
BANJO_RENUT_HOOK(sub_822553C0, GetRenderStateHook<18>);  // D3DDevice_GetRenderState_SrcBlend  // rr6-nx: the game's state table; Katamari 824DBDE0
BANJO_RENUT_HOOK(sub_82255458, GetRenderStateHook<19>);  // D3DDevice_GetRenderState_DestBlend  // rr6-nx: the game's state table; Katamari 824DBE70
BANJO_RENUT_HOOK(sub_82255328, GetRenderStateHook<20>);  // D3DDevice_GetRenderState_BlendOp  // rr6-nx: the game's state table; Katamari 824DBD50
BANJO_RENUT_HOOK(sub_82255548, GetRenderStateHook<21>);  // D3DDevice_GetRenderState_SrcBlendAlpha  // rr6-nx: the game's state table; Katamari 824DBF50
BANJO_RENUT_HOOK(sub_822555C0, GetRenderStateHook<22>);  // D3DDevice_GetRenderState_DestBlendAlpha  // rr6-nx: the game's state table; Katamari 824DBFC0
BANJO_RENUT_HOOK(sub_822554D0, GetRenderStateHook<23>);  // D3DDevice_GetRenderState_BlendOpAlpha  // rr6-nx: the game's state table; Katamari 824DBEE0
BANJO_RENUT_HOOK(sub_822551F0, GetRenderStateHook<24>);  // D3DDevice_GetRenderState_AlphaTestEnable  // rr6-nx: the game's state table; Katamari 824DBC30
BANJO_RENUT_HOOK(sub_822556B0, GetRenderStateHook<25>);  // D3DDevice_GetRenderState_AlphaRef  // rr6-nx: the game's state table; Katamari 824DC0A0
BANJO_RENUT_HOOK(sub_82255708, GetRenderStateHook<26>);  // D3DDevice_GetRenderState_AlphaFunc  // rr6-nx: the game's state table; Katamari 824DC0F0
BANJO_RENUT_HOOK(sub_82255950, GetRenderStateHook<27>);  // D3DDevice_GetRenderState_StencilEnable  // rr6-nx: the game's state table; Katamari 824DC3D8
BANJO_RENUT_HOOK(sub_82255990, GetRenderStateHook<28>);  // D3DDevice_GetRenderState_TwoSidedStencilMode  // rr6-nx: the game's state table; Katamari 824DC408
BANJO_RENUT_HOOK(sub_82255A10, GetRenderStateHook<29>);  // D3DDevice_GetRenderState_StencilFail  // rr6-nx: the game's state table; Katamari 824DC470
BANJO_RENUT_HOOK(sub_82255A58, GetRenderStateHook<30>);  // D3DDevice_GetRenderState_StencilZFail  // rr6-nx: the game's state table; Katamari 824DC4A8
BANJO_RENUT_HOOK(sub_82255A90, GetRenderStateHook<31>);  // D3DDevice_GetRenderState_StencilPass  // rr6-nx: the game's state table; Katamari 824DC4D8
BANJO_RENUT_HOOK(sub_822559C8, GetRenderStateHook<32>);  // D3DDevice_GetRenderState_StencilFunc  // rr6-nx: the game's state table; Katamari 824DC438
BANJO_RENUT_HOOK(sub_82255BC0, GetRenderStateHook<33>);  // D3DDevice_GetRenderState_StencilRef  // rr6-nx: the game's state table; Katamari 824DC5D0
BANJO_RENUT_HOOK(sub_82255BE8, GetRenderStateHook<34>);  // D3DDevice_GetRenderState_StencilMask  // rr6-nx: the game's state table; Katamari 824DC5F0
BANJO_RENUT_HOOK(sub_82255C10, GetRenderStateHook<35>);  // D3DDevice_GetRenderState_StencilWriteMask  // rr6-nx: the game's state table; Katamari 824DC610
BANJO_RENUT_HOOK(sub_82255B10, GetRenderStateHook<36>);  // D3DDevice_GetRenderState_CCWStencilFail  // rr6-nx: the game's state table; Katamari 824DC540
BANJO_RENUT_HOOK(sub_82255B58, GetRenderStateHook<37>);  // D3DDevice_GetRenderState_CCWStencilZFail  // rr6-nx: the game's state table; Katamari 824DC578
BANJO_RENUT_HOOK(sub_82255B90, GetRenderStateHook<38>);  // D3DDevice_GetRenderState_CCWStencilPass  // rr6-nx: the game's state table; Katamari 824DC5A8
BANJO_RENUT_HOOK(sub_82255AC8, GetRenderStateHook<39>);  // D3DDevice_GetRenderState_CCWStencilFunc  // rr6-nx: the game's state table; Katamari 824DC508
BANJO_RENUT_HOOK(sub_82255C38, GetRenderStateHook<40>);  // D3DDevice_GetRenderState_CCWStencilRef  // rr6-nx: the game's state table; Katamari 824DC630
BANJO_RENUT_HOOK(sub_82255C60, GetRenderStateHook<41>);  // D3DDevice_GetRenderState_CCWStencilMask  // rr6-nx: the game's state table; Katamari 824DC650
BANJO_RENUT_HOOK(sub_82255C88, GetRenderStateHook<42>);  // D3DDevice_GetRenderState_CCWStencilWriteMask  // rr6-nx: the game's state table; Katamari 824DC670
BANJO_RENUT_HOOK(sub_82255CC0, GetRenderStateHook<43>);  // D3DDevice_GetRenderState_ClipPlaneEnable  // rr6-nx: the game's state table; Katamari 824DC6B8
BANJO_RENUT_HOOK(sub_82256020, GetRenderStateHook<44>);  // D3DDevice_GetRenderState_PointSize  // rr6-nx: the game's state table; Katamari 824DC9F0
BANJO_RENUT_HOOK(sub_82256070, GetRenderStateHook<45>);  // D3DDevice_GetRenderState_PointSizeMin  // rr6-nx: the game's state table; Katamari 824DCA48
BANJO_RENUT_HOOK(sub_82255FD0, GetRenderStateHook<46>);  // D3DDevice_GetRenderState_PointSpriteEnable  // rr6-nx: the game's state table; Katamari 824DC998
BANJO_RENUT_HOOK(sub_822560C0, GetRenderStateHook<47>);  // D3DDevice_GetRenderState_PointSizeMax  // rr6-nx: the game's state table; Katamari 824DCAA0
BANJO_RENUT_HOOK(sub_82255E68, GetRenderStateHook<48>);  // D3DDevice_GetRenderState_MultiSampleAntiAlias  // rr6-nx: the game's state table; Katamari 824DC860
BANJO_RENUT_HOOK(sub_82255EA0, GetRenderStateHook<49>);  // D3DDevice_GetRenderState_MultiSampleMask  // rr6-nx: the game's state table; Katamari 824DC888
BANJO_RENUT_HOOK(sub_82255CD0, GetRenderStateHook<50>);  // D3DDevice_GetRenderState_ScissorTestEnable  // rr6-nx: the game's state table; Katamari 824DC6C8
BANJO_RENUT_HOOK(sub_82255D78, GetRenderStateHook<51>);  // D3DDevice_GetRenderState_SlopeScaleDepthBias  // rr6-nx: the game's state table; Katamari 824DC778
BANJO_RENUT_HOOK(sub_82255E30, GetRenderStateHook<52>);  // D3DDevice_GetRenderState_DepthBias  // rr6-nx: the game's state table; Katamari 824DC830
BANJO_RENUT_HOOK(sub_82255EE8, GetRenderStateHook<53>);  // D3DDevice_GetRenderState_ColorWriteEnable  // rr6-nx: the game's state table; Katamari 824DC8C8
BANJO_RENUT_HOOK(sub_82255F30, GetRenderStateHook<54>);  // D3DDevice_GetRenderState_ColorWriteEnable1  // rr6-nx: the game's state table; Katamari 824DC908
BANJO_RENUT_HOOK(sub_82255F78, GetRenderStateHook<55>);  // D3DDevice_GetRenderState_ColorWriteEnable2  // rr6-nx: the game's state table; Katamari 824DC948
BANJO_RENUT_HOOK(sub_82255FC0, GetRenderStateHook<56>);  // D3DDevice_GetRenderState_ColorWriteEnable3  // rr6-nx: the game's state table; Katamari 824DC988
BANJO_RENUT_HOOK(sub_82256840, GetRenderStateHook<57>);  // D3DDevice_GetRenderState_TessellationMode  // rr6-nx: the game's state table; Katamari 824DD1B8
BANJO_RENUT_HOOK(sub_822567E0, GetRenderStateHook<58>);  // D3DDevice_GetRenderState_MinTessellationLevel  // rr6-nx: the game's state table; Katamari 824DD148
BANJO_RENUT_HOOK(sub_82256810, GetRenderStateHook<59>);  // D3DDevice_GetRenderState_MaxTessellationLevel  // rr6-nx: the game's state table; Katamari 824DD180
BANJO_RENUT_HOOK(sub_822563C0, GetRenderStateHook<60>);  // D3DDevice_GetRenderState_Wrap0  // rr6-nx: the game's state table; Katamari 824DCD10
BANJO_RENUT_HOOK(sub_822563D0, GetRenderStateHook<61>);  // D3DDevice_GetRenderState_Wrap1  // rr6-nx: the game's state table; Katamari 824DCD20
BANJO_RENUT_HOOK(sub_822563E0, GetRenderStateHook<62>);  // D3DDevice_GetRenderState_Wrap2  // rr6-nx: the game's state table; Katamari 824DCD30
BANJO_RENUT_HOOK(sub_822563F0, GetRenderStateHook<63>);  // D3DDevice_GetRenderState_Wrap3  // rr6-nx: the game's state table; Katamari 824DCD40
BANJO_RENUT_HOOK(sub_82256400, GetRenderStateHook<64>);  // D3DDevice_GetRenderState_Wrap4  // rr6-nx: the game's state table; Katamari 824DCD50
BANJO_RENUT_HOOK(sub_82256410, GetRenderStateHook<65>);  // D3DDevice_GetRenderState_Wrap5  // rr6-nx: the game's state table; Katamari 824DCD60
BANJO_RENUT_HOOK(sub_82256420, GetRenderStateHook<66>);  // D3DDevice_GetRenderState_Wrap6  // rr6-nx: the game's state table; Katamari 824DCD70
BANJO_RENUT_HOOK(sub_82256430, GetRenderStateHook<67>);  // D3DDevice_GetRenderState_Wrap7  // rr6-nx: the game's state table; Katamari 824DCD80
BANJO_RENUT_HOOK(sub_82256440, GetRenderStateHook<68>);  // D3DDevice_GetRenderState_Wrap8  // rr6-nx: the game's state table; Katamari 824DCD90
BANJO_RENUT_HOOK(sub_82256450, GetRenderStateHook<69>);  // D3DDevice_GetRenderState_Wrap9  // rr6-nx: the game's state table; Katamari 824DCDA0
BANJO_RENUT_UNHOOKED_HOOK(unlinked_824DCDB0, GetRenderStateHook<70>);  // D3DDevice_GetRenderState_Wrap10  // rr6-nx: not hooked in this XDK; Katamari 824DCDB0
BANJO_RENUT_UNHOOKED_HOOK(unlinked_824DCDC0, GetRenderStateHook<71>);  // D3DDevice_GetRenderState_Wrap11  // rr6-nx: not hooked in this XDK; Katamari 824DCDC0
BANJO_RENUT_UNHOOKED_HOOK(unlinked_824DCDD0, GetRenderStateHook<72>);  // D3DDevice_GetRenderState_Wrap12  // rr6-nx: not hooked in this XDK; Katamari 824DCDD0
BANJO_RENUT_UNHOOKED_HOOK(unlinked_824DCDE0, GetRenderStateHook<73>);  // D3DDevice_GetRenderState_Wrap13  // rr6-nx: not hooked in this XDK; Katamari 824DCDE0
BANJO_RENUT_UNHOOKED_HOOK(unlinked_824DCDF0, GetRenderStateHook<74>);  // D3DDevice_GetRenderState_Wrap14  // rr6-nx: not hooked in this XDK; Katamari 824DCDF0
BANJO_RENUT_UNHOOKED_HOOK(unlinked_824DCE00, GetRenderStateHook<75>);  // D3DDevice_GetRenderState_Wrap15  // rr6-nx: not hooked in this XDK; Katamari 824DCE00
BANJO_RENUT_HOOK(sub_822564D0, GetRenderStateHook<76>);  // D3DDevice_GetRenderState_ViewportEnable  // rr6-nx: the game's state table; Katamari 824DCE50
BANJO_RENUT_HOOK(sub_82256590, GetRenderStateHook<77>);  // D3DDevice_GetRenderState_HighPrecisionBlendEnable  // rr6-nx: the game's state table; Katamari 824DCF08
BANJO_RENUT_HOOK(sub_82256648, GetRenderStateHook<78>);  // D3DDevice_GetRenderState_HighPrecisionBlendEnable1  // rr6-nx: the game's state table; Katamari 824DCFB8
BANJO_RENUT_HOOK(sub_82256700, GetRenderStateHook<79>);  // D3DDevice_GetRenderState_HighPrecisionBlendEnable2  // rr6-nx: the game's state table; Katamari 824DD068
BANJO_RENUT_HOOK(sub_822567B8, GetRenderStateHook<80>);  // D3DDevice_GetRenderState_HighPrecisionBlendEnable3  // rr6-nx: the game's state table; Katamari 824DD118
BANJO_RENUT_HOOK(sub_82256878, GetRenderStateHook<81>);  // D3DDevice_GetRenderState_HalfPixelOffset  // rr6-nx: the game's state table; Katamari 824DD1F0
BANJO_RENUT_HOOK(sub_822568B0, GetRenderStateHook<82>);  // D3DDevice_GetRenderState_PrimitiveResetEnable  // rr6-nx: the game's state table; Katamari 824DD220
BANJO_RENUT_HOOK(sub_822568E0, GetRenderStateHook<83>);  // D3DDevice_GetRenderState_PrimitiveResetIndex  // rr6-nx: the game's state table; Katamari 824DD250
BANJO_RENUT_HOOK(sub_82256910, GetRenderStateHook<84>);  // D3DDevice_GetRenderState_AlphaToMaskEnable  // rr6-nx: the game's state table; Katamari 824DD278
BANJO_RENUT_HOOK(sub_82256948, GetRenderStateHook<85>);  // D3DDevice_GetRenderState_AlphaToMaskOffsets  // rr6-nx: the game's state table; Katamari 824DD2A8
BANJO_RENUT_HOOK(sub_82256988, GetRenderStateHook<86>);  // D3DDevice_GetRenderState_GuardBand_X  // rr6-nx: the game's state table; Katamari 824DD2E8
BANJO_RENUT_HOOK(sub_822569B8, GetRenderStateHook<87>);  // D3DDevice_GetRenderState_GuardBand_Y  // rr6-nx: the game's state table; Katamari 824DD318
BANJO_RENUT_HOOK(sub_822569E8, GetRenderStateHook<88>);  // D3DDevice_GetRenderState_DiscardBand_X  // rr6-nx: the game's state table; Katamari 824DD340
BANJO_RENUT_HOOK(sub_82256A18, GetRenderStateHook<89>);  // D3DDevice_GetRenderState_DiscardBand_Y  // rr6-nx: the game's state table; Katamari 824DD370
BANJO_RENUT_HOOK(sub_82256A48, GetRenderStateHook<90>);  // D3DDevice_GetRenderState_HiStencilEnable  // rr6-nx: the game's state table; Katamari 824DD430
BANJO_RENUT_HOOK(sub_82256A80, GetRenderStateHook<91>);  // D3DDevice_GetRenderState_HiStencilWriteEnable  // rr6-nx: the game's state table; Katamari 824DD460
BANJO_RENUT_HOOK(sub_82256AB8, GetRenderStateHook<92>);  // D3DDevice_GetRenderState_HiStencilFunc  // rr6-nx: the game's state table; Katamari 824DD490
BANJO_RENUT_HOOK(sub_82256AE8, GetRenderStateHook<93>);  // D3DDevice_GetRenderState_HiStencilRef  // rr6-nx: the game's state table; Katamari 824DD4B8
BANJO_RENUT_HOOK(sub_82256AF8, GetRenderStateHook<94>);  // D3DDevice_GetRenderState_PresentInterval  // rr6-nx: the game's state table; Katamari 824DD4C8
BANJO_RENUT_HOOK(sub_82256B10, GetRenderStateHook<95>);  // D3DDevice_GetRenderState_PresentImmediateThreshold  // rr6-nx: the game's state table; Katamari 824DD4E0
BANJO_RENUT_UNHOOKED_HOOK(unlinked_824DD398, GetRenderStateHook<96>);  // D3DDevice_GetRenderState_HiZEnable  // rr6-nx: not hooked in this XDK; Katamari 824DD398
BANJO_RENUT_UNHOOKED_HOOK(unlinked_824DD400, GetRenderStateHook<97>);  // D3DDevice_GetRenderState_HiZWriteEnable  // rr6-nx: not hooked in this XDK; Katamari 824DD400
BANJO_RENUT_UNHOOKED_HOOK(unlinked_824DC248, GetRenderStateHook<98>);  // D3DDevice_GetRenderState_LastPixel  // rr6-nx: not hooked in this XDK; Katamari 824DC248
BANJO_RENUT_UNHOOKED_HOOK(unlinked_824DC298, GetRenderStateHook<99>);  // D3DDevice_GetRenderState_LineWidth  // rr6-nx: not hooked in this XDK; Katamari 824DC298
BANJO_RENUT_UNHOOKED_HOOK(unlinked_824DC2E8, GetRenderStateHook<100>);  // D3DDevice_GetRenderState_Buffer2Frames  // rr6-nx: not hooked in this XDK; Katamari 824DC2E8

// Sampler state getters (off_82E50BD0, field 0).
BANJO_RENUT_HOOK(sub_82257148, GetSamplerStateHook<0>);  // D3DDevice_GetSamplerState_AddressU  // rr6-nx: the game's state table; Katamari 824DDC68
BANJO_RENUT_HOOK(sub_82257198, GetSamplerStateHook<1>);  // D3DDevice_GetSamplerState_AddressV  // rr6-nx: the game's state table; Katamari 824DDCB8
BANJO_RENUT_HOOK(sub_822571E8, GetSamplerStateHook<2>);  // D3DDevice_GetSamplerState_AddressW  // rr6-nx: the game's state table; Katamari 824DDD08
BANJO_RENUT_HOOK(sub_822570F0, GetSamplerStateHook<3>);  // D3DDevice_GetSamplerState_BorderColor  // rr6-nx: the game's state table; Katamari 824DDC10
BANJO_RENUT_HOOK(sub_82256CB8, GetSamplerStateHook<4>);  // D3DDevice_GetSamplerState_MagFilter  // rr6-nx: the game's state table; Katamari 824DD740
BANJO_RENUT_HOOK(sub_82256BA8, GetSamplerStateHook<5>);  // D3DDevice_GetSamplerState_MinFilter  // rr6-nx: the game's state table; Katamari 824DD5B0
BANJO_RENUT_HOOK(sub_82256D78, GetSamplerStateHook<6>);  // D3DDevice_GetSamplerState_MipFilter  // rr6-nx: the game's state table; Katamari 824DD850
BANJO_RENUT_HOOK(sub_82256F60, GetSamplerStateHook<7>);  // D3DDevice_GetSamplerState_MipMapLodBias  // rr6-nx: the game's state table; Katamari 824DDA80
BANJO_RENUT_HOOK(sub_82257010, GetSamplerStateHook<8>);  // D3DDevice_GetSamplerState_MaxMipLevel  // rr6-nx: the game's state table; Katamari 824DDB30
BANJO_RENUT_HOOK(sub_82256E48, GetSamplerStateHook<9>);  // D3DDevice_GetSamplerState_MaxAnisotropy  // rr6-nx: the game's state table; Katamari 824DD968
BANJO_RENUT_HOOK(sub_82256D28, GetSamplerStateHook<10>);  // D3DDevice_GetSamplerState_MagFilterZ  // rr6-nx: the game's state table; Katamari 824DD800
BANJO_RENUT_HOOK(sub_82256C20, GetSamplerStateHook<11>);  // D3DDevice_GetSamplerState_MinFilterZ  // rr6-nx: the game's state table; Katamari 824DD670
BANJO_RENUT_HOOK(sub_82256DD0, GetSamplerStateHook<12>);  // D3DDevice_GetSamplerState_SeparateZFilterEnable  // rr6-nx: the game's state table; Katamari 824DD8F0
BANJO_RENUT_HOOK(sub_82257090, GetSamplerStateHook<13>);  // D3DDevice_GetSamplerState_MinMipLevel  // rr6-nx: the game's state table; Katamari 824DDBB0
BANJO_RENUT_HOOK(sub_82257240, GetSamplerStateHook<14>);  // D3DDevice_GetSamplerState_TrilinearThreshold  // rr6-nx: the game's state table; Katamari 824DDD60
BANJO_RENUT_HOOK(sub_82256EB8, GetSamplerStateHook<15>);  // D3DDevice_GetSamplerState_AnisotropyBias  // rr6-nx: the game's state table; Katamari 824DD9D8
BANJO_RENUT_HOOK(sub_82257298, GetSamplerStateHook<16>);  // D3DDevice_GetSamplerState_HGradientExpBias  // rr6-nx: the game's state table; Katamari 824DDDB8
BANJO_RENUT_HOOK(sub_822572F0, GetSamplerStateHook<17>);  // D3DDevice_GetSamplerState_VGradientExpBias  // rr6-nx: the game's state table; Katamari 824DDE10
BANJO_RENUT_HOOK(sub_82257348, GetSamplerStateHook<18>);  // D3DDevice_GetSamplerState_WhiteBorderColorW  // rr6-nx: the game's state table; Katamari 824DDE68
BANJO_RENUT_HOOK(sub_822573A8, GetSamplerStateHook<19>);  // D3DDevice_GetSamplerState_PointBorderEnable  // rr6-nx: the game's state table; Katamari 824DDEC8
BANJO_RENUT_HOOK(sub_82256460, Rr6SetRenderState57);  // rr6-nx: the state table, row 57
BANJO_RENUT_HOOK(sub_82256478, Rr6GetRenderState57);  // rr6-nx: the state table, row 57
