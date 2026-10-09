# misterlily-art

Personal script that makes colour pictures for [MiSTerLily](https://github.com/alberthorta/MiSTerLily)
from the names of the tty2oled pictures. The pictures are logos and marquees owned by other
people, so they are for my own MiSTer only and are not in this repo.

## Sources

- **Arcade cores** (MAME set names): the marquee from the [Arcade Database](https://adb.arcadeitalia.net).
  If there is none, the marquee of the parent set, then the title screen.
- **System cores**: the colour logo from the Batocera Carbon theme
  ([fabricecaruso/es-theme-carbon](https://github.com/fabricecaruso/es-theme-carbon)), mapped in
  `systems.py`. Logos with black parts get a light panel behind them.

## Needs

- Python 3 with Pillow and py7zr: `python3 -m pip install Pillow py7zr`
- `rsvg-convert` for the SVG logos: `brew install librsvg`
- The MiSTerLily repo next to this one (`../MISTerLily`), for `tools/convert_asset.py`.
  Another place: `--misterlily PATH`.

## Use

```sh
python3 fetch.py                       # all cores; keeps pictures already in out/art
python3 fetch.py --only SNES outzone   # some cores
python3 fetch.py --force               # rebuild everything
python3 fetch.py --no-arcade           # only system cores
```

The first run downloads the tty2oled picture pack and takes a while (about 1,700 arcade
games, with a pause between requests). Downloads are cached in `cache/`.

Then:

1. Open `out/review.html`: each core shows the tty2oled picture and the colour one.
2. Delete the pictures you do not like from `out/art/`. To replace one, put your own
   `<CORE>.png` there (`../MISTerLily/tools/convert_asset.py` makes it 320x170).
   The next run keeps files that are already there.
3. `out/missing.txt` lists the cores without a picture and why.
4. Copy to the MiSTer:

   ```sh
   scp out/art/* root@<mister-ip>:/media/fat/MiSTerLily/art/
   ```

## Not done

- Colouring the tty2oled picture with an image model for the cores without a source.
- Cores with no logo in the theme (EDSAC, Tamagotchi, ZXNext, ...): add them to `systems.py`
  if a logo appears in the theme, or make them by hand.
