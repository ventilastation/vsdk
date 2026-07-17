import ctypes
import math
import random
import time
import traceback

import pyglet

if pyglet.version < "2.0":
    raise RuntimeError("Pyglet 2.0 or higher is required")

import pyglet.math as pm
from pyglet import shapes
from pyglet.gl import GL_FUNC_ADD, GL_MAX, GL_SRC_COLOR, Config, glBlendEquation
from pyglet.gl import (
    glActiveTexture,
    glBindTexture,
    glEnable,
    glBlendFunc,
    glDisable,
    glFinish,
    glTexSubImage2D,
    GL_TEXTURE0,
    GL_TEXTURE1,
    GL_TEXTURE_2D,
    GL_TRIANGLES,
    GL_BLEND,
    GL_RGBA,
    GL_RGBA8,
    GL_UNSIGNED_BYTE,
    GL_NEAREST,
)
from pyglet.math import Mat4
from pyglet.graphics import Group
from pyglet.graphics.shader import Shader, ShaderProgram

import numpy as np

import comms
import config
from povrender import (
    COLUMNS, render_frame, snapshot_scene_shader_input, snapshot_vs2_scene,
)
from scene_shader import DesktopSceneCompositor

display_enabled = config.DISPLAY_ENABLED
pyglet.options['vsync'] = display_enabled

###############################
# Define a basic Shader Program
###############################
_vertex_source = """#version 330 core
    in vec2 position;
    in vec3 tex_coords;
    in vec2 led_uv;
    out vec3 texture_coords;
    out vec2 v_led_uv;

    uniform WindowBlock
    {                       // This UBO is defined on Window creation, and available
        mat4 projection;    // in all Shaders. You can modify these matrixes with the
        mat4 view;          // Window.view and Window.projection properties.
    } window;

    void main()
    {
        gl_Position = window.projection * window.view * vec4(position, 1, 1);
        texture_coords = tex_coords;
        v_led_uv = led_uv;
    }
"""

_fragment_source = """#version 330 core
    in vec3 texture_coords;
    in vec2 v_led_uv;
    out vec4 final_colors;

    uniform sampler2D our_texture;
    uniform sampler2D led_colors;

    // Pill shape with bloom glow
    void main() {
        vec2 uv = texture_coords.xy;
        vec2 center = vec2(0.5);
        vec2 p = uv - center;

        // Pill dimensions
        float width = 0.1;
        float height = 0.05;
        float radius = height;

        // Distance to pill shape
        vec2 q = abs(p) - vec2(width - radius, height - radius);
        float dist = length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - radius;

        float pill = smoothstep(0.01, -0.01, dist);
        float glow = exp(-dist * dist * 10.0) * 0.3;

        vec4 led_color = texture(led_colors, v_led_uv);
        final_colors = led_color * (pill + glow);
    }

"""

vert_shader = Shader(_vertex_source, 'vertex')
frag_shader = Shader(_fragment_source, 'fragment')
shader_program = ShaderProgram(vert_shader, frag_shader)

#####################################################
# Define a custom `Group` to encapsulate OpenGL state
#####################################################
class RenderGroup(Group):
    """A Group that enables and binds two Textures and a ShaderProgram.

    `texture` (unit 0) is the glow/pill shape; `led_texture` (unit 1) holds
    the current frame's per-LED colors, sampled directly in the fragment
    shader instead of carrying them as a per-vertex attribute (see
    display_draw()). RenderGroups are equal if their Textures and
    ShaderProgram are equal.
    """
    def __init__(self, texture, led_texture, program, order=0, parent=None):
        """Create a RenderGroup.

        :Parameters:
            `texture` : `~pyglet.image.Texture`
                Glow/pill shape texture to bind on unit 0.
            `led_texture` : `~pyglet.image.Texture`
                Per-LED color data texture to bind on unit 1.
            `program` : `~pyglet.graphics.shader.ShaderProgram`
                ShaderProgram to use.
            `order` : int
                Change the order to render above or below other Groups.
            `parent` : `~pyglet.graphics.Group`
                Parent group.
        """
        super().__init__(order, parent)
        self.texture = texture
        self.led_texture = led_texture
        self.program = program

    def set_state(self):
        glActiveTexture(GL_TEXTURE0)
        glBindTexture(self.texture.target, self.texture.id)
        glActiveTexture(GL_TEXTURE1)
        glBindTexture(self.led_texture.target, self.led_texture.id)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_COLOR, GL_SRC_COLOR)
        glBlendEquation(GL_MAX)
        self.program.use()

    def unset_state(self):
        glBlendEquation(GL_FUNC_ADD)
        glDisable(GL_BLEND)

    def __hash__(self):
        return hash((self.texture.target, self.texture.id, self.led_texture.id,
                     self.order, self.parent, self.program))

    def __eq__(self, other):
        return (self.__class__ is other.__class__ and
                self.texture.target == other.texture.target and
                self.texture.id == other.texture.id and
                self.led_texture.id == other.led_texture.id and
                self.order == other.order and
                self.program == other.program and
                self.parent == other.parent)


window = pyglet.window.Window(config=Config(double_buffer=display_enabled), fullscreen=config.FULLSCREEN, resizable=True)
logo = pyglet.image.load("logo.png")
window.set_icon(logo)
window.set_caption("Ventilastation Emulator")
fps_display = pyglet.window.FPSDisplay(window)
scene_renderer_label = pyglet.text.Label(
    "", font_name="Arial", font_size=11, x=8, y=window.height - 7,
    color=(150, 190, 255, 255), anchor_y="top",
)
batch = pyglet.graphics.Batch()


