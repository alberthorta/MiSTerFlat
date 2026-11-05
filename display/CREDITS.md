# Credits

MiSTerLily exists because of **[MiSTer_tty2oled](https://github.com/venice1200/MiSTer_tty2oled)**
by **venice1200** and **ojaksch**. Its serial protocol, the `CMDCOR` picture transfer, the core
picture library and the idea of a small display that follows the running core all come from
tty2oled. MiSTerLily speaks that protocol, so the unmodified tty2oled daemon and its pictures work
with it, and our own daemon reuses the tty2oled picture library.

- tty2oled: venice1200 (author), ojaksch (USB transfer, updater, tty2tft), and the contributors they
  credit: Jukk@M, jawler, gojira54, stefer09, d.ti, mr-fitzie, salamantecas.
  https://github.com/venice1200/MiSTer_tty2oled
- tty2oled picture library: venice1200 and everyone who drew the core pictures.
  https://github.com/venice1200/MiSTer_tty2oled_pictures. The pictures are not included here; the
  MiSTer downloads them from the tty2oled server.
- MiSTer FPGA: sorgelig and the MiSTer-devel community. https://github.com/MiSTer-devel
- Mr. Fusion (MiSTer SD card installer): Michael Smith and contributors.
  https://github.com/MiSTer-devel/mr-fusion
- LovyanGFX (display driver, PNG/JPEG decoders, fonts): lovyan03. https://github.com/lovyan03/LovyanGFX
- Arduino core for the ESP32: Espressif. https://github.com/espressif/arduino-esp32
- LILYGO T-Display-S3 board files and examples: LILYGO. https://github.com/Xinyuan-LilyGO/T-Display-S3
- Unity test framework: ThrowTheSwitch.org. https://github.com/ThrowTheSwitch/Unity

The MiSTer logo used as the default start-up picture belongs to the MiSTer project.

## Licence

MiSTerLily is free software under the GNU General Public License v3.0, the same licence as
tty2oled. See [LICENSE](LICENSE).
