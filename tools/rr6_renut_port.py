#!/usr/bin/env python3
"""rr6-nx (2026-11-02): the hand edits that move Renut's Direct3D layer to Ridge Racer 6 (XDK 2.0.2135), after
tools/renut_hook_remap_rr6.py (hooks). docs/rr6-notes.md, "Renut at XDK 2.0.2135", has the evidence. In pacman-nx's form (its
tools/renut_port_pacman.py), with the adapters from zuma-nx, which runs the same XDK.

Each edit is an exact (file, old, new) text pair; a pair whose new text is already there is skipped (idempotent), one whose
old text is missing is reported.

  python -I tools/rr6_renut_port.py [--check]
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GPU = os.path.join(ROOT, 'app', 'src', 'renut_engine', 'gpu')

DEFAULTS = '''// rr6-nx: this XDK's tables have 97 records in another order (below), so N&B's 101 defaults, in the order of kRenderStateFns,
// are kept here (zuma-nx's: from Bejeweled 3's tables, the same values). The 20 sampler states are in the same order.
constexpr u32 kRenderStateDefaults[101] = {
    0x00000000u, 0x00000003u, 0x00000001u, 0x00000000u, 0x00000000u, 0x00000000u, 0x3F800000u, 0x00000000u,
    0x00000000u, 0x00000000u, 0x00000001u, 0x00000003u, 0x00000001u, 0x00000000u, 0x00000006u, 0x00000000u,
    0x00000000u, 0xFFFFFFFFu, 0x00000001u, 0x00000000u, 0x00000000u, 0x00000001u, 0x00000000u, 0x00000000u,
    0x00000000u, 0x00000000u, 0x00000007u, 0x00000000u, 0x00000000u, 0x00000000u, 0x00000000u, 0x00000000u,
    0x00000007u, 0x00000000u, 0xFFFFFFFFu, 0xFFFFFFFFu, 0x00000000u, 0x00000000u, 0x00000000u, 0x00000007u,
    0x00000000u, 0xFFFFFFFFu, 0xFFFFFFFFu, 0x00000000u, 0x3F800000u, 0x3F800000u, 0x00000000u, 0x42800000u,
    0x00000001u, 0xFFFFFFFFu, 0x00000000u, 0x00000000u, 0x00000000u, 0x0000000Fu, 0x0000000Fu, 0x0000000Fu,
    0x0000000Fu, 0x00000001u, 0x3F800000u, 0x3F800000u, 0x00000000u, 0x00000000u, 0x00000000u, 0x00000000u,
    0x00000000u, 0x00000000u, 0x00000000u, 0x00000000u, 0x00000000u, 0x00000000u, 0x00000000u, 0x00000000u,
    0x00000000u, 0x00000000u, 0x00000000u, 0x00000000u, 0x00000001u, 0x00000000u, 0x00000000u, 0x00000000u,
    0x00000000u, 0x00000000u, 0x00000000u, 0x0000FFFFu, 0x00000000u, 0x00000087u, 0x40000000u, 0x40000000u,
    0x3F800000u, 0x3F800000u, 0x00000000u, 0x00000000u, 0x00000000u, 0x00000000u, 0x00000000u, 0x00000000u,
    0x00000002u, 0x00000002u, 0x00000001u, 0x3F800000u, 0x00000001u,
};
constexpr u32 kSamplerStateDefaults[20] = {
    0x00000000u, 0x00000000u, 0x00000000u, 0x00000000u, 0x00000000u, 0x00000000u, 0x00000002u, 0x00000000u,
    0x00000000u, 0x00000001u, 0x00000000u, 0x00000000u, 0x00000000u, 0x0000000Du, 0x00000000u, 0x00000000u,
    0x00000000u, 0x00000000u, 0x00000000u, 0x00000001u,
};
'''

ADAPTERS_RESOURCE = '''
// ---------------------------------------------------------------------------
// rr6-nx (2026-11-02): XDK 2.0.2135's own objects (zuma-nx's design, extended to surfaces, volumes and index buffers)
// ---------------------------------------------------------------------------
// This game's textures and surfaces stay XDK 2135 objects: the game's D3DX code and its loaders read their headers, which are
// not N&B's. A resource head of 12 bytes: Common (reference count in the low byte, type in bits 16-18, the bind count in
// bits 19-23), the fence at +4, the flush range at +8; a texture's fetch constant at +16..+40 (40 bytes); a surface
// is 64 bytes: the same six words, its texture at +44, then SurfaceInfo +48, Color / DepthInfo +52, HiControl +56.
// The game's own CreateTexture, GetSurfaceLevel, GetDesc, GetLevelDesc, AddRef, Release and GetType run on them (pure header
// work and XMemAlloc / XMemFree). What touches the device goes to Renut through a SHADOW per object (N&B's layout, the key of
// Renut's texture and surface caches): SetTexture, the locks, SetRenderTarget, SetDepthStencilSurface, Resolve. Renut's own
// objects (vertex and index buffers, declarations, shaders, the automatic surfaces: OwnsHeader or a record) keep Renut's
// AddRef and Release.
REX_IMPORT(__imp__sub_82254608, Rr6GuestAddRef, u32(u32));
REX_IMPORT(__imp__sub_82254B88, Rr6GuestRelease, u32(u32));
REX_IMPORT(__imp__sub_82254670, Rr6GuestGetType, u32(u32));
REX_IMPORT(__imp__sub_82254720, Rr6GuestDestroy, void(u32));
REX_IMPORT(__imp__sub_82252CB8, Rr6GuestCreateSurface, u32(u32, u32, u32, u32, u32));
REX_IMPORT(__imp__sub_82252FC0, Rr6GuestSurfaceGetDesc, void(u32, u32));

std::mutex g_rr6_shadow_mutex;
std::unordered_map<u32, u32> g_rr6_texture_shadows;  // the game's texture -> its shadow header (kept per address)
std::unordered_map<u32, u32> g_rr6_surface_shadows;  // the game's surface -> Renut's surface record
std::unordered_map<u32, u32> g_rr6_surface_guests;   // Renut's surface record -> the game's surface

bool Rr6IsRenutObject(u32 resource) {
  RecordKind kind;
  return OwnsHeader(resource) || records::Lookup(resource, &kind);
}

// XDK 2135's GetType numbers (surface 1, volume 2, texture 3, volume texture 4, cube 5, vertex buffer 6, index buffer 7).
u32 Rr6TypeFromRenut(u32 type) {
  switch (type) {
    case 1: return 6;
    case 2: return 7;
    case 3: case 19: case 20: return 3;
    case 4: return 1;
    case 16: return 2;
    case 17: return 4;
    case 18: return 5;
    default: return 0;
  }
}

// The shadow of a game texture, its fetch constant copied again at every use (the game's header may be set up again in
// place). A shadow is kept for the address once made: a texture made again there reuses it.
u32 Rr6ShadowTexture(u32 texture) {
  const auto *g = GuestPtr<const be_u32>(texture);
  if (!g)
    return 0;
  std::lock_guard lock(g_rr6_shadow_mutex);
  u32 &shadow = g_rr6_texture_shadows[texture];
  if (!shadow) {
    shadow = AllocHeader(0x34);
    if (!shadow)
      return 0;
    auto *t = GuestPtr<be_u32>(shadow);
    t[0] = 0x100003u;    // Common: a texture (as SetTextureHeader writes it)
    t[1] = 1u;           // ReferenceCount
    t[5] = 0xFFFF0000u;  // BaseFlush
    t[6] = 0xFFFF0000u;  // MipFlush
  }
  auto *t = GuestPtr<be_u32>(shadow);
  for (u32 i = 0; i < 6; ++i)
    t[7 + i] = u32(g[4 + i]);  // the fetch constant: XDK 2135's +16 to N&B's +0x1C
  return shadow;
}

// A game surface's Renut record: made at the game's CreateSurface (the format is only an argument there); a surface the
// game built some other way, from its header.
u32 Rr6MakeSurfaceShadow(u32 surface, u32 width, u32 height, u32 format, u32 multisample) {
  auto *record = CreateRecord<SurfaceRecord>(RecordKind::Surface);
  if (!record)
    return 0;
  auto *s = reinterpret_cast<be_u32 *>(&record->x360);
  u32 tiles = 0, hiz_size = 0;
  SetSurfaceHeader(width, height, format, multisample, 0, s, tiles, hiz_size);
  s[0] = u32(s[0]) | kCommonD3DCreated;
  // Its EDRAM is the game's: the base its allocator (sub_8225C000) gave and the HiZ word.
  const u32 info = LoadU32(surface + 52);
  s[7] = native::Insert(s[7], info & 0xFFF, 0, 12);
  s[8] = LoadU32(surface + 56);
  std::lock_guard lock(g_rr6_shadow_mutex);
  g_rr6_surface_shadows[surface] = record->self_va;
  g_rr6_surface_guests[record->self_va] = surface;
  return record->self_va;
}

u32 Rr6ShadowSurface(u32 surface) {
  if (!surface || Rr6IsRenutObject(surface))
    return surface;
  {
    std::lock_guard lock(g_rr6_shadow_mutex);
    auto it = g_rr6_surface_shadows.find(surface);
    if (it != g_rr6_surface_shadows.end())
      return it->second;
  }
  // Not from CreateSurface: its size and format from the fetch words, as the game's GetDesc reads them.
  const u32 size = LoadU32(surface + 24);
  const u32 dword0 = LoadU32(surface + 16), dword1 = LoadU32(surface + 20), dword3 = LoadU32(surface + 28);
  u32 swizzle = (((dword3 >> 10) & 7) << 3) | ((dword3 >> 7) & 7);
  swizzle = (swizzle << 3) | ((dword3 >> 4) & 7);
  swizzle = (swizzle << 3) | ((dword3 >> 1) & 7);
  u32 f = (swizzle << 1) | (dword3 & 1);
  f = (f << 2) | ((dword0 >> 8) & 3);
  f = (f << 2) | ((dword0 >> 6) & 3);
  f = (f << 2) | ((dword0 >> 4) & 3);
  f = (f << 2) | ((dword0 >> 2) & 3);
  f = (f << 1) | (dword0 >> 31);
  f = (f << 2) | ((dword1 >> 6) & 3);
  f = (f << 6) | (dword1 & 0x3F);
  RGPU_INFO("[rr6] surface {:08X} not from CreateSurface: {}x{} format {:08X}", surface, (size & 0x1FFF) + 1,
            ((size >> 13) & 0x1FFF) + 1, f);
  return Rr6MakeSurfaceShadow(surface, (size & 0x1FFF) + 1, ((size >> 13) & 0x1FFF) + 1, f,
                              (LoadU32(surface + 48) >> 16) & 3);
}

// A game object destroyed: what Renut holds for it goes after the work queued before it.
void Rr6DropShadow(u32 resource) {
  u32 shadow = 0, record = 0;
  {
    std::lock_guard lock(g_rr6_shadow_mutex);
    auto it = g_rr6_texture_shadows.find(resource);
    if (it != g_rr6_texture_shadows.end())
      shadow = it->second;
    auto its = g_rr6_surface_shadows.find(resource);
    if (its != g_rr6_surface_shadows.end()) {
      record = its->second;
      g_rr6_surface_guests.erase(record);
      g_rr6_surface_shadows.erase(its);
    }
  }
  if (shadow)
    render_thread::Queue([shadow] { ReleaseHostTextureLocked(shadow); });
  if (record)
    D3DResource_Destroy_hook(record);
}

// D3DSurface *D3DDevice_CreateSurface(Width, Height, D3DFORMAT, D3DMULTISAMPLE_TYPE, const D3DSURFACE_PARAMETERS*)
u32 Rr6CreateSurface(u32 width, u32 height, u32 format, u32 multisample, u32 parameters) {
  const u32 surface = Rr6GuestCreateSurface(width, height, format, multisample, parameters);
  if (surface)
    Rr6MakeSurfaceShadow(surface, width, height, format, multisample);
  return surface;
}

u32 Rr6AddRef(u32 resource) {
  return Rr6IsRenutObject(resource) ? AddRef(resource) : Rr6GuestAddRef(resource);
}
u32 Rr6Release(u32 resource) {
  if (Rr6IsRenutObject(resource))
    return Release(resource);
  // The game's object: bound objects stay alive by the bind count (Common bits 19-23).
  const u32 count = Rr6GuestRelease(resource);
  if (!count && !(LoadU32(resource) & 0x00F80000u))
    Rr6DropShadow(resource);
  return count;
}
u32 Rr6GetType(u32 resource) {
  return Rr6IsRenutObject(resource) ? Rr6TypeFromRenut(ResourceType(resource)) : Rr6GuestGetType(resource);
}
void Rr6SurfaceGetDesc(u32 surface, mapped_u32 desc) {
  if (Rr6IsRenutObject(surface))
    D3DSurface_GetDesc_hook(surface, desc);
  else
    Rr6GuestSurfaceGetDesc(surface, desc.guest_address());
}

// D3DDevice_CreateIndexBuffer(Length, Usage, Format): this XDK's Format is 0 for 16-bit and 1 for 32-bit indices (sub_82254DA0:
// `cmpwi cr6,r28,1; oris r10,r30,0x8000`; the game's two calls pass 0), N&B's D3DFMT_INDEX16 1 and INDEX32 6.
u32 Rr6CreateIndexBuffer(u32 length, u32 usage, u32 format) {
  return D3DDevice_CreateIndexBuffer_hook(length, usage, format == 1 ? 6 : 1);
}

// The buffers' locks return base + offset in this XDK (Feeding Frenzy's and Zuma's adapter).
u32 Rr6VertexBufferLock(u32 buffer, u32 offset, u32 size, u32 flags) {
  const u32 base = D3DVertexBuffer_Lock_hook(buffer, offset, size, flags);
  return base ? base + offset : 0;
}
u32 Rr6IndexBufferLock(u32 buffer, u32 offset, u32 size, u32 flags) {
  const u32 base = D3DIndexBuffer_Lock_hook(buffer, offset, size, flags);
  return base ? base + offset : 0;
}

// Lock2DSurface (texture, face, level, locked, rect, flags): the target of the texture's and the cube's LockRect thunks.
void Rr6TextureLockRect(u32 texture, u32 face, u32 level, mapped_u32 locked_rect, mapped_u32 rect, u32 flags) {
  D3D_Lock2DSurface_hook(Rr6ShadowTexture(texture), face, level, locked_rect, rect, flags);
}
void Rr6TextureUnlockRect(u32 texture) {
  if (const u32 shadow = Rr6ShadowTexture(texture))
    D3DArrayTexture_UnlockRect_hook(shadow);
}
// D3DSurface_LockRect (surface, locked, rect, flags): a texture level's surface, its texture at +44, face
// ((+24 >> 26) & 63) and level ((+32 >> 2) & 15), as the game's sub_82253018 passes them on.
void Rr6SurfaceLockRect(u32 surface, mapped_u32 locked_rect, mapped_u32 rect, u32 flags) {
  const u32 texture = LoadU32(surface + 44);
  D3D_Lock2DSurface_hook(Rr6ShadowTexture(texture), (LoadU32(surface + 24) >> 26) & 63, (LoadU32(surface + 32) >> 2) & 15,
                         locked_rect, rect, flags);
}
void Rr6SurfaceUnlockRect(u32 surface) {
  if (const u32 shadow = Rr6ShadowTexture(LoadU32(surface + 44)))
    D3DArrayTexture_UnlockRect_hook(shadow);
}
void Rr6VolumeLockBox(u32 volume, mapped_u32 locked_box, mapped_u32 box, u32 flags) {
  D3D_Lock3DSurface_hook(Rr6ShadowTexture(LoadU32(volume + 44)), (LoadU32(volume + 32) >> 2) & 15, locked_box, box, flags);
}
'''

NATIVE_RR6 = '''
// rr6-nx: XDK 2135's objects, for hooks/state.cpp and hooks/draw.cpp (the section above).
u32 Rr6TextureShadow(u32 texture) {
  if (!texture || Rr6IsRenutObject(texture))
    return texture;
  return Rr6ShadowTexture(texture);
}
u32 Rr6SurfaceShadow(u32 surface) {
  return Rr6ShadowSurface(surface);
}
u32 Rr6SurfaceGuest(u32 shadow) {
  std::lock_guard lock(g_rr6_shadow_mutex);
  auto it = g_rr6_surface_guests.find(shadow);
  return it != g_rr6_surface_guests.end() ? it->second : shadow;
}
// XDK 2135's Set* count a binding in the object's Common (`add r11,r11,0x80000`); the last unbinding of an object with no
// references destroys it. Renut's own objects: a reference.
void Rr6Bind(u32 resource) {
  if (!resource)
    return;
  if (Rr6IsRenutObject(resource))
    AddRef(resource);
  else
    AtomicAddGuest(resource, 0x80000);
}
void Rr6Unbind(u32 resource) {
  if (!resource)
    return;
  if (Rr6IsRenutObject(resource)) {
    Release(resource);
    return;
  }
  const u32 now = AtomicAddGuest(resource, 0u - 0x80000u) - 0x80000u;
  if (!(now & 0x00F800FFu)) {
    Rr6GuestDestroy(resource);
    Rr6DropShadow(resource);
  }
}
u32 Rr6AddRefAny(u32 resource) {
  return Rr6AddRef(resource);
}
'''

ADAPTERS_STATE = '''
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
'''

EDITS = [
    # 1. The device's head: XDK 2135's own code (compiled into the game from the headers) writes shader constants at +0x780 /
    # +0x1780 and marks them at +16 / +24 (`ld r11,8(r10)` with r10 = device + 16; tools/rr6_device_census.py), with the ring at
    # +0, the count at +12 and the state tables at +0x60 / +0x1E4 / +0x234 / +0x3B8. So those fields are at this XDK's places.
    ('d3d/d3d.h', '''  be_u64 m_Pending[5];                // +0x0000  D3DTAGCOLLECTION dirty masks
  be_u64 m_Predicated_PendingMask2;   // +0x0028
  be_u32 m_pRing;                     // +0x0030
  be_u32 m_pRingLimit;                // +0x0034
  be_u32 m_pRingGuarantee;            // +0x0038
  be_u32 m_ReferenceCount;            // +0x003C
  be_u32 m_SetRenderStateCall[101];   // +0x0040
  be_u32 m_SetSamplerStateCall[20];   // +0x01D4
  be_u32 m_GetRenderStateCall[101];   // +0x0224
  be_u32 m_GetSamplerStateCall[20];   // +0x03B8''', '''  // rr6-nx: the head as XDK 2.0.2135's inline code uses it (N&B: masks at +0, ring at +0x30, tables at +0x40).
  be_u32 m_pRing;                     // +0x0000
  be_u32 m_pRingLimit;                // +0x0004
  be_u32 m_pRingGuarantee;            // +0x0008
  be_u32 m_ReferenceCount;            // +0x000C
  be_u64 m_Pending[5];                // +0x0010  D3DTAGCOLLECTION dirty masks: vertex and pixel float constants first
  be_u64 m_Predicated_PendingMask2;   // +0x0038
  u8 pad_0040[0x60 - 0x40];           // +0x0040
  be_u32 m_SetRenderStateCall[97];    // +0x0060
  be_u32 m_SetSamplerStateCall[20];   // +0x01E4
  be_u32 m_GetRenderStateCall[97];    // +0x0234
  be_u32 m_GetSamplerStateCall[20];   // +0x03B8'''),
    ('d3d/d3d.h', 'static_assert(offsetof(Device, m_pRing) == 0x30);', 'static_assert(offsetof(Device, m_pRing) == 0);'),
    ('d3d/d3d.h', 'static_assert(offsetof(Device, m_ReferenceCount) == 0x3C);', 'static_assert(offsetof(Device, m_ReferenceCount) == 12);\nstatic_assert(offsetof(Device, m_Pending) == 16);'),
    ('d3d/d3d.h', 'static_assert(offsetof(Device, m_SetRenderStateCall) == 0x40);', 'static_assert(offsetof(Device, m_SetRenderStateCall) == 0x60);'),
    ('d3d/d3d.h', 'static_assert(offsetof(Device, m_SetSamplerStateCall) == 0x1D4);', 'static_assert(offsetof(Device, m_SetSamplerStateCall) == 0x1E4);'),
    ('d3d/d3d.h', 'static_assert(offsetof(Device, m_GetRenderStateCall) == 0x224);', 'static_assert(offsetof(Device, m_GetRenderStateCall) == 0x234);'),
    ('d3d/d3d_native.h', 'void TouchTags() const { g_touch[slot].chunks |= TagChunks(Q(2 * 8), Q(3 * 8), Q(4 * 8)); }',
     'void TouchTags() const { g_touch[slot].chunks |= TagChunks(Pending(2), Pending(3), Pending(4)); }'),
    ('d3d/d3d_native.h', 'u64 Pending(u32 word) const { return Q(word * 8); }', 'u64 Pending(u32 word) const { return Q(16 + word * 8); }  // rr6-nx: XDK 2135\'s place'),
    ('d3d/d3d_native.h', 'void SetPending(u32 word, u64 value) { SetQ(word * 8, value); }', 'void SetPending(u32 word, u64 value) { SetQ(16 + word * 8, value); }'),
    ('d3d/d3d_native.h', 'constexpr u32 Ring = 0x30;                 // m_pRing', 'constexpr u32 Ring = 0;                    // m_pRing (rr6-nx: XDK 2135)'),
    ('d3d/d3d_native.h', 'constexpr u32 RingLimit = 0x34;            // m_pRingLimit', 'constexpr u32 RingLimit = 4;               // m_pRingLimit'),
    ('d3d/d3d_native.h', 'constexpr u32 RingGuarantee = 0x38;        // m_pRingGuarantee', 'constexpr u32 RingGuarantee = 8;           // m_pRingGuarantee'),
    ('d3d/d3d_native.h', 'constexpr u32 PredicatedPending2 = 0x28;   // m_Predicated_PendingMask2', 'constexpr u32 PredicatedPending2 = 0x38;   // m_Predicated_PendingMask2'),
    ('d3d/d3d_native.h', 'constexpr u32 SetRenderStateCall = 0x40;   // [101]', 'constexpr u32 SetRenderStateCall = 0x60;   // [97]'),
    ('d3d/d3d_native.h', 'constexpr u32 SetSamplerStateCall = 0x1D4; // [20]', 'constexpr u32 SetSamplerStateCall = 0x1E4; // [20]'),
    ('d3d/d3d_native.h', 'constexpr u32 GetRenderStateCall = 0x224;  // [101]', 'constexpr u32 GetRenderStateCall = 0x234;  // [97]'),
    ('d3d/d3d_native.h', 'u32 CreateSurface(u32 width, u32 height, u32 format, u32 multisample, u32 parameters_va);',
     'u32 CreateSurface(u32 width, u32 height, u32 format, u32 multisample, u32 parameters_va);\n'
     '// pacman-nx: the automatic front buffer, InitializePresentationParameters\' CreateTexture(Width, Height, 1, 1, 0, format, 0, 3).\n'
     'u32 CreateFrontBufferTexture(u32 width, u32 height, u32 format);\n'
     '// rr6-nx: XDK 2.0.2135\'s own objects (hooks/resource.cpp): their shadows, and the bindings Set* keeps on them.\n'
     'u32 Rr6TextureShadow(u32 texture);\nu32 Rr6SurfaceShadow(u32 surface);\nu32 Rr6SurfaceGuest(u32 shadow);\nvoid Rr6Bind(u32 resource);\n'
     'void Rr6Unbind(u32 resource);\nu32 Rr6AddRefAny(u32 resource);'),
    # 2. The state tables (tools/renut_state_tables.py's method, Zuma's defaults): 97 + 20 records.
    ('d3d/d3d_native_state.cpp', '''// N&B's state tables: {getter, setter, default} per state.
constexpr u32 kRenderStateTable = 0x82AD8E48;  // katamari-nx: 0x82D8A948->0x82AD8E48
constexpr u32 kSamplerStateTable = 0x82AD9308;  // katamari-nx: 0x82D8AE28->0x82AD9308
''', '''// rr6-nx: this game's state tables, {getter, setter, default} per state: 97 render states at 0x823763E0 and 20 sampler states at
// 0x82376870, found by Zuma's defaults (the same XDK; the only match of each). Its D3D_InitializeApiState copies them to the
// device's dispatch tables, through which the game reaches every state function.
constexpr u32 kRenderStateTable = 0x823763E0, kRr6RenderStates = 97;
constexpr u32 kSamplerStateTable = 0x82376870, kRr6SamplerStates = 20;
''' + DEFAULTS),
    ('d3d/d3d_native_state.cpp', '''  for (u32 i = 0; i < kRenderStates; ++i) {
    device.SetW(off::SetRenderStateCall + i * 4, TableWord(kRenderStateTable, i, 1));
    device.SetW(off::GetRenderStateCall + i * 4, TableWord(kRenderStateTable, i, 0));
    kRenderStateFns[i](device, TableWord(kRenderStateTable, i, 2));
  }
  for (u32 sampler = 0; sampler < kTextureSamplers; ++sampler) {
    for (u32 i = 0; i < kSamplerStates; ++i) {
      device.SetW(off::SetSamplerStateCall + i * 4, TableWord(kSamplerStateTable, i, 1));
      device.SetW(off::GetSamplerStateCall + i * 4, TableWord(kSamplerStateTable, i, 0));
      kSamplerStateFns[i](device, sampler, TableWord(kSamplerStateTable, i, 2));
    }
    SetTexture(device, sampler, 0);
  }''', '''  for (u32 i = 0; i < kRenderStates; ++i)
    kRenderStateFns[i](device, kRenderStateDefaults[i]);
  for (u32 i = 0; i < kRr6RenderStates; ++i) {
    device.SetW(off::SetRenderStateCall + i * 4, TableWord(kRenderStateTable, i, 1));
    device.SetW(off::GetRenderStateCall + i * 4, TableWord(kRenderStateTable, i, 0));
  }
  for (u32 i = 0; i < kRr6SamplerStates; ++i) {
    device.SetW(off::SetSamplerStateCall + i * 4, TableWord(kSamplerStateTable, i, 1));
    device.SetW(off::GetSamplerStateCall + i * 4, TableWord(kSamplerStateTable, i, 0));
  }
  for (u32 sampler = 0; sampler < kTextureSamplers; ++sampler) {
    for (u32 i = 0; i < kSamplerStates; ++i)
      kSamplerStateFns[i](device, sampler, kSamplerStateDefaults[i]);
    SetTexture(device, sampler, 0);
  }'''),
    # 3. Guest data.
    ('d3d/d3d_native_state.cpp', 'constexpr u32 kFormatTable = 0x820FA9D0;', 'constexpr u32 kFormatTable = 0x8206C088;  // rr6-nx: Zuma\'s 128 bytes, word for word; CreateSurface `addi r9,r9,-16248`;'),
    ('d3d/hooks/resource.cpp', 'constexpr u32 kFormatTable = 0x820FA9D0;', 'constexpr u32 kFormatTable = 0x8206C088;  // rr6-nx: Zuma\'s 128 bytes, word for word;'),
    ('d3d/hooks/resource.cpp', 'REX_IMPORT(__imp__sub_824CAB98, GameXMemFree', 'REX_IMPORT(__imp__sub_8224DBB0, GameXMemFree'),
    ('d3d/hooks/resource.cpp', 'constexpr u32 kGameNoLargePagesVa = 0x8315DFE0;', 'constexpr u32 kGameNoLargePagesVa = 0;  // rr6-nx: none in XDK 2135 (zuma-nx);'),
    ('d3d/hooks/resource.cpp', 'if (const auto *no_large_pages = GuestPtr<const be_u32>(kGameNoLargePagesVa); u32(*no_large_pages))',
     'if (const auto *no_large_pages = kGameNoLargePagesVa ? GuestPtr<const be_u32>(kGameNoLargePagesVa) : nullptr; no_large_pages && u32(*no_large_pages))'),
    ('d3d/hooks/resource.cpp', 'constexpr u32 kHiZOwnerVa = 0x8315E830;', 'constexpr u32 kHiZOwnerVa = 0;  // rr6-nx: the game\'s surfaces carry their own HiZ word; Renut\'s automatic one takes HiZ base 0;'),
    ('d3d/hooks/resource.cpp', '#include <unordered_set>\n', '#include <unordered_map>\n#include <unordered_set>\n'),
    ('d3d/hooks/device.cpp', 'constexpr u32 kGlobalQwordVa = 0x82AD93F8;', 'constexpr u32 kGlobalQwordVa = 0x82376960;  // rr6-nx: holds 0x0002000008574000 (2.0.2135.0);'),
    ('d3d/hooks/device.cpp', 'constexpr u32 kVdGlobalDeviceImportSlot = 0x82000750;', 'constexpr u32 kVdGlobalDeviceImportSlot = 0x82000598;  // rr6-nx: the image\'s only word 0xFFCAE000 (sub_8224E758 reads it);'),
    ('d3d/hooks/device.cpp', 'constexpr u32 kDeviceCapsVa = 0x820FC1F8;', 'constexpr u32 kDeviceCapsVa = 0x8206BF58;  // rr6-nx: GetDeviceCaps sub_8224F0D8 copies 304 bytes from it;'),
    ('d3d/hooks/device.cpp', 'REX_IMPORT(__imp__sub_824C1C10, GuestGetCurrentThreadId', 'REX_IMPORT(__imp__sub_8231CBB8, GuestGetCurrentThreadId'),
    ('d3d/hooks/device.cpp', '''  if (!p[15])  // DisableAutoFrontBuffer
    RGPU_ERROR("InitializePresentationParameters: an automatic front buffer is not supported");
''', '''  // pacman-nx: a game that asks for the automatic front buffer (N&B's parameters disable it): D3D's Present resolves the back
  // buffer into it and swaps it.
  if (!p[15]) {  // DisableAutoFrontBuffer
    const u32 texture = native::CreateFrontBufferTexture(width, height, front_format);
    if (!texture)
      return false;
    d.SetW(native::off::AutoFrontBuffer, texture);
  }
'''),
    ('d3d/hooks/draw.cpp', 'constexpr u32 kFullViewport = 0x820FAEB4;', 'constexpr u32 kFullViewport = 0;  // rr6-nx: only BeginTiling / EndTiling use it, which this XDK does not have;'),
    # 4. The resolve's destination is the game's texture; the end of Begin*Vertices has this XDK's offsets.
    ('d3d/hooks/draw.cpp', '''  Resolve(device, flags, has_rect ? &rect : nullptr, dest_texture, dest_x, dest_y, dest_level,
          dest_slice, color_va, float(clear_z), clear_stencil, parameters);
}
''', '''  // rr6-nx: the destination is the game's XDK 2135 texture: its shadow (hooks/resource.cpp).
  Resolve(device, flags, has_rect ? &rect : nullptr, native::Rr6TextureShadow(dest_texture), dest_x, dest_y, dest_level,
          dest_slice, color_va, float(clear_z), clear_stencil, parameters);
}

// rr6-nx: XDK 2135's EndVertices (sub_82254080: the ring pointer back from +13636, a kick unless the byte at +10432 has 0x80,
// both of them other fields of Renut's device): nothing to do, the vertices are taken at the device's next hook.
void Rr6EndVertices(u32 /*device*/) {}

// rr6-nx: the setters that keep a binding on Renut's own objects in this XDK (zuma-nx's reading of sub_82124A50).
u32 g_rr6_vs = 0, g_rr6_ps = 0;
void Rr6SetVertexShader(u32 device, u32 shader) {
  if (shader != g_rr6_vs) {
    native::Rr6Bind(shader);
    const u32 old = g_rr6_vs;
    g_rr6_vs = shader;
    native::Rr6Unbind(old);
  }
  native::SetVertexShader(native::DeviceAt(device), shader);
}
void Rr6SetPixelShader(u32 device, u32 shader) {
  if (shader != g_rr6_ps) {
    native::Rr6Bind(shader);
    const u32 old = g_rr6_ps;
    g_rr6_ps = shader;
    native::Rr6Unbind(old);
  }
  native::SetPixelShader(native::DeviceAt(device), shader);
}
'''),
    # 5. Version 0x0E containers (XDK 2135's compiler; feedingfrenzy-nx).
    ('d3d/hooks/shader.cpp', '''  if ((u32(header->flags) & 0xFFFFFF00u) != 0x102A1100u) {
    RGPU_ERROR("Create{}Shader: not a shader container (flags {:08X})", pixel ? "Pixel" : "Vertex",''', '''  // feedingfrenzy-nx (2026-10-26): version 0x0E too (XDK 2135's compiler); the translator reads it through
  // XenosRecomp/container_0e.h, and only the sizes are read here.
  if ((u32(header->flags) & 0xFFFFFF00u) != 0x102A1100u && (u32(header->flags) & 0xFFFFFF00u) != 0x102A0E00u) {
    RGPU_ERROR("Create{}Shader: not a shader container (flags {:08X})", pixel ? "Pixel" : "Vertex",'''),
    # 6. The adapters, in front of the resource hooks.
    ('d3d/hooks/resource.cpp', '''// _GetMaxMipLevels (0x8263DC20): the levels down to 1x1x1 of the largest''', ADAPTERS_RESOURCE.lstrip('\n') + '''
// _GetMaxMipLevels (0x8263DC20): the levels down to 1x1x1 of the largest'''),
    ('d3d/hooks/resource.cpp', '''u32 AddRefResource(u32 resource) {
  return AddRef(resource);
}
''', '''u32 AddRefResource(u32 resource) {
  return AddRef(resource);
}

u32 CreateFrontBufferTexture(u32 width, u32 height, u32 format) {
  return D3DDevice_CreateTexture_hook(width, height, 1, 1, 0, format, 0, 3);
}
''' + NATIVE_RR6),
    ('d3d/hooks/state.cpp', '''// D3DSurface *GetRenderTarget(D3DDevice*, DWORD Index) [0x82636ED0]''', ADAPTERS_STATE.lstrip('\n') + '''
// D3DSurface *GetRenderTarget(D3DDevice*, DWORD Index) [0x82636ED0]'''),
]


# Hook lines Katamari's table has no line for (after tools/renut_hook_remap_rr6.py, which leaves them alone: they say rr6-nx).
EXTRA = {
    'd3d/hooks/draw.cpp': ['BANJO_RENUT_HOOK(sub_82254080, Rr6EndVertices);  // D3DDevice_EndVertices  // rr6-nx: 30 sites, each after a BeginVertices'],
    'd3d/hooks/state.cpp': ['BANJO_RENUT_HOOK(sub_82256460, Rr6SetRenderState57);  // rr6-nx: the state table, row 57',
                            'BANJO_RENUT_HOOK(sub_82256478, Rr6GetRenderState57);  // rr6-nx: the state table, row 57'],
    'd3d/hooks/resource.cpp': ['BANJO_RENUT_HOOK(sub_8224E758, Rr6Release);  // rr6-nx: a shader\'s own Release (the count at +4, data at +12): Renut\'s objects',
                               'BANJO_RENUT_HOOK(sub_8224ED60, Rr6Release);  // rr6-nx: a declaration\'s own Release (the count at +4): Renut\'s objects'],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true')
    a = ap.parse_args()
    done = skipped = 0
    bad = []
    for rel, old, new in EDITS:
        p = os.path.join(GPU, rel.replace('/', os.sep))
        t = open(p, encoding='utf-8', errors='surrogateescape', newline='').read()
        crlf = '\r\n' in t
        o, n = (old.replace('\n', '\r\n'), new.replace('\n', '\r\n')) if crlf else (old, new)
        if n in t:
            skipped += 1
        elif o in t:
            if not a.check:
                t = t.replace(o, n, 1)
                open(p, 'w', encoding='utf-8', errors='surrogateescape', newline='').write(t)
            done += 1
        else:
            bad.append((rel, old[:70]))
    for rel, hook_lines in EXTRA.items():
        p = os.path.join(GPU, rel.replace('/', os.sep))
        t = open(p, encoding='utf-8', errors='surrogateescape', newline='').read()
        nl = '\r\n' if '\r\n' in t else '\n'
        missing = [line for line in hook_lines if line not in t]
        if missing and not a.check:
            open(p, 'w', encoding='utf-8', errors='surrogateescape', newline='').write(t.rstrip() + nl + nl.join(missing) + nl)
    print(f'{done} edits applied, {skipped} already there, {len(bad)} missing')
    for b in bad:
        print('MISSING', b)
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
