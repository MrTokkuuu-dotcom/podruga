// 3D-героиня из VRM (VRoid). Собирается esbuild в avatar/vrm3d.js (один файл, без интернета).
// Позы задаются поворотами костей поверх «T-позы» VRM (лицом к камере, +Z).
//  левая рука (+X):  z<0 — вниз,  y<0 — вперёд;   правая (-X): z>0 — вниз, y>0 — вперёд
//  предплечье: y — сгиб в локте вперёд (левое <0, правое >0)
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { VRMLoaderPlugin, VRMUtils } from '@pixiv/three-vrm';

const S = {
  face: 'sleep', emo: 'calm', act: '', actStart: 0, mouth: 0, lipT: 0,
  lookX: 0, lookY: 0, lookT: 0,
  idle: 'rest', idleUntil: 0,
  touch: '', touchStart: 0, touchUntil: 0, dragging: false,
};
let vrm = null, renderer, scene, camera, clock, lookTarget, host, canvas;
const sm = {};
const lerp = (a, b, k) => a + (b - a) * k;
let FRAME_DT = 1 / 30;
// k — доля пути за 1/30 с; пересчитываем под реальную длину кадра, чтобы плавность не зависела от FPS
function ease(key, target, k) {
  const kk = k >= 1 ? 1 : 1 - Math.pow(1 - k, FRAME_DT * 30);
  sm[key] = lerp(sm[key] ?? target, target, kk); return sm[key];
}
const clamp01 = (x) => Math.max(0, Math.min(1, x));
const bell = (t, len) => Math.sin(clamp01(t / len) * Math.PI);      // 0 → 1 → 0 за len секунд
let INSTANT = false;                                                // для проверки поз

const EMO = {
  calm:     {},
  joy:      { happy: 0.75 },
  tender:   { relaxed: 0.55, happy: 0.15 },
  shy:      { happy: 0.35, relaxed: 0.3 },
  surprise: { surprised: 0.85 },
  sad:      { sad: 0.7 },
  think:    { relaxed: 0.15 },
};

// ---------- позы ----------
// Поза = набор поворотов. Всё, чего нет в позе, берётся из REST.
const REST = {
  lUpZ: -1.22, rUpZ: 1.22, lUpY: -0.08, rUpY: 0.08, lUpX: 0, rUpX: 0,
  lLoY: -0.3, rLoY: 0.3, lLoZ: 0, rLoZ: 0, lHandZ: -0.1, rHandZ: 0.1, lHandX: 0, rHandX: 0,
  spineX: 0, spineZ: 0, chestX: 0, headX: 0, headY: 0, headZ: 0, hipsZ: 0, hipsY: 0, lift: 0,
};
const POSES = {
  // руки сцеплены спереди — скромно, мило
  clasp:   { lUpZ: -1.3, rUpZ: 1.3, lUpY: -0.42, rUpY: 0.42, lLoY: -1.15, rLoY: 1.15, lLoZ: -0.35, rLoZ: 0.35,
             lHandZ: 0.2, rHandZ: -0.2, headZ: 0.05 },
  // руки за спиной, чуть покачивается
  behind:  { lUpZ: -1.28, rUpZ: 1.28, lUpY: 0.35, rUpY: -0.35, lLoY: 0.5, rLoY: -0.5, chestX: -0.04 },
  // рука на поясе
  hip:     { rUpZ: 0.75, rUpY: -0.1, rLoY: 0.35, rLoZ: 1.5, rHandZ: 0.5, hipsZ: 0.04, headZ: -0.06 },
  // задумалась: рука у подбородка
  think:   { rUpZ: 1.0, rUpY: 0.45, rLoY: 2.5, rLoZ: 0.2, rHandX: 0.2,
             lUpZ: -1.25, lUpY: -0.45, lLoY: -1.2, lLoZ: -0.3, headZ: -0.12, headX: -0.06 },
  // поправляет волосы
  hair:    { rUpZ: -0.15, rUpY: 0.35, rLoY: 2.4, rLoZ: 0.4, headZ: -0.1 },
  // смущение: руки к груди, голова вниз и вбок
  shy:     { lUpZ: -1.2, rUpZ: 1.2, lUpY: -0.55, rUpY: 0.55, lLoY: -1.9, rLoY: 1.9, lLoZ: -0.3, rLoZ: 0.3,
             headX: 0.18, headZ: 0.1, headY: 0.15 },
  // радость: кулачки у груди
  happy:   { lUpZ: -1.1, rUpZ: 1.1, lUpY: -0.35, rUpY: 0.35, lLoY: -2.1, rLoY: 2.1, lLoZ: -0.2, rLoZ: 0.2 },
  // грусть: опущенные плечи и голова
  sad:     { lUpZ: -1.32, rUpZ: 1.32, lUpY: -0.2, rUpY: 0.2, lLoY: -0.5, rLoY: 0.5, headX: 0.22, spineX: 0.08 },
  // удивление: руки чуть вверх-вперёд
  surprise:{ lUpZ: -1.05, rUpZ: 1.05, lUpY: -0.2, rUpY: 0.2, lLoY: -0.5, rLoY: 0.5, lLoZ: 0.6, rLoZ: -0.6, headX: -0.08, spineX: -0.05 },
  // её гладят: голова в ладонь, руки сцеплены
  pat:     { lUpZ: -1.3, rUpZ: 1.3, lUpY: -0.42, rUpY: 0.42, lLoY: -1.15, rLoY: 1.15, lLoZ: -0.35, rLoZ: 0.35,
             headX: 0.12, headZ: 0.14 },
  // ткнули в щёку: отпрянула, дуется
  poke:    { lUpZ: -1.0, rUpZ: 1.15, lUpY: -0.5, lLoY: -2.0, headY: -0.25, headZ: -0.12, spineZ: -0.05 },
  // тащат окно: руки в стороны, «ой-ой»
  drag:    { lUpZ: -0.45, rUpZ: 0.45, lUpY: -0.2, rUpY: 0.2, lLoY: -0.6, rLoY: 0.6, headX: -0.05 },
  // спит стоя
  sleep:   { lUpZ: -1.3, rUpZ: 1.3, lUpY: -0.35, rUpY: 0.35, lLoY: -1.0, rLoY: 1.0, lLoZ: -0.3, rLoZ: 0.3,
             headX: 0.38, headZ: 0.15, spineX: 0.06 },
};
const IDLE = ['rest', 'rest', 'clasp', 'behind', 'hip', 'hair', 'look', 'sway', 'think'];

