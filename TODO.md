= Pending prompts =

- Close the loop. Allow the agent to access a sandboxed browser and http server so it can watch and interact with the emulator

- Merge the common boot code from the browser and main, the part where the games_menu_class is created and pushed, and the commented part where the Default VentilagonIdle is created and pushed.

- Have some way to see running micropython code and step by step it.

- Create some way to edit the micropython code for some app, and do live reloading without going back to the menu

- [DONE] Integrate the compilation of PNG images into ROM files, inside the web workflow. This will need replacing python's Pillow for something that can run more natively in the browser.

- Create a pixel editor integrated into the workflow, so assets can be created without leaving the emulator.

- Create a new type of sprite, that can hold an array of bytes to be used as text, taking the images from a given strip. It could also be used for tile based rendering of backgrounds.

- Create an editor for tiles

- Compile the Super Ventilagon C code into wasm, and have it displayable inside the desktop and browser renderers. Or port it to micropython

- Port existing games to the v2 APIs

- The app.js source file is huge. Please split it in a few files per each concern

- Add a pill that shows the webgl resolution scale, useful for when Auto is selected


- Go thru the list of suggestions in Discord and bug reports in Github, and create a Ventilastation API v2, with breaking changes but cleaner:
 - Allow music to automatically repeat. To the method "director.music_play" add an optional named parameter "repeat" that defaults to False.
 - 

- have some way to import binary modules. For eg, ventilastation, and voom

- make voom run again on the esp32-s3, but be able to start it from micropython. It's ok to reboot the esp when ending doom.

- ease the deployment, 




= VOOM FIXES =
- image is rotated 90 degrees clockwise
- buttons don't stay pressed
- sounds are missing. The emulator should have a local copy of the wad file, should be able to convert the midis to mp3s, and prboom should send the triggers to play a sound or music, or stop the music, like micropython games do.