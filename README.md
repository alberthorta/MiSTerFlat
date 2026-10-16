# MiSTerManager

A small web page that runs on the MiSTer itself. Open it from a phone or a computer on the
same network to:

- see what is running (core and game) and the state of the Linux side: CPU, memory, free
  space on the SD card, uptime, IP and Wi-Fi;
- browse the games on the SD card by system, search them and start one with a button;
- go back to the MiSTer menu.

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
