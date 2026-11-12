// The hologram engine: WebGL (Three.js, bundled locally) with bloom, falling back to Canvas2D.
// Motion is driven by real audio features; quality scales itself to hold the frame rate.
import { features } from '../core/audio.js';
import { buildParticles, buildFilaments, buildFieldLines, shellSegments, SHELLS, cpuPosition } from './forms.js';
import * as S from './shaders.js';

const FORM_INDEX = { jarvis: 0, friday: 1, robin: 2 };
const COLOURS = {
  jarvis: ['#ffc24a', '#ff8a1f'], friday: ['#ff6a3d', '#ffd166'], robin: ['#c9a7ff', '#ff8fc2'],
};
const THINK = { jarvis: '#fff3c4', friday: '#ffe6c2', robin: '#ffd9ec' };
const MAX_PARTICLES = 16000;

function glyphAtlas() {   // 16 original rune-like glyphs drawn from random strokes on a 3x4 grid
  const c = document.createElement('canvas');
  c.width = c.height = 256;
  const g = c.getContext('2d');
  g.strokeStyle = '#fff'; g.lineWidth = 4; g.lineCap = 'round';
  let seed = 42;
  const r = () => { seed = (seed * 1664525 + 1013904223) >>> 0; return seed / 4294967296; };
  for (let i = 0; i < 16; i++) {
    const ox = (i % 4) * 64, oy = Math.floor(i / 4) * 64;
    const pts = [];
    for (let y = 0; y < 4; y++) for (let x = 0; x < 3; x++) pts.push([ox + 16 + x * 16, oy + 10 + y * 14.5]);
    g.beginPath();
    let p = pts[Math.floor(r() * pts.length)];
    g.moveTo(p[0], p[1]);
    for (let k = 0; k < 4 + Math.floor(r() * 3); k++) {
      const q = pts[Math.floor(r() * pts.length)];
      if (r() < 0.3) g.moveTo(q[0], q[1]); else g.lineTo(q[0], q[1]);
      p = q;
    }
    g.stroke();
  }
  return c;
}

export class Hologram {
  constructor(canvas) {
    this.canvas = canvas;
    this.form = 'jarvis'; this.prevForm = 'jarvis';
    this.morphT = 1; this.weights = [1, 0, 0];
    this.state = 'idle'; this.stateW = [0, 0, 0, 0];   // listen, think, speak, notice
    this.humor = 0.4; this.assemble = 0; this.assembleTarget = 0;
    this.spin = [0, 0]; this.spinVel = [0, 0]; this.zoom = 1; this.zoomTarget = 1;
    this.beatEnv = 0; this.thinkSince = 0; this.party = false; this.paused = false;
    this.fps = 60; this.frameMs = 16; this.quality = 1; this.mode = 'none';
    this.count = MAX_PARTICLES; this.breathPhase = 0; this.breathRate = 1; this.nextBreathShift = 0;
    this.t0 = performance.now(); this.last = this.t0; this.slowFrames = 0; this.fastFrames = 0;
    this.testFeatures = null;   // tests can inject audio features
    this._frame = this._frame.bind(this);
    document.addEventListener('visibilitychange', () => { this.paused = document.hidden; if (!this.paused) { this.last = performance.now(); requestAnimationFrame(this._frame); } });
  }

  async init() {
    try {
      const probe = document.createElement('canvas').getContext('webgl2') || document.createElement('canvas').getContext('webgl');
      if (!probe || new URLSearchParams(location.search).has('nogl')) throw new Error('no webgl');
      await this._initGL();
      this.mode = 'webgl';
    } catch (err) {
      console.warn('[holo] WebGL unavailable, using the Canvas2D fallback:', err.message);
      this._init2D();
      this.mode = '2d';
    }
    this.resize();
    new ResizeObserver(() => this.resize()).observe(this.canvas.parentElement);
    requestAnimationFrame(this._frame);
    return this.mode;
  }

