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
    GL_TEXTURE0,
    GL_TRIANGLES,
    GL_BLEND,
)
from pyglet.math import Mat4
from pyglet.graphics import Group
from pyglet.graphics.shader import Shader, ShaderProgram

import comms
import config
from povrender import COLUMNS, pack_colors, repeated, render

display_enabled = config.DISPLAY_ENABLED
pyglet.options['vsync'] = display_enabled

###############################
# Define a basic Shader Program
###############################
_vertex_source = """#version 330 core
    in vec2 position;
    in vec3 tex_coords;
    in vec4 colors;
    out vec3 texture_coords;
    out vec4 v_colors;

    uniform WindowBlock 
    {                       // This UBO is defined on Window creation, and available
        mat4 projection;    // in all Shaders. You can modify these matrixes with the
        mat4 view;          // Window.view and Window.projection properties.
    } window;  

    void main()
    {
        gl_Position = window.projection * window.view * vec4(position, 1, 1);
        texture_coords = tex_coords;
        v_colors = colors;
    }
"""

_fragment_source = """#version 330 core
    in vec3 texture_coords;
    in vec4 v_colors;
    out vec4 final_colors;

    uniform sampler2D our_texture;

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
        
        final_colors = v_colors * (pill + glow);
    }
    
"""

vert_shader = Shader(_vertex_source, 'vertex')
frag_shader = Shader(_fragment_source, 'fragment')
shader_program = ShaderProgram(vert_shader, frag_shader)

#####################################################
# Define a custom `Group` to encapsulate OpenGL state
#####################################################
class RenderGroup(Group):
    """A Group that enables and binds a Texture and ShaderProgram.

    RenderGroups are equal if their Texture and ShaderProgram
    are equal.
    """
    def __init__(self, texture, program, order=0, parent=None):
        """Create a RenderGroup.

        :Parameters:
            `texture` : `~pyglet.image.Texture`
                Texture to bind.
            `program` : `~pyglet.graphics.shader.ShaderProgram`
                ShaderProgram to use.
            `order` : int
                Change the order to render above or below other Groups.
            `parent` : `~pyglet.graphics.Group`
                Parent group.
        """
        super().__init__(order, parent)
        self.texture = texture
        self.program = program

    def set_state(self):
        glActiveTexture(GL_TEXTURE0)
        glBindTexture(self.texture.target, self.texture.id)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_COLOR, GL_SRC_COLOR)
        glBlendEquation(GL_MAX)
        self.program.use()

    def unset_state(self):
        glBlendEquation(GL_FUNC_ADD)
        glDisable(GL_BLEND)

    def __hash__(self):
        return hash((self.texture.target, self.texture.id, self.order, self.parent, self.program))

    def __eq__(self, other):
        return (self.__class__ is other.__class__ and
                self.texture.target == other.texture.target and
                self.texture.id == other.texture.id and
                self.order == other.order and
                self.program == other.program and
                self.parent == other.parent)


window = pyglet.window.Window(config=Config(double_buffer=display_enabled), fullscreen=config.FULLSCREEN, resizable=True)
logo = pyglet.image.load("logo.png")
window.set_icon(logo)
window.set_caption("Ventilastation Emulator")
fps_display = pyglet.window.FPSDisplay(window)
help_label = pyglet.text.Label("ⓘ help goes here", font_name="Arial", font_size=12, y=5, x=window.width-5, color=(128, 128, 128, 255), anchor_x="right")
batch = pyglet.graphics.Batch()


led_count = 54
LED_SIZE = 100
vertex_list = None
texture = pyglet.image.load("glow.png").get_texture(rectangle=True)
group = RenderGroup(texture, shader_program)

