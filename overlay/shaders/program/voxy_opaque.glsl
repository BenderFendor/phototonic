#define RENDER_VOXY
#define RENDER_GBUFFER
#define RENDER_FRAG

#include "/lib/constants.glsl"
#include "/lib/common.glsl"

layout(location = 0) out vec4 outDeferredColor;
layout(location = 1) out uvec4 outDeferredData;
layout(location = 2) out vec3 outDeferredTexNormal;
layout(location = 3) out vec4 outVelocity;

vec3 PhototonicVoxyFaceNormal(const uint face) {
    vec3 axis = vec3(
        uint((face >> 1u) == 2u),
        uint((face >> 1u) == 0u),
        uint((face >> 1u) == 1u)
    );
    return axis * (float(int(face & 1u)) * 2.0 - 1.0);
}

void voxy_emitFragment(VoxyFragmentParameters parameters) {
    vec3 baseColor = clamp(parameters.sampledColour.rgb * parameters.tinting.rgb, vec3(0.0), vec3(1.0));
    vec3 localNormal = PhototonicVoxyFaceNormal(parameters.face);
    float roughness = 1.0;
    float metalF0 = 0.04;
    float occlusion = 1.0;
    float emission = 0.0;
    float sss = 0.0;

    outDeferredColor = vec4(baseColor, 1.0);
    outDeferredTexNormal = localNormal * 0.5 + 0.5;
    outDeferredData.r = packUnorm4x8(vec4(localNormal * 0.5 + 0.5, sss));
    outDeferredData.g = packUnorm4x8(vec4(clamp(parameters.lightMap, vec2(0.0), vec2(1.0)), occlusion, emission));
    outDeferredData.b = packUnorm4x8(vec4(0.0, 1.0, 0.0, 0.0));
    outDeferredData.a = packUnorm4x8(vec4(roughness, metalF0, 0.0, 1.0));
    outVelocity = vec4(0.0);
}
