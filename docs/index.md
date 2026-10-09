# Ventilastation documentation

Make circular games in MicroPython with **VS2, API revision 2**.
You can start on a computer; no console or electronics are needed.

## Make your first game

1. [Set up the desktop emulator](guides/desktop.md).
2. [Create a game and steer your first ship](vs2/tutorial/first-game.md).
3. [Build Trench Run through seven short chapters](vs2/tutorial/index.md).
4. [Add your own assets and share the game](guides/assets-and-sharing.md).

Use the desktop emulator to develop and test your games, with local files you
can keep in Git.

## Find a specific answer

- [VS2 API reference](vs2/reference/index.md): generated from the runtime source.
- [Glossary](vs2/glossary.md): the circular display and API vocabulary.
- [Going further](vs2/going-further.md): advanced patterns after the tutorial.
- [SDK and hardware internals](internals/README.md): for contributors and console builders.

The website introduces the console and links to desktop development. These
documentation sources live in `ventilastation/vsdk/docs/` and are built for both the website's
`/docs/` and [Read the Docs](https://ventilastation.readthedocs.io/). [Return to the website](https://ventilastation.protocultura.net/).

```{toctree}
:hidden:
:caption: Make games
:maxdepth: 2

guides/desktop
vs2/index
guides/assets-and-sharing
```

```{toctree}
:hidden:
:caption: Maintain the project
:maxdepth: 1

internals/README
guides/documentation
legacy/index
```
