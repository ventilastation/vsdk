# Play and edit in the browser

[Open the browser emulator](https://ventilastation.protocultura.net/emulator/).
It runs MicroPython in a worker and includes a code editor and sprite editor.

## Try a small change

1. Open **Games**, choose `demos/tutorial_game`, then use **Files** to open its main Python file.
2. Change a gameplay constant, such as the enemy speed. The VS2 tutorial explains
   [movement and sprites](../vs2/tutorial/sprites.md).
3. Click **Save + Run** to save the current file into the workspace and restart
   the game. **Save** alone writes the file but does not restart the running code.
4. If it fails, inspect the runtime output/traceback and fix the named line.

PNG files open in the sprite editor. Save the image and use **Save + Run** to
rebuild changed image ROMs and run again. Image strips and their frame counts
are described in [the first chapter](../vs2/tutorial/first-game.md#images).

## Keep your work

The workspace is held in the page's memory. **Save** survives a runtime restart
within the same page, but it does not write back to GitHub or to your computer.
Reloading or closing the page can discard your edits. Copy your code into a local
SDK checkout before leaving; keep original PNGs and editable sprite sources too.

The **Push to console** action is available only when the hosting server supports
package installation. It sends a distribution package, not a Git commit or a
backup of all editable sources. The public static website does not provide a
GitHub clone/commit/push workflow.

For a complete first game with durable files, follow
[desktop setup](desktop.md) and [the seven-chapter tutorial](../vs2/tutorial/index.md).
For a new browser game, **New Game** creates a VS2 skeleton; add assets and
metadata using [the game conventions](assets-and-sharing.md).
