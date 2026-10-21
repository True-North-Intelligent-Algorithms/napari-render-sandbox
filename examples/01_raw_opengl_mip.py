# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "scikit-image", "pooch", "PyQt6", "PyOpenGL"]
# ///
"""Example 1: a 3D volume shader with raw OpenGL (no vispy)

Shows the cells3d nuclei as a maximum intensity projection (MIP).
Drag with the mouse to turn the volume.

Everything vispy normally hides is spelled out here:
  1. write two small GLSL programs (a vertex shader and a fragment shader)
  2. compile and link them on the GPU
  3. upload the 3D image as a texture
  4. each frame: set the uniforms and draw one square covering the window

The trick: we draw only a flat square. The fragment shader runs once per
pixel of that square, and for each pixel it walks a ray straight back
through the volume and keeps the brightest value it meets. That is a MIP.

Run:  uv run examples/01_raw_opengl_mip.py
"""

import numpy as np
from OpenGL import GL
from PyQt6.QtGui import QSurfaceFormat
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtWidgets import QApplication
from skimage import data

# ---------------------------------------------------------------------------
# The data: the nuclei channel of cells3d
# ---------------------------------------------------------------------------

cells = data.cells3d()  # shape (z, channel, y, x) = (60, 2, 256, 256), uint16
nuclei = cells[:, 1, :, :]  # channel 1 is the nuclei

# The shader will work with floats from 0 to 1, so rescale here.
# The brightest 0.5 % of voxels end up at 1 (saturated).
low, high = np.percentile(nuclei, [1, 99.5])
nuclei = (nuclei - low) / (high - low)
nuclei = np.clip(nuclei, 0, 1)
nuclei = np.ascontiguousarray(nuclei, dtype=np.float32)

# Physical size of the volume in µm: z steps are 0.29 µm, x/y pixels 0.26 µm.
# The volume is flat (60 slices), so the box we draw must be flat too.
nz, ny, nx = nuclei.shape
size_um = np.array([nx * 0.26, ny * 0.26, nz * 0.29])  # x, y, z order
box_size = size_um / size_um.max()  # scale so the longest side is 1

# ---------------------------------------------------------------------------
# The shaders (GLSL, the language that runs on the GPU)
# ---------------------------------------------------------------------------

# The vertex shader runs once per corner of the square (4 times).
# It only passes the corner position on.
VERTEX_SHADER = """
#version 330 core

in vec2 a_position;      // one corner of the square, x and y from -1 to 1
out vec2 v_position;     // sent on to the fragment shader

void main() {
    v_position = a_position;
    gl_Position = vec4(a_position, 0.0, 1.0);
}
"""

# The fragment shader runs once per pixel. The GPU blends v_position
# between the corners, so each pixel gets its own position.
FRAGMENT_SHADER = """
#version 330 core

in vec2 v_position;              // this pixel, x and y from -1 to 1
out vec4 frag_color;             // the color we decide for this pixel

uniform sampler3D u_volume;      // the 3D image
uniform mat3 u_screen_to_volume; // turns a screen point into a volume point
uniform vec3 u_box_size;         // size of the box, longest side = 1

const int N_STEPS = 300;

void main() {
    // The ray for this pixel starts in front of the volume (z = -1)
    // and goes straight back to z = +1.
    vec3 ray_start = vec3(v_position, -1.0);
    vec3 ray_step = vec3(0.0, 0.0, 2.0 / float(N_STEPS));

    float brightest = 0.0;
    int count = 0;

    for (int i = 0; i < N_STEPS; i++) {
        // a point on the ray, in screen space
        vec3 point = ray_start + float(i) * ray_step;

        // the same point, in the volume's own (rotated) space
        point = u_screen_to_volume * point;

        // box coordinates (-size/2 .. +size/2) to texture coordinates (0 .. 1)
        vec3 tex = point / u_box_size + 0.5;

        // only sample if the point is inside the box
        bool inside = all(greaterThanEqual(tex, vec3(0.0)))
                   && all(lessThanEqual(tex, vec3(1.0)));

        if (inside) {
            float value = texture(u_volume, tex).r;
            // brightest = min(brightest, value);
            brightest = brightest + value;
            count = count + 1;
        }
    }

    brightest = brightest / float(count);

    frag_color = vec4(brightest, brightest, brightest, 1.0);  // gray
}
"""

# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def compile_shader(source, shader_type):
    """Compile one shader on the GPU and return its id."""
    shader = GL.glCreateShader(shader_type)
    GL.glShaderSource(shader, source)
    GL.glCompileShader(shader)
    if not GL.glGetShaderiv(shader, GL.GL_COMPILE_STATUS):
        error = GL.glGetShaderInfoLog(shader).decode()
        raise RuntimeError(f"Shader did not compile:\n{error}")
    return shader


def rotation_x(degrees):
    """Rotation matrix around the x axis (tilt forward and back)."""
    a = np.radians(degrees)
    return np.array(
        [
            [1, 0, 0],
            [0, np.cos(a), -np.sin(a)],
            [0, np.sin(a), np.cos(a)],
        ]
    )


def rotation_y(degrees):
    """Rotation matrix around the y axis (turn left and right)."""
    a = np.radians(degrees)
    return np.array(
        [
            [np.cos(a), 0, np.sin(a)],
            [0, 1, 0],
            [-np.sin(a), 0, np.cos(a)],
        ]
    )


# ---------------------------------------------------------------------------
# The window
# ---------------------------------------------------------------------------


