// GLSL for the hologram. One particle system holds all three creatures; each particle
// knows where it lives in every form, so switching assistants is a true morph.

export const COMMON = /* glsl */`
uniform float uTime, uLevel, uOnset, uMic, uBreath, uAssemble, uHumor, uBeat, uMorphT, uThinkAge;
uniform vec4 uBands;          // voice spectrum: low, low-mid, high-mid, high
uniform vec4 uState;          // listen, think, speak, notice (each 0..1, smoothed)
uniform vec3 uMorph;          // weight of jarvis, friday, robin
uniform vec2 uSpin;           // user rotation (pinch-drag)
const float PI = 3.14159265;
mat2 rot(float a) { float c = cos(a), s = sin(a); return mat2(c, -s, s, c); }
float hash(float n) { return fract(sin(n) * 43758.5453123); }
vec3 hash3(float n) { return fract(sin(vec3(n, n + 1.7, n + 3.1)) * vec3(43758.5453, 22578.1459, 19642.3490)); }
float noise(vec3 p) {
  vec3 i = floor(p); vec3 f = fract(p); f = f * f * (3.0 - 2.0 * f);
  float n = i.x + i.y * 57.0 + i.z * 113.0;
  return mix(mix(mix(hash(n), hash(n + 1.0), f.x), mix(hash(n + 57.0), hash(n + 58.0), f.x), f.y),
             mix(mix(hash(n + 113.0), hash(n + 114.0), f.x), mix(hash(n + 170.0), hash(n + 171.0), f.x), f.y), f.z);
}
vec3 swirl(vec3 p, float t) {   // cheap curl-like flow used while morphing and for drift
  return vec3(noise(p * 1.7 + vec3(0.0, t, 7.0)), noise(p * 1.7 + vec3(13.0, 0.0, t)), noise(p * 1.7 + vec3(t, 29.0, 0.0))) - 0.5;
}
vec3 userSpin(vec3 p) { p.xz = rot(uSpin.x) * p.xz; p.yz = rot(uSpin.y) * p.yz; return p; }
`;