function bone(name) { return vrm.humanoid.getNormalizedBoneNode(name); }

let fitCamera = function (w, h) {
  camera.aspect = w / h;
  const top = (sm.headY || 1.6) + 0.16;
  const span = w / h > 1.3 ? 0.85 : 1.05;
  const fov = 22;
  camera.fov = fov;
  const dist = (span / 2) / Math.tan(THREE.MathUtils.degToRad(fov / 2));
  const cy = top - span / 2;
  camera.position.set(0, cy + 0.05, dist);
  camera.lookAt(0, cy, 0);
  camera.updateProjectionMatrix();
};

function resize() {
  const w = host.clientWidth || 200, h = host.clientHeight || 260;
  renderer.setSize(w, h, false);
  fitCamera(w, h);
}

// смешать позы: base + overlay с весом w
function mix(base, over, w) {
  if (!over || w <= 0) return base;
  const out = { ...base };
  for (const k in over) out[k] = lerp(base[k] ?? REST[k] ?? 0, over[k], w);
  return out;
}

function chooseIdle(t) {
  if (t < S.idleUntil) return;
  const prev = S.idle;
  let next = IDLE[Math.floor(Math.random() * IDLE.length)];
  if (next === prev) next = 'rest';
  S.idle = next;
  S.idleUntil = t + (next === 'rest' ? 6 + Math.random() * 8 : next === 'hair' ? 3 : 5 + Math.random() * 6);
}

