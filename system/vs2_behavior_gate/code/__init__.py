"""ESP32-S3 pre-gate microbenchmark for the VS2 behavior proposal.

This is intentionally not an implementation of Actions or Behaviors. It
measures their proposed dispatch shapes against the current VS2 Sprite facade
on the physical board before either abstraction becomes runtime API.
"""

import gc
import utime

import vs2


SPRITE_COUNT = 60
BEHAVIOR_COUNT = 10
MULTI_BEHAVIOR_SPRITES = SPRITE_COUNT // 2
# One pass is already a meaningful 60-sprite workload on the physical rotor.
# Repeating it suppresses the scene's own update cadence and turns this gate
# into a scheduler benchmark rather than a dispatch benchmark.
PASSES_PER_TICK = 1
WARMUP_UPDATES = 4
Y_LIMIT = 240
_GATE_MODES = ("inline", "column", "per_sprite", "hybrid")
_X_DELTAS = (1, 2, -1, 3, -2, 1, -3, 2, -1, 3)
_Y_DELTAS = (1, -1, 2, 1, -2, 3, 1, -3, 2, -1)


class BehaviorKernel:
    """One distinct proposed Behavior/Action kernel, sealed at build time."""

    def __init__(self, speed_x, speed_y):
        self.speed_x = speed_x
        self.speed_y = speed_y

    def run(self, members):
        dx = self.speed_x
        dy = self.speed_y
        index = 0
        count = len(members)
        while index < count:
            sprite = members[index]
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
        self.primary = []
        self.secondary = []
        self.members = [[] for _ in range(BEHAVIOR_COUNT)]
        for index in range(SPRITE_COUNT):
            sprite = layer.sprite(
                "galaga.png",
                x=(index * 37) % vs2.display.width,
                y=(index * 13) % Y_LIMIT,
                frame=index % 12,
            )
            primary = index % BEHAVIOR_COUNT
            secondary = -1
            self.sprites.append(sprite)
            self.primary.append(primary)
            self.secondary.append(secondary)
            self.members[primary].append(sprite)
            # The latter half has both a primary and independent secondary
            # behavior: 90 active behavior slots across 60 sprites.
            if index >= MULTI_BEHAVIOR_SPRITES:
                secondary = (primary + 3) % BEHAVIOR_COUNT
                self.secondary[index] = secondary
                self.members[secondary].append(sprite)
        self.kernels = []
        index = 0
        while index < BEHAVIOR_COUNT:
            self.kernels.append(BehaviorKernel(
                _X_DELTAS[index], _Y_DELTAS[index]
            ))
            index += 1
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
            behavior = self.primary[index]
            sprite.x = (sprite.x + _X_DELTAS[behavior]) % vs2.display.width
            y = sprite.y + _Y_DELTAS[behavior]
            sprite.y = y - Y_LIMIT if y >= Y_LIMIT else y
            behavior = self.secondary[index]
            if behavior >= 0:
                sprite.x = (sprite.x + _X_DELTAS[behavior]) % vs2.display.width
                y = sprite.y + _Y_DELTAS[behavior]
                sprite.y = y - Y_LIMIT if y >= Y_LIMIT else y
            index += 1

    def _column(self):
        index = 0
        while index < BEHAVIOR_COUNT:
            self.kernels[index].run(self.members[index])
            index += 1

    def _per_sprite(self, live):
        index = 0
        count = len(live)
        while index < count:
            self.kernels[self.primary[index]].run_one(live[index])
            behavior = self.secondary[index]
            if behavior >= 0:
                self.kernels[behavior].run_one(live[index])
            index += 1

    def _hybrid(self, live):
        self._column()
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
        pass_index = 0
        while pass_index < PASSES_PER_TICK:
            if mode == "inline":
                self._inline(live)
            elif mode == "column":
                self._column()
            elif mode == "per_sprite":
                self._per_sprite(live)
            else:
                self._hybrid(live)
            pass_index += 1
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
            "behaviors": BEHAVIOR_COUNT,
            "multi_behavior_sprites": MULTI_BEHAVIOR_SPRITES,
            "behavior_slots": SPRITE_COUNT + MULTI_BEHAVIOR_SPRITES,
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