export const POINTS_VERT = COMMON + /* glsl */`
attribute vec3 aJ, aF, aR;    // per-form parameters (see forms.js)
attribute vec4 aRand;
attribute vec3 aKind;         // subtype inside each form
uniform float uPixel, uScale;
uniform vec3 uColJ, uColJ2, uColF, uColF2, uColR, uColR2, uThink;
varying vec3 vColor; varying float vAlpha; varying float vType; varying float vSeed;

// ---- JARVIS: the golden mind ------------------------------------------------------------
vec3 formJ(out float glow, out float size) {
  vec3 p = aJ;
  float r = length(p);
  p *= 1.0 + uBreath * 0.045 + uState.x * uMic * 0.10;
  p += swirl(p * 1.3 + aRand.xyz * 4.0, uTime * 0.12) * (0.035 + 0.03 * uHumor);
  // thinking: neurons fire in cascades that sweep through the volume
  float sweep = fract(uTime * (0.35 + 0.5 * uThinkAge) + aRand.x * 0.15 - dot(normalize(p + 0.001), vec3(0.3, 0.8, 0.5)) * 0.5);
  float fire = pow(max(0.0, 1.0 - abs(sweep - 0.5) * 5.0), 3.0) * uState.y;
  // speaking: a wave of light rolls outward from the core with every syllable
  float front = fract(uTime * 0.9 + uOnset * 0.2) * 1.25;
  float wave = smoothstep(0.16, 0.0, abs(r - front)) * (0.35 + uLevel * 1.6) * uState.z;
  p += normalize(p + 0.0001) * (wave * 0.07 + uLevel * 0.05 * uState.z + uOnset * 0.05 * aRand.y);
  // idle micro-events: a rare spark
  float spark = step(0.9965, fract(aRand.z + floor(uTime * 1.3) * 0.618)) * (1.0 - max(uState.y, uState.z));
  p.xz = rot(uTime * 0.11 + uState.y * uTime * 0.05) * p.xz;
  glow = 0.42 + fire * 1.5 + wave * 1.3 + spark * 2.5 + uState.w * 0.6 + aKind.x * 0.3;
  size = mix(1.0, 2.1, aKind.x) * (1.0 + fire * 0.8 + wave * 0.9 + spark * 2.0);
  return p;
}

// ---- FRIDAY: the solar forge ------------------------------------------------------------
vec3 formF(out float glow, out float size) {
  vec3 p; glow = 0.5; size = 1.0;
  float band = uBands.x * (1.0 - aRand.w) + uBands.z * aRand.w;
  if (aKind.y < 0.5) {            // plasma core surface
    vec3 n = normalize(aF);
    float boil = noise(n * 3.0 + uTime * 0.6) - 0.5;
    p = n * (0.36 + boil * 0.07 + uLevel * 0.10 * uState.z + uBreath * 0.02 + uState.x * uMic * 0.06);
    glow = 0.75 + uLevel * 1.2 * uState.z + boil * 0.5; size = 1.25;
  } else if (aKind.y < 1.5) {     // charged particles riding dipole field lines
    float L = aF.x * (1.0 + band * 0.55 * uState.z + uBreath * 0.04);
    float phi = aF.y + uState.y * sin(aF.z * 6.283 + uTime * 1.6) * 0.9 + uTime * 0.05;   // field twists while thinking
    float theta = fract(aF.z + uTime * (0.045 + 0.05 * aRand.x + 0.12 * uState.y) * (aRand.y > 0.5 ? 1.0 : -1.0)) * PI;
    float rr = L * sin(theta) * sin(theta);
    p = vec3(rr * sin(theta) * cos(phi), rr * cos(theta), rr * sin(theta) * sin(phi));
    p += (aRand.xyz - 0.5) * 0.025;
    glow = 0.45 + band * 1.3 * uState.z + uState.x * uMic; size = 0.9 + band * 0.9;
  } else {                        // coronal flares: thrown out on strong syllables
    vec3 n = normalize(aF);
    float life = fract(aRand.x + uTime * (0.22 + aRand.y * 0.3));
    float reach = 0.4 + life * (0.35 + 1.5 * uOnset * uState.z + 0.25 * uState.z * uLevel);
    p = n * reach + swirl(n * 2.0, uTime * 0.3) * 0.12 * life;
    glow = (1.0 - life) * (0.25 + 1.8 * uOnset * uState.z + 0.3 * uState.w); size = 0.8 + (1.0 - life);
  }
  p.xz = rot(uTime * 0.07) * p.xz;
  p.xy = rot(0.32) * p.xy;        // tilted magnetic axis
  return p;
}

// ---- ROBIN: the petal archive -----------------------------------------------------------
vec3 formR(out float glow, out float size, out float type) {
  vec3 p; glow = 0.5; size = 1.0; type = 0.0;
  if (aKind.z < 0.5) {            // fracturing crystal: nested shells counter-rotating
    p = aR;
    float shell = aRand.w;        // 0, 0.5, 1 for the three shells
    float dir = shell < 0.25 ? 1.0 : (shell < 0.75 ? -1.0 : 0.6);
    p.xz = rot(uTime * 0.16 * dir + uState.y * uTime * 0.2 * dir) * p.xz;
    p.xy = rot(uTime * 0.07 * dir) * p.xy;
    float burst = (uLevel * 0.30 + uOnset * 0.35) * uState.z * step(0.55, aRand.x);   // vertices burst with her voice
    p *= 1.0 + burst * (0.4 + aRand.y) + uBreath * 0.03 + uState.x * uMic * 0.08;
    glow = 0.55 + burst * 2.0 + uState.y * 0.3; size = 1.0 + burst * 2.0;
  } else if (aKind.z < 1.5) {     // glyph helices: runes climb while she reads / thinks
    float climb = 0.035 + 0.22 * uState.y + 0.05 * uState.z;
    float h = fract(aR.y + uTime * climb) * 2.2 - 1.1;
    float ang = aR.x + h * 2.6 + uTime * 0.25;
    float rad = aR.z * (1.0 + 0.08 * sin(uTime + aR.x));
    p = vec3(cos(ang) * rad, h, sin(ang) * rad);
    glow = (0.35 + 0.9 * uState.y + 0.3 * uState.z * uLevel) * smoothstep(1.1, 0.7, abs(h)); size = 2.6; type = 1.0;
  } else {                        // sakura vortex: petals shaken loose when she speaks
    float fall = fract(aR.y - uTime * (0.03 + 0.04 * aRand.x));
    float h = fall * 2.4 - 1.2;
    float ang = aR.x + uTime * (0.22 + 0.2 * aRand.y) + h * 1.2;
    float rad = aR.z * (0.75 + 0.5 * fall) + (uLevel * 0.35 + uOnset * 0.5) * uState.z * aRand.z;
    p = vec3(cos(ang) * rad, h, sin(ang) * rad);
    p += swirl(p + aRand.xyz, uTime * 0.2) * 0.12;
    glow = 0.55 + 0.4 * uState.z * uLevel; size = 2.4 + aRand.x * 1.6; type = 2.0;
  }
  return p;
}

void main() {
  float gJ, sJ, gF, sF, gR, sR, tR;
  vec3 pJ = formJ(gJ, sJ);
  vec3 pF = formF(gF, sF);
  vec3 pR = formR(gR, sR, tR);
  vec3 p = pJ * uMorph.x + pF * uMorph.y + pR * uMorph.z;
  float glow = gJ * uMorph.x + gF * uMorph.y + gR * uMorph.z;
  float size = sJ * uMorph.x + sF * uMorph.y + sR * uMorph.z;

  // hand-off: mid-morph the particles flow like a liquid instead of sliding in straight lines
  float flow = sin(uMorphT * PI);
  p += swirl(p * 1.2 + aRand.xyz * 3.0, uTime * 0.5 + aRand.w) * flow * 0.9;
  p.xz = rot(flow * (aRand.x - 0.5) * 2.2) * p.xz;
  glow += flow * 0.5;

  // boot assembly / clean-slate collapse
  float a = smoothstep(aRand.w * 0.6, aRand.w * 0.6 + 0.4, uAssemble);
  vec3 scattered = normalize(aRand.xyz - 0.5 + 0.001) * (3.5 + aRand.w * 3.0);
  p = mix(scattered, p, a);
  glow *= 0.25 + 0.75 * a;

  // playful wobble at high humor, heartbeat on the metronome
  p.y += sin(uTime * 2.2 + p.x * 3.0) * 0.02 * uHumor;
  p *= 1.0 + uBeat * 0.06;
  p = userSpin(p);

  vec3 base = uColJ * uMorph.x + uColF * uMorph.y + uColR * uMorph.z;
  vec3 alt = uColJ2 * uMorph.x + uColF2 * uMorph.y + uColR2 * uMorph.z;
  vec3 col = mix(base, alt, aRand.y * 0.9);
  col = mix(col, uThink, uState.y * 0.45 * (0.5 + 0.5 * sin(uTime * 3.0 + aRand.x * 20.0)));
  vColor = col;
  vAlpha = clamp(glow, 0.0, 3.0);
  vType = tR * step(0.5, uMorph.z) * step(flow, 0.6);
  vSeed = aRand.x;

  vec4 mv = modelViewMatrix * vec4(p * uScale, 1.0);
  gl_Position = projectionMatrix * mv;
  gl_PointSize = size * uPixel * (2.6 / -mv.z) * (0.75 + 0.5 * aRand.z);
}
`;