led_count = 54
LED_SIZE = 100
vertex_list = None
texture = pyglet.image.load("glow.png").get_texture(rectangle=True)
# Per-LED color data as a small texture instead of a per-vertex attribute:
# one texel per LED (COLUMNS x led_count), updated wholesale each frame via
# glTexSubImage2D in display_draw(). GL_NEAREST so sampling never blends
# neighboring LEDs/columns together.
led_color_texture = pyglet.image.Texture.create(
    COLUMNS, led_count, target=GL_TEXTURE_2D, internalformat=GL_RGBA8,
    min_filter=GL_NEAREST, mag_filter=GL_NEAREST, fmt=GL_RGBA,
)
group = RenderGroup(texture, led_color_texture, shader_program)
# our_texture (unit 0, the glow/pill shape) isn't actually sampled in the
# fragment shader -- the pill/glow effect is procedural, computed from
# texture_coords directly -- so the GLSL compiler optimizes that uniform
# away and setting it would raise. Only led_colors (unit 1) is real.
shader_program.use()
shader_program["led_colors"] = 1
shader_program.stop()

# The conventional/native frame compositor remains the default.  The shader
# is instantiated only when selected so a normal emulator startup never pays
# a compilation cost (and so a driver without integer textures has a clean
# CPU fallback).
scene_renderer = config.SCENE_RENDERER
scene_compositor = None
scene_renderer_status = "F2 switches CPU/shader · F3 measures this scene"


def _update_scene_renderer_label():
    scene_renderer_label.text = "Scene renderer: %s  |  %s" % (
        "GPU shader" if scene_renderer == "shader" else "CPU",
        scene_renderer_status,
    )


# The display itself stays uncluttered.  A small toolbar opens the two
# overlays; those overlays are deliberately modal so a click through a panel
# never changes a game input or a workbench setting by accident.
OVERLAY_HELP = "help"
OVERLAY_SETTINGS = "settings"
active_overlay = None

_toolbar_radius = 15
toolbar_settings_button = shapes.Circle(0, 0, _toolbar_radius, color=(50, 68, 88))
toolbar_help_button = shapes.Circle(0, 0, _toolbar_radius, color=(50, 68, 88))
toolbar_settings_label = pyglet.text.Label(
    "⚙", font_name="Arial", font_size=18, anchor_x="center", anchor_y="center",
    color=(238, 244, 255, 255),
)
toolbar_help_label = pyglet.text.Label(
    "?", font_name="Arial", font_size=17, weight="bold", anchor_x="center", anchor_y="center",
    color=(238, 244, 255, 255),
)

overlay_scrim = shapes.Rectangle(0, 0, 1, 1, color=(0, 0, 0))
overlay_scrim.opacity = 175
overlay_panel = shapes.Rectangle(0, 0, 1, 1, color=(19, 26, 37))
overlay_panel.opacity = 248
overlay_header = shapes.Rectangle(0, 0, 1, 1, color=(39, 59, 82))
overlay_close_button = shapes.Rectangle(0, 0, 1, 1, color=(86, 52, 56))
overlay_title_label = pyglet.text.Label(
    "", font_name="Arial", font_size=17, weight="bold", anchor_y="top",
    color=(241, 245, 255, 255),
)
overlay_body_label = pyglet.text.Label(
    "", width=1, font_name="Arial", font_size=12, anchor_y="top", multiline=True,
    color=(210, 220, 234, 255),
)
overlay_close_label = pyglet.text.Label(
    "Close  ×", font_name="Arial", font_size=10, anchor_x="center", anchor_y="center",
    color=(255, 242, 242, 255),
)

_HELP_TEXT = """Player 1
  Arrows or WASD — move
  Space — A/action     O — B     P — X     Y — Y
  Page Up — Start      Page Down — Back

Player 2
  H J K L — left/down/up/right
  Z — A     X — B     C — X     V — Y
  Home — Start         End — Back

Gamepads
  One pad: left stick/D-pad is Player 1; right stick and shoulders are Player 2.
  Two pads: the second pad controls Player 2.

Emulator
  F1 — keyboard help   F4 — settings
  F2 — CPU/GPU renderer   F3 — renderer comparison
  Ctrl/⌘-U — send an OTA upgrade   Q — quit
  Esc — close this panel, or send the extra game button"""


def _point_in_circle(x, y, center_x, center_y, radius):
    return (x - center_x) ** 2 + (y - center_y) ** 2 <= radius ** 2


def _layout_toolbar():
    y = window.height - 24
    help_x = window.width - 24
    settings_x = help_x - 38
    toolbar_help_button.position = (help_x, y)
    toolbar_settings_button.position = (settings_x, y)
    toolbar_help_label.position = (help_x, y - 1, 0)
    toolbar_settings_label.position = (settings_x, y - 1, 0)
    toolbar_help_button.color = (78, 108, 145) if active_overlay == OVERLAY_HELP else (50, 68, 88)
    toolbar_settings_button.color = (78, 108, 145) if active_overlay == OVERLAY_SETTINGS else (50, 68, 88)


def _draw_toolbar():
    _layout_toolbar()
    toolbar_settings_button.draw()
    toolbar_help_button.draw()
    toolbar_settings_label.draw()
    toolbar_help_label.draw()


