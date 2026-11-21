#!/usr/bin/env python3
"""rr6-nx (2026-11-21, the user: "rencoding audio as opus ... copy what culdcept saga does"): makes NAME.opcm from a game
file NAME whose music is 16-bit PCM (sdk/include/rex/filesystem/opus_pcm.h has the format): pack_bgm.bin (20 RIFF WAVE
tracks back to back) or a DLC music pack (an Xbox 360 STFS package holding one WAV). Every byte outside the samples is
kept as it is; the samples become Opus (ffmpeg's libopus, 20 ms packets, 128 kbit/s stereo by default) made from the PCM
resampled to 48 kHz by the same windowed-sinc filter the port's reader resamples back with.

  python -I tools/opus_pcm_pack.py IN OUT.opcm [--bitrate 128000] [--ffmpeg C:/ffmpeg/ffmpeg.exe]
      [--header-out PACKAGE]   for a package: also write PACKAGE, the package cut to its header (what the port reads
                               beside PACKAGE.opcm)
  python -I tools/opus_pcm_pack.py --check IN OUT.opcm     decode OUT.opcm as the port does (ffmpeg's libopus, the
                               port's filter) and compare it with IN: every stored byte, and the PCM's SNR per stream
  python -I tools/opus_pcm_pack.py --compare IN DUMP [--opcm IN.opcm]   DUMP: a file the port wrote with opus_pcm_dump (the bytes the
                               game read, at their offsets; zeros where it read nothing): the SNR of what it read

The resampler (the reader's, sdk/src/filesystem/opus_pcm.cpp): a Kaiser-windowed sinc, beta 8, 64 taps a phase, the
cutoff at 97 % of the lower rate's Nyquist, each phase normalised to unity gain; output sample n of rate B from rate A
sits at input position n * A / B, the taps on input samples floor(n * A / B) - 31 .. + 32.
"""
import argparse
import math
import os
import struct
import subprocess
import sys
import tempfile

import numpy as np

MAGIC = b'RXOPCM01'
OPUS_RATE = 48000
FRAME = 960
HALF = 32
TAPS = 2 * HALF
BETA = 8.0
BLOCK = 4096


# ---- the filter -------------------------------------------------------------------------------------------------

def filter_bank(src_rate, dst_rate):
    """(L, M, h): output n sits at input n * M / L; h[phase] the TAPS coefficients (phase = n * M mod L)."""
    g = math.gcd(src_rate, dst_rate)
    L, M = dst_rate // g, src_rate // g
    fc = 0.5 * min(src_rate, dst_rate) / src_rate * 0.97  # cycles an input sample
    frac = np.arange(L, dtype=np.float64)[:, None] / L
    t = np.arange(TAPS, dtype=np.float64)[None, :] - HALF + 1 - frac
    x = 2.0 * fc * t
    sinc = np.where(np.abs(x) < 1e-12, 1.0, np.sin(np.pi * x) / np.where(x == 0, 1.0, np.pi * x))
    r = t / HALF
    w = np.where(np.abs(r) >= 1.0, 0.0, np.i0(BETA * np.sqrt(np.clip(1.0 - r * r, 0.0, None))) / np.i0(BETA))
    h = 2.0 * fc * sinc * w
    h /= h.sum(axis=1, keepdims=True)
    return L, M, h.astype(np.float32)


def resample(x, src_rate, dst_rate, out_len=None):
    """x: (frames, channels) float32 at src_rate -> (out_len, channels) at dst_rate, as the port's filter."""
    if src_rate == dst_rate:
        return x.copy() if out_len is None else x[:out_len].copy()
    L, M, h = filter_bank(src_rate, dst_rate)
    n_in, ch = x.shape
    if out_len is None:
        out_len = (n_in * L + M - 1) // M
    pad = np.zeros((HALF + 1, ch), np.float32)
    xp = np.concatenate([pad, x, pad, pad])  # xp[k + HALF + 1] = x[k]
    out = np.empty((out_len, ch), np.float32)
    step = 32768
    taps = np.arange(TAPS)
    for s in range(0, out_len, step):
        n = np.arange(s, min(out_len, s + step), dtype=np.int64)
        q = n * M
        i = q // L
        ph = q % L
        idx = (i - HALF + 1)[:, None] + taps[None, :] + HALF + 1
        idx = np.clip(idx, 0, len(xp) - 1)
        hh = h[ph]
        for c in range(ch):
            out[s:s + len(n), c] = np.einsum('ij,ij->i', hh, xp[idx, c])
    return out


