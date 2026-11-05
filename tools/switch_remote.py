#!/usr/bin/env python3
"""rr6-nx (2026-11-04): the console over the network, through two sysmodules the user runs under Atmosphere:
sys-botbase (masagrator's fork; TCP 6000: controller presses, screenshots, memory) and ftpd (TCP 5000: the SD card).
Outbound connections only; nothing on this PC listens.
The user's rule (2026-11-05): on the SD card only /switch/rr6-nx may be touched. Every ftp path is checked against it and
refused otherwise, relative paths are taken from it, and raw takes only commands that cannot reach the card or write memory.
ftp logs in anonymously, and sys-ftpd-light has that off by default: it needs anonymous:=1 in the card's
/config/sys-ftpd/config.ini. Never run against a console yet.

    python tools/switch_remote.py [--host IP] CMD ...

  shot [OUT.jpg]             the screen as the console shows it (pixelPeek)
  click A [B ...]            taps, one after the other (A B X Y L R ZL ZR PLUS MINUS HOME CAPTURE
                             DUP DDOWN DLEFT DRIGHT LSTICK RSTICK)
  hold BTN [ms]              press and release after ms (default 400)
  stick L|R X Y [ms]         a stick at X, Y in -1..1 (y up), released after ms (default 300)
  title | version | heap     getTitleID, getVersion, getHeapBase
  peek ADDR SIZE             SIZE bytes at the absolute address, hex
  ls [PATH]                  ftp listing (default /switch/rr6-nx)
  get REMOTE [LOCAL]         ftp download (a folder: every file in it, one level)
  put LOCAL REMOTE           ftp upload
  rm REMOTE                  ftp delete (a file)
  raw "CMD ..."              a sys-botbase command as it is, the reply printed

The host comes from --host, else the RR6_SWITCH_HOST environment variable, else out/switch_host.txt's first line.
"""
import os
import posixpath
import socket
import sys
import time
from ftplib import FTP

BOT_PORT, FTP_PORT = 6000, 5000
SD_ROOT = '/switch/rr6-nx'
RAW_ALLOWED = ('click', 'press', 'release', 'setStick', 'pixelPeek', 'getTitleID', 'getVersion', 'getHeapBase', 'peekAbsolute',
               'configure')


def sd_path(path=''):
    """The path on the card, refused unless it is inside SD_ROOT."""
    full = posixpath.normpath(posixpath.join(SD_ROOT, path.replace('\\', '/')))
    if full != SD_ROOT and not full.startswith(SD_ROOT + '/'):
        sys.exit('refused: %s is outside %s' % (path, SD_ROOT))
    return full


def host_of(args):
    if '--host' in args:
        i = args.index('--host')
        host = args[i + 1]
        del args[i:i + 2]
        return host
    if os.environ.get('RR6_SWITCH_HOST'):
        return os.environ['RR6_SWITCH_HOST']
    here = os.path.dirname(os.path.abspath(__file__))
    p = os.path.join(here, '..', 'out', 'switch_host.txt')
    if os.path.exists(p):
        return open(p, encoding='utf-8').readline().strip()
    sys.exit('no host: pass --host IP, set RR6_SWITCH_HOST, or write the IP into out/switch_host.txt')


class Bot:
    """One sys-botbase connection. Commands are lines ending in \\r\\n; replies (where there is one) end in \\n."""

    def __init__(self, host, timeout=10.0):
        self.s = socket.create_connection((host, BOT_PORT), timeout=timeout)
        self.send('configure echoCommands 0')

    def send(self, cmd):
        self.s.sendall((cmd + '\r\n').encode('ascii'))

    def ask(self, cmd, timeout=15.0):
        self.send(cmd)
        self.s.settimeout(timeout)
        data = b''
        while not data.endswith(b'\n'):
            chunk = self.s.recv(1 << 16)
            if not chunk:
                break
            data += chunk
        return data.decode('ascii', 'replace').strip()

    def shot(self, out):
        hexjpg = self.ask('pixelPeek', timeout=30.0)
        raw = bytes.fromhex(hexjpg)
        open(out, 'wb').write(raw)
        return len(raw)

    def close(self):
        try:
            self.s.close()
        except OSError:
            pass