def _overlay_bounds(kind):
    max_width = max(280, window.width - 40)
    max_height = max(220, window.height - 40)
    desired_height = 390 if kind == OVERLAY_HELP else 300
    width = min(580, max_width)
    height = min(desired_height, max_height)
    return ((window.width - width) / 2, (window.height - height) / 2, width, height)


def _layout_overlay(kind):
    left, bottom, width, height = _overlay_bounds(kind)
    overlay_scrim.position = (0, 0)
    overlay_scrim.width, overlay_scrim.height = window.width, window.height
    overlay_panel.position = (left, bottom)
    overlay_panel.width, overlay_panel.height = width, height
    overlay_header.position = (left, bottom + height - 42)
    overlay_header.width, overlay_header.height = width, 42
    overlay_close_button.position = (left + width - 82, bottom + height - 33)
    overlay_close_button.width, overlay_close_button.height = 66, 24
    overlay_close_label.position = (left + width - 49, bottom + height - 21, 0)
    overlay_title_label.position = (left + 18, bottom + height - 12, 0)
    overlay_body_label.position = (left + 22, bottom + height - 58, 0)
    overlay_body_label.width = width - 44
    return left, bottom, width, height


def toggle_help_overlay():
    global active_overlay
    active_overlay = None if active_overlay == OVERLAY_HELP else OVERLAY_HELP


def toggle_settings_overlay():
    global active_overlay
    active_overlay = None if active_overlay == OVERLAY_SETTINGS else OVERLAY_SETTINGS


def dismiss_overlay():
    """Close the modal panel and report whether there was one to close."""
    global active_overlay
    if active_overlay is None:
        return False
    active_overlay = None
    return True


def _draw_overlay():
    if active_overlay is None:
        return
    left, bottom, width, height = _layout_overlay(active_overlay)
    overlay_scrim.draw()
    overlay_panel.draw()
    overlay_header.draw()
    overlay_close_button.draw()
    if active_overlay == OVERLAY_HELP:
        overlay_title_label.text = "Keyboard shortcuts"
        overlay_body_label.text = _HELP_TEXT
    else:
        overlay_title_label.text = "Settings & workbench"
        overlay_body_label.text = "Rotation, board reset and upgrade, colour calibration, and POV timing tools."
        _layout_settings_controls(left, bottom, width, height)
    overlay_title_label.draw()
    overlay_body_label.draw()
    overlay_close_label.draw()
    if active_overlay == OVERLAY_SETTINGS:
        draw_workbench_controls()


def _ensure_scene_compositor():
    global scene_compositor
    if scene_compositor is None:
        scene_compositor = DesktopSceneCompositor()
    return scene_compositor


def set_scene_renderer(renderer):
    """Select ``cpu`` or the raw-scene OpenGL compositor (Pyglet 2 only)."""
    global scene_renderer, scene_renderer_status
    if renderer not in ("cpu", "shader"):
        raise ValueError("unknown scene renderer: %s" % renderer)
    if renderer == "shader":
        try:
            _ensure_scene_compositor()
        except Exception as error:
            scene_renderer = "cpu"
            scene_renderer_status = "shader unavailable: %s" % error
            _update_scene_renderer_label()
            print("Scene shader disabled:", error)
            return scene_renderer
    scene_renderer = renderer
    scene_renderer_status = "F2 switches CPU/shader · F3 measures this scene"
    _update_scene_renderer_label()
    return scene_renderer


def toggle_scene_renderer():
    return set_scene_renderer("cpu" if scene_renderer == "shader" else "shader")


def _upload_cpu_frame(pixels):
    """Upload the established CPU/native compositor result to the LED texture."""
    image = np.ascontiguousarray(pixels.reshape(COLUMNS, led_count).T)
    glBindTexture(GL_TEXTURE_2D, led_color_texture.id)
    glTexSubImage2D(
        GL_TEXTURE_2D, 0, 0, 0, COLUMNS, led_count,
        GL_RGBA, GL_UNSIGNED_BYTE,
        image.ctypes.data_as(ctypes.c_void_p),
    )


def compare_scene_renderers(samples=12):
    """Benchmark current scene once through both paths and verify pixels.

    The CPU timing includes native/Python full-frame composition and its LED
    texture upload.  The GPU timing includes scene packing, texture uploads,
    and a ``glFinish`` so it measures completed work rather than merely queued
    commands.  This makes the F3 readout useful across desktops with very
    different graphics drivers.
    """
    global scene_renderer_status
    scene_input = snapshot_scene_shader_input()
    if scene_input is None:
        scene_renderer_status = "comparison needs sprites or a VS2 scene (not a captured frame)"
        _update_scene_renderer_label()
        return scene_renderer_status
    try:
        compositor = _ensure_scene_compositor()
        vs2_scene = snapshot_vs2_scene()
        # Warm up allocations/program state outside the measurement loop.
        compositor.render(scene_input, led_color_texture)
        glFinish()
        _upload_cpu_frame(render_frame(vs2_scene))
        glFinish()

        cpu_start = time.perf_counter()
        cpu_pixels = None
        for _ in range(samples):
            cpu_pixels = render_frame(vs2_scene)
            _upload_cpu_frame(cpu_pixels)
        glFinish()
        cpu_ms = (time.perf_counter() - cpu_start) * 1000 / samples

        gpu_start = time.perf_counter()
        for _ in range(samples):
            compositor.render(scene_input, led_color_texture)
        glFinish()
        gpu_ms = (time.perf_counter() - gpu_start) * 1000 / samples

        gpu_rgba = compositor.read_pixels()
        cpu_rgba = np.ascontiguousarray(cpu_pixels.view(np.uint8).reshape(-1, 4))
        equal = np.array_equal(gpu_rgba, cpu_rgba)
        ratio = cpu_ms / gpu_ms if gpu_ms else float("inf")
        scene_renderer_status = "CPU %.2f ms | shader %.2f ms | %.1fx | %s" % (
            cpu_ms, gpu_ms, ratio, "pixels match" if equal else "PIXELS DIFFER",
        )
    except Exception as error:
        scene_renderer_status = "comparison failed: %s" % error
        traceback.print_exc()
    _update_scene_renderer_label()
    print("Scene renderer:", scene_renderer_status)
    return scene_renderer_status


