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

## New game

- Let's plan a new ventilastation game called "Vixeous", make a new branch for that. It should play similarly to Xevious, the 1983 game by Namco, but the surface of the game should be similar to a tube, like Gyruss. I expect it to have waves of enemies, dropping bombs on targets, bosses, different areas. And all with fast action, cool graphics and music, fun gameplay. The tubular world would rotate as the player moves, but keeping the spaceship always centered. The game Tincho Vrunner already manipulates a lot of sprites that may be needed for a game like this, but we may need to extend the VSDK apis with a scrolling tile renderer to accelerate the display of an extensive playfield.

## cleanups

- [done] Since the workbench was added to this project, the feature to have the main board emit display frames via wifi no longer makes sense (the tcp bridge). Remove that feature, and all references to it in the project, Makefiles, documentation, etc.
- Create some script that identifies what USB port the ventilastation board and the workbench board are connected to. Perhaps add some identification in the build or flash process, or in the NVS partition, so the two types of boards can be told apart. Then make all Makefile targets that expect a PORT default to using this new script so the user does not need to specify the PORT all of the time, only if more than one board is found of the same type, or if the user wants to force the reflash of a given type of board.
- the sync-server.py and sync.py combo were the fastest way to upload changes files to the lfs partition. I want them integrated into the upgrade_server, so 

- provide a way to start an upgrade from the web editor. Using webserial, and having the browser connect to the micropython board via websockets. 
- serve the whole editor from the ventilastation webserver. Perhaps it's the raspi doing the wifi AP and http serving?
- connect the web editor to github, send merge requests from it
- packaging for ventilastation apps: roms, py files, sounds all, in one zip.
- be able to add new images and sounds from the editor.
- [alecu] code a whole new game in the editor.

- move hw_config to NVS, use the GPIOs defined there for retro-go, prboom, et al.



- Let's plan a new vsdk branch, call it "vsdk-api-v2" and branch it from main. I want to build a new API for ventilastation games, but for now keep the existing API in parallel. Games should be able to import from one API or the other, not both. There are some requests for this new API in the issue tracker at [https://github.com/ventilastation/vsdk/issues](https://github.com/ventilastation/vsdk/issues) , issues #89, #90, #91, #92, #93, #95, #96, #97, #98, #109, #110, #111, #112. All of this work might need a separate render function in gpu.c and a different memory structure for sprites, and new renderers in both emulators. We can create a copy of Vyruss and port it to this new API, but please change the menu icon so we can tell them apart.