export const POINTS_FRAG = /* glsl */`
precision highp float;
uniform sampler2D uGlyphs; uniform float uTime;
varying vec3 vColor; varying float vAlpha; varying float vType; varying float vSeed;
void main() {
  vec2 uv = gl_PointCoord;
  vec2 c = uv - 0.5;
  float d = length(c);
  float a;
  vec3 col = vColor;
  if (vType > 1.5) {            // petal: a rotated, notched teardrop
    float ang = vSeed * 6.283 + uTime * (0.6 + vSeed);
    float cs = cos(ang), sn = sin(ang);
    vec2 q = vec2(c.x * cs - c.y * sn, c.x * sn + c.y * cs) * 2.0;
    q.x *= 1.0 + 0.9 * sin(uTime * 1.3 + vSeed * 30.0);   // tumbling: the petal turns edge-on
    float petal = length(vec2(q.x * 1.55, q.y - 0.12 * (1.0 - q.y)));
    float notch = smoothstep(0.0, 0.12, length(q - vec2(0.0, 0.62)) - 0.13);
    a = smoothstep(0.62, 0.42, petal) * notch;
    col = mix(col, vec3(1.0, 0.72, 0.86), 0.65) * (0.75 + 0.5 * q.y);
    a *= 0.75;
  } else if (vType > 0.5) {     // rune from the glyph atlas
    float idx = floor(vSeed * 16.0);
    vec2 cell = vec2(mod(idx, 4.0), floor(idx / 4.0));
    a = texture2D(uGlyphs, (cell + vec2(uv.x, 1.0 - uv.y)) / 4.0).r * 1.2;
  } else {                      // soft point of light with a hot centre
    if (d > 0.5) discard;
    a = smoothstep(0.5, 0.0, d);
    a = a * a + smoothstep(0.12, 0.0, d) * 0.6;
  }
  gl_FragColor = vec4(col * a * vAlpha, a * vAlpha);
}
`;