  async _initGL() {
    const THREE = await import('three');
    const { EffectComposer } = await import('three/addons/postprocessing/EffectComposer.js');
    const { RenderPass } = await import('three/addons/postprocessing/RenderPass.js');
    const { UnrealBloomPass } = await import('three/addons/postprocessing/UnrealBloomPass.js');
    const { OutputPass } = await import('three/addons/postprocessing/OutputPass.js');
    this.THREE = THREE;
    this.renderer = new THREE.WebGLRenderer({ canvas: this.canvas, antialias: false, alpha: false, powerPreference: 'high-performance',
      preserveDrawingBuffer: true });   // lets the pop-out orb (and tests) copy the picture
    this.renderer.setClearColor(0x000000, 1);
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(42, 1, 0.1, 50);
    this.camera.position.set(0, 0, 4.2);

    const col = (hex) => new THREE.Color(hex);
    this.uniforms = {
      uTime: { value: 0 }, uLevel: { value: 0 }, uOnset: { value: 0 }, uMic: { value: 0 }, uBreath: { value: 0 },
      uAssemble: { value: 0 }, uHumor: { value: 0.4 }, uBeat: { value: 0 }, uMorphT: { value: 1 }, uThinkAge: { value: 0 },
      uBands: { value: new THREE.Vector4() }, uState: { value: new THREE.Vector4() }, uMorph: { value: new THREE.Vector3(1, 0, 0) },
      uSpin: { value: new THREE.Vector2() }, uPixel: { value: 8 }, uScale: { value: 1 },
      uColJ: { value: col(COLOURS.jarvis[0]) }, uColJ2: { value: col(COLOURS.jarvis[1]) },
      uColF: { value: col(COLOURS.friday[0]) }, uColF2: { value: col(COLOURS.friday[1]) },
      uColR: { value: col(COLOURS.robin[0]) }, uColR2: { value: col(COLOURS.robin[1]) },
      uThink: { value: col(THINK.jarvis) }, uGlyphs: { value: new THREE.CanvasTexture(glyphAtlas()) },
    };
    const U = (extra = {}) => ({ ...this.uniforms, ...extra });
    const additive = { transparent: true, depthWrite: false, depthTest: false, blending: THREE.AdditiveBlending };

    const P = this.particles = buildParticles(MAX_PARTICLES);
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(P.count * 3), 3));
    for (const [name, size] of [['aJ', 3], ['aF', 3], ['aR', 3], ['aRand', 4], ['aKind', 3]]) geo.setAttribute(name, new THREE.BufferAttribute(P[name], size));
    geo.boundingSphere = new THREE.Sphere(new THREE.Vector3(), 20);
    this.points = new THREE.Points(geo, new THREE.ShaderMaterial({ uniforms: U(), vertexShader: S.POINTS_VERT, fragmentShader: S.POINTS_FRAG, ...additive }));
    this.points.frustumCulled = false;

    const lineMesh = (attrs, vert, frag, uniforms) => {
      const g = new THREE.BufferGeometry();
      for (const [name, [arr, size]] of Object.entries(attrs)) g.setAttribute(name, new THREE.BufferAttribute(arr, size));
      if (!attrs.position) g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(Object.values(attrs)[0][0].length / Object.values(attrs)[0][1] * 3), 3));
      const m = new THREE.LineSegments(g, new THREE.ShaderMaterial({ uniforms, vertexShader: vert, fragmentShader: frag, ...additive }));
      m.frustumCulled = false;
      return m;
    };
    const fil = buildFilaments(P.neurons);
    this.filaments = lineMesh({ position: [fil.position, 3], aRand3: [fil.aRand3, 3], aAlong: [fil.aAlong, 1] }, S.LINES_VERT, S.LINES_FRAG,
      U({ uColor: { value: col(COLOURS.jarvis[0]) } }));
    const field = buildFieldLines();
    this.field = lineMesh({ aParam: [field.aParam, 3], aBand: [field.aBand, 1] }, S.FIELD_VERT, S.LINES_FRAG,
      U({ uColor: { value: col(COLOURS.friday[0]) }, uColor2: { value: col(COLOURS.friday[1]) } }));
    this.core = new THREE.Mesh(new THREE.IcosahedronGeometry(1, 5), new THREE.ShaderMaterial({
      uniforms: U({ uColor: { value: col('#ffd9a0') }, uColor2: { value: col('#ff4a1c') } }), vertexShader: S.CORE_VERT, fragmentShader: S.CORE_FRAG,
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending }));
    this.core.frustumCulled = false;
    this.shells = SHELLS.map((shell, i) => lineMesh({ position: [shellSegments(shell), 3] }, S.SHELL_VERT, S.SHELL_FRAG,
      U({ uColor: { value: col(i === 1 ? COLOURS.robin[1] : COLOURS.robin[0]) }, uDir: { value: [1, -1, 0.6][i] }, uShell: { value: shell.shell } })));
    this.scene.add(this.core, this.field, this.filaments, ...this.shells, this.points);

    this.composer = new EffectComposer(this.renderer);
    this.composer.addPass(new RenderPass(this.scene, this.camera));
    this.bloom = new UnrealBloomPass(new THREE.Vector2(256, 256), 0.5, 0.45, 0.22);
    this.composer.addPass(this.bloom);
    this.composer.addPass(new OutputPass());
    this.canvas.addEventListener('webglcontextlost', (e) => { e.preventDefault(); this.paused = true; });
    this.canvas.addEventListener('webglcontextrestored', () => { this.paused = false; requestAnimationFrame(this._frame); });
  }

  _init2D() {
    this.ctx2d = this.canvas.getContext('2d');
    this.particles = buildParticles(1400);
    this.count = 1400;
  }

  resize() {
    const box = this.canvas.parentElement.getBoundingClientRect();
    const w = Math.max(2, Math.floor(box.width)), h = Math.max(2, Math.floor(box.height));
    this.w = w; this.h = h;
    const dpr = Math.min(window.devicePixelRatio || 1, this.quality > 0.7 ? 2 : 1.25);
    if (this.mode === '2d' || this.ctx2d) {
      this.canvas.width = w * dpr; this.canvas.height = h * dpr; this.dpr = dpr;
      return;
    }
    if (!this.renderer) return;
    this.renderer.setPixelRatio(dpr);
    this.renderer.setSize(w, h, false);
    this.composer.setPixelRatio(dpr);
    this.composer.setSize(w, h);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.uniforms.uPixel.value = Math.min(w, h) * dpr / 95;
    this.uniforms.uScale.value = w / h < 0.9 ? 0.72 : 1;
  }

  // ---- public controls ------------------------------------------------------------------
  setPersona(id, instant = false) {
    if (!(id in FORM_INDEX) || id === this.form) return;
    this.prevForm = this.form; this.form = id;
    this.morphT = instant ? 1 : 0;
    if (this.uniforms) this.uniforms.uThink.value.set(THINK[id]);
  }
  setState(state) { if (state === 'think' && this.state !== 'think') this.thinkSince = performance.now(); this.state = state; }
  setMood(humor) { this.humor = Math.max(0, Math.min(1, humor / 100)); }
  assembleIn() { this.assembleTarget = 1; }
  collapse() { this.assembleTarget = 0; }
  rotate(dx, dy) { this.spinVel[0] += dx; this.spinVel[1] += dy; }
  setZoom(z) { this.zoomTarget = Math.max(0.55, Math.min(1.9, z)); }
  beat(strength = 1) { this.beatEnv = strength; }
  setParty(on) { this.party = on; }
  stats() { return { mode: this.mode, fps: Math.round(this.fps), particles: this.count, quality: +this.quality.toFixed(2), state: this.state, form: this.form, morph: +this.morphT.toFixed(2) }; }

  // ---- frame ----------------------------------------------------------------------------
  _frame(now) {
    if (this.paused) return;
    requestAnimationFrame(this._frame);
    const dt = Math.min(0.1, (now - this.last) / 1000);
    this.last = now;
    const t = (now - this.t0) / 1000;
    this.frameMs += (dt * 1000 - this.frameMs) * 0.05;
    this.fps = 1000 / Math.max(1, this.frameMs);
    this._autoQuality(dt);

    const f = this.testFeatures || features();
    const target = { listen: [1, 0, 0, 0], think: [0, 1, 0, 0], speak: [0, 0, 1, 0], notice: [0, 0, 0, 1] }[this.state] || [0, 0, 0, 0];
    for (let i = 0; i < 4; i++) this.stateW[i] += (target[i] - this.stateW[i]) * Math.min(1, dt * (i === 3 ? 9 : 4.5));

    // breathing: a slow cycle whose rate drifts, so it never looks looped
    if (t > this.nextBreathShift) { this.breathRate = 0.85 + Math.random() * 0.4; this.nextBreathShift = t + 4 + Math.random() * 5; }
    this.breathPhase += dt * (Math.PI * 2 / 5) * this.breathRate;
    const breath = Math.sin(this.breathPhase) * 0.7 + Math.sin(this.breathPhase * 0.37 + 1.3) * 0.3;

    if (this.morphT < 1) this.morphT = Math.min(1, this.morphT + dt / 1.05);
    const e = this.morphT * this.morphT * (3 - 2 * this.morphT);
    const w = [0, 0, 0];
    w[FORM_INDEX[this.prevForm]] += 1 - e; w[FORM_INDEX[this.form]] += e;
    this.weights = w;
    this.assemble += (this.assembleTarget - this.assemble) * Math.min(1, dt * 1.6);
    this.beatEnv *= Math.pow(0.02, dt);
    this.zoom += (this.zoomTarget - this.zoom) * Math.min(1, dt * 6);
    this.spin[0] += this.spinVel[0]; this.spin[1] = Math.max(-1.2, Math.min(1.2, this.spin[1] + this.spinVel[1]));
    this.spinVel[0] *= 0.9; this.spinVel[1] *= 0.9;
    if (Math.abs(this.spinVel[0]) < 1e-4) this.spin[1] *= 0.985;   // drift back upright when released
    const partyBeat = this.party ? f.mic.level * 1.4 : 0;
    const thinkAge = this.state === 'think' ? Math.min(1, (now - this.thinkSince) / 6000) : 0;

    if (this.mode === 'webgl') {
      const u = this.uniforms;
      u.uTime.value = t; u.uLevel.value = Math.min(1, f.out.level * 1.25 + partyBeat); u.uOnset.value = f.out.onset; u.uMic.value = f.mic.level;
      u.uBreath.value = breath; u.uAssemble.value = this.assemble; u.uHumor.value = this.humor + (this.party ? 0.8 : 0);
      u.uBeat.value = this.beatEnv + this.stateW[3] * 0.5; u.uMorphT.value = this.morphT; u.uThinkAge.value = thinkAge;
      u.uBands.value.set(...f.out.bands.map((b, i) => Math.min(1, b * 1.6 + (this.party ? f.mic.bands[i] : 0))));
      u.uState.value.set(Math.max(this.stateW[0], this.party ? 0.6 : 0), this.stateW[1], Math.max(this.stateW[2], this.party ? 0.7 : 0), this.stateW[3]);
      u.uMorph.value.set(w[0], w[1], w[2]);
      u.uSpin.value.set(this.spin[0], this.spin[1]);
      this.camera.position.z = 4.2 / this.zoom;
      this.bloom.strength = 0.5 + this.stateW[2] * f.out.level * 0.22 + this.stateW[1] * 0.12 + this.stateW[3] * 0.3;
      this.core.visible = w[1] > 0.02; this.field.visible = w[1] > 0.02; this.filaments.visible = w[0] > 0.02;
      this.shells.forEach((s) => { s.visible = w[2] > 0.02; });
      this.composer.render();
    } else {
      this._draw2D(t, f, w);
    }
    this.frames = (this.frames || 0) + 1;
  }

  _autoQuality(dt) {
    if (this.mode !== 'webgl' || this.frames < 12) return;
    if (this.frameMs > 21) { this.slowFrames += dt; this.fastFrames = 0; } else if (this.frameMs < 15) { this.fastFrames += dt; this.slowFrames = 0; }
    if (this.slowFrames > 1.5 && this.quality > 0.2) { this.quality = Math.max(0.2, this.quality * 0.75); this._applyQuality(); }
    else if (this.fastFrames > 12 && this.quality < 1) { this.quality = Math.min(1, this.quality * 1.15); this._applyQuality(); }
  }
  _applyQuality() {
    this.slowFrames = this.fastFrames = 0;
    this.count = Math.max(3000, Math.floor(MAX_PARTICLES * this.quality));
    this.points.geometry.setDrawRange(0, this.count);
    this.bloom.enabled = this.quality > 0.3;
    this.resize();
  }

  _draw2D(t, f, w) {
    const g = this.ctx2d, P = this.particles;
    const W = this.canvas.width, H = this.canvas.height;
    g.globalCompositeOperation = 'source-over';
    g.fillStyle = 'rgba(0,0,0,0.3)';
    g.fillRect(0, 0, W, H);
    g.globalCompositeOperation = 'lighter';
    const scale = Math.min(W, H) * 0.3 * this.zoom * (0.4 + 0.6 * this.assemble);
    const lvl = { level: f.out.level * this.stateW[2] + f.mic.level * this.stateW[0] };
    const colour = COLOURS[this.form][0], colour2 = COLOURS[this.form][1];
    for (let i = 0; i < P.count; i++) {
      let x = 0, y = 0, z = 0;
      for (let k = 0; k < 3; k++) {
        if (w[k] < 0.01) continue;
        const p = cpuPosition(k, P, i, t, lvl);
        x += p[0] * w[k]; y += p[1] * w[k]; z += p[2] * w[k];
      }
      const cs = Math.cos(this.spin[0]), sn = Math.sin(this.spin[0]);
      const rx = x * cs - z * sn, rz = x * sn + z * cs;
      const persp = 3.4 / (3.4 - rz);
      const size = (1.1 + P.aKind[i * 3] * 1.4) * persp * (this.dpr || 1) * (1 + lvl.level);
      g.globalAlpha = Math.min(1, 0.35 + lvl.level * 0.6 + this.stateW[1] * 0.25 * Math.sin(t * 6 + i));
      g.fillStyle = P.aRand[i * 4 + 1] > 0.6 ? colour2 : colour;
      g.fillRect(W / 2 + rx * scale * persp - size / 2, H / 2 - y * scale * persp - size / 2, size, size);
    }
    g.globalAlpha = 1;
  }
}
