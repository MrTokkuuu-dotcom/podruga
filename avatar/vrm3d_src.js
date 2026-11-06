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
  walkDir: 0, walkPhase: 0, walkPx: 0, sit: false, lie: false, full: false, shape: 'aa',
  worldX: 0, glanceUntil: 0, nextGlance: 0,
  idle: 'rest', idleUntil: 0,
  touch: '', touchStart: 0, touchUntil: 0, dragging: false,
};
let vrm = null, renderer, scene, camera, clock, lookTarget, host, canvas;
const sm = {};
const smv = {};                // скорости для пружин
const lerp = (a, b, k) => a + (b - a) * k;
let FRAME_DT = 1 / 30;
// Пружина вместо простого сглаживания: движение разгоняется, чуть «проскакивает» и успокаивается —
// как у живого тела. f — частота (Гц, выше = резче), z — затухание (меньше = больше покачивания).
function spring(key, target, f = 2, z = 0.75) {
  if (INSTANT) { sm[key] = target; smv[key] = 0; return target; }
  let x = sm[key] ?? target, v = smv[key] ?? 0;
  const w = 2 * Math.PI * f;
  let left = FRAME_DT;
  while (left > 1e-6) {                          // мелкие шаги — устойчиво при любом FPS
    const h = Math.min(left, 1 / 120);
    v += (w * w * (target - x) - 2 * z * w * v) * h;
    x += v * h;
    left -= h;
  }
  sm[key] = x; smv[key] = v; return x;
}
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
  lLegX: 0, rLegX: 0, lKneeX: 0, rKneeX: 0, lFootX: 0, rFootX: 0, drop: 0, spineY: 0,
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

