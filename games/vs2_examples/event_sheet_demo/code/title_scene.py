"""Title scene: hand-written build(), plus the one escape hatch this
proving game needs.

The generated TitleSceneEvents mixin (title_scene_events.py, generated
from title_scene.vs2events.json) only carries the ``on_start`` event --
T16's condition/expression grammar has no way to express "button A was
just pressed" (no input-state expression, no edge-trigger condition), so
"press A to start" is a few hand-written lines here instead, exactly the
escape hatch this task's own brief pre-approved for this case: leave the
actual button-check as a tiny hand-written ``if`` in a thin hand-written
subclass wrapper, the same spirit as T15's ``on_build_N()`` hooks being
hand-called from a companion.
"""

import vs2
from vs2.controls import A, joy1

from games.vs2_examples.event_sheet_demo.code import title_scene_events


class Title(title_scene_events.TitleSceneEvents, vs2.Scene):
    def build(self):
        self.hud = self.layer("hud")
        self.title_label = self.hud.label("font.png", columns=9, rows=1)

    def update(self):
        super().update()
        if joy1.just_pressed(A):
            # Hand-written scene transition: T16's block vocabulary has no
            # button-press condition to generate this from (see this
            # module's docstring). Propagate the same two attributes
            # generated goto_scene actions propagate -- see
            # tools/vs2_event_gen/generator.py's docstring for why this
            # is load-bearing, not decorative.
            from games.vs2_examples.event_sheet_demo.code import playing_scene
            target = playing_scene.Playing()
            target._vs_api_slug = self._vs_api_slug
            target._vs_declared_api = self._vs_declared_api
            self.switch(target)
