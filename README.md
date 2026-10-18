# MiSTerManager

A small web page that runs on the MiSTer itself. Open it from a phone or a computer on the
same network to:

- see what is running (core and game) and the state of the Linux side: CPU, memory, free
  space on the SD card, uptime, IP and Wi-Fi;
- browse the games on the SD card by system, or search all systems at once, and start one with
  a button;
- see the box art of each game, if update_all's Game Artwork DBs are installed (it falls back to
  the title screen, then to a screenshot);
- change general settings: the main volume, the scaling mode, the default video preset for all
  cores, arcade and vertical arcade, and the filters of the presets in `Presets/Custom`
  (scanlines, sharpness, gamma, shadow mask);
- go back to the MiSTer menu or reboot it;
- change the OSD options of 136 console and computer cores, saved like the core's own
  "Save settings" in `config/<core>.CFG`;
- download and upload PlayStation memory cards (one per game, `saves/PSX/<folder>.sav`; takes
  .mcd/.mcr/.sav, .gme and .vmp);
- see the connected controllers (with battery level for PlayStation pads) and stop
  DualShock 4 / DualSense motion sensors from moving the character by themselves (a switch in
  Settings, on by default; see `mistermanager/motion.py`).

It is one Python program with no extra packages. The MiSTer already has Python 3.9.

## How it starts a game

MiSTer Main reads commands from the fifo `/dev/MiSTer_cmd`. `load_core <file>` loads an `.rbf`,
an `.mra` or an `.mgl` file.

- Arcade: the `.mra` file is sent as it is.
- Consoles: the server writes `/tmp/mistermanager.mgl` with the core and the absolute path of
  the game, then loads that file.
- Neo Geo: the Darksoft folders listed in `games/NEOGEO/romsets.xml`, and `.neo` files.

The core paths and MGL slot numbers per system are in `mistermanager/systems.py`.

The server only starts games that are in its own index of the SD card, and it checks that each
path stays inside the folder of its system. There is no password: use it only on your home
network.

## Settings

Volume goes through the same fifo (`volume 0`-`volume 7`, `volume mute|unmute`) and MiSTer saves
it in `config/Volume.dat`. The page only changes `vscale_mode` and `preset_default` in
`MiSTer.ini` (sections `[MiSTer]`, `[arcade]`, `[arcade_vertical]`); video modes and sync options
are left out because a wrong value can leave the screen black. Every change keeps a copy of the
previous file in `/media/fat/MiSTerManager/backups` (last 10). MiSTer reads these files when a core
loads, so changes apply from the next core load.

## Core options

A core's option list (`CONF_STR`) is compiled into its `.rbf`, so it cannot be read on the
MiSTer. `tools/build_core_catalog.py` reads it from each core's source in the MiSTer-devel
GitHub organisation and writes `mistermanager/cores.json` (needs the `gh` CLI):

```sh
python3 tools/build_core_catalog.py NES SNES MegaDrive PSX NeoGeo
```

The server reads and writes the 128-bit status in `config/<name>.CFG` (little-endian, as
MiSTer Main saves it) and keeps the last copies in `/media/fat/MiSTerManager/backups/cores`.
Changes apply the next time the core loads. Arcade cores and Minimig/AtariST are not covered:
they keep their settings in other files.

## Artwork

update_all's "Game Artwork DBs" put images in `/media/fat/docs/<system>/Artwork`, `Titles` and
`Screenshots`. Console images use No-Intro names; arcade and Neo Geo images use the MAME set name
(read from the `.mra` file or the Darksoft folder name). Games with older GoodTools names are
matched on the bare title, preferring the region of the game. See `mistermanager/artwork.py`.

## Install

From a computer with SSH access to the MiSTer:

```sh
./deploy.sh root@192.168.53.83
```

This copies the files to `/media/fat/MiSTerManager`, adds a line to
`/media/fat/linux/user-startup.sh` so it starts at boot, and starts it. Then open
`http://<MiSTer IP>/`.

On the MiSTer:

```sh
/media/fat/MiSTerManager/S60mistermanager restart   # or start, stop, status
bash /media/fat/MiSTerManager/uninstall.sh          # remove everything
```

The log is `/tmp/mistermanager.log`. The game index is `/media/fat/MiSTerManager/index.json`;
it is built again at every start, and the Rescan button builds it on demand.

## Development

```sh
python3 -m unittest discover -s tests -t .
python3 -m mistermanager --port 8080 --fat /path/to/a/copy/of/media/fat --fifo /tmp/fake_cmd
```