_update_scene_renderer_label()

def display_init(led_count):
    """Build the LED quad geometry as an indexed vertex list.

    Each LED quad has 4 distinct corners; the previous non-indexed list
    stored 6 vertices per LED (2 duplicated) so every triangle could inline
    its own corners. That meant the "colors" attribute -- the one thing
    updated every frame from the rendered pixels -- carried 6x redundant
    copies of the same per-LED color, tripling the pack/upload cost for no
    visual difference. Indexing lets each corner (and its color) exist once,
    referenced twice by the index buffer for its two triangles.
    """
    led_step = (LED_SIZE / led_count)
    vertex_pos = []
    led_uv = []
    theta = (math.pi * 2 / COLUMNS)
    def arc_chord(r):
        return 2 * r * math.sin(theta / 2)

    indices = []

    for column in range(COLUMNS):
        x1, x2 = 0, 0
        for i in range(led_count):
            y1 = led_step * i - (led_step * 2.5)
            y2 = y1 + (led_step * 5)
            x3 = arc_chord(y2) * 3.5
            x4 = -x3

            angle = -theta * column + math.pi
            v1 = pm.Vec2(x1, y1).rotate(angle)
            v2 = pm.Vec2(x2, y1).rotate(angle)
            v3 = pm.Vec2(x4, y2).rotate(angle)
            v4 = pm.Vec2(x3, y2).rotate(angle)
            # 4 unique corners; the original two triangles were (v1,v2,v3)
            # and (v1,v3,v4), reproduced here via indices instead of
            # duplicating v1/v3 in the vertex data itself.
            base = (column * led_count + i) * 4
            vertex_pos.extend([v1.x, v1.y, v2.x, v2.y, v3.x, v3.y, v4.x, v4.y])
            indices.extend([base, base + 1, base + 2, base, base + 2, base + 3])
            # Texel center for this LED in led_color_texture (COLUMNS wide,
            # led_count tall); identical for all 4 corners -- it's which LED
            # this quad is, not a per-corner value.
            u = (column + 0.5) / COLUMNS
            v = (i + 0.5) / led_count
            led_uv.extend([u, v] * 4)
            x1, x2 = x3, x4

    texture_pos = (0.0, 0.0, 0, 1.0, 0.0, 0, 1.0, 1.0, 0, 0.0, 1.0, 0) * led_count * COLUMNS

    global vertex_list
    vertex_list = shader_program.vertex_list_indexed(
        led_count * 4 * COLUMNS,
        GL_TRIANGLES,
        indices,
        position=('f', vertex_pos),
        led_uv=('f', led_uv),
        tex_coords=('f', texture_pos),
        group=group,
        batch=batch
    )

@window.event
def on_resize(width, height):
    print(f'The window was resized to {width},{height}')

#################################################################
# Workbench controls: an RPM slider (0-700, default 600) and a
# reset button, for interacting with the hardware workbench over
# Wi-Fi (see comms.send_workbench and vsdk/docs/internals/workbench.md). Harmless
# no-ops when not connected to a real workbench.
#################################################################
RPM_MIN, RPM_MAX, RPM_DEFAULT = 0, 700, 600

controls_batch = pyglet.graphics.Batch()

_slider_x, _slider_y, _slider_w, _slider_h = 20, 20, 200, 6
_handle_radius = 9

_current_rpm = RPM_DEFAULT
_last_sent_rpm = None
_dragging_slider = False


def _rpm_to_x(rpm):
    frac = (rpm - RPM_MIN) / (RPM_MAX - RPM_MIN)
    return _slider_x + frac * _slider_w


def _x_to_rpm(x):
    frac = max(0.0, min(1.0, (x - _slider_x) / _slider_w))
    return round(RPM_MIN + frac * (RPM_MAX - RPM_MIN))


slider_track = shapes.Rectangle(_slider_x, _slider_y, _slider_w, _slider_h,
                                 color=(90, 90, 90), batch=controls_batch)
slider_handle = shapes.Circle(_rpm_to_x(_current_rpm), _slider_y + _slider_h / 2, _handle_radius,
                               color=(255, 180, 0), batch=controls_batch)
rpm_label = pyglet.text.Label(f"RPM: {_current_rpm}", font_name="Arial", font_size=11,
                               x=_slider_x, y=_slider_y + 16,
                               color=(220, 220, 220, 255), batch=controls_batch)
settings_rotation_label = pyglet.text.Label("Rotation & board", font_name="Arial", font_size=10,
                                             color=(150, 180, 210, 255), batch=controls_batch)

_reset_x, _reset_y, _reset_w, _reset_h = 250, 12, 70, 24
reset_button = shapes.Rectangle(_reset_x, _reset_y, _reset_w, _reset_h,
                                 color=(120, 40, 40), batch=controls_batch)
