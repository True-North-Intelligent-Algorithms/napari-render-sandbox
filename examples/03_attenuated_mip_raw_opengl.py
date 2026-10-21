# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "tifffile", "PyQt6", "PyOpenGL"]
# ///
"""Example 3: attenuated MIP (AMIP) with raw OpenGL (no vispy)

A copy of vispy's attenuated_mip shader, exactly as napari uses it today,
written out in plain GLSL. As a ray goes deeper it gets dimmer, by how much
bright stuff it has already passed through (Beer-Lambert law). Things in
front hide things behind, so it reads as 3D. With attenuation 0 it is a
plain MIP.

This is the STARTING POINT for napari#8241: the current behaviour, with only
the controls napari has for it (same ranges and defaults):

    drag              turn the volume
    mouse wheel       zoom
    attenuation       0 to 0.5, steps of 0.001, default 0.05
    contrast limits   low / high; default = napari's automatic estimate
    gamma             0.2 to 2.0, steps of 0.02, default 1

The loop, per step from front to back, as in vispy's volume.py:

    sumval += step * clamp((val - clim_low) / (clim_high - clim_low), 0, 1)
    scale   = exp(-attenuation * (sumval - 1))
    maxval  = max(maxval, val * scale)

The contrast limits appear inside the attenuation, so moving them changes
how much things attenuate, not just the brightness.

Data: BrainGlobe atlas kim_dev_mouse_e15-5_lsfm_20um (light-sheet, mouse
E15.5 brain, 20 µm voxels), Kronman et al., Nat Commun 2024,
https://doi.org/10.1038/s41467-024-53254-w. The image TimMonko used in
napari#8241.

Run:  uv run examples/03_attenuated_mip_raw_opengl.py
"""

import tarfile
import urllib.request
from pathlib import Path

import numpy as np
import tifffile
from OpenGL import GL
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QSurfaceFormat
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QSlider,
    QVBoxLayout,
    QWidget,
)

# ---------------------------------------------------------------------------
# The data: the reference image of a BrainGlobe atlas
# ---------------------------------------------------------------------------

ATLAS = "kim_dev_mouse_e15-5_lsfm_20um_v1.3"
DATA_DIR = Path(__file__).parent.parent / "data" / "kim_e15-5_lsfm_20um"
DATA_FILE = DATA_DIR / ATLAS / "reference.tiff"
ATLAS_URL = f"https://gin.g-node.org/brainglobe/atlases/raw/master/{ATLAS}.tar.gz"

if not DATA_FILE.exists():
    # The atlas comes as one archive (111 MB). Read it as it downloads and
    # keep only the reference image.
    print(f"Downloading {ATLAS} (111 MB), keeping only reference.tiff")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(ATLAS_URL) as response:
        with tarfile.open(fileobj=response, mode="r|gz") as archive:
            for member in archive:
                if member.name.endswith("reference.tiff"):
                    archive.extract(member, DATA_DIR)

volume = tifffile.imread(DATA_FILE)  # (600, 412, 480), uint16, 20 µm voxels