def display_init(led_count):
    led_step = (LED_SIZE / led_count)
    vertex_pos = []
    theta = (math.pi * 2 / COLUMNS)
    def arc_chord(r):
        return 2 * r * math.sin(theta / 2)


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
            vertex_pos.extend([v1.x, v1.y, v2.x, v2.y, v3.x, v3.y,
                                v1.x, v1.y, v3.x, v3.y, v4.x, v4.y])
            x1, x2 = x3, x4

    vertex_colors = (255, 128, 0, 255) * led_count * 6 * COLUMNS
    texture_pos = (0.0,0.0,0, 1.0,0.0,0, 1.0,1.0,0, 
                   0.0,0.0,0, 1.0,1.0,0, 0.0,1.0,0) * led_count * COLUMNS

    global vertex_list
    vertex_list = shader_program.vertex_list(
        led_count * 6 * COLUMNS,
        mode=GL_TRIANGLES,
        position=('f', vertex_pos),
        colors=('Bn', vertex_colors),
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
for text, x in (("SAVE", _cal_commit_x), ("REVERT", _cal_revert_x), ("FACTORY", _cal_factory_x)):
    pyglet.text.Label(text, font_name="Arial", font_size=9,
                      x=x + _cal_button_w / 2, y=_cal_button_y + _cal_button_h / 2,
                      anchor_x="center", anchor_y="center",
                      color=(255, 255, 255, 255), batch=controls_batch)


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
    elif _point_in_rect(x, y, _cal_x - _cal_handle_radius, _cal_y + 32 - _cal_handle_radius,
                       _cal_w + 2 * _cal_handle_radius, _cal_h + 2 * _cal_handle_radius):
        _cal_dragging = "radial_exponent"
        _set_calibration_value("radial_exponent", _cal_x_to_value(x, _cal_radial_max))
    elif _point_in_rect(x, y, _cal_commit_x, _cal_button_y, _cal_button_w, _cal_button_h):
        comms.send_povcal("commit")
    elif _point_in_rect(x, y, _cal_revert_x, _cal_button_y, _cal_button_w, _cal_button_h):
        comms.send_povcal("revert")
    elif _point_in_rect(x, y, _cal_factory_x, _cal_button_y, _cal_button_w, _cal_button_h):
        comms.send_povcal("factory")


@window.event
def on_mouse_drag(x, y, dx, dy, buttons, modifiers):
    if _dragging_slider:
        _set_rpm(_x_to_rpm(x))
    elif _cal_dragging == "master":
        _set_calibration_value("master", _cal_x_to_value(x, _cal_master_max))
    elif _cal_dragging == "radial_exponent":
        _set_calibration_value("radial_exponent", _cal_x_to_value(x, _cal_radial_max))


@window.event
def on_mouse_release(x, y, button, modifiers):
    global _dragging_slider, _cal_dragging
    _dragging_slider = False
    _cal_dragging = None


def draw_workbench_controls():
    _sync_calibration_controls()
    controls_batch.draw()


def draw_base_preview():
    """Draw a compact Super Ventilagon-inspired base state preview."""
    state = comms.base_control
    width, height = 194, 126
    x, y = window.width - width - 14, 14
    shapes.Rectangle(x, y, width, height, color=(3, 4, 6)).draw()
    shapes.Rectangle(x + 4, y + 4, width - 8, height - 8, color=(13, 16, 22)).draw()

    red, green, blue = state.dial_rgb

    # The 16 WS2812s are hidden behind a rectangular, black-bezel instrument
    # panel. Their current strip color lights its face rather than appearing
    # as individual dots.
    dial_x, dial_y, dial_w, dial_h = x + 12, y + 34, 100, 64
    shapes.Rectangle(dial_x, dial_y, dial_w, dial_h, color=(1, 2, 4)).draw()
    # The illuminated display occupies the upper part; the lower third is
    # the black control panel where the real needle pivots.
    shapes.Rectangle(dial_x + 6, dial_y + 22, dial_w - 12, dial_h - 29,
                     color=(red, green, blue)).draw()
    # The real pivot sits below the rectangular panel. A 100-degree sweep
    # reproduces its constrained mechanical travel: left-up, top, right-up.
    center_x, center_y = dial_x + dial_w / 2, dial_y + 11
    pyglet.text.Label("SUPER", font_name="Courier New", font_size=7, weight="bold",
                      x=center_x, y=dial_y + 45, anchor_x="center",
                      color=(0, 0, 0, 255)).draw()
    pyglet.text.Label("VENTILAGON", font_name="Courier New", font_size=6, weight="bold",
                      x=center_x, y=dial_y + 37, anchor_x="center",
                      color=(0, 0, 0, 255)).draw()
    # Preview orientation: 0 = left-up, midpoint = top, 255 = right-up.
    angle = math.radians(140 - 100 * state.servo_position / 255)
    needle_x = center_x + math.cos(angle) * 40
    needle_y = center_y + math.sin(angle) * 40
    shapes.Line(center_x, center_y, needle_x, needle_y, thickness=3, color=(0, 0, 0)).draw()
    shapes.Circle(center_x, center_y, 4, color=(0, 0, 0)).draw()

    now_ms = int(time.monotonic() * 1000)
    for index, mask in enumerate((1, 2)):
        lit = state.button_lit(mask, now_ms)
        button_x = x + 130 + index * 37
        shapes.Circle(button_x, y + 39, 15, color=(20, 22, 25)).draw()
        shapes.Circle(button_x, y + 39, 12, color=(235, 235, 230)).draw()
        shapes.Circle(button_x, y + 39, 5, color=(230, 24, 20) if lit else (52, 12, 12)).draw()

def display_draw():
    window.clear()
    fps_display.draw()
    help_label.x = window.width - 5
    help_label.draw()

    smaller_dimension = min(window.width, window.height)
    x_half = window.width / smaller_dimension * 100
    y_half = window.height / smaller_dimension * 100

    orig_projection = window.projection
    window.projection = pm.Mat4.orthogonal_projection(-x_half, x_half, -y_half, y_half, -100, 100)

    all_pixels = []
    try:
        for column in range(COLUMNS):
            all_pixels.extend(render(column))

        vertex_colors = pack_colors(list(repeated(6, all_pixels)))
        vertex_list.set_attribute_data("colors", vertex_colors)
        batch.draw()
    except Exception as e:
        traceback.print_exc()
    finally:
        window.projection = orig_projection

    draw_workbench_controls()
    draw_base_preview()