function pose(t) {
  const asleep = S.face === 'sleep';
  const talking = Date.now() - S.lipT < 350;
  const now = performance.now();
  let P = { ...REST };

  // 1) простой: сама меняет позы, пока ничего не происходит
  if (!asleep && S.face !== 'think' && !talking) chooseIdle(t);
  if (asleep) P = mix(P, POSES.sleep, 1);
  else if (POSES[S.idle]) P = mix(P, POSES[S.idle], 1);
  if (!asleep && S.idle === 'look') { P.headY += Math.sin(t * 0.7) * 0.35; P.headX -= 0.05; }
  if (!asleep && S.idle === 'sway') { P.hipsZ += Math.sin(t * 2.2) * 0.05; P.headZ += Math.sin(t * 2.2 + 1) * 0.08; }
  if (!asleep && S.idle === 'hair') { const k = bell(t - (S.idleUntil - 3), 3); P = mix(mix({ ...REST }, POSES.clasp, 0), POSES.hair, k); }

  // 2) эмоция в теле (пока говорит и пару секунд после)
  const emoPose = { joy: 'happy', shy: 'shy', sad: 'sad', surprise: 'surprise', think: 'think', tender: 'clasp' }[S.emo];
  if (!asleep && emoPose) P = mix(P, POSES[emoPose], 0.85);
  if (S.face === 'think') P = mix(P, POSES.think, 1);
  if (!asleep && S.emo === 'joy') P.lift = Math.max(0, Math.sin(t * 6)) * 0.012;   // подпрыгивает
  if (!asleep && S.emo === 'joy') P.hipsZ += Math.sin(t * 3) * 0.03;

  // 3) касания и перетаскивание
  if (S.dragging) P = mix(P, POSES.drag, 1);
  else if (S.touch && now < S.touchUntil) {
    const tt = (now - S.touchStart) / 1000;
    const w = Math.min(1, tt * 4) * Math.min(1, (S.touchUntil - now) / 400);
    if (S.touch === 'head') { P = mix(P, POSES.pat, w); P.headZ += Math.sin(tt * 5) * 0.06 * w; }
    if (S.touch === 'face') P = mix(P, POSES.poke, w);
    if (S.touch === 'body') P = mix(P, POSES.shy, w);
  }

  // 4) разовые движения из программы
  const a = S.act, at = (now - S.actStart) / 1000;
  if (a === 'act-wave') {
    P.rUpZ = 1.25; P.rUpY = 0; P.rLoY = 0; P.rLoZ = -2.65 + Math.sin(at * 9) * 0.25; P.headZ -= 0.08;
  } else if (a === 'act-nod') {
    P.headX += Math.max(0, Math.sin(at * 8)) * 0.18 * Math.max(0, 1 - at / 1.4);
  } else if (a === 'act-stretch') {
    const k = bell(at, 2.4);
    P.lUpZ = lerp(P.lUpZ, 1.25, k); P.rUpZ = lerp(P.rUpZ, -1.25, k); P.lLoY = lerp(P.lLoY, 0, k); P.rLoY = lerp(P.rLoY, 0, k);
    P.headX -= 0.2 * k; P.spineX -= 0.1 * k; P.lift += 0.01 * k;
  } else if (a === 'act-yawn') {
    const k = bell(at, 2.5);
    P.headX -= 0.25 * k; P.rUpZ = lerp(P.rUpZ, 1.25, k); P.rUpY = lerp(P.rUpY, 0.6, k); P.rLoY = lerp(P.rLoY, 2.5, k);
  }

  // дыхание, покачивание, «говорящая» голова
  const breath = Math.sin(t * 1.6) * 0.5 + 0.5;
  P.spineX += (asleep ? 0.05 : 0.015) * breath;
  P.headZ += Math.sin(t * 0.5) * 0.02;
  P.hipsZ += Math.sin(t * 0.4) * 0.015;
  if (talking) P.headX += Math.sin(t * 7) * 0.015;

  // взгляд за курсором
  const looking = Date.now() - S.lookT < 4000 && !asleep && !S.touch;
  const lx = ease('lx', looking ? S.lookX : 0, INSTANT ? 1 : 0.08), ly = ease('ly', looking ? S.lookY : 0, INSTANT ? 1 : 0.08);
  P.headY += lx * 0.35; P.headX += ly * 0.18;

  // применить с плавностью
  const k = INSTANT ? 1 : 0.12, kh = INSTANT ? 1 : 0.1;
  const set = (name, axis, v, kk = k) => { const b = bone(name); if (b) b.rotation[axis] = ease(name + axis, v, kk); };
  set('leftUpperArm', 'z', P.lUpZ); set('rightUpperArm', 'z', P.rUpZ);
  set('leftUpperArm', 'y', P.lUpY); set('rightUpperArm', 'y', P.rUpY);
  set('leftUpperArm', 'x', P.lUpX); set('rightUpperArm', 'x', P.rUpX);
  set('leftLowerArm', 'y', P.lLoY); set('rightLowerArm', 'y', P.rLoY);
  set('leftLowerArm', 'z', P.lLoZ); set('rightLowerArm', 'z', P.rLoZ);
  set('leftHand', 'z', P.lHandZ); set('rightHand', 'z', P.rHandZ);
  set('leftHand', 'x', P.lHandX); set('rightHand', 'x', P.rHandX);
  set('spine', 'x', P.spineX, kh); set('chest', 'x', P.chestX + P.spineX * 0.6, kh);
  set('spine', 'z', P.spineZ, kh);
  set('neck', 'x', P.headX * 0.4, kh); set('head', 'x', P.headX * 0.6, kh);
  set('neck', 'y', P.headY * 0.4, kh); set('head', 'y', P.headY * 0.6, kh);
  set('head', 'z', P.headZ, kh);
  set('hips', 'z', P.hipsZ, 0.05); set('hips', 'y', P.hipsY, 0.05);
  avoidBody();
  const hips = bone('hips');
  if (hips) { sm.hipsBase ??= hips.position.y; hips.position.y = sm.hipsBase + ease('lift', P.lift, 0.3); }

  if (vrm.lookAt) {
    lookTarget.position.set(lx * 1.2, camera.position.y + ly * 0.6, camera.position.z);
    vrm.lookAt.target = asleep ? null : lookTarget;
  }
}