reset_label = pyglet.text.Label("RESET", font_name="Arial", font_size=11,
                                 x=_reset_x + _reset_w / 2, y=_reset_y + _reset_h / 2,
                                 anchor_x="center", anchor_y="center",
                                 color=(255, 255, 255, 255), batch=controls_batch)

_ota_x, _ota_y, _ota_w, _ota_h = 330, 12, 70, 24
ota_button = shapes.Rectangle(_ota_x, _ota_y, _ota_w, _ota_h,
                               color=(40, 80, 140), batch=controls_batch)
ota_label = pyglet.text.Label("UPGRADE", font_name="Arial", font_size=11,
                               x=_ota_x + _ota_w / 2, y=_ota_y + _ota_h / 2,
                               anchor_x="center", anchor_y="center",
                               color=(255, 255, 255, 255), batch=controls_batch)

# Board colour calibration controls. Their values always originate from an
# acknowledged ``povcal_state`` profile; dragging sends an edit but the board
# response remains authoritative and snaps the controls to the active value.
_cal_x, _cal_y, _cal_w, _cal_h = 20, 70, 200, 5
_cal_handle_radius = 7
_cal_generation_seen = None
_cal_dragging = None
_cal_master_max = 4000
_cal_radial_max = 4000
_cal_last_sent = {"master": None, "radial_exponent": None}

cal_master_track = shapes.Rectangle(_cal_x, _cal_y, _cal_w, _cal_h,
                                    color=(70, 70, 70), batch=controls_batch)
cal_radial_track = shapes.Rectangle(_cal_x, _cal_y + 32, _cal_w, _cal_h,
                                    color=(70, 70, 70), batch=controls_batch)
cal_master_handle = shapes.Circle(_cal_x, _cal_y + _cal_h / 2, _cal_handle_radius,
                                  color=(100, 190, 255), batch=controls_batch)
cal_radial_handle = shapes.Circle(_cal_x, _cal_y + 32 + _cal_h / 2, _cal_handle_radius,
                                  color=(160, 220, 110), batch=controls_batch)
cal_master_label = pyglet.text.Label("Master: waiting", font_name="Arial", font_size=10,
                                     x=_cal_x, y=_cal_y + 10,
                                     color=(210, 210, 210, 255), batch=controls_batch)
cal_radial_label = pyglet.text.Label("Radial: waiting", font_name="Arial", font_size=10,
                                     x=_cal_x, y=_cal_y + 42,
                                     color=(210, 210, 210, 255), batch=controls_batch)
cal_status_label = pyglet.text.Label("POV CAL: waiting for board profile", font_name="Arial", font_size=10,
                                     x=_cal_x, y=_cal_y + 60,
                                     color=(150, 180, 210, 255), batch=controls_batch)

_cal_commit_x, _cal_revert_x, _cal_factory_x = 240, 310, 390
_cal_button_y, _cal_button_w, _cal_button_h = 70, 62, 22
cal_commit_button = shapes.Rectangle(_cal_commit_x, _cal_button_y, _cal_button_w, _cal_button_h,
                                     color=(42, 100, 66), batch=controls_batch)
cal_revert_button = shapes.Rectangle(_cal_revert_x, _cal_button_y, _cal_button_w, _cal_button_h,
                                     color=(80, 70, 38), batch=controls_batch)
cal_factory_button = shapes.Rectangle(_cal_factory_x, _cal_button_y, _cal_button_w, _cal_button_h,
                                      color=(80, 46, 46), batch=controls_batch)

cal_button_labels = []
for text, x in (("SAVE", _cal_commit_x), ("REVERT", _cal_revert_x), ("FACTORY", _cal_factory_x)):
    cal_button_labels.append(pyglet.text.Label(text, font_name="Arial", font_size=9,
                        x=x + _cal_button_w / 2, y=_cal_button_y + _cal_button_h / 2,
                        anchor_x="center", anchor_y="center",
                        color=(255, 255, 255, 255), batch=controls_batch)
    )

# POV render timing controls. A capture start picks one encoder before
# enabling measurement; STOP prints the board's final ``povperf`` report in
# the emulator console.
_perf_legacy_x, _perf_stop_x, _perf_calibrated_x = 240, 330, 405
_perf_button_y, _perf_button_h = 102, 22
_perf_legacy_w, _perf_stop_w, _perf_calibrated_w = 85, 70, 100
perf_legacy_button = shapes.Rectangle(_perf_legacy_x, _perf_button_y, _perf_legacy_w, _perf_button_h,
                                      color=(92, 66, 26), batch=controls_batch)
perf_stop_button = shapes.Rectangle(_perf_stop_x, _perf_button_y, _perf_stop_w, _perf_button_h,
                                    color=(105, 45, 45), batch=controls_batch)
perf_calibrated_button = shapes.Rectangle(_perf_calibrated_x, _perf_button_y, _perf_calibrated_w, _perf_button_h,
                                          color=(37, 74, 112), batch=controls_batch)
settings_performance_label = pyglet.text.Label("On-device POV timing", font_name="Arial", font_size=10,
                                                color=(150, 180, 210, 255), batch=controls_batch)
