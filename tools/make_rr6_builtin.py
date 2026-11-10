#!/usr/bin/env python3
"""rr6-nx (2026-11-10, the user: "what I want in config.toml, hardcode everything else not to show up"): the player's build
(RR6_BUILTIN_CONFIG=ON, app/out/switch-ult) from the console play toml.

  app/rr6_switch_defaults.toml  every setting of the play toml but the player's, compiled into the NRO
  app/rr6_switch.toml           the player's config.toml (written next to the NRO when there is none): language,
                                banjo_renut_smaa, msaa_level, input_xbox_layout, input_joycon_sideways,
                                input_joycon_sideways_stick, [input_p1] and [input_p2]

  python tools/make_rr6_builtin.py [--play out/console_tests/play_ultimate_smaa.toml]

Checks that the two together give every value of the play toml (with the player's msaa_level and language added).
"""
import argparse
import os
import re
import tomllib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLAYER_KEYS = ('language', 'banjo_renut_smaa', 'msaa_level', 'input_rumble', 'rr6_dlc_unlock_keys', 'input_xbox_layout',
               'input_joycon_sideways', 'input_joycon_sideways_stick')  # rumble and the DLC: the user, 2026-11-10
PLAYER_TABLES = ('input_p1', 'input_p2')
# The final build's own values over the play toml's (the user, 2026-11-10: "no logging enabled besides crash logs"): with
# every level off no log file is made, and the crash handler still writes logs/rex/rex_crash.log (sdk logging.cpp).
FINAL = {'log_level': '"off"'}

PLAYER_HEAD = '''# Ridge Racer 6 for the Nintendo Switch (rr6-nx): your options. Every other setting is built into the game.
# Delete this file and the game writes it again at the next start.

# The game's language: "auto" (the Switch's language), or english, japanese, french, german, spanish, italian.
# A language the game has no text for shows in English.
language = "auto"

# SMAA edge smoothing on the 3D (the HUD and text stay sharp).
banjo_renut_smaa = true

# The game's own edge smoothing (MSAA): 0 off, 2 the game's 2x. Off is lighter on the GPU; SMAA smooths edges either way.
msaa_level = 0

# Controller vibration (rumble). false = none.
input_rumble = true

# The DLC in the dlc folder next to the game: the music packs always load. true = the 36 car Unlock Key packs too
# (they unlock cars at once).
rr6_dlc_unlock_keys = false

# Face buttons by position, as on an Xbox pad (the bottom button is A). false = by letter (the Switch's A is A).
input_xbox_layout = true

# Single Joy-Cons are held sideways, one per player.
input_joycon_sideways = true
# With it, a single Joy-Con's stick is turned for the sideways grip.
input_joycon_sideways_stick = true

# Each player's buttons: the Switch buttons that press each Xbox button, for example a = "B, ZR". Empty = the default.
# Buttons: A B X Y L R ZL ZR PLUS MINUS LSTICK RSTICK UP DOWN LEFT RIGHT SL SR, or NONE.
'''


def tables(text):
    """[(name, start, end)] of the text's [table] sections, end at the next one or the end of the text."""
    heads = [(m.group(1), m.start()) for m in re.finditer(r'(?m)^\[([^\]]+)\]\s*$', text)]
    return [(n, s, heads[i + 1][1] if i + 1 < len(heads) else len(text)) for i, (n, s) in enumerate(heads)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--play', default=os.path.join(ROOT, 'out', 'console_tests', 'play_ultimate_smaa.toml'))
    a = ap.parse_args()
    play = open(a.play, encoding='utf-8').read().replace('\r\n', '\n')
    values = tomllib.loads(play)

    # the built-in part: the player's tables and keys taken out
    sections = tables(play)
    keep = play
    for name, s, e in reversed(sections):
        if name in PLAYER_TABLES:
            keep = keep[:s] + keep[e:]
    first = re.search(r'(?m)^\[', keep)
    top, rest = (keep[:first.start()], keep[first.start():]) if first else (keep, '')
    top = re.sub(r'(?m)^(%s)\s*=.*\n' % '|'.join(PLAYER_KEYS), '', top)
    for k, v in FINAL.items():
        top, n = re.subn(r'(?m)^%s\s*=.*$' % k, f'{k} = {v}  # the final build: no logs but the crash logs (rex_crash.log)', top)
        assert n == 1, k
    defaults = ('# rr6-nx: the Switch build\'s fixed settings, compiled into the NRO (RR6_BUILTIN_CONFIG=ON); the player\'s are '
                'in config.toml\n# (app/rr6_switch.toml). Made by tools/make_rr6_builtin.py from ' +
                os.path.relpath(a.play, ROOT).replace(os.sep, '/') + '.\n\n' + top.rstrip('\n') + '\n' +
                ('\n' + rest.strip('\n') + '\n' if rest.strip() else ''))
    assert ')KATAMARICONFIG' not in defaults

    # the player's file: the head above and the play toml's own [input_p1] / [input_p2]
    player = PLAYER_HEAD
    for name, s, e in sections:
        if name in PLAYER_TABLES:
            player += '\n' + play[s:e].strip('\n') + '\n'

    d, p = tomllib.loads(defaults), tomllib.loads(player)
    for k in PLAYER_KEYS:
        assert k not in d, f'{k} left in the built-in part'
    for t in PLAYER_TABLES:
        assert t not in d and t in p, t
    merged = {**d, **p}
    for k, v in values.items():
        if k in FINAL:
            assert merged.get(k) == tomllib.loads(f'x = {FINAL[k]}')['x'], k
            continue
        assert merged.get(k) == v, f'{k}: {merged.get(k)!r} against the play toml\'s {v!r}'
    open(os.path.join(ROOT, 'app', 'rr6_switch_defaults.toml'), 'w', encoding='utf-8', newline='\n').write(defaults)
    open(os.path.join(ROOT, 'app', 'rr6_switch.toml'), 'w', encoding='utf-8', newline='\n').write(player)
    print(f'app/rr6_switch_defaults.toml: {len(d)} keys/tables built in; app/rr6_switch.toml (config.toml): '
          f'{len(p)} ({", ".join(p)})')


if __name__ == '__main__':
    main()