// ---------- руки не проходят сквозь тело ----------
// При загрузке «ощупываем» модель лучами: где перед и бока туловища на разной высоте.
let BODY = null;
function measureBody() {
  // Только туловище (от таза до плеч): ширина — по костям, глубина груди/живота — лучами по центру.
  vrm.scene.updateMatrixWorld(true);
  const meshes = []; vrm.scene.traverse((o) => { if (o.isMesh) meshes.push(o); });
  const rc = new THREE.Raycaster();
  const P = (n) => bone(n).getWorldPosition(new THREE.Vector3());
  const hipsY = P('hips').y, shY = P('leftUpperArm').y;
  const hipHalf = Math.abs(P('leftUpperLeg').x) + 0.06, chestHalf = Math.abs(P('leftUpperArm').x) - 0.03;
  const ys = [], front = [], back = [], half = [];
  const hit = (o, d) => { rc.set(o, d); rc.far = 4; const h = rc.intersectObjects(meshes, false); return h.length ? h[0].point : null; };
  for (let y = hipsY; y <= shY - 0.04; y += 0.035) {
    let f = -1, b = 1;
    for (const x of [-0.08, 0, 0.08]) {
      const pf = hit(new THREE.Vector3(x, y, 2), new THREE.Vector3(0, 0, -1)); if (pf) f = Math.max(f, pf.z);
      const pb = hit(new THREE.Vector3(x, y, -2), new THREE.Vector3(0, 0, 1)); if (pb) b = Math.min(b, pb.z);
    }
    if (f < -0.9) continue;
    const u = (y - hipsY) / (shY - hipsY);
    ys.push(y); front.push(Math.min(f, 0.25)); back.push(Math.max(b, -0.25)); half.push(lerp(hipHalf, chestHalf, u));
  }
  BODY = ys.length > 1 ? { ys, front, back, half } : null;
}
function bodyAt(y) {
  const B = BODY; if (!B || y < B.ys[0] || y > B.ys[B.ys.length - 1]) return null;
  let i = 0; while (i < B.ys.length - 2 && B.ys[i + 1] < y) i++;
  const u = (y - B.ys[i]) / (B.ys[i + 1] - B.ys[i] || 1);
  return { f: lerp(B.front[i], B.front[i + 1], u), b: lerp(B.back[i], B.back[i + 1], u), h: lerp(B.half[i], B.half[i + 1], u) };
}
function inBody(p, margin) {
  const b = bodyAt(p.y); if (!b) return false;
  return Math.abs(p.x) < b.h + margin && p.z < b.f + margin && p.z > b.b - margin;
}
const _v = new THREE.Vector3(), _w = new THREE.Vector3();
function avoidBody() {
  if (!BODY) return;
  for (const side of ['left', 'right']) {
    const up = bone(side + 'UpperArm'), lo = bone(side + 'LowerArm'), hand = bone(side + 'Hand');
    if (!up || !lo || !hand) continue;
    const key = 'push_' + side;
    // вывести руку вперёд = поворот плеча вокруг X (он применяется последним, поэтому работает при любой позе)
    up.rotation.x -= (sm[key] || 0);
    hand.updateWorldMatrix(true, false);
    const pts = [hand.getWorldPosition(_v).clone(), lo.getWorldPosition(_w).clone()];
    pts.push(pts[0].clone().add(pts[1]).multiplyScalar(0.5));
    const inside = pts.some((p) => inBody(p, 0.015)), near = pts.some((p) => inBody(p, 0.045));
    let push = sm[key] || 0;
    if (inside) push = Math.min(0.7, push + 2.0 * FRAME_DT);        // выводим руку вперёд
    else if (!near) push = Math.max(0, push - 0.6 * FRAME_DT);       // свободно — медленно возвращаем
    if (INSTANT && inside) {                                          // для проверки — сразу до упора
      for (let i = 0; i < 14 && pts.some((p) => inBody(p, 0.015)); i++) {
        push += 0.05; up.rotation.x -= 0.05; hand.updateWorldMatrix(true, false);
        pts[0] = hand.getWorldPosition(_v).clone(); pts[1] = lo.getWorldPosition(_w).clone();
        pts[2] = pts[0].clone().add(pts[1]).multiplyScalar(0.5);
      }
    }
    sm[key] = push;
  }
}

