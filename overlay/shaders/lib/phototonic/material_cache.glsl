#ifndef PHOTOTONIC_MATERIAL_CACHE_GLSL
#define PHOTOTONIC_MATERIAL_CACHE_GLSL

#ifdef PHOTOTONIC_ENABLED
    // One representative linear-space albedo per Shrimple block/material id.
    // The custom image is cleared each frame. Terrain fragments atomically claim
    // the first sample for an id, avoiding undefined competing imageStore writes.
    layout(r32ui) uniform coherent uimage2D imgPhototonicBlockAlbedo;

    const uint PHOTOTONIC_BLOCK_MATERIAL_CAPACITY = 2048u;

    void PhototonicCaptureBlockAlbedo(const uint blockId, const vec3 linearAlbedo) {
        if (blockId >= PHOTOTONIC_BLOCK_MATERIAL_CAPACITY) return;
        vec3 clampedAlbedo = clamp(linearAlbedo, vec3(0.0), vec3(1.0));
        uint packed = packUnorm4x8(vec4(clampedAlbedo, 1.0));
        imageAtomicCompSwap(imgPhototonicBlockAlbedo, ivec2(int(blockId), 0), 0u, packed);
    }

    vec3 PhototonicLoadBlockAlbedo(const uint blockId) {
        if (blockId >= PHOTOTONIC_BLOCK_MATERIAL_CAPACITY) return vec3(0.5);
        uint packed = imageLoad(imgPhototonicBlockAlbedo, ivec2(int(blockId), 0)).r;
        if (packed == 0u) return vec3(0.5);
        return unpackUnorm4x8(packed).rgb;
    }
#endif

#endif
