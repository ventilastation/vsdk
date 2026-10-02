"""The tutorial game's own GameOver scene, opened directly with a score a short
game could reach (13 enemies dodged), so the screenshot does not depend on playing."""

from games.demos.tutorial_game.code.tutorial_game import GameOver


def main():
    return GameOver(130)