perf_button_labels = []
for text, x, width in (("LEGACY START", _perf_legacy_x, _perf_legacy_w),
                       ("STOP / PRINT", _perf_stop_x, _perf_stop_w),
                       ("CAL. START", _perf_calibrated_x, _perf_calibrated_w)):
    perf_button_labels.append(pyglet.text.Label(text, font_name="Arial", font_size=8,
                        x=x + width / 2, y=_perf_button_y + _perf_button_h / 2,
                        anchor_x="center", anchor_y="center",
                        color=(255, 255, 255, 255), batch=controls_batch)
    )


def _layout_settings_controls(left, bottom, width, height):
    """Place the existing hardware controls inside the modal settings card."""
    global _slider_x, _slider_y, _reset_x, _reset_y, _ota_x, _ota_y
    global _cal_x, _cal_y, _cal_commit_x, _cal_revert_x, _cal_factory_x, _cal_button_y
    global _perf_legacy_x, _perf_stop_x, _perf_calibrated_x, _perf_button_y

    content_x = left + 22
    _slider_x, _slider_y = content_x, bottom + 181
    _reset_x, _reset_y = content_x + 232, bottom + 174
    _ota_x, _ota_y = content_x + 314, bottom + 174
    _cal_x, _cal_y = content_x, bottom + 112
    _cal_commit_x, _cal_revert_x, _cal_factory_x = content_x + 232, content_x + 302, content_x + 382
    _cal_button_y = _cal_y - 5
    _perf_legacy_x, _perf_stop_x, _perf_calibrated_x = content_x + 232, content_x + 327, content_x + 409
    _perf_button_y = bottom + 16

    settings_rotation_label.x, settings_rotation_label.y = content_x, bottom + 216
    slider_track.position = (_slider_x, _slider_y)
    slider_handle.position = (_rpm_to_x(_current_rpm), _slider_y + _slider_h / 2)
    rpm_label.x, rpm_label.y = _slider_x, _slider_y + 16
    reset_button.position = (_reset_x, _reset_y)
    reset_label.x, reset_label.y = _reset_x + _reset_w / 2, _reset_y + _reset_h / 2
    ota_button.position = (_ota_x, _ota_y)
    ota_label.x, ota_label.y = _ota_x + _ota_w / 2, _ota_y + _ota_h / 2

    cal_status_label.x, cal_status_label.y = _cal_x, bottom + 151
    cal_master_track.position = (_cal_x, _cal_y)
    cal_radial_track.position = (_cal_x, _cal_y - 38)
    cal_master_handle.y = _cal_y + _cal_h / 2
    cal_radial_handle.y = _cal_y - 38 + _cal_h / 2
    cal_master_label.x, cal_master_label.y = _cal_x, _cal_y + 10
    cal_radial_label.x, cal_radial_label.y = _cal_x, _cal_y - 28
    for button, x in ((cal_commit_button, _cal_commit_x),
                      (cal_revert_button, _cal_revert_x),
                      (cal_factory_button, _cal_factory_x)):
        button.position = (x, _cal_button_y)
    for label, x in zip(cal_button_labels, (_cal_commit_x, _cal_revert_x, _cal_factory_x)):
        label.x, label.y = x + _cal_button_w / 2, _cal_button_y + _cal_button_h / 2

    settings_performance_label.x, settings_performance_label.y = _perf_legacy_x, _perf_button_y + 31
    perf_legacy_button.position = (_perf_legacy_x, _perf_button_y)
    perf_stop_button.position = (_perf_stop_x, _perf_button_y)
    perf_calibrated_button.position = (_perf_calibrated_x, _perf_button_y)
    for label, x, button_width in zip(
            perf_button_labels,
            (_perf_legacy_x, _perf_stop_x, _perf_calibrated_x),
            (_perf_legacy_w, _perf_stop_w, _perf_calibrated_w)):
        label.x, label.y = x + button_width / 2, _perf_button_y + _perf_button_h / 2

def _set_rpm(rpm):
    global _current_rpm, _last_sent_rpm
    rpm = max(RPM_MIN, min(RPM_MAX, round(rpm)))
    _current_rpm = rpm
    slider_handle.x = _rpm_to_x(rpm)
    rpm_label.text = f"RPM: {rpm}"
    if rpm != _last_sent_rpm:
        comms.send_workbench(f"rpm {rpm}".encode())
        _last_sent_rpm = rpm


def _cal_value_to_x(value, maximum):
    return _cal_x + max(0.0, min(1.0, value / maximum)) * _cal_w


def _cal_x_to_value(x, maximum):
    return round(max(0.0, min(1.0, (x - _cal_x) / _cal_w)) * maximum)


def _sync_calibration_controls():
    global _cal_generation_seen
    state = comms.povcal_state
    cal_status_label.text = state.status_text()
    if not state.ready or state.generation == _cal_generation_seen:
        return
    profile = state.profile
    _cal_generation_seen = profile.generation
    cal_master_handle.x = _cal_value_to_x(profile.master_milli, _cal_master_max)
    cal_radial_handle.x = _cal_value_to_x(profile.radial_exponent_milli, _cal_radial_max)
    cal_master_label.text = "Master: %d" % profile.master_milli
    cal_radial_label.text = "Radial: %d" % profile.radial_exponent_milli


def _set_calibration_value(name, value):
    if name == "master":
        cal_master_handle.x = _cal_value_to_x(value, _cal_master_max)
        cal_master_label.text = "Master: %d (applying)" % value
    else:
        cal_radial_handle.x = _cal_value_to_x(value, _cal_radial_max)
        cal_radial_label.text = "Radial: %d (applying)" % value
    if _cal_last_sent[name] != value:
        _cal_last_sent[name] = value
        comms.send_povcal("set %s %d" % (name, value))


