# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "PyQt6", "PyOpenGL"]
# ///
"""Example 2: splatting SMLM localizations with raw OpenGL (no vispy)

Shows ~300,000 3D localizations of nuclear pores over a whole nucleus,
each drawn as a small Gaussian blob ("splat"). The blobs are ADDED
together, so dense places get bright: the image shows density.

    drag          turn the nucleus
    mouse wheel   zoom
    up / down     brighter / dimmer (the gain)

Compare with example 1 (volume MIP):
  - Example 1 rotates the RAYS, in the fragment shader, and draws one square.
  - Here we rotate the POINTS, in the vertex shader, and draw one sprite
    (a small square) per point. The fragment shader paints a Gaussian on it.

Each Gaussian's width is the localization precision (crlbX/crlbY, ~17 nm).
Zoomed out, that is far smaller than a pixel, so there is a minimum size
(MIN_SIGMA_PX). Zoom in and the real precision takes over.

Simplifications: round splats (the z precision is ignored), and a plain
8-bit window, so very dense places saturate. Turn the gain down for those.

Data: "Zola-3D NUP full nucleus", Aristov et al., Nat Commun 9, 2409 (2018),
from ShareLoc.XYZ, https://doi.org/10.5281/zenodo.7233696, CC BY 4.0.

Run:  uv run examples/02_smlm_splats_raw_opengl.py
"""

import ctypes
import json
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
from OpenGL import GL
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QSurfaceFormat
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtWidgets import QApplication

# ---------------------------------------------------------------------------
# The data: a ShareLoc .smlm file (a zip holding a table of localizations)
# ---------------------------------------------------------------------------

DATA_FILE = (
    Path(__file__).parent.parent
    / "data"
    / "shareloc_zola3d_nup"
    / "sample-1"
    / "data.smlm"
)
DATA_URL = (
    "https://zenodo.org/api/records/7233696/files/sample-1/data.smlm/content"
)

if not DATA_FILE.exists():
    print(f"Downloading the dataset (12 MB) to {DATA_FILE}")
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(DATA_URL, DATA_FILE)

# Inside the zip: manifest.json says what the columns are, and default.bin
# holds the numbers, one row per localization, all float32.
with zipfile.ZipFile(DATA_FILE) as smlm:
    manifest = json.loads(smlm.read("manifest.json"))
    raw = np.frombuffer(smlm.read("default.bin"), dtype="<f4")

headers = manifest["formats"]["smlm-table(binary)-0"]["headers"]
table = raw.reshape(-1, len(headers))  # one row per localization
column = {name: table[:, i] for i, name in enumerate(headers)}

x, y, z = column["x"], column["y"], column["z"]  # in nm
precision_nm = (column["crlbX"] + column["crlbY"]) / 2  # lateral, in nm
n_points = len(x)

# Move the centre of the data to 0 and scale so the longest side is 1,
# the same box convention as example 1.
xyz = np.stack([x, y, z], axis=1)
low, high = xyz.min(axis=0), xyz.max(axis=0)
centre = (low + high) / 2
nm_to_box = 1 / (high - low).max()
positions = (xyz - centre) * nm_to_box
sigmas = precision_nm * nm_to_box

# Pack 4 floats per point for the GPU: x, y, z, sigma.
points = np.column_stack([positions, sigmas])
points = np.ascontiguousarray(points, dtype=np.float32)

# ---------------------------------------------------------------------------
# The shaders
# ---------------------------------------------------------------------------

MIN_SIGMA_PX = 1.0  # never draw a splat narrower than this (in pixels)
WINDOW_PX = 600

# The vertex shader runs once per POINT (n_points times; ~300,000 for this file).
# It rotates the point and decides how big its sprite is.
VERTEX_SHADER = """
#version 330 core

in vec3 a_position;           // the point, in box coordinates
in float a_sigma;             // its precision, in box units

uniform mat3 u_rotation;      // how the user has turned the data
uniform float u_zoom;         // 1 = whole box fits in half the window
uniform float u_px_per_unit;  // pixels per box unit at zoom 1
uniform float u_min_sigma_px; // smallest splat we allow, in pixels

out float v_sigma_px;         // the splat width in pixels, for the fragment shader

void main() {
    vec3 p = u_rotation * a_position;          // turn the point
    gl_Position = vec4(p.xy * u_zoom, 0.0, 1.0);

    // Width of this Gaussian on screen, in pixels, with a minimum.
    float sigma_px = a_sigma * u_px_per_unit * u_zoom;
    v_sigma_px = max(sigma_px, u_min_sigma_px);

    // The sprite is a square covering +-3 sigma, which holds nearly all of
    // the Gaussian.
    gl_PointSize = 6.0 * v_sigma_px;
}
"""

