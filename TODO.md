# TODO

Open work items. Completed and discarded entries are pruned; see git
history of this file for the record.

## Tooling / emulator

- Close the loop: let an agent drive a sandboxed browser + HTTP server so
  it can watch and interact with the web emulator.
- Merge the common boot code between `ventilastation/browser.py` and
  `main.py` (games menu creation/push).
- [ONGOING] Step-by-step debugging of running MicroPython code.
- [ONGOING] Pixel editor integrated into the web workflow (Piskel embed
  exists; finish the flow).
- Create an editor for tiles.
- Add a pill showing the WebGL resolution scale when Auto is selected.
- Split the remaining `BrowserHostApp` class in `web/app.js` by concern
  (renderers/audio/support modules are already split out).

## Runtime / API v2

- New sprite type holding a byte array rendered as text from a strip; also
  usable for tile-based backgrounds.
- Port existing games to the v2 APIs.
- Go through the Discord suggestions and GitHub bug reports and shape the
  v2 API list (music loop flag already done).

## Deployment / OTA (see docs/internals/ota.md)

- Upgrade voom without rebooting (partition OTA works; still reboots).
- Generated list of console ROMs.

## Display quality

- Darker colors in the center LEDs are way off for Voom; the gamma curve
  may need a rework.
- Master System shows display delays; NES degrades quickly — audit what
  else runs on the POV core.
- Exit keys are unreliable in SMS/NES; consider forcing a key combo.

## Voom

- [ONGOING] Make the rest of retro-go usable on the LED POV and emulator
  displays, including the launcher menus (text illegible at POV
  resolution today).
- Stereo separation/pan as available in I_StartSound.
- Disable the board OPL synth and audio playback in LED/emulator modes.

## Workbench

- Color intensity needs a proper reversal of the full finish_with_gamma
  pipeline (per-LED intensity table + brightness); put_pixel currently
  passes wire bytes through unchanged. The intensity table's origin:
  vyruss/images/intensidades.py in the pre-vsdk repo.
- Ventilagon is not rendered properly on the workbench capture.
