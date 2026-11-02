<h1 align=center>Ridge Racer 6: Nintendo Switch port</h1>

A port of the Xbox 360 game **Ridge Racer 6** (Namco, 2005) to the Nintendo Switch, with a PC build as the step on the way.

It's not an emulator. The PowerPC code of the game's `default.xex` is statically recompiled to C++ with
[ReXGlue](https://github.com/rexglue/rexglue-sdk), and the game's Direct3D calls are drawn by
[reNut](https://github.com/masterspike52/reNut)'s Direct3D-level renderer, on the Switch GPU's own API, deko3d.

> [!NOTE]
> Work in progress. See `docs/progress-log.md` for what works now, and `docs/rr6-notes.md` for the evidence and the open
> visual differences.
>
> You need your own copy of the game. Game data is never part of this repository or its packages.

## Documentation

| File | What it holds |
|---|---|
| `docs/rr6-notes.md` | This game: decisions, code generation, game fixes, Renut at XDK 2.0.2135, visual differences |
| `docs/progress-log.md` | The work in order |
| `docs/building.md` | How to build (written for katamari-nx; its game-specific file names are still to be updated) |
| `docs/optimising-functions.md` | The hot-function method |
| `docs/from-katamari/` | The notes of the port this one started from |

## Credits

- **Ridge Racer 6 Recomp** by Sirhalo23 (BSD 3-Clause, `docs/licenses/`): its codegen work and its notes on this game.
- **reNut** by masterspike52: the renderer. Its author permits reuse in these ports.
- **katamari-nx**, the port this tree was copied from, and **banjo-nx**, the renderer's adaptation and the method docs.
- **sa2-nx**, **NetherSX2_nx**, **battd_nx**, **bejeweled3-nx** and the **Zuma** ports.

`THIRD_PARTY_NOTICES.md` has the full list and each project's license. GPL-3.0 where the sources are (`LICENSE`).

Ridge Racer is a trademark of its owner. This project is not affiliated with or endorsed by them.
