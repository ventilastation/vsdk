"""The tutorial game's own GameOver scene, opened directly with a score a short
game could reach (13 enemies dodged) and a saved best a little higher, so the
screenshot does not depend on playing."""

import vs2
from games.demos.tutorial_game.code.tutorial_game import BEST, GameOver


def main():
    vs2.saves.save(BEST, 250)
    return GameOver(130)