# ---- finding the PCM ---------------------------------------------------------------------------------------------

class Region:
    """One WAV's samples: channels, rate, big-endian, and the byte ranges of the file they lie in, in order."""

    def __init__(self, name, channels, rate, big, ranges):
        self.name, self.channels, self.rate, self.big, self.ranges = name, channels, rate, big, ranges


def wav_data(read, length, name):
    """(fmt, data offset, data length) of a RIFF WAVE read through read(offset, n), or None."""
    h = read(0, 12)
    if h[:4] != b'RIFF' or h[8:12] != b'WAVE':
        return None
    riff_end = min(length, 8 + struct.unpack('<I', h[4:8])[0])
    pos, fmt = 12, None
    while pos + 8 <= riff_end:
        c = read(pos, 8)
        cid, cl = c[:4], struct.unpack('<I', c[4:8])[0]
        if cid == b'fmt ':
            fmt = struct.unpack('<HHIIHH', read(pos + 8, 16))
        elif cid == b'data':
            return fmt, pos + 8, min(cl, length - pos - 8)
        pos += 8 + cl + (cl & 1)
    return None


def pcm_ok(fmt):
    return fmt is not None and fmt[0] == 1 and fmt[5] == 16 and fmt[1] in (1, 2)


def guess_big(sample_bytes):
    """Whether 16-bit PCM bytes read smoother big-endian (music is smooth from sample to sample)."""
    a = np.frombuffer(sample_bytes[:len(sample_bytes) & ~3], '<i2').astype(np.int64)
    b = np.frombuffer(sample_bytes[:len(sample_bytes) & ~3], '>i2').astype(np.int64)
    def rough(v):
        return np.abs(np.diff(v[::2])).sum() / max(1, np.abs(v).sum())
    return rough(b) < rough(a)


def regions_riff(data):
    """pack_bgm.bin: RIFF WAVE files back to back (each at a 2 KB boundary)."""
    out, pos, k = [], 0, 0
    while pos + 12 <= len(data) and data[pos:pos + 4] == b'RIFF':
        size = 8 + struct.unpack('<I', data[pos + 4:pos + 8])[0]
        w = wav_data(lambda o, n: data[pos + o:pos + o + n], len(data) - pos, k)
        if w and pcm_ok(w[0]):
            fmt, off, length = w
            body = data[pos + off:pos + off + min(length, 1 << 22)]
            out.append(Region(f'wav {k} at {pos}', fmt[1], fmt[2], guess_big(body), [(pos + off, length)]))
        nxt = pos + size
        found = data.find(b'RIFF', nxt, nxt + (1 << 16)) if nxt < len(data) else -1
        if found < 0:
            break
        pos = found
        k += 1
    return out


