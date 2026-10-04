# Set up the desktop emulator

Use this route for the tutorial and for keeping your game in files and Git.
The emulator runs your MicroPython game on your computer; no console is needed.

## Install dependencies

The previous setup guides recorded Ubuntu 24.04 x86_64, macOS Sonoma 14.5 on
an M1 MacBook Air, and Windows 10 Intel 64-bit. These are recorded environments,
not a claim that every current combination has been retested. SDK CI uses Python 3.12.

**Linux (Ubuntu):**

```sh
sudo apt install git micropython python3.12-venv ffmpeg
```

**macOS:** install [Homebrew](https://brew.sh/), then:

```sh
brew install git python@3.12 micropython ffmpeg
```

Use Homebrew's installation instructions to put its binaries on PATH; its
prefix differs between Apple Silicon and Intel machines.

**Windows:** install [Git](https://git-scm.com/downloads/win) and
[Python 3.12](https://www.python.org/downloads/), with Python on PATH.
The SDK includes `emulator/micropython.exe`. FFmpeg is needed for audio
conversion; see `emulator/ffmpeg-win/README.md` in the repository for the
local binary directory. Game code is MicroPython, distinct from the CPython
used to run the emulator host.

## Clone and install

```sh
git clone https://github.com/ventilastation/vsdk.git
cd vsdk
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
```

On Windows, use these commands in Command Prompt instead:

```bat
git clone https://github.com/ventilastation/vsdk.git
cd vsdk
py -3.12 -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python -m pip install pywin32
```

You do not need to initialize the Retro-Go firmware submodule to write
MicroPython games.

## Run a known VS2 game

On Linux/macOS, run from the repository root:

```sh
./vs-emu.sh --game demos.tutorial_game
```

On Windows, with the virtual environment still active:

```bat
vs-emu.bat --game demos.tutorial_game
```

You should see Trench Run. Left/right arrows steer; Space is A and Page Down
is Back. Without `--game`, the emulator opens the launcher; the finished tutorial
is in **Tech Demos**. ROM generation happens automatically when sources change.

**Next: [create your own game and steer a ship](../vs2/tutorial/first-game.md).**

## Controls and troubleshooting

| Control | Keyboard |
|---|---|
| Joy1 directions | Arrow keys or W/A/S/D |
| Joy1 A/B/X/Y | Space/O/P/Y |
| Joy1 Start/Back | Page Up/Page Down |
| Joy2 directions | H/J/K/L |
| Joy2 A/B/X/Y | Z/X/C/V |
| Joy2 Start/Back | Home/End |

A USB gamepad also works. The terminal that launched the emulator shows Python
tracebacks: keep it open when debugging. A missing PNG usually means
`images/__images__.yaml` names a file you have not copied.

If `python`, `micropython`, or FFmpeg cannot be found, check PATH and activate
`.venv`. If your game is missing, check its `games/<group>/<name>/code/<name>.py`
entry point and metadata. `--game group.name` uses a dot between group and name.

The Unix launcher tries to build the optional native renderer. The GPU shader
renderer needs OpenGL 3.3; `./vs-emu.sh --scene-renderer cpu` selects the CPU
path. **F2** switches CPU/GPU, and **F3** compares both render paths. These are
emulator tools, not requirements for your first game.
