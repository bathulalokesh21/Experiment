// Geometry for the three creatures. Pure maths (no three.js) so it can be tested and
// reused by the Canvas2D fallback.

export function rng(seed = 1) {   // deterministic so the creatures look the same every launch
  let s = seed >>> 0;
  return () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; };
}
const onSphere = (r) => {
  const u = r() * 2 - 1, a = r() * Math.PI * 2, q = Math.sqrt(1 - u * u);
  return [q * Math.cos(a), u, q * Math.sin(a)];
};

/** JARVIS: an irregular, lobed volume (not a ball): several overlapping lobes of neurons. */
export function mindPoint(r, lobes) {
  const lobe = lobes[Math.floor(r() * lobes.length)];
  const d = onSphere(r);
  const rad = lobe.r * Math.pow(r(), 0.42);           // denser toward the surface: a cortex
  const wrinkle = 1 + 0.16 * Math.sin(d[0] * 9 + lobe.c[0] * 7) * Math.sin(d[1] * 7 + d[2] * 5);
  return [lobe.c[0] + d[0] * rad * wrinkle * lobe.s[0], lobe.c[1] + d[1] * rad * wrinkle * lobe.s[1], lobe.c[2] + d[2] * rad * wrinkle * lobe.s[2]];
}
export function mindLobes(r) {
  const lobes = [{ c: [0, 0.02, 0], r: 0.62, s: [1.15, 0.85, 0.95] }];
  for (let i = 0; i < 6; i++) {
    const d = onSphere(r);
    lobes.push({ c: [d[0] * 0.48, d[1] * 0.3 + 0.05, d[2] * 0.4], r: 0.3 + r() * 0.2, s: [1 + r() * 0.3, 0.8 + r() * 0.3, 0.9 + r() * 0.3] });
  }
  return lobes;
}

/** ROBIN: points along the edges of nested polyhedra. */
const PHI = (1 + Math.sqrt(5)) / 2;
export const ICOSA = [[-1, PHI, 0], [1, PHI, 0], [-1, -PHI, 0], [1, -PHI, 0], [0, -1, PHI], [0, 1, PHI], [0, -1, -PHI], [0, 1, -PHI],
  [PHI, 0, -1], [PHI, 0, 1], [-PHI, 0, -1], [-PHI, 0, 1]].map((v) => { const l = Math.hypot(...v); return v.map((x) => x / l); });
export const OCTA = [[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]];
export function edgesOf(verts, edgeLen) {
  const out = [];
  for (let i = 0; i < verts.length; i++) for (let j = i + 1; j < verts.length; j++) {
    const d = Math.hypot(verts[i][0] - verts[j][0], verts[i][1] - verts[j][1], verts[i][2] - verts[j][2]);
    if (Math.abs(d - edgeLen) < 0.02) out.push([verts[i], verts[j]]);
  }
  return out;
}
export const ICOSA_EDGES = edgesOf(ICOSA, 2 / Math.hypot(1, PHI));
export const OCTA_EDGES = edgesOf(OCTA, Math.SQRT2);
export const SHELLS = [{ edges: ICOSA_EDGES, scale: 0.62, shell: 0 }, { edges: OCTA_EDGES, scale: 0.4, shell: 0.5 }, { edges: ICOSA_EDGES, scale: 0.22, shell: 1 }];

/** Build every attribute for N particles. */
export function buildParticles(count, seed = 7) {
  const r = rng(seed);
  const aJ = new Float32Array(count * 3), aF = new Float32Array(count * 3), aR = new Float32Array(count * 3);
  const aRand = new Float32Array(count * 4), aKind = new Float32Array(count * 3);
  const lobes = mindLobes(rng(seed + 1));
  const neurons = [];
  for (let i = 0; i < count; i++) {
    const rand = [r(), r(), r(), r()];
    // --- JARVIS
    const big = r() < 0.07 ? 1 : 0;                   // bright neuron vs fine dust
    const pj = mindPoint(r, lobes);
    if (big && neurons.length < 420) neurons.push(pj);
    // --- FRIDAY
    let kf, pf;
    const pick = r();
    if (pick < 0.22) { kf = 0; pf = onSphere(r); }
    else if (pick < 0.86) { kf = 1; pf = [0.55 + Math.floor(r() * 5) * 0.2 + r() * 0.03, Math.floor(r() * 14) / 14 * Math.PI * 2 + (r() - 0.5) * 0.05, r()]; }
    else { kf = 2; pf = onSphere(r); }
    // --- ROBIN
    let kr, pr;
    const pick2 = r();
    if (pick2 < 0.68) {
      kr = 0;
      const shell = SHELLS[Math.floor(r() * SHELLS.length)];
      const [a, b] = shell.edges[Math.floor(r() * shell.edges.length)];
      const t = r() < 0.25 ? Math.round(r()) : r();   // extra light at the vertices
      pr = [0, 1, 2].map((k) => (a[k] + (b[k] - a[k]) * t) * shell.scale + (r() - 0.5) * 0.006);
      rand[3] = shell.shell;
    } else if (pick2 < 0.86) { kr = 1; pr = [Math.floor(r() * 3) / 3 * Math.PI * 2, r(), 0.86 + Math.floor(r() * 2) * 0.12]; }
    else { kr = 2; pr = [r() * Math.PI * 2, r(), 0.5 + r() * 0.75]; }
    aJ.set(pj, i * 3); aF.set(pf, i * 3); aR.set(pr, i * 3);
    aRand.set(rand, i * 4); aKind.set([big, kf, kr], i * 3);
  }
  return { count, aJ, aF, aR, aRand, aKind, neurons };
}

