import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parent.parent
RETRO_GO = ROOT / "apps" / "retro-go" / "components" / "retro-go"


class NativeExitTransitionTests(unittest.TestCase):
    def test_reset_and_exit_freeze_then_black_out_before_restart(self):
        bridge = (RETRO_GO / "vs_host_bridge.c").read_text()
        # "reset"/"exit" and RESYNC (see
        # docs/internals/input-protocol-v2.md#resync--device-identification)
        # both share vs_reset_and_restart(): confirm it mutes+fades before
        # restarting, and that both call sites use it.
        helper = bridge.index("static void vs_reset_and_restart(void)")
        restart = bridge.index("rg_system_restart();", helper)
        self.assertLess(bridge.index("rg_audio_set_mute(true);", helper), restart)
        self.assertLess(
            bridge.index("rg_display_fade_last_frame_to_black(500);", helper),
            restart,
        )
        self.assertIn('vs_reset_and_restart();', bridge[bridge.index('strcmp(cmd, "reset")'):])

    def test_pov_fade_freezes_the_last_frame_and_reaches_the_center(self):
        pov = (RETRO_GO / "drivers" / "display" / "ventilastation_pov.c").read_text()
        self.assertIn("if (__atomic_load_n(&vs_exit_fade_active, __ATOMIC_ACQUIRE))", pov)
        self.assertIn("led >= RG_VS_PIXELS - black_outer_leds", pov)
        self.assertIn("rg_vs_pov_fade_last_frame_to_black(uint32_t duration_ms)", pov)
        self.assertIn("__atomic_store_n(&vs_exit_black_outer_leds, RG_VS_PIXELS", pov)
        self.assertIn("vs_exit_presented_generation", pov)


if __name__ == "__main__":
    unittest.main()