def _point_in_rect(x, y, rx, ry, rw, rh):
    return rx <= x <= rx + rw and ry <= y <= ry + rh


def _unflash_reset_button(dt=None):
    reset_button.color = (120, 40, 40)


def _unflash_ota_button(dt=None):
    ota_button.color = (40, 80, 140)


@window.event
def on_mouse_press(x, y, button, modifiers):
    global _dragging_slider, _cal_dragging
    _layout_toolbar()
    if _point_in_circle(x, y, *toolbar_help_button.position, _toolbar_radius):
        toggle_help_overlay()
        return pyglet.event.EVENT_HANDLED
    if _point_in_circle(x, y, *toolbar_settings_button.position, _toolbar_radius):
        toggle_settings_overlay()
        return pyglet.event.EVENT_HANDLED
    if active_overlay is None:
        return pyglet.event.EVENT_HANDLED

    left, bottom, width, height = _layout_overlay(active_overlay)
    if _point_in_rect(x, y, overlay_close_button.x, overlay_close_button.y,
                      overlay_close_button.width, overlay_close_button.height):
        dismiss_overlay()
        return pyglet.event.EVENT_HANDLED
    if not _point_in_rect(x, y, left, bottom, width, height):
        dismiss_overlay()
        return pyglet.event.EVENT_HANDLED
    if active_overlay != OVERLAY_SETTINGS:
        return pyglet.event.EVENT_HANDLED
    _layout_settings_controls(left, bottom, width, height)

    if _point_in_rect(x, y, _slider_x - _handle_radius, _slider_y - _handle_radius,
                       _slider_w + 2 * _handle_radius, _slider_h + 2 * _handle_radius):
        _dragging_slider = True
        _set_rpm(_x_to_rpm(x))
    elif _point_in_rect(x, y, _reset_x, _reset_y, _reset_w, _reset_h):
        comms.send_workbench(b"reset")
        reset_button.color = (220, 80, 80)
        pyglet.clock.schedule_once(_unflash_reset_button, 0.2)
    elif _point_in_rect(x, y, _ota_x, _ota_y, _ota_w, _ota_h):
        comms.trigger_ota()
        ota_button.color = (80, 140, 220)
        pyglet.clock.schedule_once(_unflash_ota_button, 0.2)
    elif _point_in_rect(x, y, _cal_x - _cal_handle_radius, _cal_y - _cal_handle_radius,
                       _cal_w + 2 * _cal_handle_radius, _cal_h + 2 * _cal_handle_radius):
        _cal_dragging = "master"
        _set_calibration_value("master", _cal_x_to_value(x, _cal_master_max))
    elif _point_in_rect(x, y, _cal_x - _cal_handle_radius, _cal_y - 38 - _cal_handle_radius,
                       _cal_w + 2 * _cal_handle_radius, _cal_h + 2 * _cal_handle_radius):
        _cal_dragging = "radial_exponent"
        _set_calibration_value("radial_exponent", _cal_x_to_value(x, _cal_radial_max))
    elif _point_in_rect(x, y, _cal_commit_x, _cal_button_y, _cal_button_w, _cal_button_h):
        comms.send_povcal("commit")
    elif _point_in_rect(x, y, _cal_revert_x, _cal_button_y, _cal_button_w, _cal_button_h):
        comms.send_povcal("revert")
    elif _point_in_rect(x, y, _cal_factory_x, _cal_button_y, _cal_button_w, _cal_button_h):
        comms.send_povcal("factory")
    elif _point_in_rect(x, y, _perf_legacy_x, _perf_button_y, _perf_legacy_w, _perf_button_h):
        comms.start_povperf_capture("legacy")
    elif _point_in_rect(x, y, _perf_stop_x, _perf_button_y, _perf_stop_w, _perf_button_h):
        comms.stop_povperf_capture()
    elif _point_in_rect(x, y, _perf_calibrated_x, _perf_button_y,
                       _perf_calibrated_w, _perf_button_h):
        comms.start_povperf_capture("calibrated")
    return pyglet.event.EVENT_HANDLED


@window.event
def on_mouse_drag(x, y, dx, dy, buttons, modifiers):
    if active_overlay != OVERLAY_SETTINGS:
        return pyglet.event.EVENT_HANDLED
    if _dragging_slider:
        _set_rpm(_x_to_rpm(x))
    elif _cal_dragging == "master":
        _set_calibration_value("master", _cal_x_to_value(x, _cal_master_max))
    elif _cal_dragging == "radial_exponent":
        _set_calibration_value("radial_exponent", _cal_x_to_value(x, _cal_radial_max))
    return pyglet.event.EVENT_HANDLED


@window.event
def on_mouse_release(x, y, button, modifiers):
    global _dragging_slider, _cal_dragging
    _dragging_slider = False
    _cal_dragging = None


def draw_workbench_controls():
    _sync_calibration_controls()
    controls_batch.draw()


# Base state preview: a compact Super Ventilagon-inspired dial + button
# preview. Built once here and repositioned/recolored in place every frame
# instead of allocating fresh Shape/Label objects per draw (each allocation
# sets up its own vertex list/shader state, which was costing several
# ms/frame -- occasionally tens of ms -- for geometry that's otherwise
# static from frame to frame).
_bp_width, _bp_height = 194, 126
_bp_dial_w, _bp_dial_h = 100, 64
base_preview_batch = pyglet.graphics.Batch()