def stfs_files(data):
    """An STFS package's files: (name, [(physical offset, length) of each 4 KB block run, in order], length)."""
    header_size = struct.unpack('>I', data[0x340:0x344])[0]
    vd = data[0x379:0x379 + 0x24]
    read_only = vd[2] & 1
    bpht = 1 if read_only else 2
    ft_count = struct.unpack('<H', vd[3:5])[0]
    ft_start = int.from_bytes(vd[5:8], 'little')
    base = (header_size + BLOCK - 1) // BLOCK * BLOCK

    def b2o(bi):
        b, n = bi, 170
        for _ in range(3):
            b += ((bi + n) // n) * bpht
            if bi < n:
                break
            n *= 170
        return base + (b << 12)

    def next_block(bi):
        raise SystemExit('a package file whose blocks are not contiguous: not handled (none of the DLC is)')

    files = []
    blk = ft_start
    for _ in range(ft_count):
        o = b2o(blk)
        for k in range(BLOCK // 0x40):
            e = data[o + k * 0x40:o + (k + 1) * 0x40]
            if e[0] == 0:
                break
            fl = e[0x28]
            if fl & 0x80:
                continue  # a folder
            name = e[:fl & 0x3F].decode('latin-1')
            nblocks = int.from_bytes(e[0x29:0x2C], 'little')
            start = int.from_bytes(e[0x2F:0x32], 'little')
            length = struct.unpack('>I', e[0x34:0x38])[0]
            blocks = []
            b = start
            for i in range(nblocks):
                blocks.append(b)
                b = b + 1 if fl & 0x40 else next_block(b)
            runs = []
            left = length
            for b in blocks:
                n = min(BLOCK, left)
                off = b2o(b)
                if runs and runs[-1][0] + runs[-1][1] == off:
                    runs[-1] = (runs[-1][0], runs[-1][1] + n)
                else:
                    runs.append((off, n))
                left -= n
                if left <= 0:
                    break
            files.append((name, runs, length))
        blk = blk + 1
    return files, base


def logical(runs):
    """read(offset, n) over a file's runs."""
    def read_fn(data):
        def read(o, n):
            out, pos = bytearray(), 0
            for off, ln in runs:
                if o < pos + ln and o + n > pos:
                    a = max(o, pos) - pos
                    b = min(o + n, pos + ln) - pos
                    out += data[off + a:off + b]
                pos += ln
            return bytes(out)
        return read
    return read_fn


def sub_runs(runs, start, length):
    """The physical runs of a file's logical bytes [start, start + length)."""
    out, pos = [], 0
    for off, ln in runs:
        a, b = max(start, pos), min(start + length, pos + ln)
        if a < b:
            out.append((off + a - pos, b - a))
        pos += ln
    return out


def regions_stfs(data):
    files, _ = stfs_files(data)
    out = []
    for name, runs, length in files:
        read = logical(runs)(data)
        w = wav_data(read, length, name)
        if not (w and pcm_ok(w[0])):
            continue
        fmt, off, dlen = w
        body = read(off, min(dlen, 1 << 22))
        out.append(Region(name, fmt[1], fmt[2], guess_big(body), sub_runs(runs, off, dlen)))
    return out


def find_regions(data):
    if data[:4] == b'RIFF':
        return regions_riff(data), None
    if data[:4] in (b'LIVE', b'PIRS', b'CON '):
        header_size = struct.unpack('>I', data[0x340:0x344])[0]
        return regions_stfs(data), (header_size + BLOCK - 1) // BLOCK * BLOCK
    return [], None


def pcm_of(data, region):
    raw = b''.join(data[o:o + n] for o, n in region.ranges)
    frame = region.channels * 2
    usable = len(raw) - len(raw) % frame
    a = np.frombuffer(raw[:usable], '>i2' if region.big else '<i2').reshape(-1, region.channels)
    return a, usable


# ---- Opus ------------------------------------------------------------------------------------------------------

def ogg_packets(blob):
    """The packets of an Ogg stream (one logical stream)."""
    packets, cur, pos = [], b'', 0
    while pos + 27 <= len(blob):
        if blob[pos:pos + 4] != b'OggS':
            raise SystemExit('not an Ogg page')
        nseg = blob[pos + 26]
        lace = blob[pos + 27:pos + 27 + nseg]
        p = pos + 27 + nseg
        for l in lace:
            cur += blob[p:p + l]
            p += l
            if l < 255:
                packets.append(cur)
                cur = b''
        pos = p
    return packets


def encode_opus(ffmpeg, pcm48, channels, bitrate):
    """float32 (frames, channels) at 48 kHz -> (pre-skip, [packets])."""
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, 'o.ogg')
        cmd = [ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', '-f', 'f32le', '-ar', str(OPUS_RATE), '-ac',
               str(channels), '-i', '-', '-c:a', 'libopus', '-b:a', str(bitrate), '-vbr', 'on', '-frame_duration', '20',
               '-application', 'audio', '-f', 'ogg', out]
        p = subprocess.run(cmd, input=pcm48.astype('<f4').tobytes(), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           timeout=3600)
        if p.returncode:
            raise SystemExit('ffmpeg failed: ' + p.stderr.decode(errors='replace'))
        packets = ogg_packets(open(out, 'rb').read())
    head = packets[0]
    if head[:8] != b'OpusHead':
        raise SystemExit('no OpusHead')
    pre_skip = struct.unpack('<H', head[10:12])[0]
    audio = packets[2:]
    for k, pk in enumerate(audio):
        if frame_samples(pk) != FRAME:
            raise SystemExit(f'packet {k} is not 20 ms ({frame_samples(pk)} samples)')
    return pre_skip, audio


def frame_samples(packet):
    toc = packet[0]
    config = toc >> 3
    if config < 12:
        per = [480, 960, 1920, 2880][config & 3]
    elif config < 16:
        per = [480, 960][config & 1]
    else:
        per = [120, 240, 480, 960][config & 3]
    code = toc & 3
    count = 1 if code == 0 else 2 if code in (1, 2) else packet[1] & 0x3F
    return per * count


def decode_opus(ffmpeg, pre_skip, packets, channels):
    """The decoded 48 kHz stream as the port's reader sees it: (pre-skip + frames, channels), pre-skip NOT removed."""
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, 'd.ogg')
        write_ogg(src, packets, channels, 0)  # pre-skip 0: ffmpeg gives every decoded sample
        p = subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-c:a', 'libopus', '-i', src, '-f', 'f32le', '-ac', str(channels),
                            '-ar', str(OPUS_RATE), '-'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=3600)
        if p.returncode:
            raise SystemExit('ffmpeg decode failed: ' + p.stderr.decode(errors='replace'))
    return np.frombuffer(p.stdout, '<f4').reshape(-1, channels)