let nextBlink = 0, blinkT = -1;
function face(t) {
  const em = vrm.expressionManager; if (!em) return;
  const asleep = S.face === 'sleep';
  const now = performance.now();
  let want = asleep ? { relaxed: 0.4 } : { ...(EMO[S.emo] || {}) };
  if (S.touch && now < S.touchUntil) {
    if (S.touch === 'head') want = { happy: asleep ? 0.4 : 0.9 };
    if (S.touch === 'face') want = asleep ? { relaxed: 0.5 } : { angry: 0.35, surprised: 0.2 };
    if (S.touch === 'body') want = asleep ? { relaxed: 0.5 } : { happy: 0.3, surprised: 0.35 };
  }
  if (S.dragging) want = { surprised: 0.7 };
  const kk = INSTANT ? 1 : 0.12;
  for (const k of ['happy', 'relaxed', 'sad', 'surprised', 'angry'])
    em.setValue(k, ease('e_' + k, want[k] || 0, kk));
  let blink = 0;
  if (asleep) blink = 1;
  else {
    if (t > nextBlink && blinkT < 0) { blinkT = t; nextBlink = t + 2.5 + Math.random() * 3.5; }
    if (blinkT >= 0) { const p = (t - blinkT) / 0.16; blink = p < 1 ? Math.sin(p * Math.PI) : 0; if (p >= 1) blinkT = -1; }
  }
  em.setValue('blink', ease('blink', blink, asleep ? 0.08 : 0.6));
  const talking = Date.now() - S.lipT < 350;
  const m = talking ? S.mouth : 0;
  const yawn = S.act === 'act-yawn' ? bell((now - S.actStart) / 1000, 2.5) : 0;
  em.setValue('aa', ease('aa', Math.max(Math.min(1, m * 1.4), yawn * 0.9), 0.5));
  em.setValue('oh', ease('oh', talking ? Math.max(0, Math.sin(t * 11)) * m * 0.4 : 0, 0.4));
}

// ---------- касания ----------
// Где на экране голова: проецируем кость головы в координаты холста.
function zoneAt(x, y) {
  const r = canvas.getBoundingClientRect();
  const p = new THREE.Vector3();
  bone('head').getWorldPosition(p);
  p.project(camera);
  const hx = (p.x * 0.5 + 0.5) * r.width, hy = (-p.y * 0.5 + 0.5) * r.height;
  const scale = r.height / 1.05 * 0.11;           // примерный «радиус головы» в пикселях
  const dx = x - r.left - hx, dy = y - r.top - hy;
  if (Math.abs(dx) < scale * 1.6 && dy < -scale * 0.9 && dy > -scale * 3.0) return 'head';
  if (Math.abs(dx) < scale * 1.2 && dy >= -scale * 0.9 && dy < scale * 0.55) return 'face';
  if (dy >= scale * 0.8 && dy < scale * 7 && Math.abs(dx) < scale * 2.5) return 'body';
  return '';
}

function touch(zone, ms) {
  const now = performance.now();
  if (S.touch !== zone || now > S.touchUntil) S.touchStart = now;
  S.touch = zone; S.touchUntil = now + ms;
  if (window.pywebview && window.pywebview.api && window.pywebview.api.touch) window.pywebview.api.touch(zone);
}