bp_panel_outer = shapes.Rectangle(0, 0, _bp_width, _bp_height, color=(3, 4, 6), batch=base_preview_batch)
bp_panel_inner = shapes.Rectangle(0, 0, _bp_width - 8, _bp_height - 8, color=(13, 16, 22), batch=base_preview_batch)
# The 16 WS2812s are hidden behind a rectangular, black-bezel instrument
# panel. Their current strip color lights its face rather than appearing
# as individual dots.
bp_dial_back = shapes.Rectangle(0, 0, _bp_dial_w, _bp_dial_h, color=(1, 2, 4), batch=base_preview_batch)
# The illuminated display occupies the upper part; the lower third is
# the black control panel where the real needle pivots.
bp_dial_face = shapes.Rectangle(0, 0, _bp_dial_w - 12, _bp_dial_h - 29, color=(0, 0, 0), batch=base_preview_batch)
bp_label_super = pyglet.text.Label("SUPER", font_name="Courier New", font_size=7, weight="bold",
                                    anchor_x="center", color=(0, 0, 0, 255), batch=base_preview_batch)
bp_label_ventilagon = pyglet.text.Label("VENTILAGON", font_name="Courier New", font_size=6, weight="bold",
                                         anchor_x="center", color=(0, 0, 0, 255), batch=base_preview_batch)
bp_needle = shapes.Line(0, 0, 0, 0, thickness=3, color=(0, 0, 0), batch=base_preview_batch)
bp_pivot = shapes.Circle(0, 0, 4, color=(0, 0, 0), batch=base_preview_batch)
bp_button_rings = [shapes.Circle(0, 0, 15, color=(20, 22, 25), batch=base_preview_batch) for _ in range(2)]
bp_button_faces = [shapes.Circle(0, 0, 12, color=(235, 235, 230), batch=base_preview_batch) for _ in range(2)]
bp_button_leds = [shapes.Circle(0, 0, 5, color=(52, 12, 12), batch=base_preview_batch) for _ in range(2)]


def draw_base_preview():
    """Position/recolor the base state preview for this frame and draw it."""
    state = comms.base_control
    # Right-aligned against the window edge, so this is recomputed every
    # frame in case the window was resized.
    x, y = window.width - _bp_width - 14, 14
    bp_panel_outer.position = (x, y)
    bp_panel_inner.position = (x + 4, y + 4)

    dial_x, dial_y = x + 12, y + 34
    bp_dial_back.position = (dial_x, dial_y)
    bp_dial_face.position = (dial_x + 6, dial_y + 22)
    bp_dial_face.color = state.dial_rgb

    # The real pivot sits below the rectangular panel. A 100-degree sweep
    # reproduces its constrained mechanical travel: left-up, top, right-up.
    center_x, center_y = dial_x + _bp_dial_w / 2, dial_y + 11
    bp_label_super.position = (center_x, dial_y + 45, 0)
    bp_label_ventilagon.position = (center_x, dial_y + 37, 0)

    # Preview orientation: 0 = left-up, midpoint = top, 255 = right-up.
    angle = math.radians(140 - 100 * state.servo_position / 255)
    bp_needle.x, bp_needle.y = center_x, center_y
    bp_needle.x2 = center_x + math.cos(angle) * 40
    bp_needle.y2 = center_y + math.sin(angle) * 40
    bp_pivot.position = (center_x, center_y)

    now_ms = int(time.monotonic() * 1000)
    for index, mask in enumerate((1, 2)):
        lit = state.button_lit(mask, now_ms)
        button_x = x + 130 + index * 37
        bp_button_rings[index].position = (button_x, y + 39)
        bp_button_faces[index].position = (button_x, y + 39)
        bp_button_leds[index].position = (button_x, y + 39)
        bp_button_leds[index].color = (230, 24, 20) if lit else (52, 12, 12)

    base_preview_batch.draw()

def display_draw():
    global scene_compositor, scene_renderer, scene_renderer_status
    window.clear()
    fps_display.draw()
    scene_renderer_label.y = window.height - 7
    scene_renderer_label.draw()

    smaller_dimension = min(window.width, window.height)
    x_half = window.width / smaller_dimension * 100
    y_half = window.height / smaller_dimension * 100

    orig_projection = window.projection
    window.projection = pm.Mat4.orthogonal_projection(-x_half, x_half, -y_half, y_half, -100, 100)

    try:
        scene_input = snapshot_scene_shader_input()
        rendered_by_shader = False
        if scene_renderer == "shader" and scene_input is not None:
            try:
                _ensure_scene_compositor().render(scene_input, led_color_texture)
                rendered_by_shader = True
            except Exception as error:
                # Keep the image visible even if a driver rejects the scene
                # program after it was selected.  The next F2 can retry.
                scene_renderer = "cpu"
                scene_compositor = None
                scene_renderer_status = "shader failed; using CPU: %s" % error
                _update_scene_renderer_label()
                traceback.print_exc()
        if not rendered_by_shader:
            vs2_scene = snapshot_vs2_scene()
            pixels = render_frame(vs2_scene)  # uint32[COLUMNS*led_count], 0xAABBGGRR == RGBA bytes
            _upload_cpu_frame(pixels)
        batch.draw()
    except Exception as e:
        traceback.print_exc()
    finally:
        window.projection = orig_projection

    draw_base_preview()
    _draw_overlay()
    _draw_toolbar()