def crc32_ogg(data):
    table = crc32_ogg.table
    if table is None:
        table = []
        for i in range(256):
            r = i << 24
            for _ in range(8):
                r = ((r << 1) ^ 0x04C11DB7) if r & 0x80000000 else (r << 1)
            table.append(r & 0xFFFFFFFF)
        crc32_ogg.table = table
    c = 0
    for b in data:
        c = ((c << 8) ^ table[((c >> 24) ^ b) & 0xFF]) & 0xFFFFFFFF
    return c


crc32_ogg.table = None


def write_ogg(path, packets, channels, pre_skip):
    head = b'OpusHead' + bytes([1, channels]) + struct.pack('<HIhB', pre_skip, OPUS_RATE, 0, 0)
    tags = b'OpusTags' + struct.pack('<I', 4) + b'rr6x' + struct.pack('<I', 0)
    pages = []
    def page(payloads, granule, seq, flags):
        lace, body = [], b''
        for pk in payloads:
            n = len(pk)
            while n >= 255:
                lace.append(255)
                n -= 255
            lace.append(n)
            body += pk
        hdr = b'OggS' + bytes([0, flags]) + struct.pack('<qII', granule, 0x52523658, seq) + b'\0\0\0\0' + \
            bytes([len(lace)]) + bytes(lace)
        crc = crc32_ogg(hdr + body)
        hdr = hdr[:22] + struct.pack('<I', crc) + hdr[26:]
        pages.append(hdr + body)
    page([head], 0, 0, 2)
    page([tags], 0, 1, 0)
    seq, gran, k = 2, 0, 0
    while k < len(packets):
        chunk = packets[k:k + 50]
        gran += FRAME * len(chunk)
        k += len(chunk)
        page(chunk, gran, seq, 4 if k >= len(packets) else 0)
        seq += 1
    open(path, 'wb').write(b''.join(pages))


# ---- the .opcm file -----------------------------------------------------------------------------------------------

def build(data, regions, streams_opus):
    """The .opcm bytes. streams_opus[i] = (pre_skip, packets, frames, usable_bytes)."""
    size = len(data)
    # The PCM byte ranges of the file, each with its stream and the offset in the stream's PCM.
    pcm = []
    for si, (region, (_, _, _, usable)) in enumerate(zip(regions, streams_opus)):
        pos = 0
        for off, n in region.ranges:
            take = min(n, usable - pos)
            if take > 0:
                pcm.append((off, take, si, pos))
            pos += n
    pcm.sort()
    segments, stored = [], bytearray()
    at = 0
    for off, n, si, src in pcm:
        if off > at:
            segments.append((at, off - at, 0, 0, len(stored)))
            stored += data[at:off]
        segments.append((off, n, 1, si, src))
        at = off + n
    if at < size:
        segments.append((at, size - at, 0, 0, len(stored)))
        stored += data[at:size]
    # Merge neighbouring stored segments (and PCM ones that continue the same stream).
    merged = []
    for s in segments:
        if merged:
            p = merged[-1]
            if p[2] == s[2] == 0 and p[4] + p[1] == s[4]:
                merged[-1] = (p[0], p[1] + s[1], 0, 0, p[4])
                continue
            if p[2] == s[2] == 1 and p[3] == s[3] and p[4] + p[1] == s[4]:
                merged[-1] = (p[0], p[1] + s[1], 1, p[3], p[4])
                continue
        merged.append(s)
    segments = merged
    n_streams = len(regions)
    seg_off = 64
    str_off = seg_off + 32 * len(segments)
    stored_off = str_off + 48 * n_streams
    pos = stored_off + len(stored)
    stream_rows, tail = [], bytearray()
    for region, (pre_skip, packets, frames, _) in zip(regions, streams_opus):
        sizes_off = pos + len(tail)
        tail += b''.join(struct.pack('<H', len(p)) for p in packets)
        pk_off = pos + len(tail)
        tail += b''.join(packets)
        stream_rows.append(struct.pack('<HHIIIQIIQQ', region.channels, 16, region.rate, 1 if region.big else 0,
                                       pre_skip, frames, len(packets), FRAME, sizes_off, pk_off))
    out = bytearray()
    out += MAGIC + struct.pack('<IIQIIQQQQ', 1, n_streams, size, len(segments), 0, seg_off, str_off, stored_off,
                               len(stored))
    for s in segments:
        out += struct.pack('<QQIIQ', s[0], s[1], s[2], s[3], s[4])
    for r in stream_rows:
        out += r
    out += stored
    out += tail
    return bytes(out), segments


