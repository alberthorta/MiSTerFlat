# Assets

- `STARTUP.png`: the display's start-up picture, 320×130 (the area above the "Waiting for MiSTer"
  line; the firmware version is drawn small in the top-right corner). Made from `src/misterlogo.png` (298×65): scaled 1.3× and cropped
  centered to 320×130 (the outer 2 px on the left of the artwork are cut).

Store it on the display with `python3 tools/set_logo.py <port> assets/STARTUP.png`, or copy it to
`/media/fat/MiSTerLily/art/STARTUP.png` on the MiSTer (the daemon stores it when it changes).