function setupTouch() {
  let down = null, moved = false, patTimer = null;
  canvas.addEventListener('mousedown', (e) => {
    down = { x: e.screenX, y: e.screenY, zone: zoneAt(e.clientX, e.clientY), t: performance.now() };
    moved = false;
    if (down.zone === 'head') {
      e.stopPropagation();          // по голове — гладим, а не тащим окно
      patTimer = setTimeout(() => touch('head', 2600), 350);
    }
  });
  window.addEventListener('mousemove', (e) => {
    if (!down) return;
    if (Math.hypot(e.screenX - down.x, e.screenY - down.y) > 6) {
      if (!moved) { moved = true; clearTimeout(patTimer); }
      if (down.zone === 'head') { touch('head', 1800); return; }                       // водит по голове — гладит
      S.dragging = true;                                                                // тащат окно
    }
  });
  window.addEventListener('mouseup', () => {
    if (!down) return;
    clearTimeout(patTimer);
    if (S.dragging) { S.dragging = false; touch('dropped', 10); }
    else if (!moved && down.zone && performance.now() - down.t < 350) touch(down.zone, down.zone === 'head' ? 2200 : 1600);
    down = null;
  });
}

// ---------- цикл ----------
let last = 0;
function loop(now) {
  requestAnimationFrame(loop);
  if (now - last < 1000 / 62) return;          // до 60 кадров/с
  last = now;
  const dt = Math.min(0.1, clock.getDelta()), t = clock.elapsedTime;
  FRAME_DT = dt || 1 / 60;
  if (vrm) { pose(t); face(t); vrm.update(dt); }
  renderer.render(scene, camera);
}

async function init(url) {
  host = document.getElementById('char');
  canvas = document.createElement('canvas');
  canvas.id = 'vrmCanvas';
  renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true, powerPreference: 'low-power' });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(22, 1, 0.1, 20);
  const light = new THREE.DirectionalLight(0xffffff, Math.PI * 0.9); light.position.set(0.5, 1.5, 2); scene.add(light);
  scene.add(new THREE.AmbientLight(0xffffff, Math.PI * 0.35));
  lookTarget = new THREE.Object3D(); scene.add(lookTarget);
  clock = new THREE.Clock();

  const loader = new GLTFLoader();
  loader.register((p) => new VRMLoaderPlugin(p));
  const gltf = await loader.loadAsync(url);
  vrm = gltf.userData.vrm;
  VRMUtils.removeUnnecessaryVertices(gltf.scene);
  if (VRMUtils.combineSkeletons) VRMUtils.combineSkeletons(gltf.scene);
  VRMUtils.rotateVRM0(vrm);
  vrm.scene.traverse((o) => { o.frustumCulled = false; });
  scene.add(vrm.scene);
  try { measureBody(); console.log('[3D] тело измерено:', BODY && BODY.ys.length, 'срезов'); } catch (e) { console.warn('[3D] тело не измерено', e); }
  const head = bone('head'); const p = new THREE.Vector3(); head.getWorldPosition(p);
  sm.headY = p.y + 0.12;

  host.appendChild(canvas);
  document.body.classList.add('has3d');
  resize();
  new ResizeObserver(resize).observe(host);
  setupTouch();
  requestAnimationFrame(loop);
  return true;
}

window.VRM3D = {
  ready: false,
  async start(url) {
    try { await init(url); this.ready = true; console.log('[3D] модель загружена'); return true; }
    catch (e) { console.error('[3D] не загрузилась', e); return false; }
  },
  state(face, emo, act) {
    if (act !== S.act && act) S.actStart = performance.now();
    S.face = face; S.emo = emo || 'calm'; S.act = act || '';
  },
  look(dx, dy) { S.lookX = dx; S.lookY = dy; S.lookT = Date.now(); },
  mouth(v) { S.mouth = v; S.lipT = Date.now(); },
  _zone(x, y) { return zoneAt(x, y); },
  _body() { return BODY; },
  _portrait(span = 0.42, down = 0.0) {        // крупный план лица (для иконки)
    const top = (sm.headY || 1.6) + 0.14 - down, fov = 22;
    const dist = (span / 2) / Math.tan(THREE.MathUtils.degToRad(fov / 2));
    camera.fov = fov; camera.aspect = 1; camera.position.set(0, top - span / 2, dist);
    camera.lookAt(0, top - span / 2, 0); camera.updateProjectionMatrix();
    window.removeEventListener('resize', resize); fitCamera = () => {};
  },
  // для проверки поз: VRM3D._test('clasp')
  _test(name, opts = {}) {
    INSTANT = true; S.idle = name; S.idleUntil = 1e12; S.face = opts.face || 'listen';
    S.emo = opts.emo || 'calm'; S.act = opts.act || '';
    if (opts.touch) { S.touch = opts.touch; S.touchStart = performance.now() - 1000; S.touchUntil = performance.now() + 1e9; }
    else S.touch = '';
    S.dragging = !!opts.drag;
  },
};
