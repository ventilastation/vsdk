# fold_demo_scene_events_fast.py  -- generated, do not edit. body-sha: 64b5ad9a
import vs2
from urandom import randrange


class FoldDemoSceneEvents(vs2.Scene):
    def on_enter(self):
        super().on_enter()
        self._vs2_events_ticks = 0
        vs2.project.var('score', 0)
        vs2.project.score = 0

    def update(self):
        super().update()
        self._vs2_events_ticks += 1
        if True:
            vs2.project.score = randrange(1, (1) + 1)
        if False:
            vs2.project.score = 999

# blocks: eNqtUL0OgkAMfpfODGrigIlO6gs4GkPKUfXicSV3Jwvh3S2IMKhoolt/vn4/rUAZ9D6xmBMsYMsmW1POO0WWNiXZ4CECuheLfQWogmZ7ry/aZnLjKSQlOo2pIQF3TF6xa9oSzVX6Hm10IIdm2Ezq+hCBYpvpB7X0HZpt4gO6AHX0izaOGZjWEaSfAN3Ooc04h2fL/bXivMBW3dAxjNJOhJcLWa2WMnX6dB7Fz1vV4TFBq8uPf3knFcfxfyI+Ei6/Sjh7mVBGJTkvLhrCG5G45AE=
