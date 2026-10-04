"""Game Over scene: hand-written build() only -- reading the surviving
project score, displaying it, and transitioning back to Title after a
wait are all generated from gameover_scene.vs2events.json into
gameover_scene_events.py.
"""

import vs2

from games.vs2_examples.event_sheet_demo.code import gameover_scene_events


class GameOver(gameover_scene_events.GameOverSceneEvents, vs2.Scene):
    def build(self):
        self.hud = self.layer("hud")
        self.title_label = self.hud.label("font.png", columns=10, rows=1, y=8)
        self.score_label = self.hud.label("font.png", columns=5, rows=1, y=16)
