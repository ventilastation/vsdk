"""Entry point for games/vs2_examples/event_sheet_demo.

The T16 "event sheet" proving case: a small, original three-scene game
(title screen, playable scene, game over, with a score surviving the
scene transition) authored almost entirely through
tools/vs2_event_gen -- see that package's own docstring, and this task's
report, for exactly how much of it is generated versus the one
hand-written escape hatch (Title's "press A" button check).
"""

from games.vs2_examples.event_sheet_demo.code.title_scene import Title


def main():
    return Title()
