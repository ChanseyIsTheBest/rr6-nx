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


RR6_TITLE = 0x050C558A3DE72000  # Ridge Racer 6's icon on the user's console


def title_of(bot):
    """The running title's id, 0 on the home menu."""
    # killGame answers "ok", which can arrive ahead of this answer: the last word of the reply is the one asked for.
    words = bot.ask('getTitleID', timeout=8.0).split()
    t = words[-1] if words else ''
    return int(t, 16) if t and all(c in '0123456789abcdefABCDEF' for c in t) else 0


def running(bot):
    return title_of(bot) != 0


def close_game(bot):
    """The normal way, HOME, X, A: killGame leaves the system's 'closed because an error occurred' dialog (the user, 2026-11-05),
    which then needs A. killGame only as the fallback."""
    bot.send('release ZR')
    time.sleep(0.3)
    bot.send('click HOME')
    time.sleep(2.5)
    bot.send('click X')
    time.sleep(1.5)
    bot.send('click A')
    for _ in range(24):
        time.sleep(0.5)
        if not running(bot):
            time.sleep(1.5)
            return 'closed'
    print('normal close failed: killGame, then A for its dialog')
    bot.ask('killGame', timeout=15.0)
    time.sleep(4)
    bot.send('click A')
    time.sleep(2)
    return 'killed'


def launch(bot):
    """One A on the icon a screenshot has just shown selected (read it first, tools/switch_remote.py shot): no cursor moves, no
    second press. On 2026-11-05 presses here opened the eShop and, with blind moves to the first icon, Sonic Unleashed, whose
    timeline of presses then ran in that game. So only Ridge Racer 6's own title id starts the timeline; the time it was seen
    running counts as the start."""
    bot.send('click A')
    began = time.time()
    for _ in range(20):
        time.sleep(0.5)
        t = title_of(bot)
        if t == RR6_TITLE:
            print('launched Ridge Racer 6')
            return began
        if t:
            print('WRONG TITLE %016X running: stopping, no more presses' % t)
            return None
    print('the game did not start: stopping, no more presses')
    return None


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
    a.add_argument('--script-file', help='the --script text in a file (long mash timelines)')
    a.add_argument('--pre', default='', help='comma-separated home menu presses before the launch, e.g. click DRIGHT')
    a.add_argument('--until', type=float, default=120)
    a.add_argument('--no-launch', action='store_true')
    a.add_argument('--no-kill', action='store_true')
    args = a.parse_args()
    host = sr.host_of(sys.argv)
    out = os.path.join(ROOT, 'out', 'console_runs', args.name)
    os.makedirs(out, exist_ok=True)

    bot = sr.Bot(host, timeout=15)
    running_now = title_of(bot)
    if not args.no_launch and running_now:
        # No close here: a launch needs a screenshot of the home menu read first, and another game is not this tool's to close.
        print('a game is running (%016X): stopping, nothing sent' % running_now)
        bot.close()
        sys.exit(1)
    if args.no_launch and running_now != RR6_TITLE:
        print('Ridge Racer 6 is not running (%016X): stopping, nothing sent' % running_now)
        bot.close()
        sys.exit(1)
    if args.toml:
        put(host, args.toml, 'renut.toml')
    if args.nro:
        put(host, args.nro, 'rr6-nx.nro')
    for spec in args.put:
        local, remote = spec.split('=', 1)
        put(host, local, remote)

    steps = []
    text = open(args.script_file, encoding='utf-8').read() if args.script_file else args.script
    for item in filter(None, (s.strip() for s in text.split(','))):
        t, action = item.split(':', 1)
        steps.append((float(t), action.strip()))
    steps.sort(key=lambda s: s[0])

    if not args.no_launch:
        for press in filter(None, (s.strip() for s in args.pre.split(','))):
            bot.send(press)
            time.sleep(0.8)
        start = launch(bot)
        if start is None:
            bot.close()
            sys.exit(1)
    else:
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
                # A fractional time (a burst of shots) keeps its fraction in the name.
                path = os.path.join(out, 'shot_%04d.jpg' % t if t == int(t) else 'shot_%07.2f.jpg' % t)
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
        alive = title_of(bot) == RR6_TITLE
    except OSError as e:
        print('botbase:', e)
    print('game running at the end:', alive, '; finished', time.strftime('%H:%M:%S'))
    if alive and not args.no_kill:
        print('closing:', close_game(bot))
    bot.close()
    sheet(out, shots)
    if not args.no_kill:
        try:
            fetch_logs(host, out)
        except (OSError, EOFError) as e:
            print('log fetch stopped:', e)
    print('out', os.path.normpath(out))


if __name__ == '__main__':
    main()
