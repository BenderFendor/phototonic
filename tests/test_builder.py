from __future__ import annotations

import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path

from phototonic.builder import build

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REAL_SOURCE = PROJECT_ROOT.parent / "Shrimple_v0.12.zip"


def make_synthetic_source(path: Path) -> None:
    files = {
        "LICENSE": "Copyright (c) Joshua Miller\nAll Rights Reserved\n",
        "shaders/lib/common.glsl": "#define LIGHTING_TRACED_JITTER\n",
        "shaders/lib/sampling/depth.glsl": """
float linearizeDepth(float d, float n, float f) { return d; }
float linearizeDepthFast(float d, float n, float f) { return d; }
vec3 linearizeDepthFast3(vec3 d, float n, float f) { return d; }
float delinearizeDepth(float d, float n, float f) { return d; }
""".strip() + "\n",
        "shaders/program/gbuffers_terrain.fsh": """
#include "/lib/common.glsl"
void main() {
    vec4 color = vec4(1.0);
    vec3 albedo = RGBToLinear(color.rgb);
}
""".strip() + "\n",
        "shaders/program/composite10.fsh": """
#include "/lib/lighting/voxel/tracing.glsl"
void main() {
    float depth = 0.5;
    if (depth < 1.0) {
        SampleDynamicLighting(diffuseFinal, specularFinal, localPos, localNormal, texNormal, albedo, roughL, metal_f0, occlusion, sss);
    }
}
""".strip() + "\n",
        "shaders/program/deferred1.csh": """
float reduceOne(float sampleZ) {
    float minZ = 1.0;
    minZ = min(minZ, sampleZ);
    return minZ;
}
float reduceTile(vec2 sampleUV, vec2 sourceSize, float sampleZ) {
    float minZ = 1.0;
    float sampleWeight = float(any(greaterThanEqual(sampleUV, sourceSize)));
\tminZ = min(minZ, max(sampleZ, sampleWeight));
    return minZ;
}
""".strip() + "\n",
        "shaders/shaders.properties": """
#if LIGHTING_MODE == 3
    image.imgDiffuseRT=texDiffuseRT RGBA RGBA16F HALF_FLOAT false true 1.0 1.0
#endif
screen.LIGHTING_TRACE_OPTIONS=\\
    LIGHTING_TRACE_RES LIGHTING_TRACE_SAMPLE_MAX \\
    LIGHTING_TINT_MODE LIGHTING_TINT_STRENGTH \\
    LIGHTING_TRACED_JITTER LIGHTING_TRACED_ACCUMULATE \\
    [LIGHTING_TRACE_BLOCK_OPTIONS] [LIGHTING_TRACE_ADVANCED_OPTIONS]
""".strip() + "\n",
        "shaders/program/depth_user.fsh": """
#include "/lib/common.glsl"
float f(float depth) {
    if (depth >= 1.0) return 0.0;
    return linearizeDepthFast(depth, near, far);
}
""".strip() + "\n",
        "shaders/program/dh_user.fsh": """
#include "/lib/common.glsl"
float f() { return linearizeDepthFast(gl_FragCoord.z, dhNearPlane, dhFarPlane); }
""".strip() + "\n",
        "shaders/lib/shadows/test.glsl": """
float shadowTest(float depthOpaque, float depthTrans) {
    if (depthTrans >= 1.0 || depthOpaque >= 1.0) return 1.0;
    return 0.0;
}
""".strip() + "\n",
    }
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, text in files.items():
            archive.writestr(name, text)


class SyntheticBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "synthetic-shrimple.zip"
        make_synthetic_source(self.source)

    def build_output(self, name: str = "built.zip") -> Path:
        output = self.root / name
        build(self.source, output, project_root=PROJECT_ROOT)
        return output

    def read(self, archive: zipfile.ZipFile, name: str) -> str:
        return archive.read(name).decode("utf-8", errors="strict")

    def test_overlay_and_patch_points(self) -> None:
        output = self.build_output()
        with zipfile.ZipFile(output) as archive:
            names = set(archive.namelist())
            self.assertIn("shaders/lib/phototonic/voxel_gi.glsl", names)
            self.assertIn("shaders/program/voxy.json", names)
            self.assertIn("shaders/world0/voxy_opaque.glsl", names)
            self.assertIn("shaders/world-1/voxy_opaque.glsl", names)
            self.assertIn("shaders/world1/voxy_opaque.glsl", names)
            self.assertIn("PhototonicSampleVoxelGI", self.read(archive, "shaders/program/composite10.fsh"))
            self.assertIn("PhototonicCaptureBlockAlbedo", self.read(archive, "shaders/program/gbuffers_terrain.fsh"))
            self.assertIn("PHOTOTONIC_GI_STRENGTH", self.read(archive, "shaders/shaders.properties"))

    def test_reversed_z_separates_camera_dh_and_shadow_depth(self) -> None:
        output = self.build_output()
        with zipfile.ZipFile(output) as archive:
            camera = self.read(archive, "shaders/program/depth_user.fsh")
            dh = self.read(archive, "shaders/program/dh_user.fsh")
            shadow = self.read(archive, "shaders/lib/shadows/test.glsl")
            hiz = self.read(archive, "shaders/program/deferred1.csh")
        self.assertIn("PhototonicIsBackgroundDepth(depth)", camera)
        self.assertIn("PhototonicLinearizeGameDepthFast(depth, near, far)", camera)
        self.assertIn("linearizeDepthFast(gl_FragCoord.z, dhNearPlane, dhFarPlane)", dh)
        self.assertNotIn("PhototonicLinearizeGameDepthFast(gl_FragCoord.z, dhNearPlane", dh)
        self.assertIn("depthTrans >= 1.0", shadow)
        self.assertIn("depthOpaque >= 1.0", shadow)
        self.assertIn("PhototonicNearestDepth", hiz)
        self.assertIn("PhototonicBackgroundDepthValue", hiz)

    def test_dimension_wrappers_define_the_world(self) -> None:
        output = self.build_output()
        with zipfile.ZipFile(output) as archive:
            self.assertIn('#include "overworld.glsl"', self.read(archive, "shaders/world0/voxy_opaque.glsl"))
            self.assertIn('#include "nether.glsl"', self.read(archive, "shaders/world-1/voxy_opaque.glsl"))
            self.assertIn('#include "end.glsl"', self.read(archive, "shaders/world1/voxy_opaque.glsl"))

    def test_build_is_byte_deterministic(self) -> None:
        first = self.build_output("first.zip")
        second = self.build_output("second.zip")
        self.assertEqual(hashlib.sha256(first.read_bytes()).digest(), hashlib.sha256(second.read_bytes()).digest())


@unittest.skipUnless(REAL_SOURCE.exists(), "Shrimple_v0.12.zip is not available in this test environment")
class RealShrimpleBuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.output = Path(cls.tmp.name) / "built.zip"
        build(REAL_SOURCE, cls.output, project_root=PROJECT_ROOT)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_real_pack_contains_phototonic_and_voxy_files(self) -> None:
        with zipfile.ZipFile(self.output) as archive:
            names = set(archive.namelist())
            self.assertIn("shaders/lib/phototonic/voxel_gi.glsl", names)
            self.assertIn("shaders/program/voxy.json", names)
            self.assertIn("shaders/world0/voxy_opaque.glsl", names)
            self.assertIn("shaders/world-1/voxy_opaque.glsl", names)
            self.assertIn("shaders/world1/voxy_opaque.glsl", names)

    def test_real_pack_patches_gi_and_reversed_z(self) -> None:
        with zipfile.ZipFile(self.output) as archive:
            composite10 = archive.read("shaders/program/composite10.fsh").decode()
            composite11 = archive.read("shaders/program/composite11.csh").decode()
            terrain = archive.read("shaders/program/gbuffers_terrain.fsh").decode()
            common = archive.read("shaders/lib/common.glsl").decode()
            depth_compat = archive.read("shaders/lib/phototonic/depth_compat.glsl").decode()
            props = archive.read("shaders/shaders.properties").decode()
        self.assertIn("PhototonicSampleVoxelGI", composite10)
        self.assertIn("PhototonicHasGeometryDepth(depth)", composite10)
        self.assertIn("PhototonicCaptureBlockAlbedo", terrain)
        self.assertIn("/lib/phototonic/depth_compat.glsl", common)
        self.assertIn("PHOTOTONIC_REVERSED_Z", depth_compat)
        self.assertIn("PhototonicDelinearizeGameDepth", composite11)
        self.assertIn("image.imgPhototonicBlockAlbedo", props)

    def test_no_active_old_camera_background_checks(self) -> None:
        offenders: list[str] = []
        with zipfile.ZipFile(self.output) as archive:
            for name in archive.namelist():
                if "/lib/shadows/" in name:
                    continue
                if not name.startswith("shaders/") or not name.endswith((".glsl", ".fsh", ".csh", ".vsh")):
                    continue
                text = archive.read(name).decode("utf-8", errors="replace")
                for line_number, line in enumerate(text.splitlines(), 1):
                    stripped = line.strip()
                    if stripped.startswith("//"):
                        continue
                    if any(token in line for token in (
                        "depth >= 1.0", "depth < 1.0",
                        "depthOpaque >= 1.0", "depthOpaque < 1.0",
                        "depthTrans >= 1.0", "depthTrans < 1.0",
                        "sampleDepth >= 1.0", "sampleDepth < 1.0",
                        "sampleClipDepth >= 1.0", "sampleClipDepth < 1.0",
                    )):
                        offenders.append(f"{name}:{line_number}:{stripped}")
        self.assertEqual([], offenders, "\n".join(offenders))


if __name__ == "__main__":
    unittest.main()
