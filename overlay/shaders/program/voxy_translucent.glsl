#define RENDER_VOXY
#define RENDER_GBUFFER
#define RENDER_FRAG
#define RENDER_TRANSLUCENT

#include "/lib/constants.glsl"
#include "/lib/common.glsl"

layout(location = 0) out vec4 outFinal;

void voxy_emitFragment(VoxyFragmentParameters parameters) {
    vec4 color = parameters.sampledColour * parameters.tinting;
    outFinal = vec4(clamp(color.rgb, vec3(0.0), vec3(1.0)), clamp(color.a, 0.0, 1.0));
}