/** JARVIS filaments: connect each bright neuron to a couple of near neighbours, with a kink (circuit feel). */
export function buildFilaments(neurons, seed = 11) {
  const r = rng(seed);
  const pos = [], rand = [], along = [];
  for (let i = 0; i < neurons.length; i++) {
    const a = neurons[i];
    const near = neurons.map((b, j) => [j, Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2])])
      .filter(([j, d]) => j > i && d < 0.3).sort((x, y) => x[1] - y[1]).slice(0, 2);
    for (const [j] of near) {
      const b = neurons[j];
      const mid = [b[0], a[1], (a[2] + b[2]) / 2];    // right-angled kink
      const seedv = [r(), r(), r()];
      for (const [p, q, t0, t1] of [[a, mid, 0, 0.5], [mid, b, 0.5, 1]]) {
        pos.push(...p, ...q); rand.push(...seedv, ...seedv); along.push(t0, t1);
      }
    }
  }
  return { position: new Float32Array(pos), aRand3: new Float32Array(rand), aAlong: new Float32Array(along) };
}

/** FRIDAY field lines as line segments in dipole parameters (L, phi, theta). */
export function buildFieldLines(seed = 13) {
  const r = rng(seed);
  const param = [], band = [];
  const SEG = 40;
  for (let shell = 0; shell < 5; shell++) {
    const L = 0.55 + shell * 0.2;
    const lines = 7 + shell;
    for (let k = 0; k < lines; k++) {
      const phi = (k / lines) * Math.PI * 2 + shell * 0.4 + (r() - 0.5) * 0.1;
      const b = shell / 4;
      for (let s = 0; s < SEG; s++) {
        const t0 = 0.06 + (s / SEG) * 0.88, t1 = 0.06 + ((s + 1) / SEG) * 0.88;
        param.push(L, phi, t0, L, phi, t1); band.push(b, b);
      }
    }
  }
  return { aParam: new Float32Array(param), aBand: new Float32Array(band) };
}

export function shellSegments(shell) {
  const out = [];
  for (const [a, b] of shell.edges) out.push(...a.map((x) => x * shell.scale), ...b.map((x) => x * shell.scale));
  return new Float32Array(out);
}

/** CPU version of the particle positions, used by the Canvas2D fallback. */
export function cpuPosition(form, P, i, t, f) {
  const j3 = i * 3;
  if (form === 0) {
    const s = 1 + Math.sin(t * 1.2) * 0.03 + f.level * 0.08;
    const a = t * 0.11, x = P.aJ[j3] * s, z = P.aJ[j3 + 2] * s;
    return [x * Math.cos(a) - z * Math.sin(a), P.aJ[j3 + 1] * s, x * Math.sin(a) + z * Math.cos(a)];
  }
  if (form === 1) {
    const kind = P.aKind[j3 + 1];
    if (kind !== 1) { const s = (kind === 0 ? 0.36 : 0.4 + ((P.aRand[i * 4] + t * 0.3) % 1) * (0.4 + f.level)); return [P.aF[j3] * s, P.aF[j3 + 1] * s, P.aF[j3 + 2] * s]; }
    const L = P.aF[j3] * (1 + f.level * 0.4), phi = P.aF[j3 + 1] + t * 0.05, th = ((P.aF[j3 + 2] + t * 0.06) % 1) * Math.PI;
    const rr = L * Math.sin(th) ** 2;
    return [rr * Math.sin(th) * Math.cos(phi), rr * Math.cos(th), rr * Math.sin(th) * Math.sin(phi)];
  }
  const kind = P.aKind[j3 + 2];
  if (kind === 0) {
    const a = t * 0.16 * (P.aRand[i * 4 + 3] < 0.25 ? 1 : -1), s = 1 + f.level * 0.25;
    const x = P.aR[j3] * s, z = P.aR[j3 + 2] * s;
    return [x * Math.cos(a) - z * Math.sin(a), P.aR[j3 + 1] * s, x * Math.sin(a) + z * Math.cos(a)];
  }
  const h = (((P.aR[j3 + 1] + t * (kind === 1 ? 0.05 : -0.04)) % 1) + 1) % 1 * 2.3 - 1.15;
  const ang = P.aR[j3] + h * (kind === 1 ? 2.6 : 1.2) + t * 0.25;
  const rad = P.aR[j3 + 2] * (kind === 2 ? 0.75 + f.level * 0.3 : 1);
  return [Math.cos(ang) * rad, h, Math.sin(ang) * rad];
}
