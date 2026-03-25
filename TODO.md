= Pending prompts =

- Close the loop. Allow the agent to access a sandboxed browser and http server so it can watch and interact with the emulator

- Merge the common boot code from the browser and main, the part where the games_menu_class is created and pushed, and the commented part where the Default VentilagonIdle is created and pushed.

- Have some way to see running micropython code and step by step it.

- Create some way to edit the micropython code for some app, and do live reloading without going back to the menu

- Integrate the compilation of PNG images into ROM files, inside the web workflow. This will need replacing python's Pillow for something that can run more natively in the browser.

- Create a pixel editor integrated into the workflow, so assets can be created without leaving the emulator.

- Create a new type of sprite, that can hold an array of bytes to be used as text, taking the images from a given strip. It could also be used for tile based rendering of backgrounds.

- Create an editor for tiles

- Compile the Super Ventilagon C code into wasm, and have it displayable inside the desktop and browser renderers. Or port it to micropython

- Go thru the list of suggestions in Discord and bug reports in Github, and create a Ventilastation API v2, with breaking changes but cleaner

- Port existing games to the v2 APIs

- The app.js source file is huge. Please split it in a few files per each concern

- Add a pill that shows the webgl resolution scale, useful for when Auto is selected