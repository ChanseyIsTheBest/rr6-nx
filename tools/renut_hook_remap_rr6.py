#!/usr/bin/env python3
"""rr6-nx (2026-11-02): moves Renut's hook table (app/src/renut_engine/gpu/d3d/hooks/*.cpp, at Beautiful Katamari's addresses, XDK
2.0.5632) to Ridge Racer 6's (XDK 2.0.2135, the same XDK as Zuma's). docs/rr6-notes.md, "Renut at XDK 2.0.2135", has the evidence.

A hook is matched by the name in its line's comment:
  API       an address read from the code, with the evidence (the pairs of tools/d3d_propagate.py against Zuma, Feeding Frenzy,
            Katamari, and tools/rr6_d3d_api.py's list of what the game calls);
  ADAPTERS  the game's object is an XDK 2135 one: the hook goes to an adapter in resource.cpp / state.cpp;
  table     the render and sampler state hooks from the game's own tables, 97 records at 0x823763E0 and 20 at 0x82376870 ({getter,
            setter, default}, as Zuma's: rows 0-56 are N&B's, row 57 a state N&B lacks, N&B's 57-95 are rows 58-96, N&B's 96-100 are
            not in this XDK);
  anything else stays compiled, unregistered, with no address in the code ("Stale mentions" in docs/optimising-functions.md).

Lines already moved (`rr6-nx:`) are left alone, so it is idempotent.

  python -I tools/renut_hook_remap_rr6.py [--dry-run]
"""
import argparse
import os
import re
import struct

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS = os.path.join(ROOT, 'app', 'src', 'renut_engine', 'gpu', 'd3d', 'hooks')
B = 0x82000000
LIB = (0x8224E000, 0x82264000)
RENDER_TABLE, RENDER_ROWS = 0x823763E0, 97
SAMPLER_TABLE, SAMPLER_ROWS = 0x82376870, 20

API = {
    # device.cpp
    'Direct3D_CreateDevice': ('8225A260', 'Zuma pair of sub_82121838; 1 site'),
    'D3DDevice_AddRef': ('8225A148', 'Zuma pair of sub_82121720: the count at +12'),
    'D3DDevice_Release': ('8225A208', 'Zuma pair of sub_821217E0; 3 sites'),
    'D3DDevice_GetDeviceCaps': ('8224F0D8', 'Katamari pair; 1 site'),
    'D3DResource_GetDevice': ('82254C08', 'Zuma pair of sub_82122900; 1 site'),
    # draw.cpp
    'D3DDevice_DrawVertices': ('82254128', 'Zuma pair of sub_8212AA88; 12 sites'),
    'D3DDevice_DrawIndexedVertices': ('82254368', 'reads the index buffer +12532, the same immediates as DrawVertices; 2 sites'),
    'D3DDevice_DrawVerticesUP': ('822540A0', 'BeginVertices, memcpy, the end; 16 sites'),
    'D3DDevice_BeginVertices': ('82253E00', 'Recomp\'s notes; 30 sites, each followed by sub_82254080'),
    'D3DDevice_Clear': ('82253D50', 'Zuma pair of sub_821287F8; 4 sites'),
    'D3DDevice_Resolve': ('82258980', 'Zuma pair of sub_82134138; 14 sites'),
    'D3DDevice_Present': ('8225A008', 'Zuma pair of sub_821221C0; 1 site'),
    # resource.cpp
    'D3DVertexBuffer_Unlock': ('82254D90', '4 instructions, reads +12; 11 sites, one for each Lock'),
    'D3DDevice_CreateVertexBuffer': ('82254C70', 'Zuma pair of sub_82122968; 11 sites'),
    # shader.cpp
    'D3DDevice_CreateVertexShader': ('8224EF40', 'Zuma pair of sub_82125BB8; 1 site'),
    'D3DDevice_CreatePixelShader': ('8224EE50', 'Zuma pair of sub_82125AC8; 1 site'),
    'D3DDevice_CreateVertexDeclaration': ('8224ECA0', 'Zuma pair of sub_82124AB8; 2 sites'),
    # state.cpp
    'D3DDevice_SetViewport': ('82257488', 'writes the 6 words at +12808 and the viewport floats; 3 sites'),
    'D3DDevice_GetViewport': ('822576D0', 'copies 6 words from +12808; 6 sites'),
    'D3DDevice_SetShaderGPRAllocation': ('8224EDA0', 'Feeding Frenzy pair of sub_820B6258, register 0x0D00 (imm 3328); 3 sites'),
    'D3DDevice_SetClipPlane': ('822579C0', 'four floats at register 1480; 1 site'),
}

