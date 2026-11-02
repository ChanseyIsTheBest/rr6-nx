#!/usr/bin/env python3
"""pacman-nx: the emulator's test tomls in out/emu, made from the package's tomls (tools/make_pacman_tomls.py) so they keep
its settings. Each adds the scripted pad, captures every 15 s and what the test needs:
  emu_verify.toml   configs/renut_verify.toml: every verify key on, the pad to gameplay
  emu_attract.toml  the same with no pad input: the game's title and attract loop
  emu_profile.toml  renut_play.toml: no diagnostics, the pad to gameplay, the sampling profiler on
  emu_ab.toml       renut_ab.toml: the in-run A/B, the pad to gameplay
  emu_tour.toml     configs/renut_verify.toml: tools/tour_script.txt (menus, courses, the Visuals skins)
  emu_game.toml     configs/renut_verify.toml: a whole game and its results screens
  python tools/make_emu_tomls.py
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, 'dist', 'switch', 'pacman-nx')
OUT = os.path.join(ROOT, 'out', 'emu')
PAD = 'input_script = "45:START,55:A,65:A,75:A,85:A,95:A,105:A"\ninput_script_sticks = 115\n'
NO_PAD = 'input_script = ""\ninput_script_sticks = 0\n'
CAPTURES = 'nfsmw_captura_cada_s = 15\nnfsmw_captura_max = 60\n'
TOUR = 'input_script = "' + open(os.path.join(ROOT, 'tools', 'tour_script.txt'), encoding='utf-8').read().strip() + \
       '"\ninput_script_sticks = 227\n'
# A whole game: the 5-minute score attack from 115 s, the results screens after it. The tour's skin changes stay apart: its
# random stick would move the start menu's cursor.
GAME = 'input_script = "45:START,55:A,65:A,75:A,85:A,95:A,105:A,430:A,440:A,450:A,460:A,470:A"\ninput_script_sticks = 115\n'
TESTS = {
    'emu_verify.toml': (os.path.join('configs', 'renut_verify.toml'), PAD + CAPTURES),
    'emu_game.toml': (os.path.join('configs', 'renut_verify.toml'), GAME + CAPTURES),
    'emu_attract.toml': (os.path.join('configs', 'renut_verify.toml'), NO_PAD + CAPTURES),
    'emu_tour.toml': (os.path.join('configs', 'renut_verify.toml'), TOUR + CAPTURES),
    'emu_profile.toml': ('renut_play.toml', PAD + 'switch_profile_stacks = true\n'),
    'emu_ab.toml': ('renut_ab.toml', PAD),
}


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, (source, extra) in TESTS.items():
        lines = open(os.path.join(DIST, source), encoding='utf-8').read().split('\n')
        keys = {l.split('=', 1)[0].strip() for l in extra.split('\n') if '=' in l}
        kept = [l for l in lines if not ('=' in l and l.split('=', 1)[0].strip() in keys)]
        # Before the first [table]: a key after one belongs to that table and the game never reads it.
        at = next((i for i, l in enumerate(kept) if l.startswith('[')), len(kept))
        kept[at:at] = ['# tools/make_emu_tomls.py'] + extra.rstrip('\n').split('\n') + ['']
        with open(os.path.join(OUT, name), 'w', encoding='utf-8', newline='\n') as f:
            f.write('\n'.join(kept).rstrip('\n') + '\n')
        print(name, 'from', source, 'keys at line', at + 2)


if __name__ == '__main__':
    main()
