from __future__ import annotations

import argparse
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

VERSION = "0.1.0"
EXPECTED_FILES = (
    "LICENSE",
    "shaders/lib/common.glsl",
    "shaders/lib/sampling/depth.glsl",
    "shaders/program/gbuffers_terrain.fsh",
    "shaders/program/composite10.fsh",
    "shaders/program/deferred1.csh",
    "shaders/shaders.properties",
)

SETTINGS_BLOCK = r'''
// Phototonic clean-room voxel GI
#define PHOTOTONIC_ENABLED
#define PHOTOTONIC_GI_STRENGTH 70 // [0 10 20 30 40 50 60 70 80 90 100 120 140 160 180 200]
#define PHOTOTONIC_GI_DISTANCE 32 // [8 12 16 24 32 40 48 64 80 96]
#define PHOTOTONIC_GI_SKY 30 // [0 5 10 15 20 25 30 40 50 60 70 80 90 100]
#define PHOTOTONIC_GI_EMISSION 100 // [0 25 50 75 100 125 150 200 300 400]
#define PHOTOTONIC_GI_AMBIENT 2 // [0 1 2 3 4 5 6 8 10 12 16 20]

const float Phototonic_GiStrengthF = PHOTOTONIC_GI_STRENGTH * 0.01;
const float Phototonic_GiDistance = float(PHOTOTONIC_GI_DISTANCE);
const float Phototonic_GiSkyF = PHOTOTONIC_GI_SKY * 0.01;
const float Phototonic_GiEmissionF = PHOTOTONIC_GI_EMISSION * 0.01;
const float Phototonic_GiAmbientF = PHOTOTONIC_GI_AMBIENT * 0.01;
'''.strip()

DEPTH_WRAPPERS = r'''

float PhototonicLinearizeGameDepth(const in float depth, const in float zNear, const in float zFar) {
    return linearizeDepth(PhototonicToForwardDepth(depth), zNear, zFar);
}

float PhototonicLinearizeGameDepthFast(const in float depth, const in float zNear, const in float zFar) {
    return linearizeDepthFast(PhototonicToForwardDepth(depth), zNear, zFar);
}

vec3 PhototonicLinearizeGameDepthFast3(const in vec3 depth, const in float zNear, const in float zFar) {
    #ifdef PHOTOTONIC_REVERSED_Z
        return linearizeDepthFast3(vec3(1.0) - depth, zNear, zFar);
    #else
        return linearizeDepthFast3(depth, zNear, zFar);
    #endif
}

float PhototonicDelinearizeGameDepth(const in float linearDepth, const in float zNear, const in float zFar) {
    return PhototonicFromForwardDepth(delinearizeDepth(linearDepth, zNear, zFar));
}
'''.rstrip()


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one anchor, found {count}")
    return text.replace(old, new, 1)


def _safe_extract(source: Path, destination: Path) -> None:
    with zipfile.ZipFile(source) as archive:
        root = destination.resolve()
        for member in archive.infolist():
            target = (destination / member.filename).resolve()
            if root not in target.parents and target != root:
                raise RuntimeError(f"unsafe ZIP member: {member.filename}")
        archive.extractall(destination)


def _pack_root(extracted: Path) -> Path:
    if (extracted / "shaders").is_dir():
        return extracted
    children = [p for p in extracted.iterdir() if p.is_dir()]
    if len(children) == 1 and (children[0] / "shaders").is_dir():
        return children[0]
    raise RuntimeError("could not locate shader-pack root")


def _validate_source(root: Path) -> None:
    missing = [name for name in EXPECTED_FILES if not (root / name).is_file()]
    if missing:
        raise RuntimeError("source pack is missing expected files: " + ", ".join(missing))
    license_text = (root / "LICENSE").read_text(encoding="utf-8", errors="replace")
    if "All Rights Reserved" not in license_text or "Joshua Miller" not in license_text:
        raise RuntimeError("source does not look like the expected Shrimple distribution")