# name -> (address, the adapter's name, evidence). resource.cpp and state.cpp, "rr6-nx:" sections.
ADAPTERS = {
    'D3DDevice_CreateIndexBuffer': ('82254DA0', 'Rr6CreateIndexBuffer', '20-byte header, 0x41020001 / 0x01020001; 2 sites; Format 0 16-bit, 1 32-bit'),
    'D3DDevice_SetVertexShader': ('8224EC38', 'Rr6SetVertexShader', 'Zuma pair of sub_82124A50; 58 sites; keeps a reference'),
    'D3DDevice_SetPixelShader': ('8224E8C8', 'Rr6SetPixelShader', 'Zuma pair of sub_821246E0; 58 sites'),
    'D3DDevice_SetVertexDeclaration': ('8224F018', 'Rr6SetVertexDeclaration', 'Zuma pair; 47 sites; keeps a reference'),
    'D3DDevice_SetTexture': ('822530A8', 'Rr6SetTexture', 'Zuma pair of sub_8212A900; 51 sites; the game\'s texture, on its shadow'),
    'D3DDevice_SetRenderTarget': ('82257C78', 'Rr6SetRenderTarget', '(dev, index, surface); 7 sites; the bind count in Common, on the surface\'s shadow'),
    'D3DDevice_SetDepthStencilSurface': ('82257FE0', 'Rr6SetDepthStencil', '(dev, surface); 11 sites'),
    'D3DDevice_GetRenderTarget': ('82257818', 'Rr6GetRenderTarget', '18 instructions, AddRef; the game\'s surface back from its shadow'),
    'D3DDevice_GetDepthStencilSurface': ('82257860', 'Rr6GetDepthStencil', '+12552, AddRef'),
    'D3DDevice_SetStreamSource': ('822576F8', 'Rr6SetStreamSource', 'Zuma pair; 11 sites; keeps a reference, as this XDK does'),
    'D3DDevice_SetIndices': ('82257798', 'Rr6SetIndices', 'stored at +12532, the old released; 7 sites'),
    'D3DVertexBuffer_Lock': ('82254D20', 'Rr6VertexBufferLock', 'returns base + offset (Zuma\'s adapter); 11 sites'),
    'D3DIndexBuffer_Lock': ('82254E50', 'Rr6IndexBufferLock', 'returns base + offset; 2 sites'),
    'D3DSurface_LockRect': ('82253018', 'Rr6SurfaceLockRect', 'Zuma pair of sub_8212A870; on the texture\'s shadow'),
    'D3DSurface_UnlockRect': ('822510A8', 'Rr6SurfaceUnlockRect', 'Zuma pair of sub_82128958'),
    'D3DArrayTexture_UnlockRect': ('82251090', 'Rr6TextureUnlockRect', 'Zuma pair of sub_82128940; (texture, level)'),
    'D3D_Lock2DSurface': ('82252498', 'Rr6TextureLockRect', 'the target of the thunks sub_82252A18 (level) and sub_82252AD8 (face, level)'),
    'D3DVolume_LockBox': ('82253088', 'Rr6VolumeLockBox', 'Katamari pair; (volume, locked, box, flags)'),
    'D3DResource_AddRef': ('82254608', 'Rr6AddRef', 'Zuma pair of sub_82122300; 2 sites'),
    'D3DResource_Release': ('82254B88', 'Rr6Release', 'Zuma pair of sub_82122880; 57 sites'),
    'D3DResource_GetType': ('82254670', 'Rr6GetType', 'Zuma pair of sub_82122368; 8 sites'),
    'D3DSurface_GetDesc': ('82252FC0', 'Rr6SurfaceGetDesc', 'Katamari pair; the game\'s surfaces by the game\'s code, the automatic ones by Renut\'s'),
    'D3DDevice_CreateSurface': ('82252CB8', 'Rr6CreateSurface', '64-byte header, 0x01040001; 6 sites; the game\'s object and a Renut record'),
}

# Left as the game's own code: pure work on XDK 2135's headers, which D3DX reads too.
GUEST_KEPT = {
    'D3DDevice_CreateTexture': '82252B98',
    'D3DTexture_GetSurfaceLevel': '82252970',
    'D3DCubeTexture_GetCubeMapSurface': '82252A30',
    'D3DVolumeTexture_GetVolumeLevel': '82252AF0',
    'D3DBaseTexture_GetLevelCount': '822528A0',
    'D3DVolume_GetDesc': '82253040',
    'D3D_Get2DSurfaceDesc': '82251DC8',
    'D3D_Get3DSurfaceDesc': '82251E70',
    'D3D_GetTextureDimensions': '82250FF8',
    'D3D_BlockSizeOfGpuFormat': '822510C0',
    'D3D_AlignTextureDimensions': '82251268',
    'D3D_GetMipTailLevelOffsetCoords': '822518B0',
    'D3D_SetTextureHeader': '822525D0',
}

