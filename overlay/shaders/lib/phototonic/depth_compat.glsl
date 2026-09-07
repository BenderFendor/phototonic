#ifndef PHOTOTONIC_DEPTH_COMPAT_GLSL
#define PHOTOTONIC_DEPTH_COMPAT_GLSL

// Minecraft 26.2 switched the main world depth buffer to reversed-Z:
// geometry approaches 1.0 near the camera and the clear/background value is 0.0.
// Iris exposes MC_VERSION as major + two-digit minor + two-digit patch.
#if MC_VERSION >= 260200
    #define PHOTOTONIC_REVERSED_Z
#endif

bool PhototonicIsBackgroundDepth(const float depth) {
    #ifdef PHOTOTONIC_REVERSED_Z
        return depth <= 0.0000001;
    #else
        return depth >= 0.9999999;
    #endif
}

bool PhototonicHasGeometryDepth(const float depth) {
    return !PhototonicIsBackgroundDepth(depth);
}

float PhototonicBackgroundDepthValue() {
    #ifdef PHOTOTONIC_REVERSED_Z
        return 0.0;
    #else
        return 1.0;
    #endif
}

float PhototonicNearestDepth(const float a, const float b) {
    #ifdef PHOTOTONIC_REVERSED_Z
        return max(a, b);
    #else
        return min(a, b);
    #endif
}

float PhototonicToForwardDepth(const float depth) {
    #ifdef PHOTOTONIC_REVERSED_Z
        return 1.0 - depth;
    #else
        return depth;
    #endif
}

float PhototonicFromForwardDepth(const float depth) {
    #ifdef PHOTOTONIC_REVERSED_Z
        return 1.0 - depth;
    #else
        return depth;
    #endif
}

#endif
