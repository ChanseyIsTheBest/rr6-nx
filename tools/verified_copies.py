#!/usr/bin/env python3
"""rr6-nx (2026-11-03): which machine copies a verify run really checked, and the list cut down to those.

A copy counts as verified only if the guard compared at least one call of it with the original and found no difference
that repeated. A copy that was never reached, or whose every call was "not comparable" (it reached a call outside the
copy, so the original answered), has proved nothing: docs/optimising-functions.md, "It must actually be reached". The
shipped renut.toml has the guard off, so what is on there has to be proved beforehand.

  python -I tools/verified_copies.py COUNTS [COUNTS ...]           counts of each run (logs/rr6_hot_counts.txt, one per run)
  python -I tools/verified_copies.py COUNTS [COUNTS ...] --write   also cut app/src/cpu/hot/localized_bulk.txt to them

A difference in any run keeps a copy out, however many other runs compared it clean.
"""
import argparse
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BULK = os.path.join(ROOT, 'app', 'src', 'cpu', 'hot', 'localized_bulk.txt')
DROPPED = os.path.join(ROOT, 'out', 'copies_dropped.txt')
WEAKER = os.path.join(ROOT, 'out', 'copies_kept_never_compared.txt')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('counts', nargs='+')
    ap.add_argument('--write', action='store_true')
    ap.add_argument('--keep-sampled', action='store_true',
                    help='also keep a copy a profile sampled that was reached with no difference but never compared. A weaker '
                         'proof: verify mode runs its original, so it needs a run in the guard\'s normal mode (docs/optimising-functions.md)')
    a = ap.parse_args()
    totals = {}
    for path in a.counts:
        n = 0
        for line in open(path, encoding='utf-8'):
            f = line.split()
            if len(f) != 7:
                continue
            name, bulk, state, compared, not_comparable, not_repeated, differences = f
            t = totals.setdefault(name.upper().replace('SUB_', ''), {'bulk': int(bulk), 'reached': 0, 'compared': 0, 'not_comparable': 0, 'not_repeated': 0, 'differences': 0})
            t['reached'] |= int(state) != 0
            t['compared'] += int(compared)
            t['not_comparable'] += int(not_comparable)
            t['not_repeated'] += int(not_repeated)
            t['differences'] += int(differences)
            n += 1
        print(f'{path}: {n} copies')
    bulk = {k: v for k, v in totals.items() if v['bulk']}
    differ = sorted(k for k, v in bulk.items() if v['differences'])
    verified = {k for k, v in bulk.items() if v['compared'] and not v['differences']}
    only_nc = sorted(k for k, v in bulk.items() if v['reached'] and not v['compared'] and not v['differences'])
    unreached = sorted(k for k, v in bulk.items() if not v['reached'])
    print(f'bulk copies {len(bulk)}: verified {len(verified)}, with a difference {len(differ)}, reached but never compared {len(only_nc)}, never reached {len(unreached)}')
    print(f'calls compared {sum(v["compared"] for v in bulk.values())}, not comparable {sum(v["not_comparable"] for v in bulk.values())}, differed once and not when repeated {sum(v["not_repeated"] for v in bulk.values())}')
    if differ:
        print('with a difference:', ' '.join(differ[:40]))
    lines = open(BULK, encoding='utf-8').read().split('\n')
    keep, dropped = [], []
    sampled_out = []
    kept_weaker = []
    for line in lines:
        m = re.match(r'\s*([0-9A-Fa-f]{8})\b', line)
        if not m:
            keep.append(line)
            continue
        k = m.group(1).upper()
        if k in verified:
            keep.append(line)
        elif a.keep_sampled and k in only_nc and 'samples' in line:
            keep.append(line)
            kept_weaker.append(line)
        else:
            dropped.append(line)
            if 'samples' in line:
                sampled_out.append(line)
    print(f'list: {sum(1 for l in lines if re.match(r"\s*[0-9A-Fa-f]{8}\b", l))} entries, {len(dropped)} to drop, of which a profile sampled {len(sampled_out)}')
    for line in sampled_out[:25]:
        print('   sampled, dropped:', line[:90])
    if a.keep_sampled:
        print(f'kept: {len(verified)} compared, {len(kept_weaker)} sampled and never compared (the weaker proof), {len(verified) + len(kept_weaker)} in all')
        os.makedirs(os.path.dirname(DROPPED), exist_ok=True)
        open(WEAKER, 'w', encoding='utf-8', newline='\n').write('\n'.join(kept_weaker) + '\n')
    if a.write:
        open(BULK, 'w', encoding='utf-8', newline='\n').write('\n'.join(keep))
        os.makedirs(os.path.dirname(DROPPED), exist_ok=True)
        open(DROPPED, 'w', encoding='utf-8', newline='\n').write('\n'.join(dropped) + '\n')
        print('wrote', BULK, 'and', DROPPED)


if __name__ == '__main__':
    main()
