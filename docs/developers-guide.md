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


## Part III: Scenes and the director

Games and applications created for Ventilastation are composed of one or more `Scenes`.
These are a logical grouping of `Sprites` (defined in the next section of the documentation.)

Scenes are managed with a singleton called the `director`, which handles the stack of scenes via its `push(scene)` and `pop()` methods.

A scene can define an `on_enter()` method that gets called whenever the Scene is shown, and an `on_exit()` method that is called when the scene is popped. Make sure to call `super()` when you define these methods, eg: `super().on_enter()`.

After the scene is shown, the `director` will start calling your `step()` method every 30 milliseconds. Your game logic usually goes in this method.

If you need some action to happen later in the future, `Scene` provides a method called `call_later(delay, callable)`. The parameter `delay` is the number of milliseconds in the future, and `callable` is any function or bound method. If the `Scene` is finished via `director.pop()` then all pending calls in the scene are automatically discarded.

⚠️ *WARNING* ⚠️: it's advised to create all `Sprites` and other objects that will be used in the `on_enter()` method of your `Scene`, and to reuse them as much as possible. Do not create and release objects in the `step()` method, since for performance reasons the Garbage Collection only happens when entering or exiting `Scenes`.


## Part IV: Ventilastation display and Sprites

The radial display of Ventilastation means that its pixels are not square, but instead are similar to tiny arcs. We call them "Arxels". Currently there are 54 LEDs from the center, and there are 256 circular steps where LEDs can change colors. All of this is handled in an optimized piece of C code, but all of this is already done, so you should not worry about that.

As a Ventilastation game developer, you will only handle graphics using the `Sprite` class. These are up to 100 objects that Ventilastation can show and animate on its display.

In a given `Scene`, Sprites created first are always drawn on top of sprites created later, so it's very important to keep in mind the order in which you create the sprites.

```
from ventilastation.sprites import Sprite
```

Each Sprite object has the following methods:
- X - `set_x()`, `x() -> int`
- Y -  `set_y(int)`, `y() -> int`
- Strip - `set_strip(strip_number: int)`
- Frame - `set_frame(int)`, `frame() -> int`
- Perspective `set_perspective(int)`, `perspective() -> int`
- Width, Height - `width() -> int`, `height() -> int`
- Collision detection - `collision([list of sprites]) -> target` returns the first sprite that collides from the list, or None if no sprite collides.
- Hide sprite - `disable()`, call `set_frame(int)` to show it again.

There are three "perspective modes" for sprites:
- Mode 0: fullscreen images
- Mode 1: perspective sprites 
- Mode 2: non-perspective sprites

### Perspective Mode 0: fullscreen images
These images may be scaled to occupy less than a full screen with the Y property, may be rotated with the X property, but are always centered in the middle of the screen. The game Ventap shows a planet in the middle of the screen with a mode 0 sprite.
To create artwork, start with a 320x320 png image, with few colors (16 or 32 colors recommended), with optional on-off transparency (there's no fancy alpha channel in Ventilastation). For a sample of a transparent fullscreen image, take a look at the Saturn image of Vyruss.

### Perspective Mode 1: perspective sprites 
Sprites in this mode are usually the most common sprites in games. They provide a "tunnel-like" perspective, using fewer LEDs as the object moves toward the center to provide a scaling effect.

The X property starts at 0 in the bottom of the screen, rotates up to 64 in the left, 128 at the top, 192 at the right, continues up to 255 and then 0 at the bottom.

The Y property starts at 0 outside the screen, goes to 16 where the object is fully seen, and then increases up to 255 at the center of the screen, 

Using the application called Tutorial you to change the X and Y values of different modes of sprites to experiment with it.

### Perspective Mode 2: non-perspective sprites
This mode is usually reserved for images that don't need to be scaled, like scoreboards or the Game Over sign.

The X property is equal to Mode 1 sprites.

The Y property goes from 0 at the outermost LED, to (54 - the sprite height) as the innermost LED.

## Part V: Submit your game to the Ventilastation project

In order to submit your game to the Ventilastation project, please do it as a Github Pull Request.

More detailed documentation about this process is available on Github itself:
- [Fork a repository](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/working-with-forks/fork-a-repo
- [Creating a pull request from a fork](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/)proposing-changes-to-your-work-with-pull-requests/creating-a-pull-request-from-a-fork)