def ftp_open(host):
    f = FTP()
    f.connect(host, FTP_PORT, timeout=20)
    f.login()  # anonymous
    return f


def main():
    args = sys.argv[1:]
    host = host_of(args)
    if not args:
        sys.exit(__doc__)
    cmd, rest = args[0], args[1:]
    if cmd in ('shot', 'click', 'hold', 'stick', 'title', 'version', 'heap', 'peek', 'raw'):
        b = Bot(host)
        try:
            if cmd == 'shot':
                out = rest[0] if rest else time.strftime('shot_%H%M%S.jpg')
                print(out, b.shot(out), 'bytes')
            elif cmd == 'click':
                for btn in rest:
                    b.send('click ' + btn.upper())
                    time.sleep(0.25)
                print('clicked', ' '.join(rest))
            elif cmd == 'hold':
                ms = int(rest[1]) if len(rest) > 1 else 400
                b.send('press ' + rest[0].upper())
                time.sleep(ms / 1000.0)
                b.send('release ' + rest[0].upper())
                print('held', rest[0], ms, 'ms')
            elif cmd == 'stick':
                which = 'LEFT' if rest[0].upper().startswith('L') else 'RIGHT'
                x, y = float(rest[1]), float(rest[2])
                ms = int(rest[3]) if len(rest) > 3 else 300
                b.send('setStick %s %d %d' % (which, int(x * 32767), int(y * 32767)))
                time.sleep(ms / 1000.0)
                b.send('setStick %s 0 0' % which)
                print('stick', which, x, y, ms, 'ms')
            elif cmd == 'title':
                print(b.ask('getTitleID'))
            elif cmd == 'version':
                print(b.ask('getVersion'))
            elif cmd == 'heap':
                print(b.ask('getHeapBase'))
            elif cmd == 'peek':
                print(b.ask('peekAbsolute %s %s' % (rest[0], rest[1])))
            elif cmd == 'raw':
                if not rest or rest[0].split(' ')[0] not in RAW_ALLOWED:
                    sys.exit('refused: raw takes only ' + ', '.join(RAW_ALLOWED))
                print(b.ask(' '.join(rest)))
        finally:
            b.close()
    elif cmd in ('ls', 'get', 'put', 'rm'):
        # Refused before any connection is made: the card path is rest[1] for put, rest[0] for the others.
        sd_path(rest[1] if cmd == 'put' else (rest[0] if rest else ''))
        f = ftp_open(host)
        try:
            if cmd == 'ls':
                f.cwd(sd_path(rest[0] if rest else ''))
                f.retrlines('LIST')
            elif cmd == 'get':
                remote = sd_path(rest[0])
                local = rest[1] if len(rest) > 1 else os.path.basename(remote.rstrip('/')) or 'root'
                names = []
                try:
                    f.cwd(remote)
                    names = f.nlst()
                except Exception:
                    names = None
                if names is None:
                    with open(local, 'wb') as out:
                        f.retrbinary('RETR ' + remote, out.write)
                    print(local, os.path.getsize(local), 'bytes')
                else:
                    os.makedirs(local, exist_ok=True)
                    for n in names:
                        base = n.split('/')[-1]
                        try:
                            with open(os.path.join(local, base), 'wb') as out:
                                f.retrbinary('RETR ' + base, out.write)
                            print(os.path.join(local, base))
                        except Exception as e:  # a folder inside: skipped, said
                            print('skipped', base, e)
            elif cmd == 'put':
                with open(rest[0], 'rb') as src:
                    f.storbinary('STOR ' + sd_path(rest[1]), src)
                print('put', rest[0], '->', sd_path(rest[1]))
            elif cmd == 'rm':
                f.delete(sd_path(rest[0]))
                print('deleted', sd_path(rest[0]))
        finally:
            f.quit()
    else:
        sys.exit('unknown command ' + cmd)


if __name__ == '__main__':
    main()