// JARVIS filaments: circuit-like light fragments between neurons, with pulses running along them
export const LINES_VERT = COMMON + /* glsl */`
attribute vec3 aRand3; attribute float aAlong;
uniform float uScale; uniform vec3 uColor, uThink;
varying vec3 vColor; varying float vAlpha;
void main() {
  vec3 p = position;
  p *= 1.0 + uBreath * 0.045 + uState.x * uMic * 0.10;
  float r = length(p);
  p += normalize(p + 0.0001) * (uLevel * 0.05 * uState.z);
  p.xz = rot(uTime * 0.11 + uState.y * uTime * 0.05) * p.xz;
  p = userSpin(p * (1.0 + uBeat * 0.06));
  float pulse = pow(max(0.0, 1.0 - abs(fract(uTime * (0.5 + aRand3.x) + aRand3.y) - aAlong) * 4.0), 2.0);
  float front = fract(uTime * 0.9) * 1.25;
  float wave = smoothstep(0.2, 0.0, abs(r - front)) * uLevel * uState.z;
  vAlpha = (0.10 + pulse * (0.25 + 0.9 * uState.y) + wave * 1.6 + uState.w * 0.2) * uMorph.x * uMorph.x * smoothstep(0.5, 1.0, uAssemble);
  vColor = mix(uColor, uThink, uState.y * 0.5);
  gl_Position = projectionMatrix * modelViewMatrix * vec4(p * uScale, 1.0);
}`;
export const LINES_FRAG = /* glsl */`
precision highp float; varying vec3 vColor; varying float vAlpha;
void main() { gl_FragColor = vec4(vColor * vAlpha, vAlpha); }`;

