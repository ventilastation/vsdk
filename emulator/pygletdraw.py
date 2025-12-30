import math
import random
import sys
import traceback

import pyglet

if pyglet.version < "2.0":
    raise RuntimeError("Pyglet 2.0 or higher is required")

import pyglet.math as pm
from pyglet.gl import Config
from pyglet.gl import (
    glActiveTexture,
    glBindTexture,
    glEnable,
    glBlendFunc,
    glDisable,
    GL_TEXTURE0,
    GL_TRIANGLES,
    GL_BLEND,
    GL_SRC_ALPHA_SATURATE,
    GL_ONE,
    GL_SRC_ALPHA,
    GL_ONE_MINUS_SRC_ALPHA,
)
from pyglet.math import Mat4
from pyglet.graphics import Group
from pyglet.graphics.shader import Shader, ShaderProgram

import config
from vsdk import COLUMNS, pack_colors, repeated, render


pyglet.options['vsync'] = "--no-display" not in sys.argv

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

    void main()
    {
        final_colors = v_colors * texture(our_texture, texture_coords.xy);
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
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        # glBlendFunc(GL_SRC_ALPHA_SATURATE, GL_ONE)
        self.program.use()

    def unset_state(self):
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


window = pyglet.window.Window(config=Config(double_buffer=True), fullscreen=config.FULLSCREEN, resizable=True)
logo = pyglet.image.load("logo.png")
window.set_icon(logo)
window.set_caption("Ventilastation Emulator")
fps_display = pyglet.window.FPSDisplay(window)
help_label = pyglet.text.Label("←↕→ SPACE ESC Q", font_name="Arial", font_size=12, y=5, x=window.width-5, color=(128, 128, 128, 255), anchor_x="right")
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
            y1 = led_step * i - (led_step * .3)
            y2 = y1 + (led_step * 1)
            x3 = arc_chord(y2) * 0.7
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
    finally:
        window.projection = orig_projection