def parse_opcm(blob):
    if blob[:8] != MAGIC:
        raise SystemExit('not an .opcm file')
    ver, n_streams, size, n_seg, _, seg_off, str_off, stored_off, stored_len = struct.unpack('<IIQIIQQQQ', blob[8:64])
    segs = [struct.unpack('<QQIIQ', blob[seg_off + 32 * i:seg_off + 32 * i + 32]) for i in range(n_seg)]
    streams = []
    for i in range(n_streams):
        ch, bits, rate, flags, pre, frames, npk, fsz, sizes_off, pk_off = struct.unpack(
            '<HHIIIQIIQQ', blob[str_off + 48 * i:str_off + 48 * i + 48])
        sizes = struct.unpack(f'<{npk}H', blob[sizes_off:sizes_off + 2 * npk])
        packets, p = [], pk_off
        for s in sizes:
            packets.append(blob[p:p + s])
            p += s
        streams.append(dict(channels=ch, rate=rate, big=bool(flags & 1), pre_skip=pre, frames=frames, packets=packets))
    return dict(size=size, segments=segs, streams=streams, stored=blob[stored_off:stored_off + stored_len])


def port_pcm(ffmpeg, st):
    """The stream's PCM as the port's reader makes it (decoded in order), int16 (frames, channels)."""
    dec = decode_opus(ffmpeg, 0, st['packets'], st['channels'])[st['pre_skip']:]
    y = resample(dec, OPUS_RATE, st['rate'], st['frames'])
    return np.clip(np.rint(y * 32768.0), -32768, 32767).astype(np.int16)


def snr_db(ref, got):
    ref = ref.astype(np.float64)
    err = ref - got.astype(np.float64)
    e = (err * err).sum()
    return 99.0 if e == 0 else 10 * math.log10(max((ref * ref).sum(), 1e-9) / e)


# ---- main ---------------------------------------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('dst')
    ap.add_argument('--bitrate', type=int, default=128000, help='a stereo stream; mono gets half')
    ap.add_argument('--ffmpeg', default='C:/ffmpeg/ffmpeg.exe')
    ap.add_argument('--header-out', help='for a package: write it cut to its header here')
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--compare', action='store_true')
    ap.add_argument('--opcm', help='--compare: the .opcm the port read, for the comparison with its model')
    a = ap.parse_args()
    data = open(a.src, 'rb').read()
    regions, header_cut = find_regions(data)
    if a.check:
        return check(a, data, regions)
    if a.compare:
        return compare(a, data, regions)
    if not regions:
        raise SystemExit(f'{a.src}: no 16-bit PCM WAV found')
    streams = []
    for k, r in enumerate(regions):
        pcm, usable = pcm_of(data, r)
        x = pcm.astype(np.float32) / 32768.0
        y = resample(x, r.rate, OPUS_RATE)
        rate = a.bitrate if r.channels == 2 else a.bitrate // 2
        pre_skip, packets = encode_opus(a.ffmpeg, y, r.channels, rate)
        need = pre_skip + len(y)
        if len(packets) * FRAME < need:
            raise SystemExit(f'stream {k}: {len(packets)} packets cover {len(packets) * FRAME} of {need} samples')
        streams.append((pre_skip, packets, len(pcm), usable))
        print(f'  {r.name}: {r.channels} ch {r.rate} Hz{" BE" if r.big else ""}, {len(pcm) / r.rate:.1f} s, '
              f'{usable / 1e6:.1f} MB PCM in {len(r.ranges)} range(s) -> {sum(map(len, packets)) / 1e6:.2f} MB Opus',
              flush=True)
    blob, segments = build(data, regions, streams)
    tmp = a.dst + '.part'
    open(tmp, 'wb').write(blob)
    os.replace(tmp, a.dst)
    print(f'{a.dst}: {len(data) / 1e6:.1f} MB -> {len(blob) / 1e6:.1f} MB ({len(regions)} streams, {len(segments)} '
          f'segments)')
    if a.header_out:
        if header_cut is None:
            raise SystemExit('--header-out: not a package')
        open(a.header_out, 'wb').write(data[:header_cut])
        print(f'{a.header_out}: the package cut to its header, {header_cut} bytes')