# Halve the size in every direction (average each 2x2x2 block): 8x less
# GPU memory, and plenty of detail for this.
nz, ny, nx = volume.shape
volume = volume.reshape(nz // 2, 2, ny // 2, 2, nx // 2, 2).mean(axis=(1, 3, 5))

# Keep the raw intensities, like napari does. The contrast limits are applied
# in the shader, as in vispy.
volume = np.ascontiguousarray(volume, dtype=np.float32)

# napari's automatic contrast limits for a big array (calc_data_range in
# napari/layers/utils/layer_utils.py): the min and max over just the first,
# middle and last slices.
three_slices = volume[[0, volume.shape[0] // 2, -1]]
CLIM_DEFAULT = (float(three_slices.min()), float(three_slices.max()))

# The voxels are cubes (isotropic), so the box has the shape of the array.
nz, ny, nx = volume.shape
box_size = np.array([nx, ny, nz]) / max(nx, ny, nz)  # x, y, z; longest = 1

RELATIVE_STEP_SIZE = 0.8  # vispy's default: one step = 0.8 voxel
NAPARI_DEFAULT_ATTENUATION = 0.05
NAPARI_DEFAULT_GAMMA = 1.0

# ---------------------------------------------------------------------------
# The shaders
# ---------------------------------------------------------------------------

# Same as example 1: just the corners of a square covering the window.
VERTEX_SHADER = """
#version 330 core

in vec2 a_position;
out vec2 v_position;

void main() {
    v_position = a_position;
    gl_Position = vec4(a_position, 0.0, 1.0);
}
"""

FRAGMENT_SHADER = """
#version 330 core

in vec2 v_position;
out vec4 frag_color;

uniform sampler3D u_volume;
uniform mat3 u_screen_to_volume;
uniform vec3 u_box_size;
uniform vec3 u_shape;                // volume size in voxels (x, y, z)
uniform float u_zoom;                // 1 = whole box fits in half the window
uniform vec2 u_clim;                 // contrast limits, raw intensity

uniform float u_gamma;               // napari's gamma slider
uniform float u_attenuation;         // napari's attenuation slider
uniform float u_relative_step_size;  // step length in voxels (0.8)

void main() {
    // --- 1. This pixel's ray, in texture coordinates (0..1 = inside) ------
    // The viewer is at z = -1 looking towards +z, so the ray goes front to
    // back. Rotate it into the volume, then box -> texture coordinates.
    vec3 origin = u_screen_to_volume * vec3(v_position / u_zoom, -1.0);
    vec3 direction = u_screen_to_volume * vec3(0.0, 0.0, 1.0);
    origin = origin / u_box_size + 0.5;
    direction = direction / u_box_size;

    // Avoid dividing by zero for a ray exactly parallel to a face.
    if (abs(direction.x) < 1e-8) direction.x = 1e-8;
    if (abs(direction.y) < 1e-8) direction.y = 1e-8;
    if (abs(direction.z) < 1e-8) direction.z = 1e-8;

    // --- 2. Where the ray enters and leaves the box ------------------------
    // For each axis, find how far along the ray (t) it crosses the two faces
    // (0 and 1). It is inside the box between the LAST entry and the FIRST
    // exit. (vispy finds the same points from the box faces it draws.)
    vec3 t_face0 = (0.0 - origin) / direction;
    vec3 t_face1 = (1.0 - origin) / direction;
    vec3 t_in = min(t_face0, t_face1);
    vec3 t_out = max(t_face0, t_face1);
    float t_enter = max(max(t_in.x, t_in.y), t_in.z);
    float t_exit = min(min(t_out.x, t_out.y), t_out.z);

    if (t_exit <= t_enter) {                  // the ray misses the volume
        frag_color = vec4(0.0, 0.0, 0.0, 1.0);
        return;
    }
    vec3 front = origin + t_enter * direction;
    vec3 back = origin + t_exit * direction;

    // --- 3. Number of steps, as vispy: about 0.8 voxel each ----------------
    float length_in_voxels = length((back - front) * u_shape);
    int nsteps = int(length_in_voxels / u_relative_step_size + 0.5);
    if (nsteps < 1) {
        frag_color = vec4(0.0, 0.0, 0.0, 1.0);
        return;
    }
    vec3 step = (back - front) / float(nsteps);

    // --- 4. vispy's attenuated_mip loop -------------------------------------
    float maxval = u_clim.x;  // napari's mip_cutoff (translucent blending)
    float sumval = 0.0;       // how much the ray has passed through so far
    vec3 loc = front;

    for (int i = 0; i < nsteps; i++) {
        float val = texture(u_volume, loc).r;  // raw intensity

        // add what this step passes through (0..1 after contrast limits)
        float val01 = clamp((val - u_clim.x) / (u_clim.y - u_clim.x), 0.0, 1.0);
        sumval = sumval + u_relative_step_size * val01;

        // how much light from here still reaches the viewer
        // (the "- 1.0" is vispy's; #8241 proposes removing it)
        float scale = exp(-u_attenuation * (sumval - 1.0));

        // vispy's early stop: nothing deeper can beat the max any more
        if (maxval > scale * u_clim.y) {
            break;
        }

        // MIP, but of the dimmed value
        if (val * scale > maxval) {
            maxval = val * scale;
        }

        loc += step;
    }

    // --- 5. vispy's applyColormap, gray: contrast limits, then gamma -------
    float gray = clamp((maxval - u_clim.x) / (u_clim.y - u_clim.x), 0.0, 1.0);
    gray = pow(gray, u_gamma);
    frag_color = vec4(gray, gray, gray, 1.0);
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
# The 3D view
# ---------------------------------------------------------------------------


class AmipWidget(QOpenGLWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(600, 600)
        self.angle_x = -30.0  # start with an angled side view of the brain
        self.angle_y = 60.0
        self.zoom = 1.8
        self.attenuation = NAPARI_DEFAULT_ATTENUATION
        self.clim = list(CLIM_DEFAULT)
        self.gamma = NAPARI_DEFAULT_GAMMA
        self.last_mouse = None

    def initializeGL(self):
        # Everything here is the same as example 1.
        vertex = compile_shader(VERTEX_SHADER, GL.GL_VERTEX_SHADER)
        fragment = compile_shader(FRAGMENT_SHADER, GL.GL_FRAGMENT_SHADER)
        self.program = GL.glCreateProgram()
        GL.glAttachShader(self.program, vertex)
        GL.glAttachShader(self.program, fragment)
        GL.glLinkProgram(self.program)
        if not GL.glGetProgramiv(self.program, GL.GL_LINK_STATUS):
            error = GL.glGetProgramInfoLog(self.program).decode()
            raise RuntimeError(f"Program did not link:\n{error}")

        corners = np.array([[-1, -1], [+1, -1], [-1, +1], [+1, +1]], dtype=np.float32)
        self.vao = GL.glGenVertexArrays(1)
        GL.glBindVertexArray(self.vao)
        buffer = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, buffer)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, corners.nbytes, corners, GL.GL_STATIC_DRAW)
        location = GL.glGetAttribLocation(self.program, "a_position")
        GL.glEnableVertexAttribArray(location)
        GL.glVertexAttribPointer(location, 2, GL.GL_FLOAT, GL.GL_FALSE, 0, None)

        self.texture = GL.glGenTextures(1)
        GL.glBindTexture(GL.GL_TEXTURE_3D, self.texture)
        GL.glTexParameteri(GL.GL_TEXTURE_3D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR)
        GL.glTexParameteri(GL.GL_TEXTURE_3D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR)
        GL.glTexParameteri(GL.GL_TEXTURE_3D, GL.GL_TEXTURE_WRAP_S, GL.GL_CLAMP_TO_EDGE)
        GL.glTexParameteri(GL.GL_TEXTURE_3D, GL.GL_TEXTURE_WRAP_T, GL.GL_CLAMP_TO_EDGE)
        GL.glTexParameteri(GL.GL_TEXTURE_3D, GL.GL_TEXTURE_WRAP_R, GL.GL_CLAMP_TO_EDGE)
        GL.glTexImage3D(
            GL.GL_TEXTURE_3D, 0, GL.GL_R32F, nx, ny, nz, 0,
            GL.GL_RED, GL.GL_FLOAT, volume,
        )

    def paintGL(self):
        GL.glClearColor(0, 0, 0, 1)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT)
        GL.glUseProgram(self.program)

        def uniform(name):
            return GL.glGetUniformLocation(self.program, name)

        GL.glActiveTexture(GL.GL_TEXTURE0)
        GL.glBindTexture(GL.GL_TEXTURE_3D, self.texture)
        GL.glUniform1i(uniform("u_volume"), 0)
        GL.glUniform3f(uniform("u_box_size"), *box_size)
        GL.glUniform3f(uniform("u_shape"), nx, ny, nz)
        GL.glUniform1f(uniform("u_zoom"), self.zoom)
        GL.glUniform2f(uniform("u_clim"), *self.clim)
        GL.glUniform1f(uniform("u_gamma"), self.gamma)

        volume_rotation = rotation_y(self.angle_y) @ rotation_x(self.angle_x)
        GL.glUniformMatrix3fv(
            uniform("u_screen_to_volume"), 1, GL.GL_TRUE,
            volume_rotation.T.astype(np.float32),
        )

        GL.glUniform1f(uniform("u_attenuation"), self.attenuation)
        GL.glUniform1f(uniform("u_relative_step_size"), RELATIVE_STEP_SIZE)

        GL.glBindVertexArray(self.vao)
        GL.glDrawArrays(GL.GL_TRIANGLE_STRIP, 0, 4)

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
        self.update()


# ---------------------------------------------------------------------------
# The window: the 3D view, plus napari's controls for it underneath
# ---------------------------------------------------------------------------


class Window(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Example 3: attenuated MIP, as napari today")
        self.view = AmipWidget()
        layout = QVBoxLayout(self)
        layout.addWidget(self.view)

        # QSlider only does whole numbers, so each slider counts in small
        # units and we divide: attenuation in thousandths, gamma in
        # hundredths, contrast limits in whole intensity units.

        # attenuation: 0 to 0.5, steps of 0.001 (napari's range)
        self.attenuation_slider, self.attenuation_label = self.add_slider_row(
            layout, "attenuation:", 0, 500, round(NAPARI_DEFAULT_ATTENUATION * 1000)
        )
        # contrast limits: napari uses one slider with two handles; here it
        # is two sliders over the same range
        low, high = round(CLIM_DEFAULT[0]), round(CLIM_DEFAULT[1])
        self.clim_low_slider, self.clim_low_label = self.add_slider_row(
            layout, "contrast low:", low, high, low
        )
        self.clim_high_slider, self.clim_high_label = self.add_slider_row(
            layout, "contrast high:", low, high, high
        )
        # gamma: 0.2 to 2.0, steps of 0.02 (napari's range)
        self.gamma_slider, self.gamma_label = self.add_slider_row(
            layout, "gamma:", 20, 200, round(NAPARI_DEFAULT_GAMMA * 100)
        )
        self.gamma_slider.setSingleStep(2)
        self.on_change()

    def add_slider_row(self, layout, name, minimum, maximum, value):
        """A row: name, slider, current value. Returns (slider, value label)."""
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(minimum, maximum)
        slider.setValue(value)
        slider.valueChanged.connect(self.on_change)
        value_label = QLabel()
        value_label.setMinimumWidth(60)
        row = QHBoxLayout()
        name_label = QLabel(name)
        name_label.setMinimumWidth(100)
        row.addWidget(name_label)
        row.addWidget(slider)
        row.addWidget(value_label)
        layout.addLayout(row)
        return slider, value_label

    def on_change(self):
        """Any slider moved: copy all values to the view and redraw."""
        view = self.view
        view.attenuation = self.attenuation_slider.value() / 1000
        view.clim = [self.clim_low_slider.value(), self.clim_high_slider.value()]
        view.gamma = self.gamma_slider.value() / 100

        self.attenuation_label.setText(f"{view.attenuation:.3f}")
        self.clim_low_label.setText(f"{view.clim[0]}")
        self.clim_high_label.setText(f"{view.clim[1]}")
        self.gamma_label.setText(f"{view.gamma:.2f}")
        view.update()


def main():
    gl_format = QSurfaceFormat()
    gl_format.setVersion(3, 3)
    gl_format.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
    QSurfaceFormat.setDefaultFormat(gl_format)

    app = QApplication([])
    window = Window()
    window.show()
    app.exec()


if __name__ == "__main__":
    main()
