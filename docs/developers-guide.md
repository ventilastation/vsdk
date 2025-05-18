# How to make games and apps for Ventilastation

Ventilastation applications are built using the Micropython language.
This is a version of the Python programming language, but optimized in its resource and memory usage so it is able to run on Microcontrollers like the ESP32 used by the Ventilastation fan blade.

## Part I: setup and overview

### Requirements: VSDK
To develop for Ventilastation you first need the sdk and the emulator running. Follow the [steps to install it here](docs/emulator.md).
Part of the above installation is to clone the [VSDK repository](https://github.com/ventilastation/vsdk) (also known as the Ventilastation Development Kit). 

### VSDK repo, key folders
In the Ventilastation repo there are a few folders that you'll need to identify, where your code, images and sounds will go.
* `apps/micropython/apps` is the folder that will hold your code
* `apps/images` is for your graphic assets
* `apps/sounds` is for music and sound effects
* `apps/micropython/roms` - images compiled by the `regenerate-images.sh` script are put into this folder
* `apps/micropython/ventilastation` is a folder with system code

### VSDK repo, scripts
* `regenerate-images.sh` (or `.bat` under Windows) needs to be run every time you make a change in your images. It compiles the images into a `ROM` format that ventilastation and the emulator can understand.
* `vs-emu.sh` (or `.bat`) is the script to start the emulator.

## Part II: How to clone the simplest game

Let's start by cloning a very simple game: `ventap`. In the repo find the `apps/micropython/apps` folder, and make a copy of the `ventap.py` file, into a new file called `mygame.py`:

```
cp apps/micropython/apps/ventap.py apps/micropython/apps/mygame.py
```

In that file, rename the class called `Ventap` to `MyGame`, including its use in `super` calls, and the usage in the `main` function at the bottom.


Create a new folder called `mygame` inside `apps/images`, and put some PNG images into it:

```
mkdir apps/images/mygame
cp apps/images/ventap/*.png apps/images/mygame
```

Ventilastation cannot directly open PNG images, so in order to transform your assets into a format it can understand, you'll need a definition file. Create the file `apps/images/mygame/stripedefs.py` with the following content:
``` python
stripes = [
    palettegroup(
        strip("bola.png", frames=12),
        strip("target.png", frames=5),
        fullscreen("fondo.png"),
    )
]
```

Now you are ready to transform the images into the ROM format. If you ever add new images or change the existing files, you'll need to run this command again:

```
regenerate-images.sh
```

The above creates a ROM file in `apps/micropython/roms/mygame.rom`. We can reference it in our source code by changing the line `stripes_rom = "mygame"` in the `MyGame` class.

Finally, to be able to start this app it needs to be added to the main menu.
Add the following line to `main.py`:
```
    ('mygame', "mygame.png", 0),
```

You can modify the file `mygame.png` used in the menu, in the `apps/images/menu` folder. 64x30 pixels is the right size for menu items.

## Part III: Ventilastation display and Sprites
The radial display of Ventilastation means that its pixels are not square, but instead are similar to tiny arcs. We call them "Arxels". Currently there are 54 LEDs from the center, and there are 256 circular steps where LEDs can change colors. All of this is handled in an optimized piece of C code, but as a game developer you should not worry about that.

As a Ventilastation coder, you only interact with the display using `Sprites`. These are objects that Ventilastation can show and animate on its display.

```
from ventilastation.sprites import Sprite
```

Each Sprite object has the following properties:
- X
- Y
- Perspective
- Strip
- Frame

There are three "perspective modes" for sprites:
- Mode 0: fullscreen images
- Mode 1: perspective sprites 
- Mode 2: non-perspective sprites

### Mode 0: fullscreen images
(TODO)

### Mode 1: perspective sprites 
(TODO)

### Mode 2: non-perspective sprites
(TODO)

## Part IV: Scenes and the director
(TODO)

## Part V: advanced topics
(TODO)
