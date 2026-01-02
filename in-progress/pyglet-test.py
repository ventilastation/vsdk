import pyglet
import pyglet.math as pm
import random
import math

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
from pyglet.graphics import Group
from pyglet.graphics.shader import Shader, ShaderProgram


###################################
# Create a Window, and render Batch
###################################
window = pyglet.window.Window(resizable=True)
batch = pyglet.graphics.Batch()




@window.event
def on_resize(width, height):
    print(f'The window was resized to {width},{height}')

COLS = 256

@window.event
def on_draw():
    window.clear()
    rotation_axis = pm.Vec3(0.0, 0.0, 1.0) # The Z-axis
    angle = math.pi * 2 / COLS

    smaller_dimension = min(window.width, window.height)
    x_half = window.width / smaller_dimension * 100
    y_half = window.height / smaller_dimension * 100

    window.projection = pm.Mat4.orthogonal_projection(-x_half, x_half, -y_half, y_half, -100, 100)
    orig_view = window.view
  
    for n in range(COLS):
        vertex_colors = []
        for i in range(led_count):
            r, g, b = random.random(), random.random(), random.random()
            for v in range(6):
                vertex_colors.extend([r, g, b, 1.0])
        vertex_list.set_attribute_data("colors", vertex_colors)
        window.view = window.view.rotate(angle, rotation_axis)
        batch.draw()

    window.view = orig_view


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


#########################################################
# Load a Texture, and create a VertexList from the Shader
#########################################################

led_count = 54
LED_SIZE = 100
COLUMNS = 256

led_step = (LED_SIZE / led_count)
vertex_pos = []
theta = (math.pi * 2 / COLUMNS)
def arc_chord(r):
    return 2 * r * math.sin(theta / 2)

x1, x2 = 0, 0
for i in range(led_count):
    y1 = led_step * i - (led_step * .3)
    y2 = y1 + (led_step * 1)
    x3 = arc_chord(y2) * 0.7
    x4 = -x3
    vertex_pos.extend([x1, y1, x2, y1, x4, y2,
                       x1, y1, x4, y2, x3, y2])
    x1, x2 = x3, x4

vertex_colors = (1.0, 0.5, 0.0, 1.0) * led_count * 6
texture_pos = (0.0,0.0,0, 1.0,0.0,0, 1.0,1.0,0, 
               0.0,0.0,0, 1.0,1.0,0, 0.0,1.0,0) * led_count 





def create_quad(x, y, texture):
    x2 = x + texture.width
    y2 = y + texture.height
    return x, y, x2, y, x2, y2, x, y2


tex = pyglet.resource.texture('glow.png')
group = RenderGroup(tex, shader_program)
# indices = (0, 1, 2, 0, 2, 3)
# vertex_positions = create_quad(0, 0, tex)

# count, mode, indices, batch, group, *data
# vertex_list = shader_program.vertex_list_indexed(4, GL_TRIANGLES, indices, batch, group,
#                                                  position=('f', vertex_positions),
#                                                  tex_coords=('f', tex.tex_coords),
#                                                  colors=('f', (random.random(), .5, .3, .5) * 4)
#                                                  )

# print(vertex_positions)
print(vertex_pos)

vertex_list = shader_program.vertex_list(
    led_count * 6,
    mode=GL_TRIANGLES,
    position=('f', vertex_pos),
    colors=('f', vertex_colors),
    tex_coords=('f', texture_pos),
    group=group,
    batch=batch
)


# label = pyglet.text.Label("A minimal shader to display a textured quad.", x=5, y=5, batch=batch)

#####################
# Enter the main loop
#####################
pyglet.app.run()
