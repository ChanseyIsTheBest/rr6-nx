#!/usr/bin/env python3
"""rr6-nx (2026-11-05): one test run on the console, unattended, through tools/switch_remote.py's sys-botbase and ftp.

    python tools/console_run.py NAME [--toml FILE] [--nro FILE] [--put LOCAL=REMOTE ...] [--no-launch] [--no-kill]
                                [--script "T:ACTION,T:ACTION,..."] [--until SECONDS]

Closes the running game, uploads the toml as renut.toml (and the NRO if given), presses A on the home menu to start the
game (it must be the selected icon), then at T seconds after that press runs each ACTION: `shot`, `click A`, `press ZR`,
`release ZR`, `stick L x y`. At --until it closes the game, fetches the newest log and writes everything to
out/console_runs/NAME, with shots named by their second and a sheet of them. Every card path goes through
switch_remote.sd_path, so the user's rule about the SD card holds here too.
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import switch_remote as sr  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')


def put(host, local, remote):
    f = sr.ftp_open(host)
    try:
        began = time.time()
        with open(local, 'rb') as src:
            f.storbinary('STOR ' + sr.sd_path(remote), src, blocksize=1 << 16)
        print('put %s -> %s (%.1f MB in %.0f s)' % (os.path.basename(local), remote, os.path.getsize(local) / 1048576.0,
                                                   time.time() - began))
    finally:
        f.quit()


def fetch_logs(host, out):
    f = sr.ftp_open(host)
    try:
        f.cwd(sr.sd_path('logs'))
        names = [n.split('/')[-1] for n in f.nlst()]
        logs = sorted(n for n in names if n.startswith('renut_') and n.endswith('.log'))
        for n in logs[-1:]:
            with open(os.path.join(out, n), 'wb') as o:
                f.retrbinary('RETR ' + n, o.write)
            print('log', n, os.path.getsize(os.path.join(out, n)), 'bytes')
        f.cwd(sr.sd_path())
        names = [n.split('/')[-1] for n in f.nlst()]
        if 'deko3d.log' in names:
            with open(os.path.join(out, 'deko3d.log'), 'wb') as o:
                f.retrbinary('RETR deko3d.log', o.write)
    finally:
        f.quit()
    return logs[-1:] if logs else []


def running(bot):
    # killGame answers "ok", which can arrive ahead of this answer: the last word of the reply is the one asked for.
    words = bot.ask('getTitleID', timeout=8.0).split()
    t = words[-1] if words else ''
    return all(c in '0123456789abcdefABCDEF' for c in t) and bool(t) and int(t, 16) != 0


def sheet(out, shots):
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return
    if not shots:
        return
    cols = min(4, len(shots))
    rows = (len(shots) + cols - 1) // cols
    w, h = 480, 270
    img = Image.new('RGB', (cols * w, rows * h))
    for i, (t, path) in enumerate(shots):
        tile = Image.open(path).convert('RGB').resize((w, h))
        ImageDraw.Draw(tile).text((4, 4), '%d s' % t, fill=(255, 255, 0))
        img.paste(tile, ((i % cols) * w, (i // cols) * h))
    img.save(os.path.join(out, 'sheet.jpg'), quality=85)


def main():
    a = argparse.ArgumentParser()
    a.add_argument('name')
    a.add_argument('--toml')
    a.add_argument('--nro')
    a.add_argument('--put', action='append', default=[])
    a.add_argument('--script', default='')
    a.add_argument('--until', type=float, default=120)
    a.add_argument('--no-launch', action='store_true')
    a.add_argument('--no-kill', action='store_true')
    args = a.parse_args()
    host = sr.host_of(sys.argv)
    out = os.path.join(ROOT, 'out', 'console_runs', args.name)
    os.makedirs(out, exist_ok=True)

    bot = sr.Bot(host, timeout=15)
    if not args.no_launch and running(bot):
        bot.ask('killGame', timeout=15.0)
        for _ in range(20):
            time.sleep(0.5)
            if not running(bot):
                break
        time.sleep(3)
    if args.toml:
        put(host, args.toml, 'renut.toml')
    if args.nro:
        put(host, args.nro, 'rr6-nx.nro')
    for spec in args.put:
        local, remote = spec.split('=', 1)
        put(host, local, remote)

    steps = []
    for item in filter(None, (s.strip() for s in args.script.split(','))):
        t, action = item.split(':', 1)
        steps.append((float(t), action.strip()))
    steps.sort(key=lambda s: s[0])

    if not args.no_launch:
        bot.send('click A')
    start = time.time()
    print('started', time.strftime('%H:%M:%S'))
    shots = []
    dead_at = None
    for t, action in steps:
        if t > args.until:
            break
        wait = start + t - time.time()
        if wait > 0:
            time.sleep(wait)
        try:
            if action == 'shot':
                path = os.path.join(out, 'shot_%04d.jpg' % t)
                bot.shot(path)
                shots.append((t, path))
            elif action.startswith('stick '):
                _, which, x, y = action.split()
                bot.send('setStick %s %d %d' % ('LEFT' if which.upper().startswith('L') else 'RIGHT',
                                                int(float(x) * 32767), int(float(y) * 32767)))
            else:
                bot.send(action)
        except (OSError, ValueError) as e:
            print('step', t, action, 'failed:', e)
    wait = start + args.until - time.time()
    if wait > 0:
        time.sleep(wait)
    alive = False
    try:
        alive = running(bot)
    except OSError as e:
        print('botbase:', e)
    print('game running at the end:', alive, '; finished', time.strftime('%H:%M:%S'))
    if alive and not args.no_kill:
        bot.ask('killGame', timeout=15.0)
        for _ in range(20):
            time.sleep(0.5)
            if not running(bot):
                break
        time.sleep(2)
    bot.close()
    sheet(out, shots)
    if not args.no_kill:
        fetch_logs(host, out)
    print('out', os.path.normpath(out))


if __name__ == '__main__':
    main()