# The fragment shader runs once per pixel of each sprite.
# It paints the Gaussian: bright in the middle, fading out.
FRAGMENT_SHADER = """
#version 330 core

in float v_sigma_px;
out vec4 frag_color;

uniform float u_gain;          // how much each splat adds
uniform vec3 u_color;

void main() {
    // gl_PointCoord: where this pixel sits in the sprite, 0..1 in x and y.
    // Turn it into a distance from the sprite centre, in pixels.
    vec2 offset_px = (gl_PointCoord - 0.5) * (6.0 * v_sigma_px);
    float r2 = dot(offset_px, offset_px);      // distance squared

    float weight = exp(-0.5 * r2 / (v_sigma_px * v_sigma_px));  // Gaussian

    // With additive blending (see paintGL), this ADDS to the pixel.
    frag_color = vec4(u_gain * weight * u_color, 1.0);
}
"""

# ---------------------------------------------------------------------------
# Small helpers (the same as example 1)
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


class SplatWidget(QOpenGLWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(WINDOW_PX, WINDOW_PX)
        self.angle_x = 30.0
        self.angle_y = 30.0
        self.zoom = 1.0
        self.gain = 0.03
        self.last_mouse = None
        self.update_title()

    def update_title(self):
        self.setWindowTitle(
            f"Example 2: SMLM splats   zoom {self.zoom:.1f}   gain {self.gain:.3f}"
        )

    def initializeGL(self):
        # 1. Compile and link the shaders (the same as example 1).
        vertex = compile_shader(VERTEX_SHADER, GL.GL_VERTEX_SHADER)
        fragment = compile_shader(FRAGMENT_SHADER, GL.GL_FRAGMENT_SHADER)
        self.program = GL.glCreateProgram()
        GL.glAttachShader(self.program, vertex)
        GL.glAttachShader(self.program, fragment)
        GL.glLinkProgram(self.program)
        if not GL.glGetProgramiv(self.program, GL.GL_LINK_STATUS):
            error = GL.glGetProgramInfoLog(self.program).decode()
            raise RuntimeError(f"Program did not link:\n{error}")

        # 2. Upload all the points in one buffer.
        self.vao = GL.glGenVertexArrays(1)
        GL.glBindVertexArray(self.vao)
        buffer = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, buffer)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, points.nbytes, points, GL.GL_STATIC_DRAW)

        # Each point is 4 floats (16 bytes): x, y, z, sigma.
        # a_position = the first 3 floats, a_sigma = the 4th (12 bytes in).
        stride = 4 * 4
        location = GL.glGetAttribLocation(self.program, "a_position")
        GL.glEnableVertexAttribArray(location)
        GL.glVertexAttribPointer(
            location, 3, GL.GL_FLOAT, GL.GL_FALSE, stride, ctypes.c_void_p(0)
        )
        location = GL.glGetAttribLocation(self.program, "a_sigma")
        GL.glEnableVertexAttribArray(location)
        GL.glVertexAttribPointer(
            location, 1, GL.GL_FLOAT, GL.GL_FALSE, stride, ctypes.c_void_p(12)
        )

        # Let the vertex shader set the sprite size (gl_PointSize).
        GL.glEnable(GL.GL_PROGRAM_POINT_SIZE)

    def paintGL(self):
        GL.glClearColor(0, 0, 0, 1)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT)

        # Additive blending: new color = color already there + this splat.
        # Order doesn't matter for a sum, so no sorting by depth is needed.
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_ONE, GL.GL_ONE)

        GL.glUseProgram(self.program)

        def uniform(name):
            return GL.glGetUniformLocation(self.program, name)

        rotation = rotation_y(self.angle_y) @ rotation_x(self.angle_x)
        GL.glUniformMatrix3fv(
            uniform("u_rotation"), 1, GL.GL_TRUE, rotation.astype(np.float32)
        )
        GL.glUniform1f(uniform("u_zoom"), self.zoom)
        # The window spans 2 units (-1..1) across WINDOW_PX pixels.
        GL.glUniform1f(uniform("u_px_per_unit"), WINDOW_PX / 2)
        GL.glUniform1f(uniform("u_min_sigma_px"), MIN_SIGMA_PX)
        GL.glUniform1f(uniform("u_gain"), self.gain)
        GL.glUniform3f(uniform("u_color"), 1.0, 0.45, 0.15)  # orange

        # Draw every point as a sprite.
        GL.glBindVertexArray(self.vao)
        GL.glDrawArrays(GL.GL_POINTS, 0, n_points)

    # Mouse and keys: change a number, then ask Qt to redraw.

    def mousePressEvent(self, event):
        self.last_mouse = event.position()

    def mouseMoveEvent(self, event):
        position = event.position()
        self.angle_y += (position.x() - self.last_mouse.x()) * 0.5
        self.angle_x += (position.y() - self.last_mouse.y()) * 0.5
        self.last_mouse = position
        self.update()

    def wheelEvent(self, event):
        if event.angleDelta().y() > 0:
            self.zoom *= 1.2
        else:
            self.zoom /= 1.2
        self.update_title()
        self.update()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Up:
            self.gain *= 1.5
        elif event.key() == Qt.Key.Key_Down:
            self.gain /= 1.5
        self.update_title()
        self.update()


def main():
    gl_format = QSurfaceFormat()
    gl_format.setVersion(3, 3)
    gl_format.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
    QSurfaceFormat.setDefaultFormat(gl_format)

    app = QApplication([])
    widget = SplatWidget()
    widget.show()
    app.exec()


if __name__ == "__main__":
    main()
