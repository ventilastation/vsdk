# boss_orbit.py  -- generated, do not edit. body-sha: 74fafbfc
from vs2.behaviors import Behavior
from vs2.params import Number


class BossOrbit(Behavior):
    cycle_ticks = Number(192, min=2, max=1024, step=2, label='Orbit cycle', unit='tick')
    theta_speed = Number(2, min=0, max=16, step=1, label='Theta speed', unit='col/tick')
    width = Number(256, min=1, max=512, step=1, label='Display width', unit='col')
    stop_y = Number(107, min=0, max=255, step=1, label='Approach stop', unit='led')

    state = ('theta', 'phase')

    def attached(self, subject):
        pass

    def step_one(self, sprite):
        sprite.phase = ((sprite.phase + 1) % self.cycle_ticks)
        if sprite.phase < (self.cycle_ticks // 2):
            sprite.theta = ((sprite.theta + self.theta_speed) % self.width)
        else:
            sprite.theta = ((sprite.theta - self.theta_speed) % self.width)
        if sprite.y > self.stop_y:
            sprite.y += -1

# behavior-blocks: eNrNlE1r3DAQhv/KMtBTHHZtsik1pdDSey+5hSDGsrZWIstCkpuY4P/ekfyxDtnubigtOdnyvDPPfMnPgNzLRjvIb+8SQGNUx3zDUKnhC1foHNNYC8jhW+PcD1tIDwkYtFgHt2coxQ5b5SFPP2UJKCwEOUMUrnjHlSB5jU9k32RX9Co15CQcg0YF85I/ONI5L0y0+s4Eq27rQlgytJqwOQQd9MkCukDeVMLjyhkhyhl5PQI3M9AHFZtUAzD9I5A3an0Aur3eY79LZxR2q0dZ+moCb9NsJKczeRKcwXyJSzcf97ivxtgGebVyvjETLttuXxUa7Kw7g6eoEz0N2whLfbHSizjXB6nLEEZ45jx6ESOFZw6mQhfOv1C1dJ61hdRoOxbzUmLnzzNN0ce8h+B9AqTN4YIMVv6slg6KUrSo9gmk/ST/cEAedxUOblzfh0bzRpcy3IOFE29q8hNvzPbzAfyRyo9lNkZcr89pQBYKAaHcydHF9f9XoxuCT6lfnp7F8jK+ZYbDVaKiaW1HhdyxWH8Sgup31IaL/9GGv13jbk73y2ns+GdZrNzRMWDdtPro+l6m/RwAOW/rVr0cF8HuwqzH8+08v+H6BUtb3Avu2VTe8B8jgrAutiTtfwNWGzqK