LINE = re.compile(r'^(\s*)BANJO_RENUT_(UNHOOKED_)?HOOK(_RAW)?(_SHARED)?\(\s*(sub_[0-9A-F]{8}|unlinked_[0-9A-F]{8})(, ?)?([^;)]*)(\)?)(;?)\s*(?://\s*(\w+))?(.*)$')


def table_word(img, table, row, col):
    return struct.unpack_from('>I', img, table - B + 12 * row + 4 * col)[0]


def state_address(img, kind, index, setter):
    if kind == 'Render':
        row = index if index <= 56 else index + 1
        if row >= RENDER_ROWS:
            return None
        word = table_word(img, RENDER_TABLE, row, 1 if setter else 0)
    else:
        word = table_word(img, SAMPLER_TABLE, index, 1 if setter else 0)
    return f'{word:08X}' if LIB[0] <= word < LIB[1] else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    img = open(os.path.join(ROOT, 'out', 'renut_image.bin'), 'rb').read()
    used = {}
    placed = off = 0
    report = []
    for fn in sorted(os.listdir(HOOKS)):
        if not fn.endswith('.cpp'):
            continue
        path = os.path.join(HOOKS, fn)
        text = open(path, encoding='utf-8', errors='surrogateescape', newline='').read()
        nl = '\r\n' if '\r\n' in text else '\n'
        lines = text.split(nl)
        for k, line in enumerate(lines):
            if 'rr6-nx:' in line:
                if (m := re.search(r'HOOK(?:_RAW)?(?:_SHARED)?\(sub_([0-9A-F]{8})', line)):
                    used[m.group(1)] = fn
                continue
            m = LINE.match(line)
            if not m or (m.group(3) and not m.group(11)):
                # A raw hook has no name in its line: BeginTiling and EndTiling, which this XDK does not have.
                if line.lstrip().startswith(('BANJO_RENUT_HOOK_RAW', 'BANJO_RENUT_UNHOOKED_HOOK_RAW')):
                    mm = re.match(r'^(\s*)BANJO_RENUT_(?:UNHOOKED_)?HOOK_RAW(_SHARED)?\(\s*(?:sub|unlinked)_([0-9A-F]{8})\)(.*)$', line)
                    if mm:
                        lines[k] = f'{mm.group(1)}BANJO_RENUT_UNHOOKED_HOOK_RAW{mm.group(2) or ""}(unlinked_{mm.group(3)}){mm.group(4)}  // rr6-nx: not in this XDK'
                        off += 1
                continue
            indent, was_off, raw, shared, sub, _, target, _, _, name, rest = m.groups()
            old = sub.split('_')[1]
            suffix = f'{raw or ""}{shared or ""}'
            addr = why = None
            if name in ADAPTERS:
                addr, target, why = ADAPTERS[name]
            elif name in API:
                addr, why = API[name]
            elif (sm := re.match(r'(Set|Get)(Render|Sampler)StateHook<(\d+)>', target or '')):
                addr = state_address(img, sm.group(2), int(sm.group(3)), sm.group(1) == 'Set')
                why = 'the game\'s state table'
            elif name in GUEST_KEPT:
                lines[k] = f'{indent}BANJO_RENUT_UNHOOKED_HOOK{suffix}(unlinked_{old}, {target});  // {name}  // rr6-nx: the game\'s own code (sub_{GUEST_KEPT[name]}, XDK 2135\'s headers)'
                off += 1
                continue
            if addr and addr in used:
                report.append(f'DUPLICATE {fn}:{k + 1} {name} {addr} (already {used[addr]})')
                addr = None
            if addr:
                used[addr] = name
                lines[k] = f'{indent}BANJO_RENUT_HOOK{suffix}(sub_{addr}, {target});  // {name}  // rr6-nx: {why}; Katamari {old}'
                placed += 1
            else:
                lines[k] = f'{indent}BANJO_RENUT_UNHOOKED_HOOK{suffix}(unlinked_{old}, {target});  // {name}  // rr6-nx: not hooked in this XDK; Katamari {old}'
                off += 1
                report.append(f'unhooked {fn}:{k + 1} {name}')
        if not a.dry_run:
            open(path, 'w', encoding='utf-8', errors='surrogateescape', newline='').write(nl.join(lines))
    print(f'{placed} hooks placed, {off} unhooked')
    print('\n'.join(report))
    missing = [n for n in list(API) + list(ADAPTERS) if n not in used.values()]
    print('named but no line matched:', missing)


if __name__ == '__main__':
    main()