def check(a, data, regions):
    o = parse_opcm(open(a.dst, 'rb').read())
    if o['size'] != len(data):
        raise SystemExit(f'size {o["size"]} != {len(data)}')
    bad = 0
    for off, n, kind, si, src in o['segments']:
        if kind == 0 and o['stored'][src:src + n] != data[off:off + n]:
            bad += 1
    print(f'stored segments: {sum(1 for s in o["segments"] if s[2] == 0)}, differing {bad}')
    worst = 99.0
    for k, (r, st) in enumerate(zip(regions, o['streams'])):
        ref, _ = pcm_of(data, r)
        got = port_pcm(a.ffmpeg, st)
        n = min(len(ref), len(got))
        s = snr_db(ref[:n], got[:n])
        # Offset check: the SNR one sample early and late (the right alignment is the best).
        e = snr_db(ref[1:n], got[:n - 1])
        l = snr_db(ref[:n - 1], got[1:n])
        worst = min(worst, s)
        print(f'  stream {k} ({r.name}): {n} frames, SNR {s:.1f} dB (shifted by a sample: {e:.1f} / {l:.1f} dB)')
    print(f'worst SNR {worst:.1f} dB')


def compare(a, data, regions):
    dump = open(a.dst, 'rb').read()
    model = parse_opcm(open(a.opcm, 'rb').read()) if a.opcm else None
    if model is not None:
        bad = sum(1 for off, n, kind, si, src in model['segments']
                  if kind == 0 and dump[off:off + n] != model['stored'][src:src + n] and any(dump[off:off + n]))
        print(f'stored segments the game read that differ from the .opcm: {bad}')
    for k, r in enumerate(regions):
        raw = b''.join(data[o:o + n] for o, n in r.ranges)
        got = b''.join(dump[o:o + n] for o, n in r.ranges)
        got = got + b'\0' * (len(raw) - len(got))
        frame = r.channels * 2
        usable = len(raw) - len(raw) % frame
        ref = np.frombuffer(raw[:usable], '>i2' if r.big else '<i2').reshape(-1, r.channels)
        g = np.frombuffer(got[:usable], '>i2' if r.big else '<i2').reshape(-1, r.channels)
        # The frames the game read: 4 KB stretches of the dump that are not all zero.
        read_mask = np.zeros(len(ref), bool)
        gb = np.frombuffer(got[:usable], np.uint8)
        for s in range(0, len(gb), BLOCK):
            if gb[s:s + BLOCK].any():
                read_mask[s // frame:(s + BLOCK) // frame] = True
        if not read_mask.any():
            continue
        line = (f'  stream {k} ({r.name}): {read_mask.sum() / r.rate:.1f} s read, SNR against the original '
                f'{snr_db(ref[read_mask], g[read_mask]):.1f} dB')
        if model is not None:
            # Against this tool's model of the port's reader (ffmpeg's libopus decoding in order, the same filter): the
            # port's own arithmetic (its libopus, its float order; reads after a jump start 320 ms early) is all that
            # differs.
            m = port_pcm(a.ffmpeg, model['streams'][k])
            n = min(len(m), len(g))
            mask = read_mask[:n]
            line += f', against the model {snr_db(m[:n][mask], g[:n][mask]):.1f} dB'
            diff = np.abs(m[:n][mask].astype(np.int32) - g[:n][mask].astype(np.int32))
            line += f' (max sample difference {diff.max()})'
        print(line, flush=True)


if __name__ == '__main__':
    main()