// FRIDAY field lines: living dipole loops that swell with her voice and twist while thinking
export const FIELD_VERT = COMMON + /* glsl */`
attribute vec3 aParam;   // L, phi, theta(0..1)
attribute float aBand;
uniform float uScale; uniform vec3 uColor, uColor2;
varying vec3 vColor; varying float vAlpha;
void main() {
  float band = mix(uBands.x, uBands.z, aBand);
  float L = aParam.x * (1.0 + band * 0.55 * uState.z + uBreath * 0.04);
  float phi = aParam.y + uState.y * sin(aParam.z * 6.283 + uTime * 1.6) * 0.9 + uTime * 0.05;
  float theta = aParam.z * PI;
  float rr = L * sin(theta) * sin(theta);
  vec3 p = vec3(rr * sin(theta) * cos(phi), rr * cos(theta), rr * sin(theta) * sin(phi));
  p.xz = rot(uTime * 0.07) * p.xz; p.xy = rot(0.32) * p.xy;
  p = userSpin(p * (1.0 + uBeat * 0.06));
  float run = pow(max(0.0, sin(aParam.z * 14.0 - uTime * 2.5 + aParam.y * 3.0)), 6.0);
  vAlpha = (0.10 + band * 0.9 * uState.z + run * 0.25 + uState.x * uMic * 0.5 + uState.y * 0.15) * uMorph.y * uMorph.y * smoothstep(0.5, 1.0, uAssemble);
  vColor = mix(uColor, uColor2, aBand);
  gl_Position = projectionMatrix * modelViewMatrix * vec4(p * uScale, 1.0);
}`;

// FRIDAY core: boiling plasma sphere
export const CORE_VERT = COMMON + /* glsl */`
uniform float uScale; varying vec3 vN; varying vec3 vP;
void main() {
  vec3 n = normalize(position);
  float boil = noise(n * 3.0 + uTime * 0.6) - 0.5;
  vec3 p = n * (0.33 + boil * 0.05 + uLevel * 0.10 * uState.z + uBreath * 0.02 + uState.x * uMic * 0.06) * (1.0 + uBeat * 0.06);
  vN = normalize(normalMatrix * n); vP = n;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(p * uScale, 1.0);
}`;
export const CORE_FRAG = COMMON + /* glsl */`
uniform vec3 uColor, uColor2; varying vec3 vN; varying vec3 vP;
void main() {
  float rim = pow(1.0 - abs(vN.z), 1.6);
  float cells = noise(vP * 5.0 + uTime * 0.8) * noise(vP * 11.0 - uTime * 0.5);
  vec3 col = mix(uColor2, uColor, cells * 2.2) * (0.35 + cells * 1.6 + rim * 0.9 + uLevel * uState.z * 0.8);
  float a = (0.55 + rim * 0.4) * uMorph.y * uMorph.y * smoothstep(0.6, 1.0, uAssemble);
  gl_FragColor = vec4(col * a, a);
}`;

// ROBIN crystal shells (wireframe polyhedra)
export const SHELL_VERT = COMMON + /* glsl */`
uniform float uScale, uDir, uShell; uniform vec3 uColor;
varying float vAlpha;
void main() {
  vec3 p = position;
  p.xz = rot(uTime * 0.16 * uDir + uState.y * uTime * 0.2 * uDir) * p.xz;
  p.xy = rot(uTime * 0.07 * uDir) * p.xy;
  p *= 1.0 + (uLevel * 0.22 + uOnset * 0.25) * uState.z * (0.5 + uShell) + uBreath * 0.03 + uState.x * uMic * 0.08;
  p = userSpin(p * (1.0 + uBeat * 0.06));
  vAlpha = (0.30 + uLevel * 0.9 * uState.z + uState.y * 0.25 + uState.w * 0.3) * uMorph.z * uMorph.z * smoothstep(0.5, 1.0, uAssemble);
  gl_Position = projectionMatrix * modelViewMatrix * vec4(p * uScale, 1.0);
}`;
export const SHELL_FRAG = /* glsl */`
precision highp float; uniform vec3 uColor; varying float vAlpha;
void main() { gl_FragColor = vec4(uColor * vAlpha, vAlpha); }`;
