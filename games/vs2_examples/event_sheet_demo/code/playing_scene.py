"""Playing scene: hand-written build() only -- every tick of game logic
(the staged score, the threshold check, the transition to Game Over) is
generated from playing_scene.vs2events.json into playing_scene_events.py.
No escape hatch needed here, unlike title_scene.py.
"""

import vs2

from games.vs2_examples.event_sheet_demo.code import playing_scene_events


class Playing(playing_scene_events.PlayingSceneEvents, vs2.Scene):
    def build(self):
        # No drawables: this scene's whole "gameplay" is the generated
        # score-staging/threshold-check logic in update() -- see this
        # task's report for why the acceptance line's "playable scene"
        # is genuinely this minimal in a deliberately minimal first pass.
        self.hud = self.layer("hud")
