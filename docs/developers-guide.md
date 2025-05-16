# How to make games and apps for Ventilastation

## Part I: setup and overview

### Requirements: VSDK
To develop for Ventilastation you first need the sdk and the emulator running. Follow the [steps to install it here](docs/emulator.md).
Part of the above installation is to clone the [VSDK repository](https://github.com/ventilastation/vsdk) (also known as the Ventilastation Development Kit). 

### VSDK repo, key folders
In the Ventilastation repo there are a few folders that you'll need to identify, where your code, images and sounds will go.
* `apps/micropython/apps` is the folder that will hold your code
* `apps/images` is for your graphic assets
* `apps/sounds` is for music and sound effects
* `apps/micropython/roms` - images compiled by the `regenerate-images` script are put into this folder
* `apps/micropython/ventilastation` is a folder with system code

### VSDK repo, scripts
* `regenerate-images.sh` (or `.bat` under Windows) needs to be run every time you make a change in your images. It compiles the images into a `ROM` format that ventilastation and the emulator can understand.
* `vs-emu.sh` (or `.bat`) is the script to start the emulator.

## Part II: How to make a simple app

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

Ventilastation cannot directly open PNG images, but in order to transform your assets into a format it can understand, you'll need a definition file. Create the file `apps/images/mygame/stripedefs.py` with the following content:
``` python
stripes = [
    palettegroup(
        strip("bola.png", frames=12),
        strip("target.png", frames=5),
        fullscreen("fondo.png"),
    )
]
```

Now you are ready to transform the images into the ROM format:

```
regenerate-images.sh
```

The above creates a ROM file in `apps/micropython/roms/mygame.rom`. We can reference it in our source code by changing the line `stripes_rom = "mygame"` in the `MyGame` class.

## Part III: advanced topics
(TODO)