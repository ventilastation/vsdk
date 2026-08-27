"""ESP32-S3 pre-gate microbenchmark for the VS2 behavior proposal.

This is intentionally not an implementation of Actions or Behaviors. It
measures their proposed dispatch shapes against the current VS2 Sprite facade
on the physical board before either abstraction becomes runtime API.
"""

import gc
import utime

import vs2


SPRITE_COUNT = 60
# One pass is already a meaningful 60-sprite workload on the physical rotor.
# Repeating it suppresses the scene's own update cadence and turns this gate
# into a scheduler benchmark rather than a dispatch benchmark.
PASSES_PER_TICK = 1
WARMUP_UPDATES = 4
X_DELTA = 1
Y_DELTA = 1
Y_LIMIT = 240
_GATE_MODES = ("inline", "column", "per_sprite", "hybrid")


class MoveKernel:
    """The proposed uniform Action shape, without the future API wrapper."""

    def __init__(self, speed_x, speed_y):
        self.speed_x = speed_x
        self.speed_y = speed_y

    def run(self, live):
        dx = self.speed_x
        dy = self.speed_y
        index = 0
        count = len(live)
        while index < count:
            sprite = live[index]
            sprite.x = (sprite.x + dx) % vs2.display.width
            y = sprite.y + dy
            sprite.y = y - Y_LIMIT if y >= Y_LIMIT else y
            index += 1

    def run_one(self, sprite):
        sprite.x = (sprite.x + self.speed_x) % vs2.display.width
        y = sprite.y + self.speed_y
        sprite.y = y - Y_LIMIT if y >= Y_LIMIT else y


class Vs2BehaviorGate(vs2.Scene):
    """Runs one chosen dispatch shape repeatedly without allocating in tick."""

    asset_pack = "other"
    idle_timeout = None
    back_button = False

    def build(self):
        layer = self.layer("gate", projection=vs2.TUNNEL)
        self.sprites = []
        for index in range(SPRITE_COUNT):
            self.sprites.append(layer.sprite(
                "galaga.png",
                x=(index * 37) % vs2.display.width,
                y=(index * 13) % Y_LIMIT,
                frame=index % 12,
            ))
        self.move = MoveKernel(X_DELTA, Y_DELTA)
        self._gate_mode = None
        self._gate_samples = 0
        self._gate_total_us = 0
        self._gate_max_us = 0
        self._gate_heap_start = -1

    def _inline(self, live):
        index = 0
        count = len(live)
        while index < count:
            sprite = live[index]
            sprite.x = (sprite.x + X_DELTA) % vs2.display.width
            y = sprite.y + Y_DELTA
            sprite.y = y - Y_LIMIT if y >= Y_LIMIT else y
            index += 1

    def _column(self, live):
        self.move.run(live)

    def _per_sprite(self, live):
        index = 0
        count = len(live)
        while index < count:
            self.move.run_one(live[index])
            index += 1

    def _hybrid(self, live):
        self.move.run(live)
        index = 0
        count = len(live)
        while index < count:
            # This deliberately-false branch models the decision-only tail
            # after a uniform Action prologue without adding gameplay work.
            if live[index].y < 0:
                live[index].y = 0
            index += 1

    def update(self):
        mode = self._gate_mode
        if mode is None:
            return
        started = utime.ticks_us()
        live = self.sprites
        for _ in range(PASSES_PER_TICK):
            if mode == "inline":
                self._inline(live)
            elif mode == "column":
                self._column(live)
            elif mode == "per_sprite":
                self._per_sprite(live)
            else:
                self._hybrid(live)
        elapsed = utime.ticks_diff(utime.ticks_us(), started)
        self._gate_samples += 1
        self._gate_total_us += elapsed
        if elapsed > self._gate_max_us:
            self._gate_max_us = elapsed

    def gate_start(self, mode):
        if mode not in _GATE_MODES:
            raise ValueError("unknown gate mode")
        self._gate_mode = mode
        # Let method/property caches and the update frame settle before the
        # retained-heap baseline; those one-time allocations are not a
        # dispatch-loop leak.
        warmup = 0
        while warmup < WARMUP_UPDATES:
            self.update()
            warmup += 1
        gc.collect()
        self._gate_samples = 0
        self._gate_total_us = 0
        self._gate_max_us = 0
        self._gate_heap_start = -1

    def gate_baseline(self):
        """Begin retained-heap measurement after the live loop has settled."""
        gc.collect()
        self._gate_heap_start = gc.mem_free()

    def gate_stop(self):
        self._gate_mode = None
        gc.collect()

    def gate_stats(self):
        samples = self._gate_samples
        heap_free = gc.mem_free()
        return {
            "mode": self._gate_mode or "stopped",
            "passes": PASSES_PER_TICK,
            "sprites": SPRITE_COUNT,
            "samples": samples,
            "avg_us": self._gate_total_us // samples if samples else 0,
            "max_us": self._gate_max_us,
            "heap_start": self._gate_heap_start,
            "heap_free": heap_free,
            "heap_delta": (
                heap_free - self._gate_heap_start
                if self._gate_heap_start >= 0 else -1
            ),
        }


def main():
    return Vs2BehaviorGate()
