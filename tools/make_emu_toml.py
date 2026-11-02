#!/usr/bin/env python3
"""rr6-nx (2026-11-03): an emulator run's renut.toml: a toml of dist/switch/rr6-nx with keys set or added, each only once (a repeated
key makes the file invalid). A new key goes before the first [section], or it would belong to that section. A value that is not a
number or true / false gets its quotes here: PowerShell strips them from an argument, and an unquoted string makes the whole file
invalid, which the game answers by running on its built-in defaults. The result is parsed before it is written.

  python tools/make_emu_toml.py <base.toml> <out.toml> key=value [key=value ...]
"""
import re
import sys
import tomllib


def quoted(value):
    if re.fullmatch(r'-?\d+(\.\d+)?|true|false', value) or value.startswith('"'):
        return value
    return '"' + value + '"'


def main():
    base, out, pairs = sys.argv[1], sys.argv[2], sys.argv[3:]
    lines = open(base, encoding='utf-8').read().split('\n')
    for pair in pairs:
        key, value = pair.split('=', 1)
        line_out = f'{key} = {quoted(value)}'
        pattern = re.compile(r'^\s*' + re.escape(key) + r'\s*=')
        found = False
        for i, line in enumerate(lines):
            if pattern.match(line):
                lines[i] = line_out
                found = True
        if not found:
            first = next((i for i, line in enumerate(lines) if line.startswith('[')), len(lines))
            lines.insert(first, line_out)
    text = '\n'.join(lines)
    parsed = tomllib.loads(text)  # raises on an invalid file
    for pair in pairs:
        key = pair.split('=', 1)[0]
        if key not in parsed:
            sys.exit(f'{key} is not a top-level key of the result')
    open(out, 'w', encoding='utf-8', newline='\n').write(text)
    print(out, len(pairs), 'keys set, valid toml')


if __name__ == '__main__':
    main()