let VIEW = { w: 200, h: 260 };
let CAM = { x: 0, y: 1, dist: 3, ty: 1 };
let fitCamera = function (w, h) {
  VIEW = { w, h };
  camera.aspect = w / h;
  const head = (sm.headY || 1.6) + 0.16;
  const near = w / h > 1.3 ? 0.85 : 1.05;          // окно с перепиской: от макушки до бёдер
  const full = head + 0.04;                        // «только она»: во весь рост, ноги у нижнего края
  const fk = sm.fullK || 0, lk = sm.lieK || 0;
  let span = lerp(near, full, fk);
  let cy = head - span / 2 + 0.05 * (1 - fk);
  if (lk > 0.001) {                                // лежит: кадр по ширине тела
    const lieSpan = Math.max(0.55, 2.0 / (w / h));
    span = lerp(span, lieSpan, lk);
    cy = lerp(cy, lieSpan / 2 - 0.02, lk);
  }
  const fov = 22;
  camera.fov = fov;
  CAM = { y: cy, ty: cy, dist: (span / 2) / Math.tan(THREE.MathUtils.degToRad(fov / 2)) };
  placeCamera();
  camera.updateProjectionMatrix();
};
function placeCamera() {
  const x = S.worldX || 0;
  camera.position.set(x, CAM.y, CAM.dist);
  camera.lookAt(x, CAM.ty, 0);
}

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

  // 1б) гуляет по экрану / сидит / лежит
  const mPerPx = (sm.headY ? (sm.headY + 0.2) : 1.85) / Math.max(200, VIEW.h);
  const speed = spring('walkSpeed', S.walkDir ? S.walkPx * mPerPx : 0, 1.2, 1);   // м/с, плавный разгон
  const amp = Math.min(1, speed / 0.35);
  if (amp > 0.02) {
    S.walkPhase += speed * FRAME_DT / 0.55 * Math.PI;   // шаг ~55 см: ноги не скользят по земле
    const ph = S.walkPhase, sw = Math.sin(ph), cw = Math.cos(ph);
    P = mix(P, { ...REST }, amp);
    P.lLegX = -sw * 0.38 * amp; P.rLegX = sw * 0.38 * amp;
    P.lKneeX = (0.06 + 0.75 * Math.max(0, cw)) * amp; P.rKneeX = (0.06 + 0.75 * Math.max(0, -cw)) * amp;
    P.lFootX = (sw * 0.25 - 0.1 * Math.max(0, cw)) * amp; P.rFootX = (-sw * 0.25 - 0.1 * Math.max(0, -cw)) * amp;
    P.lUpX = sw * 0.38 * amp; P.rUpX = -sw * 0.38 * amp;
    P.lLoY = -0.25 - Math.max(0, -sw) * 0.45 * amp; P.rLoY = 0.25 + Math.max(0, sw) * 0.45 * amp;
    P.lift = -Math.abs(sw) * 0.022 * amp;                 // таз ниже, когда ноги расставлены
    P.hipsZ += sw * 0.045 * amp;                          // покачивание бёдрами
    P.spineY = -sw * 0.09 * amp;                          // плечи против бёдер
    P.spineX += 0.05 * amp;                               // чуть вперёд при ходьбе
    P.headZ -= sw * 0.03 * amp;                           // голова держит горизонт
  }
  P.hipsY = S.walkDir * 1.05 * (S.lie ? 0 : 1);           // повернулась туда, куда идёт
  // на ходу иногда поглядывает в экран, а когда говорит — смотрит на тебя
  if (S.walkDir) {
    if (t > S.nextGlance) { S.glanceUntil = t + 1.2 + Math.random() * 1.3; S.nextGlance = t + 4 + Math.random() * 6; }
    if (talking || t < S.glanceUntil) { P.headY -= P.hipsY * 0.75; P.spineY = (P.spineY || 0) - P.hipsY * 0.2; }
  }
  if (S.sit && !S.walkDir) {
    P = mix(P, { lLegX: -1.45, rLegX: -1.45, lKneeX: 1.5, rKneeX: 1.5, lFootX: -0.1, rFootX: -0.1,
                 drop: 0.47, lUpZ: -1.25, rUpZ: 1.25, lUpX: -0.55, rUpX: -0.55, lLoY: -0.5, rLoY: 0.5,
                 spineX: 0.06 }, 1);
  }
  if (S.lie) {                                            // спит лёжа, свернувшись калачиком
    P = mix(P, { lLegX: -1.0, rLegX: -0.7, lKneeX: 1.6, rKneeX: 1.3, lFootX: 0.2, rFootX: 0.2,
                 lUpZ: -0.9, rUpZ: 0.6, lUpX: -0.7, rUpX: -0.9, lLoY: -1.6, rLoY: 1.7,
                 spineX: 0.25, headX: 0.15, headZ: -0.2 }, 1);
  }

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
  const lx = spring('lx', looking ? S.lookX : 0, 1.5, 0.8), ly = spring('ly', looking ? S.lookY : 0, 1.5, 0.8);
  P.headY += lx * 0.35; P.headX += ly * 0.18;

  // применить: пружины — руки свободнее и с инерцией, голова мягче, ноги чётко на ходу
  const walking = amp > 0.05;
  const fArm = walking ? 3.2 : 1.5, fLeg = walking ? 7 : 2.5, fHead = 2.0, fBody = 1.6;
  const set = (name, axis, v, f, z = 0.7) => { const b = bone(name); if (b) b.rotation[axis] = spring(name + axis, v, f, z); };
  set('leftUpperArm', 'z', P.lUpZ, fArm, 0.6); set('rightUpperArm', 'z', P.rUpZ, fArm, 0.6);
  set('leftUpperArm', 'y', P.lUpY, fArm, 0.6); set('rightUpperArm', 'y', P.rUpY, fArm, 0.6);
  set('leftUpperArm', 'x', P.lUpX, fArm, 0.55); set('rightUpperArm', 'x', P.rUpX, fArm, 0.55);
  set('leftLowerArm', 'y', P.lLoY, fArm * 1.2, 0.55); set('rightLowerArm', 'y', P.rLoY, fArm * 1.2, 0.55);
  set('leftLowerArm', 'z', P.lLoZ, fArm * 1.2, 0.6); set('rightLowerArm', 'z', P.rLoZ, fArm * 1.2, 0.6);
  set('leftHand', 'z', P.lHandZ, 2.5, 0.5); set('rightHand', 'z', P.rHandZ, 2.5, 0.5);   // кисти — «с запаздыванием»
  set('leftHand', 'x', P.lHandX, 2.5, 0.5); set('rightHand', 'x', P.rHandX, 2.5, 0.5);
  set('spine', 'x', P.spineX, fBody, 0.8); set('chest', 'x', P.chestX + P.spineX * 0.6, fBody, 0.8);
  set('spine', 'z', P.spineZ, fBody, 0.8); set('spine', 'y', P.spineY || 0, walking ? 4 : fBody, 0.7);
  set('neck', 'x', P.headX * 0.4, fHead, 0.75); set('head', 'x', P.headX * 0.6, fHead, 0.7);
  set('neck', 'y', P.headY * 0.4, fHead, 0.75); set('head', 'y', P.headY * 0.6, fHead, 0.7);
  set('head', 'z', P.headZ, fHead, 0.7);
  set('hips', 'z', P.hipsZ, walking ? 5 : 1.2, 0.8); set('hips', 'y', P.hipsY, 1.1, 0.85);
  set('leftUpperLeg', 'x', P.lLegX, fLeg, 0.85); set('rightUpperLeg', 'x', P.rLegX, fLeg, 0.85);
  set('leftLowerLeg', 'x', P.lKneeX, fLeg, 0.85); set('rightLowerLeg', 'x', P.rKneeX, fLeg, 0.85);
  set('leftFoot', 'x', P.lFootX, fLeg, 0.85); set('rightFoot', 'x', P.rFootX, fLeg, 0.85);
  avoidBody();
  const hips = bone('hips');
  if (hips) {
    sm.hipsBase ??= hips.position.y;
    hips.position.y = sm.hipsBase + spring('lift', P.lift, walking ? 6 : 3, 0.7) - spring('drop', P.drop, 1.2, 0.9);
  }
  // лёжа: поворачиваем всю модель на бок
  const lk = spring('lieK', S.lie ? 1 : 0, 0.6, 1);
  vrm.scene.rotation.set(0, 0, lk * Math.PI / 2);   // на боку, лицом к нам
  vrm.scene.position.y = lk * 0.32;
  vrm.scene.position.x = (S.worldX || 0) + lk * 0.85;

  if (vrm.lookAt) {
    lookTarget.position.set((S.worldX || 0) + lx * 1.2, camera.position.y + ly * 0.6, camera.position.z);
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
  const open = Math.min(1, m * 1.4);
  for (const v of ['aa', 'ih', 'ou', 'ee', 'oh']) {     // форма рта по гласной из звука
    let w = talking && S.shape === v ? open : 0;
    if (v === 'aa') w = Math.max(w, yawn * 0.9, talking && !S.shape ? open : 0);
    em.setValue(v, ease('v_' + v, w, 0.45));
  }
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
  if (vrm) {
    const mini = document.body.classList.contains('mini');
    const fk = sm.fullK || 0, want = (mini || S.full || S.walkDir || S.sit || S.lie) ? 1 : 0;
    if (Math.abs(fk - want) > 0.002) { sm.fullK = lerp(fk, want, 1 - Math.pow(0.04, dt)); fitCamera(VIEW.w, VIEW.h); }
    pose(t); face(t);
    // она «по-настоящему» идёт в 3D-мире, а камера едет за ней — волосы и одежда отстают сами
    S.worldX = (S.worldX || 0) + (S.walkDir || 0) * (sm.walkSpeed || 0) * dt;
    if (Math.abs(S.worldX) > 50 && !S.walkDir) S.worldX = 0;
    const lk = sm.lieK || 0;
    if (lk > 0.001 && lk < 0.999) fitCamera(VIEW.w, VIEW.h); else placeCamera();
    vrm.update(dt);
  }
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
  mouth(v, shape) { S.mouth = v; S.lipT = Date.now(); if (shape) S.shape = shape; },
  walk(dir, px) { S.walkDir = dir; if (px != null) S.walkPx = px; if (dir) { S.sit = false; S.lie = false; } },
  lie(on) { S.lie = !!on; if (on) S.sit = false; },
  sit(on) { S.sit = !!on; },
  full(on) { S.full = !!on; },
  _zone(x, y) { return zoneAt(x, y); },
  _body() { return BODY; },
  _dbg() { const r = {}; for (const n of ['hips','leftUpperLeg','leftLowerLeg']) { const b = bone(n); r[n] = b ? [b.rotation.x.toFixed(2), b.rotation.y.toFixed(2), b.rotation.z.toFixed(2)] : null; } r.lie = S.lie; r.lieK = sm.lieK; return r; },
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
    S.dragging = !!opts.drag; S.walkDir = opts.walk || 0; S.walkPx = 110; sm.walkSpeed = opts.walk ? 0.5 : 0; S.sit = !!opts.sit; S.lie = !!opts.lie; sm.lieK = S.lie ? 1 : 0; S.full = true; sm.fullK = 1; if (camera) fitCamera(VIEW.w, VIEW.h);
  },
};
