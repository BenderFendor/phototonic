#ifndef PHOTOTONIC_VOXEL_GI_GLSL
#define PHOTOTONIC_VOXEL_GI_GLSL

#ifdef PHOTOTONIC_ENABLED

#ifdef WORLD_SKY_ENABLED
vec3 GetSkyLightColor();
#endif

struct PhototonicHit {
    bool hit;
    uint blockId;
    vec3 normal;
    float distance;
    vec3 transmission;
};

vec3 PhototonicCosineHemisphere(const vec3 normal, const vec2 sampleUv) {
    float phi = TAU * sampleUv.x;
    float r = sqrt(sampleUv.y);
    float z = sqrt(max(1.0 - sampleUv.y, 0.0));
    vec3 localDirection = vec3(r * cos(phi), r * sin(phi), z);
    vec3 helper = abs(normal.z) < 0.999 ? vec3(0.0, 0.0, 1.0) : vec3(1.0, 0.0, 0.0);
    vec3 tangent = normalize(cross(helper, normal));
    vec3 bitangent = cross(normal, tangent);
    return normalize(tangent * localDirection.x + bitangent * localDirection.y + normal * localDirection.z);
}

PhototonicHit PhototonicTraceFirstHit(const vec3 origin, const vec3 direction, const float maxDistance) {
    PhototonicHit result;
    result.hit = false;
    result.blockId = BLOCK_EMPTY;
    result.normal = vec3(0.0);
    result.distance = maxDistance;
    result.transmission = vec3(1.0);

    vec3 dir = normalize(direction);
    vec3 stepDir = sign(dir);
    vec3 safeDir = vec3(
        abs(dir.x) < EPSILON ? (dir.x < 0.0 ? -EPSILON : EPSILON) : dir.x,
        abs(dir.y) < EPSILON ? (dir.y < 0.0 ? -EPSILON : EPSILON) : dir.y,
        abs(dir.z) < EPSILON ? (dir.z < 0.0 ? -EPSILON : EPSILON) : dir.z
    );
    vec3 stepSizes = rcp(abs(safeDir));
    vec3 nextDist = (stepDir * 0.5 + 0.5 - fract(origin)) / safeDir;

    vec3 current = origin;
    ivec3 gridCell;
    ivec3 blockCell;

    const int maxSteps = int(DDAStepCount);
    for (int i = 0; i < maxSteps; ++i) {
        float stepDistance = minOf(nextDist);
        if (stepDistance > maxDistance) break;

        vec3 previous = current;
        current = origin + dir * stepDistance;
        vec3 axisMask = vec3(lessThanEqual(nextDist, vec3(stepDistance + 0.000001)));
        nextDist += stepSizes * axisMask;

        vec3 voxelPos = floor(current + dir * 0.0001);
        if (!GetVoxelGridCell(voxelPos, gridCell, blockCell)) continue;

        uint gridIndex = GetVoxelGridCellIndex(gridCell);
        uint blockId = GetVoxelBlockMask(blockCell, gridIndex);
        if (blockId == BLOCK_EMPTY || blockId >= 1280u) continue;

        #if LIGHTING_TINT_MODE != LIGHT_TINT_NONE
            if (blockId >= BLOCK_HONEY && blockId <= BLOCK_TINTED_GLASS) {
                vec3 glassTint = GetLightGlassTint(blockId);
                #if LIGHTING_TINT_MODE == LIGHT_TINT_ABSORB
                    result.transmission *= exp(-2.0 * Lighting_TintF * max(length(current - previous), 0.01) * (1.0 - glassTint));
                #else
                    result.transmission *= mix(vec3(1.0), glassTint, min(Lighting_TintF, 1.0));
                #endif
                continue;
            }
        #endif

        bool solidHit = blockId == BLOCK_SOLID || IsTraceFullBlock(blockId);
        if (!solidHit) {
            vec3 segment = current - previous;
            solidHit = TraceHitTest(blockId, previous - voxelPos, rcp(segment));
        }
        if (!solidHit) continue;

        result.hit = true;
        result.blockId = blockId;
        result.distance = stepDistance;
        result.normal = -stepDir * axisMask;
        if (length2(result.normal) < EPSILON) result.normal = -dir;
        else result.normal = normalize(result.normal);
        return result;
    }

    return result;
}

vec3 PhototonicSampleVoxelGI(const vec3 localPos, const vec3 localNormal, const int frameIndex) {
    vec3 randomValue = hash32(gl_FragCoord.xy + vec2(float(frameIndex) * 0.75487766, float(frameIndex) * 0.56984029));
    vec3 rayDirection = PhototonicCosineHemisphere(normalize(localNormal), randomValue.xy);
    vec3 voxelOrigin = GetVoxelBlockPosition(localPos + normalize(localNormal) * 0.02);
    PhototonicHit hit = PhototonicTraceFirstHit(voxelOrigin, rayDirection, Phototonic_GiDistance);

    if (!hit.hit) {
        #ifdef WORLD_SKY_ENABLED
            return hit.transmission * GetSkyLightColor() * Phototonic_GiSkyF;
        #else
            return vec3(0.0);
        #endif
    }

    vec3 hitAlbedo = PhototonicLoadBlockAlbedo(hit.blockId);
    float hitFacingSky = max(hit.normal.y, 0.0);
    vec3 incoming = vec3(Phototonic_GiAmbientF);
    #ifdef WORLD_SKY_ENABLED
        incoming += GetSkyLightColor() * (Phototonic_GiSkyF * hitFacingSky);
    #endif

    uint lightType = StaticBlockMap[hit.blockId].lightType;
    if (lightType > 0u && lightType < 256u) {
        vec3 emissionColor = unpackUnorm4x8(StaticLightMap[lightType].Color).rgb;
        incoming += emissionColor * Phototonic_GiEmissionF;
    }

    float distanceFade = 1.0 - saturate(hit.distance / max(Phototonic_GiDistance, 0.001));
    return hit.transmission * hitAlbedo * incoming * distanceFade * Phototonic_GiStrengthF;
}

#endif

#endif