def _patch_common(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = _replace_once(
        text,
        "#define LIGHTING_TRACED_JITTER",
        "#define LIGHTING_TRACED_JITTER\n\n" + SETTINGS_BLOCK,
        label="common settings",
    )
    text += '\n\n#include "/lib/phototonic/depth_compat.glsl"\n'
    path.write_text(text, encoding="utf-8")


def _patch_depth_library(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "PhototonicLinearizeGameDepth" not in text:
        text = text.rstrip() + DEPTH_WRAPPERS + "\n"
    path.write_text(text, encoding="utf-8")


def _patch_terrain(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = _replace_once(
        text,
        '#include "/lib/common.glsl"',
        '#include "/lib/common.glsl"\n#include "/lib/phototonic/material_cache.glsl"',
        label="terrain material-cache include",
    )
    text = _replace_once(
        text,
        "vec3 albedo = RGBToLinear(color.rgb);",
        "vec3 albedo = RGBToLinear(color.rgb);\n\n    #ifdef PHOTOTONIC_ENABLED\n        PhototonicCaptureBlockAlbedo(uint(vIn.blockId), albedo);\n    #endif",
        label="terrain albedo capture",
    )
    path.write_text(text, encoding="utf-8")


def _patch_composite10(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = _replace_once(
        text,
        '#include "/lib/lighting/voxel/tracing.glsl"',
        '#include "/lib/lighting/voxel/tracing.glsl"\n#include "/lib/phototonic/material_cache.glsl"\n#include "/lib/phototonic/voxel_gi.glsl"',
        label="composite10 GI include",
    )
    text = _replace_once(
        text,
        "if (depth < 1.0) {",
        "if (PhototonicHasGeometryDepth(depth)) {",
        label="composite10 depth background test",
    )
    anchor = "SampleDynamicLighting(diffuseFinal, specularFinal, localPos, localNormal, texNormal, albedo, roughL, metal_f0, occlusion, sss);"
    text = _replace_once(
        text,
        anchor,
        anchor + "\n\n        #ifdef PHOTOTONIC_ENABLED\n            diffuseFinal += PhototonicSampleVoxelGI(localPos, localNormal, frameCounter);\n        #endif",
        label="composite10 GI injection",
    )
    path.write_text(text, encoding="utf-8")


def _patch_properties(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    image_line = "image.imgPhototonicBlockAlbedo=none RED_INTEGER R32UI UNSIGNED_INT true false 2048 1"
    anchor = "#if LIGHTING_MODE == 3\n    image.imgDiffuseRT=texDiffuseRT RGBA RGBA16F HALF_FLOAT false true 1.0 1.0"
    text = _replace_once(text, anchor, image_line + "\n\n" + anchor, label="Phototonic material image")

    trace_anchor = """    LIGHTING_TRACED_JITTER LIGHTING_TRACED_ACCUMULATE \\
    [LIGHTING_TRACE_BLOCK_OPTIONS] [LIGHTING_TRACE_ADVANCED_OPTIONS]"""
    trace_replacement = """    LIGHTING_TRACED_JITTER LIGHTING_TRACED_ACCUMULATE \\
    PHOTOTONIC_GI_STRENGTH PHOTOTONIC_GI_DISTANCE PHOTOTONIC_GI_SKY \\
    PHOTOTONIC_GI_EMISSION PHOTOTONIC_GI_AMBIENT \\
    [LIGHTING_TRACE_BLOCK_OPTIONS] [LIGHTING_TRACE_ADVANCED_OPTIONS]"""
    text = _replace_once(text, trace_anchor, trace_replacement, label="Phototonic settings screen")
    path.write_text(text, encoding="utf-8")


_DEPTH_CALL_RE = re.compile(
    r"\b(linearizeDepthFast3|linearizeDepthFast|linearizeDepth)\(\s*"
    r"(gl_FragCoord\.z|depth(?:Now|Opaque|Trans)?|sampleDepth|sampleClipDepth|reflectDepth)\b"
)
_DEPTH_COMPARISON_NAMES = (
    "depth", "depthNow", "depthOpaque", "depthTrans", "sampleDepth", "sampleClipDepth", "reflectDepth",
)


def _patch_hiz(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = _replace_once(text, "minZ = min(minZ, sampleZ);", "minZ = PhototonicNearestDepth(minZ, sampleZ);", label="Hi-Z direct sample reduction")
    text = _replace_once(
        text,
        "float sampleWeight = float(any(greaterThanEqual(sampleUV, sourceSize)));\n\tminZ = min(minZ, max(sampleZ, sampleWeight));",
        "bool outOfBounds = any(greaterThanEqual(sampleUV, sourceSize));\n\tfloat candidateDepth = outOfBounds ? PhototonicBackgroundDepthValue() : sampleZ;\n\tminZ = PhototonicNearestDepth(minZ, candidateDepth);",
        label="Hi-Z tile sample reduction",
    )
    text = text.replace("float minZ = 1.0;", "float minZ = PhototonicBackgroundDepthValue();")
    text = text.replace("minZ = 1.0;", "minZ = PhototonicBackgroundDepthValue();")
    path.write_text(text, encoding="utf-8")


def _patch_reversed_z_tree(shader_root: Path) -> None:
    function_map = {
        "linearizeDepth": "PhototonicLinearizeGameDepth",
        "linearizeDepthFast": "PhototonicLinearizeGameDepthFast",
        "linearizeDepthFast3": "PhototonicLinearizeGameDepthFast3",
    }
    extensions = {".glsl", ".fsh", ".csh", ".vsh", ".gsh", ".tes", ".tcs"}
    for path in shader_root.rglob("*"):
        if not path.is_file() or path.suffix not in extensions:
            continue
        posix = path.as_posix()
        if posix.endswith("/lib/sampling/depth.glsl") or "/lib/shadows/" in posix:
            continue
        text = path.read_text(encoding="utf-8")
        original = text

        def depth_call(match: re.Match[str]) -> str:
            return function_map[match.group(1)] + "(" + match.group(2)

        text = _DEPTH_CALL_RE.sub(depth_call, text)
        text = text.replace("PhototonicLinearizeGameDepthFast(gl_FragCoord.z, dhNearPlane", "linearizeDepthFast(gl_FragCoord.z, dhNearPlane")
        text = text.replace("PhototonicLinearizeGameDepth(gl_FragCoord.z, dhNearPlane", "linearizeDepth(gl_FragCoord.z, dhNearPlane")
        for name in _DEPTH_COMPARISON_NAMES:
            text = re.sub(rf"\b{re.escape(name)}\s*>=\s*1\.0", f"PhototonicIsBackgroundDepth({name})", text)
            text = re.sub(rf"\b{re.escape(name)}\s*<\s*1\.0", f"PhototonicHasGeometryDepth({name})", text)
            text = re.sub(rf"\b{re.escape(name)}\s*==\s*1\.0", f"PhototonicIsBackgroundDepth({name})", text)
        if text != original:
            path.write_text(text, encoding="utf-8")

    c11 = shader_root / "program/composite11.csh"
    if c11.exists():
        text = c11.read_text(encoding="utf-8")
        text = text.replace("delinearizeDepth(depthL, near, dhFarPlane)", "PhototonicDelinearizeGameDepth(depthL, near, dhFarPlane)")
        text = text.replace("delinearizeDepth(depthL, near, farPlane)", "PhototonicDelinearizeGameDepth(depthL, near, farPlane)")
        c11.write_text(text, encoding="utf-8")


def _overlay(project_root: Path, pack_root: Path) -> None:
    shutil.copytree(project_root / "overlay", pack_root, dirs_exist_ok=True)


def build(source: Path, output: Path, project_root: Path | None = None) -> Path:
    source = source.resolve()
    output = output.resolve()
    project_root = (project_root or Path(__file__).resolve().parents[1]).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)

    with tempfile.TemporaryDirectory(prefix="phototonic-") as tmp:
        extracted = Path(tmp) / "pack"
        extracted.mkdir()
        _safe_extract(source, extracted)
        root = _pack_root(extracted)
        _validate_source(root)
        _overlay(project_root, root)

        _patch_common(root / "shaders/lib/common.glsl")
        _patch_depth_library(root / "shaders/lib/sampling/depth.glsl")
        _patch_terrain(root / "shaders/program/gbuffers_terrain.fsh")
        _patch_composite10(root / "shaders/program/composite10.fsh")
        _patch_properties(root / "shaders/shaders.properties")
        _patch_hiz(root / "shaders/program/deferred1.csh")
        _patch_reversed_z_tree(root / "shaders")

        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists():
            output.unlink()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for file in sorted(root.rglob("*")):
                if not file.is_file():
                    continue
                relative = file.relative_to(root).as_posix()
                info = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, file.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the Phototonic overlay on a local Shrimple distribution")
    parser.add_argument("source", type=Path, help="path to an unmodified Shrimple ZIP")
    parser.add_argument("-o", "--output", type=Path, default=Path("Phototonic-Shrimple.zip"))
    args = parser.parse_args()
    print(build(args.source, args.output))


if __name__ == "__main__":
    main()
