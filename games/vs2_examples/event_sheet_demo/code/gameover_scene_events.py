# gameover_scene_events.py  -- generated, do not edit. body-sha: 34381f9d
import vs2


class GameOverSceneEvents:
    def on_enter(self):
        super().on_enter()
        self._vs2_events_ticks = 0
        self.title_label.text = 'GAME OVER'
        self.score_label.text = vs2.project.score

    def update(self):
        super().update()
        self._vs2_events_ticks += 1
        if self._vs2_events_ticks >= 90:
            import games.vs2_examples.event_sheet_demo.code.title_scene as _scene
            _target = _scene.Title()
            _target._vs_api_slug = self._vs_api_slug
            _target._vs_declared_api = self._vs_declared_api
            self.switch(_target)

# blocks: eNqNUU1LBDEM/SuS8zCoN+fmYfAkCypeREpsw1q2H0uTHRaW+e+m03VwEcFTk7yXj/d6AhuQ2SSMBAM86LOZqDxbSjROlIShA2rB8HYCtOJzavHOJ6c9TGICflAwQkdRektQpCgqXgI1XKGFMaytwQsVrMCE4bAccP84Xm1exyeY5+6fK9jm8ueKCYsWz/IWpk5+78Dm5Py3Fs3P9JwMCxaBuv2n2AubXqooWJu2WbLhapnWYnaHUElb5XI/8a2hI8Z90GQx0vAnqR5HMfc2O+qbRa3/12mrEPGRiqGAeyZXdXq7U8Ld9XxxfS0vU/QXWWfAcDN/AVBOqCg=
