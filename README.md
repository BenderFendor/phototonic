# Phototonic

Phototonic is a clean-room Minecraft 26.2 voxel ray-tracing experiment built around Iris, Shrimple's existing voxel scene, and Voxy's public shader-patch interface.

It does **not** contain, decompile, or redistribute Photonics. It also does not redistribute Shrimple: Shrimple 0.12 is All Rights Reserved, so this repository ships only original overlay files and a deterministic builder that applies them to a Shrimple ZIP you already have.

## Current scope

- Minecraft 26.2 reversed-Z compatibility helpers for the main Iris depth buffer.
- One-bounce, material-aware diffuse voxel GI on Shrimple's existing traced-light voxel scene.
- Per-frame block/material albedo capture without copying Shrimple textures into a second scene structure.
- Emissive-block contribution using Shrimple's existing static light table.
- Colored-glass transmission through the voxel GI path.
- Voxy v1 shader-patch integration for opaque LOD terrain, plus a conservative translucent fallback.
- OpenGL/Iris first. There is no Vulkan backend in this repository yet.

## Build a pack locally

```bash
python -m phototonic.builder /path/to/Shrimple_v0.12.zip -o Phototonic-Shrimple.zip
```

The input ZIP is never added to the repository. The builder verifies that it looks like the expected Shrimple distribution before patching it.

For the GI path, use Shrimple's traced block-lighting mode (`LIGHTING_MODE=3`, the RTX profile). Phototonic settings are injected alongside the traced-light settings.

## Voxy

Phototonic provides `voxy.json`, `voxy_opaque.glsl`, and `voxy_translucent.glsl` for all three vanilla dimensions. The opaque path writes the deferred color/material/normal buffers Shrimple expects. The current translucent path is deliberately conservative rather than pretending to reconstruct Shrimple's water material model from information Voxy does not expose.

The current Voxy development line targets Minecraft 26.2, Iris 1.11.2, and Sodium 0.9.x. Phototonic uses only Voxy's public shader-patch contract; it does not copy Voxy code.

## Status

This is an early implementation. The builder and structural regression tests run without Minecraft, but GPU shader compilation and in-game image-quality/performance validation still need a real Minecraft 26.2 + Iris + Voxy runtime.