class VolumeWidget(QOpenGLWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(600, 600)  # square, so we don't need an aspect ratio
        self.setWindowTitle("Example 1: raw OpenGL MIP (drag to turn)")
        self.angle_x = 30.0  # current tilt, in degrees
        self.angle_y = 30.0  # current turn, in degrees
        self.last_mouse = None

    def initializeGL(self):
        """Runs once, when the GPU context is ready. Set everything up."""

        # 1. Compile both shaders and link them into one program.
        vertex = compile_shader(VERTEX_SHADER, GL.GL_VERTEX_SHADER)
        fragment = compile_shader(FRAGMENT_SHADER, GL.GL_FRAGMENT_SHADER)
        self.program = GL.glCreateProgram()
        GL.glAttachShader(self.program, vertex)
        GL.glAttachShader(self.program, fragment)
        GL.glLinkProgram(self.program)
        if not GL.glGetProgramiv(self.program, GL.GL_LINK_STATUS):
            error = GL.glGetProgramInfoLog(self.program).decode()
            raise RuntimeError(f"Program did not link:\n{error}")

        # 2. Upload the 4 corners of the square covering the window.
        corners = np.array(
            [
                [-1, -1],  # bottom left
                [+1, -1],  # bottom right
                [-1, +1],  # top left
                [+1, +1],  # top right
            ],
            dtype=np.float32,
        )
        # A "vertex array object" remembers how the corners are laid out.
        self.vao = GL.glGenVertexArrays(1)
        GL.glBindVertexArray(self.vao)
        buffer = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, buffer)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, corners.nbytes, corners, GL.GL_STATIC_DRAW)
        # Connect the buffer to `in vec2 a_position` in the vertex shader:
        # 2 floats per corner, tightly packed.
        location = GL.glGetAttribLocation(self.program, "a_position")
        GL.glEnableVertexAttribArray(location)
        GL.glVertexAttribPointer(location, 2, GL.GL_FLOAT, GL.GL_FALSE, 0, None)

        # 3. Upload the volume as a 3D texture.
        self.texture = GL.glGenTextures(1)
        GL.glBindTexture(GL.GL_TEXTURE_3D, self.texture)
        # LINEAR: blend neighbouring voxels when sampling between them
        GL.glTexParameteri(GL.GL_TEXTURE_3D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR)
        GL.glTexParameteri(GL.GL_TEXTURE_3D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR)
        # CLAMP: at the edges, don't wrap around to the other side
        GL.glTexParameteri(GL.GL_TEXTURE_3D, GL.GL_TEXTURE_WRAP_S, GL.GL_CLAMP_TO_EDGE)
        GL.glTexParameteri(GL.GL_TEXTURE_3D, GL.GL_TEXTURE_WRAP_T, GL.GL_CLAMP_TO_EDGE)
        GL.glTexParameteri(GL.GL_TEXTURE_3D, GL.GL_TEXTURE_WRAP_R, GL.GL_CLAMP_TO_EDGE)
        # numpy's (z, y, x) order matches OpenGL's (width=x, height=y, depth=z)
        GL.glTexImage3D(
            GL.GL_TEXTURE_3D,
            0,  # mipmap level 0 (full resolution)
            GL.GL_R32F,  # stored on the GPU as one 32-bit float per voxel
            nx,
            ny,
            nz,
            0,  # border, must be 0
            GL.GL_RED,  # our data has one channel...
            GL.GL_FLOAT,  # ...of float32
            nuclei,
        )

    def paintGL(self):
        """Runs every time the window needs redrawing."""
        GL.glClearColor(0, 0, 0, 1)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT)

        GL.glUseProgram(self.program)

        # Uniforms are the values that are the same for every pixel.

        # u_volume: which texture unit holds the volume (unit 0)
        GL.glActiveTexture(GL.GL_TEXTURE0)
        GL.glBindTexture(GL.GL_TEXTURE_3D, self.texture)
        GL.glUniform1i(GL.glGetUniformLocation(self.program, "u_volume"), 0)

        # u_box_size
        GL.glUniform3f(
            GL.glGetUniformLocation(self.program, "u_box_size"), *box_size
        )

        # u_screen_to_volume: turning the volume one way is the same as
        # turning the rays the other way, and the opposite of a rotation
        # matrix is its transpose.
        volume_rotation = rotation_y(self.angle_y) @ rotation_x(self.angle_x)
        screen_to_volume = volume_rotation.T.astype(np.float32)
        GL.glUniformMatrix3fv(
            GL.glGetUniformLocation(self.program, "u_screen_to_volume"),
            1,  # one matrix
            GL.GL_TRUE,  # numpy is row-major, GLSL column-major: transpose it
            screen_to_volume,
        )

        # Draw the square: 4 corners as a "triangle strip" (two triangles).
        GL.glBindVertexArray(self.vao)
        GL.glDrawArrays(GL.GL_TRIANGLE_STRIP, 0, 4)

    # Mouse: dragging changes the angles, then asks Qt to redraw.

    def mousePressEvent(self, event):
        self.last_mouse = event.position()

    def mouseMoveEvent(self, event):
        position = event.position()
        dx = position.x() - self.last_mouse.x()
        dy = position.y() - self.last_mouse.y()
        self.angle_y += dx * 0.5
        self.angle_x += dy * 0.5
        self.last_mouse = position
        self.update()  # Qt will call paintGL


def main():
    # Ask for OpenGL 3.3 "core", the version our shaders are written for.
    # This must happen before the QApplication is created.
    gl_format = QSurfaceFormat()
    gl_format.setVersion(3, 3)
    gl_format.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
    QSurfaceFormat.setDefaultFormat(gl_format)

    app = QApplication([])
    widget = VolumeWidget()
    widget.show()
    app.exec()


if __name__ == "__main__":
    main()
