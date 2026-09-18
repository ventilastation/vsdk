# playing_scene_events.py  -- generated, do not edit. body-sha: 9950d073
import vs2
from urandom import randrange


class PlayingSceneEvents(vs2.Scene):
    def on_enter(self):
        super().on_enter()
        self._vs2_events_ticks = 0
        vs2.project.var('score', 0)
        vs2.project.score = 0

    def update(self):
        super().update()
        self._vs2_events_ticks += 1
        if self._vs2_events_ticks >= 20:
            vs2.project.score = 10
        if self._vs2_events_ticks >= 60:
            vs2.project.score = randrange(25, (35) + 1)
        if vs2.project.score >= 25:
            import games.vs2_examples.event_sheet_demo.code.gameover_scene as _scene
            _target = _scene.GameOver()
            _target._vs_api_slug = self._vs_api_slug
            _target._vs_declared_api = self._vs_declared_api
            self.switch(_target)

# blocks: eNq1UsFOwzAM/Zecq2oUwWES3BBHkDgiFHmJ6aIlcRVnFWjKv+NupTA0BgjtlDz72X5+8kYZD8w6QkA1V/ceXl1sHwxGvOkxZlaVwt1n/rhRYLKjuPuvXLRSwph1D8nBwqOQx0ZsKA2wB78WPLG9y5jAf2RmpTxVylC07r214JFNUXOGlFWpTjH77MDwiZ1dwKTRQ8dopSY7sxJCMyt7+obwP+XBMY3NRanU4hjjfGCMyQTRUlB/X+vyN2vtncqtPHc9JjWVtZRJ83A6Egtk137gtcLjuudG4wuEzgvYHpTmJYo/FgPVhizWA5Gk4dji+xUMhQ62Fnp8zp+sEa+/2izWUCfo+koyybXL/IPZh2yQkOhi0SE3U94AFoEUvA==
