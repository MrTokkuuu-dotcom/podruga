// 3D-героиня из VRM (VRoid). Собирается esbuild в avatar/vrm3d.js (один файл, без интернета).
// Позы задаются поворотами костей поверх «T-позы» VRM (лицом к камере, +Z).
//  левая рука (+X):  z<0 — вниз,  y<0 — вперёд;   правая (-X): z>0 — вниз, y>0 — вперёд
//  предплечье: y — сгиб в локте вперёд (левое <0, правое >0)
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { VRMLoaderPlugin, VRMUtils, VRMSpringBoneCollider, VRMSpringBoneColliderShapeCapsule } from '@pixiv/three-vrm';
import ANIMS from './anims.json';      // анимации Quaternius (CC0), переложены tools/retarget_ual.py

const S = {
  face: 'sleep', emo: 'calm', act: '', actStart: 0, mouth: 0, lipT: 0,
  lookX: 0, lookY: 0, lookT: 0,
  full: false, shape: 'aa',
  worldX: 0, glanceUntil: 0, nextGlance: 0,
  idle: 'rest', idleUntil: 0,
  touch: '', touchStart: 0, touchUntil: 0, dragging: false,
  // большое окно: где она стоит (пиксели окна: x — центр, y — ноги над нижним краем)
  stage: false, x: 0, y: 0, W: 0, H: 0, goal: null, dir: 0, v: 0, dock: null,
  // поза: stand / sit / lie; sitting — уже идёт посадка или сидит
  posture: 'stand', sitting: false, downT: 0, upT: 9, lieRaw: 0, lay: '', layDoneT: 0,
  ledges: [], support: null, jump: null, edge: false,   // края окон, на каком стоит, прыжок, сидит на краю
  // сон по порядку: '' → drowsy (идёт, глаза открыты) → closing (лежит, глаза закрываются) → asleep
  seq: '', seqAct: '', seqActStart: 0, seqT: 0, sleepAfterLie: false,
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
let INSTANT = false;
let NO_AVOID = false;                                               // для проверки: выключить защиту рук                                                // для проверки поз

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
  lUpZ: -1.32, rUpZ: 1.32, lUpY: -0.05, rUpY: 0.05, lUpX: 0.04, rUpX: 0.04,
  lLoY: -0.18, rLoY: 0.18, lLoZ: 0, rLoZ: 0, lHandZ: -0.1, rHandZ: 0.1, lHandX: 0, rHandX: 0,
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
  think:   { rUpZ: 1.0, rUpY: 0.45, rUpX: -0.15, rLoY: 2.5, rLoZ: 0.2, rHandX: 0.2,
             lUpZ: -1.22, lUpY: -0.5, lUpX: -0.35, lLoY: -1.25, lLoZ: -0.3, headZ: -0.12, headX: -0.06 },
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
  drag:    { lUpZ: -0.85, rUpZ: 0.85, lUpY: -0.2, rUpY: 0.2, lLoY: -0.6, rLoY: 0.6, headX: -0.05 },
  // держит себя за локоть — тихо, чуть стеснительно (Аня)
  elbow:   { lUpZ: -1.28, lUpY: -0.5, lLoY: -1.45, lLoZ: -0.3, rUpZ: 1.33, rUpY: 0.12, rLoY: 0.35, rLoZ: 0.1,
             headZ: 0.08, headX: 0.05 },
  // обе руки на поясе — уверенно (Алиса)
  hips2:   { rUpZ: 0.75, rUpY: -0.1, rLoY: 0.35, rLoZ: 1.5, rHandZ: 0.5, lUpZ: -0.75, lUpY: 0.1, lLoY: -0.35, lLoZ: -1.5, lHandZ: -0.5,
             chestX: -0.04, headZ: -0.04 },
  // руки за головой — беззаботно (Алиса)
  headBehind: { lUpZ: 0.7, rUpZ: -0.7, lUpY: -0.4, rUpY: 0.4, lLoY: 0, rLoY: 0, lLoZ: 2.2, rLoZ: -2.2,
             chestX: -0.06, headX: -0.06 },
  // ладони у сердца — тепло (Таня)
  heart:   { lUpZ: -1.15, rUpZ: 1.15, lUpY: -0.6, rUpY: 0.6, lLoY: -2.0, rLoY: 2.0, lLoZ: -0.15, rLoZ: 0.15,
             headZ: 0.08, headX: 0.04 },
  // щека на ладони — мечтательно (Таня)
  cheek:   { rUpZ: 1.0, rUpY: 0.5, rUpX: -0.55, rLoY: 2.7, rLoZ: 0.1, rHandX: 0.25,
             lUpZ: -1.22, lUpY: -0.5, lUpX: -0.3, lLoY: -1.3, lLoZ: -0.3, headZ: -0.18 },
  // спит стоя
  sleep:   { lUpZ: -1.3, rUpZ: 1.3, lUpY: -0.35, rUpY: 0.35, lLoY: -1.0, rLoY: 1.0, lLoZ: -0.3, rLoZ: 0.3,
             headX: 0.38, headZ: 0.15, spineX: 0.06 },
};
const IDLE = ['rest', 'rest', 'rest', 'clasp', 'behind', 'hip', 'look', 'sway', 'think', 'foldArms', 'foldArms'];
// характер в движениях (у каждой девочки свой, приходит из avatars.json): любимые позы, как часто их меняет,
// скорость шага, размах покачивания, наклон головы, как подпрыгивает от радости
const PERSONA = { idle: IDLE, pace: 1, speed: 1, sway: 1, tilt: 0, bounce: 1 };
function setPersona(m) {
  m = m || {};
  const ok = (m.idle || []).filter(n => POSES[n] || ['rest', 'look', 'sway', 'foldArms'].includes(n));
  PERSONA.idle = ok.length ? ok : IDLE;
  for (const k of ['pace', 'speed', 'sway', 'tilt', 'bounce']) PERSONA[k] = typeof m[k] === 'number' ? m[k] : (k === 'tilt' ? 0 : 1);
}
// жесты из библиотек: только верх тела (руки, корпус, голова), ноги остаются в её ровной стойке
const GESTURES = { foldArms: 1, yes: 1, no: 1 };

function bone(name) { return vrm.humanoid.getNormalizedBoneNode(name); }

let VIEW = { w: 200, h: 260 };
let CAM = { x: 0, y: 1, dist: 3, ty: 1 };
const PX_PER_M = 286;                              // её размер на экране в режиме «только она» (как раньше)
let BOUNDS = null;                                 // реальные размеры модели: рост, размах рук, длина лёжа
let VIRT = { w: 900, h: 600 };                     // воображаемый полный кадр: холст вырезает из него нужный кусок
let CROP = { w: 0, h: 0 };
let fitCamera = function (w, h) {
  VIEW = { w, h };
  const fov = 22;
  camera.fov = fov;
  if (S.stage) {                                   // большое окно: масштаб и перспектива постоянные, ноги у нижнего края
    camera.aspect = VIRT.w / VIRT.h;
    const span = VIRT.h / PX_PER_M, cy = span / 2 - 0.015;
    CAM = { y: cy, ty: cy, dist: (span / 2) / Math.tan(THREE.MathUtils.degToRad(fov / 2)) };
    camera.setViewOffset(VIRT.w, VIRT.h, (VIRT.w - w) / 2, VIRT.h - h, w, h);
    placeCamera();
    return;
  }
  camera.clearViewOffset();
  camera.aspect = w / h;
  const head = (sm.headY || 1.6) + 0.16;
  const near = w / h > 1.3 ? 0.85 : 1.05;          // окно с перепиской: от макушки до бёдер
  const full = h / PX_PER_M;                       // «только она»: постоянный масштаб, ноги у нижнего края
  const fk = sm.fullK || 0;
  const span = lerp(near, full, fk);
  const cy = lerp(head - near / 2 + 0.05, full / 2 - 0.015, fk);
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
  const w = S.stage ? CROP.w : (host.clientWidth || 200), h = S.stage ? CROP.h : (host.clientHeight || 260);
  renderer.setSize(w, h, false);
  fitCamera(w, h);
}

// ---------- большое окно ----------
// Окно накрывает экран и стоит на месте, а холст с ней ездит внутри него в том же кадре, в котором рисуется.
const SPEED = 190, ACCEL = 300;                    // пикс/с, пикс/с²
const YAW = 1.2;                                   // на ходу развёрнута почти боком (рад)
function setCrop(w, h) {
  if (w === CROP.w && h === CROP.h) return;
  CROP = { w, h };
  host.style.width = w + 'px'; host.style.height = h + 'px';
  resize();
  placeStage(true);
}
let placedKey = '';
const EDGE_DROP = 0.5;                                // на сколько метров ниже края — ноги свисают с окна
function placeStage(force) {
  const drop = (sm.edgeK || 0) * EDGE_DROP * PX_PER_M;
  const px = Math.round((S.x - CROP.w / 2) * 2) / 2, py = Math.round((S.H - S.y + drop - CROP.h) * 2) / 2;
  const top = lerp(lerp((sm.headY || 1.6), 1.0, sm.sitK || 0), 0.55, sm.lieK || 0) * PX_PER_M;
  const key = px + ',' + py + ',' + Math.round(top) + ',' + Math.round(drop);
  if (!force && key === placedKey) return;
  placedKey = key;
  host.style.transform = `translate3d(${px}px,${py}px,0)`;
  const btn = document.getElementById('chatBtn');
  if (btn) {
    S.btnX = Math.round(S.x + 70); S.btnY = Math.round(S.H - S.y + drop - top - 8);
    btn.style.setProperty('--bx', S.btnX + 'px'); btn.style.setProperty('--by', S.btnY + 'px');
  }
  const q = document.getElementById('quitBtn');
  if (q) { q.style.setProperty('--qx', (S.btnX + 42) + 'px'); q.style.setProperty('--qy', (S.btnY + 4) + 'px'); }

}
function stageOn(W, H, x, y) {
  S.stage = true; S.W = W; S.H = H; S.x = x; S.y = y; CROP = { w: 0, h: 0 };
  document.body.classList.add('stage');
  document.getElementById('charWrap').classList.remove('pywebview-drag-region');
  VIRT = { w: Math.max(BOUNDS.w, BOUNDS.lieW) + 40, h: BOUNDS.h };
  setCrop(BOUNDS.w, BOUNDS.h);
  placeStage(true);
}
function stageOff() {
  S.stage = false; S.goal = null; S.dir = 0; S.v = 0;
  document.body.classList.remove('stage');
  document.getElementById('charWrap').classList.add('pywebview-drag-region');
  host.style.width = host.style.height = host.style.transform = '';
  resize();
}
function floorAt(x) {
  const d = S.dock;
  return d && x >= d[0] - 10 && x <= d[1] + 10 ? d[2] : 0;
}
const ledgeById = (id) => S.ledges.find((l) => l[0] === id);
function groundAt(x) {
  if (S.support != null) { const l = ledgeById(S.support); if (l) return l[3]; }
  return floorAt(x);
}
// ---------- прыжки: на край окна и вниз ----------
// Присела (jumpStart) → летит по дуге (jumpAir) → приземлилась (jumpLand). Всё тело — из анимации.
const JUMP_TAKEOFF = 0.42;                           // с какой секунды клипа отрывается от земли
function startJump(x1, y1, support) {
  if (!A.jumpStart || S.jump) return false;
  S.goal = null; S.v = 0;
  const dx = x1 - S.x, dy = y1 - S.y;
  const dur = Math.max(0.5, Math.min(1.15, 0.45 + Math.abs(dy) / 900 + Math.abs(dx) / 1200));
  S.jump = { x0: S.x, y0: S.y, x1, y1, support, t: 0, dur, arc: Math.max(0, dy) * 0.25 + 70, phase: 'crouch' };
  S.dir = Math.abs(dx) > 40 ? Math.sign(dx) : 0;
  restart('jumpStart');
  return true;
}
function jumpStep(dt) {
  const J = S.jump; if (!J) return;
  J.t += dt;
  if (J.phase === 'crouch' && J.t >= JUMP_TAKEOFF) { J.phase = 'air'; J.t0 = J.t; restart('jumpAir'); }
  if (J.phase === 'air') {
    const u = clamp01((J.t - J.t0) / J.dur);
    const nx = lerp(J.x0, J.x1, u);
    S.worldX += (nx - S.x) / PX_PER_M;
    S.x = nx; S.y = lerp(J.y0, J.y1, u) + J.arc * 4 * u * (1 - u);
    if (u >= 1) { J.phase = 'land'; J.t0 = J.t; S.support = J.support; restart('jumpLand'); }
  }
  if (J.phase === 'land' && J.t - J.t0 > 0.75) {
    S.jump = null; S.dir = 0;
    pyCall('landed', S.support == null ? null : S.support);
  }
}
function fallDown() {                                 // окно закрыли или увели из-под ног — спрыгивает вниз
  S.support = null; S.edge = false;
  if (S.posture === 'edge') S.posture = 'stand';
  if (!startJump(S.x, floorAt(S.x), null)) S.y = floorAt(S.x);
}
function pyCall(name, ...args) {
  if (window.pywebview && window.pywebview.api && window.pywebview.api[name]) window.pywebview.api[name](...args);
}
function stageMove(dt) {
  jumpStep(dt);
  if (S.jump) { placeStage(); return; }
  const g = S.goal;
  const standing = !S.sitting && S.upT > 1.45 && S.lieRaw <= 0 && !S.lay;
  let vt = 0;
  if (g && standing) {
    const dir = Math.sign(g.x - S.x) || S.dir || 1, dist = (g.x - S.x) * dir;
    S.dir = dir;
    if (Math.abs((sm.yaw || 0) - dir * YAW) < 0.55) vt = Math.min(SPEED * PERSONA.speed, Math.sqrt(2 * ACCEL * Math.max(dist, 0)));
    if (dist <= 0.5 && S.v < 8) {
      S.x = g.x; S.goal = null; S.dir = 0; S.v = 0;
      pyCall('walk_done', true);
    }
  }
  S.v += Math.max(-ACCEL * dt, Math.min(ACCEL * dt, vt - S.v));
  if (S.v < 0.5 && !S.goal) S.v = 0;
  if (S.v > 0 && S.goal) {
    const step = Math.min(S.v * dt, Math.abs(S.goal.x - S.x));
    S.x += S.dir * step;
    S.worldX += S.dir * step / PX_PER_M;             // в 3D-мире она тоже идёт: волосы и одежда отстают сами
  }
  if ((S.goal || S.v > 0) && !S.jump) {               // на «ступеньку» Dock — плавно, вниз — быстрее (спрыгнула)
    const dy = groundAt(S.x) - S.y;
    S.y += Math.max(-560 * dt, Math.min(240 * dt, dy));
  }
  document.body.classList.toggle('walking', !!(S.goal || S.v > 0 || S.sitting || S.lieRaw > 0));
  const lying = S.lieRaw > 0 || S.posture === 'lie';
  const settled = S.lieRaw >= 1;
  // холст по размеру того, что сейчас видно: руки вверх и в стороны — шире, просто стоит — меньше пикселей
  const wide = (sm.armW || 0) > 0.08 || S.dragging;
  if ((sm.sitK > 0 && sm.sitK < 1) || (sm.lieK > 0 && sm.lieK < 1) || (sm.edgeK > 0 && sm.edgeK < 1)) placedKey = '';   // кнопки едут за головой
  setCrop(lying ? Math.max(BOUNDS.w, BOUNDS.lieW) : wide ? BOUNDS.w : Math.min(BOUNDS.w, 300),
          settled ? BOUNDS.lieH : wide ? BOUNDS.h : Math.min(BOUNDS.h, 530));
  placeStage();
}

// ---------- анимации ----------
let mixer = null;
const A = {};                                      // клип → { action, w }
function buildAnims() {
  mixer = new THREE.AnimationMixer(vrm.scene);
  const hipsNode = bone('hips');
  for (const [key, c] of Object.entries(ANIMS.clips)) {
    const times = new Float32Array(c.n);
    for (let i = 0; i < c.n; i++) times[i] = c.dur * i / (c.n - 1);
    const tracks = [];
    for (const [b, vals] of Object.entries(c.q)) {
      const node = bone(b); if (!node) continue;
      tracks.push(new THREE.QuaternionKeyframeTrack(node.name + '.quaternion', times, vals));
    }
    tracks.push(new THREE.VectorKeyframeTrack(hipsNode.name + '.position', times, c.pos.map((v) => v * sm.hipsBase)));
    const action = mixer.clipAction(new THREE.AnimationClip(key, c.dur, tracks));
    const once = ['sitEnter', 'sitExit', 'layUp', 'yes', 'no', 'jumpStart', 'jumpLand'].includes(key);
    action.setLoop(once ? THREE.LoopOnce : THREE.LoopRepeat);
    action.clampWhenFinished = once;
    if (key === 'sitExit') action.timeScale = 0.72;
    action.play();
    action.setEffectiveWeight(0);
    A[key] = { action, w: 0, speed: c.speed, dur: c.dur };
  }
  const lq = ANIMS.clips.walk.q.leftUpperLeg, c = ANIMS.clips.walk;
  if (lq) {
    let best = 0, bx = 1e9;
    for (let i = 0; i < c.n; i++) {
      _e.setFromQuaternion(_q.set(lq[i * 4], lq[i * 4 + 1], lq[i * 4 + 2], lq[i * 4 + 3]));
      if (_e.x < bx) { bx = _e.x; best = i; }
    }
    A.walk.ph0 = best / (c.n - 1);
  }
  for (const k in A) A[k].w = 0;
}
function startGesture(name, sec) {
  if (!A[name]) return;
  restart(name);
  S.gesture = { name, until: performance.now() + (sec || A[name].dur) * 1000 };
}
function restart(key) { const a = A[key].action; a.reset(); a.play(); }
const smooth = (x) => { x = clamp01(x); return x * x * (3 - 2 * x); };
// Лечь и встать — игровая анимация «лежит → встаёт» (UAL2, CC0): ложится — она же задом наперёд.
// lay: '' — нет, 'down' — ложится, 'hold' — лежит, 'up' — встаёт.
const LAY_DOWN = 0.62, LAY_UP = 0.8, LAY_YAW = -1.4;
const HOLD_ADD = [['neck', 0, 0.25, 0], ['head', 0.05, 0.45, 0], ['leftUpperLeg', -0.55, 0, 0.05], ['leftLowerLeg', 1.0, 0, 0],
                  ['leftFoot', -0.35, 0, 0], ['rightUpperArm', -0.5, 0, -0.45], ['rightLowerArm', 0, 1.1, 0]];                 // скорость: ложится плавно, встаёт чуть бодрее
function layStep(dt) {
  const L = A.layUp; if (!L) return false;
  const a = L.action, wantLie = S.posture === 'lie';
  if (wantLie && (S.lay === '' || S.lay === 'up') && S.v < 1 && !S.sitting) {
    if (S.lay === '') { a.reset(); a.time = L.dur; }
    a.paused = false; a.timeScale = -LAY_DOWN; a.play(); S.lay = 'down';
  }
  if (!wantLie && (S.lay === 'down' || S.lay === 'hold')) { a.paused = false; a.timeScale = LAY_UP; a.play(); S.lay = 'up'; }
  if (S.lay === 'down' && a.time <= 0.001) { S.lay = 'hold'; a.time = 0; a.paused = true; }
  if (S.lay === 'up' && a.time >= L.dur - 0.001) { S.lay = 'done'; S.layDoneT = 0; }
  if (S.lay === 'done') { S.layDoneT += dt; if (S.layDoneT > 0.6) S.lay = ''; }
  // насколько «лежит» — для холста, кнопок и глаз
  S.lieRaw = S.lay === '' ? 0 : S.lay === 'done' ? 0 : clamp01(1 - a.time / (L.dur * 0.7));

  return true;
}
function updatePosture(dt) {
  // тело полностью из анимации: ложится/встаёт или прыгает
  const whole = (S.lay && S.lay !== 'done') || !!S.jump;
  sm.layW = lerp(sm.layW || 0, whole ? 1 : 0, 1 - Math.exp(-dt / (whole ? 0.1 : 0.22)));
  if (S.posture === 'lie' || S.lay) {
    if (layStep(dt)) {
      sm.sitK = 0; sm.lieK = smooth(S.lieRaw);
      if (S.sleepAfterLie && S.lay === 'hold') { S.sleepAfterLie = false; S.seq = 'closing'; S.seqT = 0; }
      if (S.seq === 'closing') { S.seqT += dt; if (S.seqT > 3) S.seq = 'asleep'; }
      return;
    }
  }
  const down = S.posture !== 'stand';
  if (down && !S.sitting && S.v < 1) { S.sitting = true; S.downT = 0; S.upT = 9; restart('sitEnter'); }
  if (S.sitting) S.downT += dt;
  // лечь — только когда уже сидит; встать — сначала сесть обратно
  const canLie = S.posture === 'lie' && S.sitting && S.downT > 2.0;
  S.lieRaw = clamp01(S.lieRaw + (canLie ? dt / 3.6 : -dt / 3.0));
  if (S.sitting && !down && S.lieRaw <= 0) { S.sitting = false; S.upT = 0; restart('sitExit'); }
  if (!S.sitting) S.upT += dt;
  sm.sitK = S.sitting ? smooth((S.downT - 0.55) / 1.25) : 1 - smooth(S.upT / 1.25);
  if (S.sitting && !down) sm.sitK = 1;               // пока встаёт из положения лёжа, остаётся сидя
  if (S.posture === 'edge' && S.sitting) S.edge = true;
  if (S.edge) {
    sm.edgeK = sm.sitK; sm.sitK = 0;                  // без позы «на полу»: ноги из анимации посадки
    if (!S.sitting && S.upT > 1.45) { S.edge = false; sm.edgeK = 0; }
  } else sm.edgeK = 0;
  sm.lieK = smooth(S.lieRaw);
  if (S.sleepAfterLie && S.lieRaw >= 1) { S.sleepAfterLie = false; S.seq = 'closing'; S.seqT = 0; }
  if (S.seq === 'closing') { S.seqT += dt; if (S.seqT > 3) S.seq = 'asleep'; }
}
// Микшер не перезаписывает кость, если её значение не изменилось. Поэтому перед каждым его шагом
// возвращаем кости к чистому состоянию анимации, иначе наши добавки копились бы от кадра к кадру.
const CLEAN = new Map();
let cleanHips = null;
function saveClean() {
  for (const n of ANIMS.bones) {
    const b = bone(n); if (!b) continue;
    if (!CLEAN.has(n)) CLEAN.set(n, new THREE.Quaternion());
    CLEAN.get(n).copy(b.quaternion);
  }
  (cleanHips ||= new THREE.Vector3()).copy(bone('hips').position);
}
function restoreClean() {
  for (const [n, q] of CLEAN) bone(n).quaternion.copy(q);
  if (cleanHips) bone('hips').position.copy(cleanHips);
}
function mixerStep(dt) {
  if (!mixer) return;
  restoreClean();
  const talking = Date.now() - S.lipT < 350;
  const walkW = clamp01(S.v / 70);
  const t = {};
  if (S.jump && A.jumpStart) t[S.jump.phase === 'crouch' ? 'jumpStart' : S.jump.phase === 'air' ? 'jumpAir' : 'jumpLand'] = 1;
  else if (S.lay && A.layUp) t.layUp = 1;
  else if (S.sitting) { if (S.downT < 1.2) t.sitEnter = 1; else t[talking ? 'sitTalk' : 'sitIdle'] = 1; }
  else if (S.upT < 1.35) t.sitExit = 1;
  else {
    t.walk = walkW;                                  // стоит — без клипа: прямая спина, ноги ровно, по своей позе
    const g = S.gesture && performance.now() < S.gesture.until ? S.gesture.name : (S.idle === 'foldArms' ? 'foldArms' : '');
    if (g && A[g] && walkW < 0.05) t[g] = 1;
  }
  const k = 1 - Math.exp(-dt / 0.16);
  for (const key in A) {
    const a = A[key];
    a.w += ((t[key] || 0) - a.w) * k;
    if (a.w < 0.002 && !t[key]) a.w = 0;
    a.action.setEffectiveWeight(a.w);
  }
  // шаг точно по скорости движения по экрану: ступня на опоре не едет
  const headingV = (S.v / PX_PER_M) / Math.sin(YAW);
  A.walk.action.timeScale = Math.max(0.3, headingV / (A.walk.speed * sm.hipsBase));
  mixer.update(dt);
  sm.walkPh = 2 * Math.PI * (A.walk.action.time / A.walk.dur - (A.walk.ph0 || 0));
  saveClean();
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
  const L = PERSONA.idle;
  let next = L[Math.floor(Math.random() * L.length)];
  if (next === prev) next = 'rest';
  S.idle = next;
  S.idleUntil = t + (next === 'hair' ? 3 : (next === 'rest' ? 6 + Math.random() * 8 : 5 + Math.random() * 6) * PERSONA.pace);
}

const isAsleep = () => (S.face === 'sleep' && !S.seq) || S.seq === 'asleep';
// Сидит на полу, обняв колени; лежит на боку, свернувшись. Поверх анимации, с весом sitK / lieK.
const SIT_POSE = { lLegX: -2.2, rLegX: -2.1, lKneeX: 2.7, rKneeX: 2.6, lFootX: -0.5, rFootX: -0.5,
                   spineX: 0.26, chestX: 0.05, headX: -0.2,
                   lUpZ: -1.3, rUpZ: 1.3, lUpX: -0.55, rUpX: -0.55, lUpY: -0.1, rUpY: 0.1,
                   lLoY: -0.55, rLoY: 0.55, lLoZ: 0, rLoZ: 0, lHandZ: 0.2, rHandZ: -0.2 };
const SEAT_Y = 0.23, LIE_Y = 0.32;                  // высота таза сидя и лёжа: ничего не уходит ниже пола
// Как ложится — по ключевым позам (k — доля времени укладывания). roll — насколько завалилась на бок (рад).
// Заваливается на ПРАВЫЙ бок, поэтому опирается правой рукой: сначала ладонью, потом локтем, потом кладёт на руку голову.
const LIE_KEYS = [
  { k: 0.0, roll: 0 },
  { k: 0.28, roll: 0.32, P: { spineZ: 0.22, headZ: -0.18, rUpZ: 0.6, rUpX: -0.25, rUpY: 0.1, rLoY: 0.25, rHandZ: -0.4,
                              lLegX: -2.0, rLegX: -1.9, lKneeX: 2.5, rKneeX: 2.4 } },
  { k: 0.6, roll: 0.95, P: { spineZ: 0.3, headZ: -0.3, rUpZ: 0.3, rUpX: -0.35, rUpY: 0.15, rLoY: 1.15, rHandZ: -0.2,
                             lUpZ: -1.25, lUpX: -0.6, lUpY: -0.1, lLoY: -1.0, lLegX: -1.6, rLegX: -1.3, lKneeX: 2.1, rKneeX: 1.8,
                             spineX: 0.2, headX: 0.05 } },
  { k: 0.86, roll: 1.45, P: { spineZ: 0.1, headZ: -0.1, rUpZ: -0.1, rUpX: -0.3, rUpY: 0.2, rLoY: 1.6, rHandZ: -0.3,
                              lUpZ: -1.25, lUpX: -0.55, lLoY: -1.05, lLegX: -1.3, rLegX: -0.9, lKneeX: 1.95, rKneeX: 1.35,
                              spineX: 0.22, headX: 0.1 } },
  { k: 1.0, roll: Math.PI / 2, P: { spineZ: 0.04, headZ: 0.06, rUpZ: -0.25, rUpX: -0.3, rUpY: 0.2, rLoY: 1.75, rHandZ: -0.3,
                                    lUpZ: -1.28, lUpX: -0.5, lUpY: -0.1, lLoY: -1.1, lLoZ: 0, lHandZ: 0.2,
                                    lLegX: -1.25, rLegX: -0.8, lKneeX: 1.9, rKneeX: 1.25, lFootX: 0.25, rFootX: 0.2,
                                    spineX: 0.22, chestX: 0.04, headX: 0.12 } },
];
function lieAt(k, base) {
  let i = 0; while (i < LIE_KEYS.length - 2 && k > LIE_KEYS[i + 1].k) i++;
  const a = LIE_KEYS[i], b = LIE_KEYS[i + 1], u = smooth((k - a.k) / (b.k - a.k));
  const pa = a.P || {}, pb = b.P || {}, out = {};
  for (const f of new Set([...Object.keys(pa), ...Object.keys(pb)])) {
    const va = pa[f] ?? base[f] ?? 0;
    out[f] = lerp(va, pb[f] ?? va, u);
  }
  return { roll: lerp(a.roll, b.roll, u), P: out };
}
const ADD_BONES = new Set(['neck', 'head']);
const LEG_BONES = new Set(['hips', 'leftUpperLeg', 'rightUpperLeg', 'leftLowerLeg', 'rightLowerLeg', 'leftFoot', 'rightFoot']);
const _e = new THREE.Euler(), _q = new THREE.Quaternion(), _hipsWorld = new THREE.Vector3();

function pose(t) {
  S.t = t;
  const asleep = isAsleep();
  const talking = Date.now() - S.lipT < 350;
  const now = performance.now();
  const moving = !!S.goal || S.v > 2;
  let P = { ...REST };

  // 1) простой: сама меняет позы, пока ничего не происходит
  if (moving || S.sitting || S.seq) { S.idle = 'rest'; S.idleUntil = t + 4 + Math.random() * 4; }
  else if (!asleep && S.face !== 'think' && !talking) chooseIdle(t);
  if (asleep && !S.sitting) P = mix(P, POSES.sleep, 1);
  else if (POSES[S.idle]) P = mix(P, POSES[S.idle], 1);
  if (!asleep && S.idle === 'look') { P.headY += Math.sin(t * 0.7) * 0.35; P.headX -= 0.05; }
  if (!asleep && S.idle === 'sway') { const f = 0.8 + 0.3 * PERSONA.sway; P.spineZ += Math.sin(t * f) * 0.03 * PERSONA.sway; P.headZ += Math.sin(t * f + 1) * 0.06 * PERSONA.sway; }
  if (!asleep) P.headZ += PERSONA.tilt;
  let wantArms = !asleep ? (POSES[S.idle] || S.idle === 'foldArms' ? 1 : 0) : 1;
  const walkW = A.walk ? A.walk.w : 0;
  if (walkW > 0.01 && !S.dragging) {
    const c = Math.cos(sm.walkPh || 0), a = 0.25 * walkW;
    P.lUpX = lerp(P.lUpX, a * c, walkW); P.rUpX = lerp(P.rUpX, -a * c, walkW);
    P.lLoY = lerp(P.lLoY, -(0.22 + 0.3 * Math.max(0, -c)), walkW); P.rLoY = lerp(P.rLoY, 0.22 + 0.3 * Math.max(0, c), walkW);
    P.lUpZ = lerp(P.lUpZ, -1.3, walkW); P.rUpZ = lerp(P.rUpZ, 1.3, walkW);
    P.spineX += 0.04 * walkW; P.spineY = (P.spineY || 0) + Math.cos(sm.walkPh || 0) * 0.07 * walkW;
  }
  // стоит: еле заметно переносит вес — только корпусом и головой, ступни на месте
  if (!moving && !S.sitting) { const ws = Math.sin(t * 0.23 * (0.6 + 0.4 * PERSONA.sway)) * Math.sin(t * 0.11 + 1) * PERSONA.sway; P.spineZ += ws * 0.018; P.headZ -= ws * 0.02; }

  // 1б) куда смотрит: идёт боком, стоит лицом к нам
  // ложится — разворачивается боком: лежит вдоль экрана, головой к углу, а не ногами к нам
  const layYaw = S.lay && S.lay !== 'done';
  const yaw = spring('yaw', layYaw ? LAY_YAW : S.dir * YAW, layYaw ? 1.3 : S.jump ? 2.5 : 1.0, 0.95);
  if (moving && !S.seq) {                          // на ходу иногда поглядывает в экран, а когда говорит — смотрит на тебя
    if (t > S.nextGlance) { S.glanceUntil = t + 1.2 + Math.random() * 1.3; S.nextGlance = t + 4 + Math.random() * 6; }
    if (talking || t < S.glanceUntil) { P.headY -= yaw * 0.7; P.spineY = (P.spineY || 0) - yaw * 0.15; }
  }
  const sitK = sm.sitK || 0, lieK = sm.lieK || 0;
  if (sitK > 0) {
    P = mix(P, SIT_POSE, sitK);
    wantArms = sitK > 0.15 ? 1 : wantArms;
    if (!S.seq && lieK < 0.01 && Math.sin(t * 0.37) > 0.6) P.headY += Math.sin(t * 0.9) * 0.25;   // иногда оглядывается
  }
  let roll = 0;
  if (S.lieRaw > 0 && !A.layUp) {
    const L = lieAt(S.lieRaw, P);
    P = { ...P, ...L.P };
    roll = L.roll;
  }

  // 2) эмоция в теле (пока говорит и пару секунд после)
  const emoPose = { joy: 'happy', shy: 'shy', sad: 'sad', surprise: 'surprise', think: 'think', tender: 'clasp' }[S.emo];
  if (!asleep && !S.seq && emoPose && !S.sitting) { P = mix(P, POSES[emoPose], 0.85); wantArms = 1; }
  if (S.face === 'think' && !S.sitting) { P = mix(P, POSES.think, 1); wantArms = 1; }
  if (!asleep && S.emo === 'joy') P.lift = Math.max(0, Math.sin(t * 6)) * 0.012 * PERSONA.bounce;   // подпрыгивает

  // 3) касания и перетаскивание
  if (S.dragging) { P = mix(P, POSES.drag, 1); wantArms = 1; }
  else if (S.touch && now < S.touchUntil) {
    const tt = (now - S.touchStart) / 1000;
    const w = Math.min(1, tt * 4) * Math.min(1, (S.touchUntil - now) / 400);
    if (S.touch === 'head') { P = mix(P, POSES.pat, w); P.headZ += Math.sin(tt * 5) * 0.06 * w; }
    if (S.touch === 'face') P = mix(P, POSES.poke, w);
    if (S.touch === 'body') P = mix(P, POSES.shy, w);
    if (S.touch !== 'dropped') wantArms = 1;
  }

  // 4) разовые движения из программы и при засыпании
  if (S.seqAct === 'act-yawn' && (now - S.seqActStart) / 1000 > 2.6) { S.seqAct = 'act-rub'; S.seqActStart = now; }
  if (S.seqAct === 'act-rub' && (now - S.seqActStart) / 1000 > 1.5) S.seqAct = '';
  const a = S.seqAct || S.act, at = (now - (S.seqAct ? S.seqActStart : S.actStart)) / 1000;
  if (a === 'act-wave') {
    P.rUpZ = 1.25; P.rUpY = 0; P.rLoY = 0; P.rLoZ = -2.65 + Math.sin(at * 9) * 0.25; P.headZ -= 0.08; wantArms = 1;
  } else if (a === 'act-nod') {
    P.headX += Math.max(0, Math.sin(at * 8)) * 0.18 * Math.max(0, 1 - at / 1.4);
  } else if (a === 'act-stretch') {
    const k = bell(at, 2.4);
    P.lUpZ = lerp(P.lUpZ, 1.25, k); P.rUpZ = lerp(P.rUpZ, -1.25, k); P.lLoY = lerp(P.lLoY, 0, k); P.rLoY = lerp(P.rLoY, 0, k);
    P.headX -= 0.2 * k; P.spineX -= 0.1 * k; wantArms = 1;
  } else if (a === 'act-yawn') {
    const k = bell(at, 2.5);
    P.headX -= 0.25 * k; P.rUpZ = lerp(P.rUpZ, 1.25, k); P.rUpY = lerp(P.rUpY, 0.6, k); P.rLoY = lerp(P.rLoY, 2.5, k); wantArms = 1;
  } else if (a === 'act-rub') {                     // трёт глаз: кисть у лица, голова чуть вниз
    const k = bell(at, 1.5);
    P.rUpZ = lerp(P.rUpZ, 1.0, k); P.rUpY = lerp(P.rUpY, 0.55, k); P.rLoY = lerp(P.rLoY, 2.65, k);
    P.rHandZ = lerp(P.rHandZ, Math.sin(at * 11) * 0.22, k); P.headX += 0.12 * k; P.headZ -= 0.06 * k; wantArms = 1;
  }

  // живость — только костями: дыхание в груди и плечах, лёгкая голова. Корень и ступни на месте.
  const breath = Math.sin(t * (asleep ? 1.1 : 1.6)) * 0.5 + 0.5;
  P.spineX += (asleep ? 0.04 : 0.012) * breath;
  P.chestX += (asleep ? 0.03 : 0.015) * breath;
  P.shoulder = (asleep ? 0.02 : 0.018) * breath;
  P.headZ += Math.sin(t * 0.5) * 0.015;
  P.headY += Math.sin(t * 0.31) * 0.02;
  if (talking) P.headX += Math.sin(t * 7) * 0.015;

  // взгляд за курсором
  const looking = Date.now() - S.lookT < 4000 && !asleep && !S.seq && !S.touch && !S.sitting;
  const lx = spring('lx', looking ? S.lookX : 0, 1.5, 0.8), ly = spring('ly', looking ? S.lookY : 0, 1.5, 0.8);
  P.headY += lx * 0.35; P.headX += ly * 0.18;

  // применить. Ноги и таз ведёт анимация (свои повороты — только сидя и лёжа), руки — анимация или поза,
  // корпус и голова — добавка поверх анимации.
  sm.armW = lerp(sm.armW || 0, wantArms, 1 - Math.exp(-FRAME_DT / 0.22));   // для размера холста: руки в стороны
  // руки всегда по позе (анимация рук у библиотеки «боевая»), ноги: стоит — по позе, идёт и садится — анимация
  const armW = 1;
  const clipLegs = A.walk ? A.walk.w + A.sitEnter.w + A.sitExit.w + A.sitIdle.w + A.sitTalk.w : 0;
  const legW = sitK > 0 ? sitK : clamp01(1 - clipLegs);
  // сколько верха тела отдаём жесту из библиотеки (руки на груди, кивок, жесты при разговоре)
  const gW = clamp01(A.foldArms ? A.foldArms.w + A.yes.w + A.no.w : 0);
  const fArm = 2.4, fLeg = 4, fHead = 2.0, fBody = 1.6;
  const proc = {};
  const set = (name, axis, v, f, z = 0.7) => { (proc[name] ||= { x: 0, y: 0, z: 0 })[axis] = spring(name + axis, v, f, z); };
  set('leftUpperArm', 'z', P.lUpZ, fArm, 0.7); set('rightUpperArm', 'z', P.rUpZ, fArm, 0.7);
  set('leftUpperArm', 'y', P.lUpY, fArm, 0.7); set('rightUpperArm', 'y', P.rUpY, fArm, 0.7);
  set('leftUpperArm', 'x', P.lUpX, fArm, 0.7); set('rightUpperArm', 'x', P.rUpX, fArm, 0.7);
  set('leftLowerArm', 'y', P.lLoY, fArm * 1.2, 0.7); set('rightLowerArm', 'y', P.rLoY, fArm * 1.2, 0.7);
  set('leftLowerArm', 'z', P.lLoZ, fArm * 1.2, 0.7); set('rightLowerArm', 'z', P.rLoZ, fArm * 1.2, 0.7);
  set('leftHand', 'z', P.lHandZ, 2.5, 0.6); set('rightHand', 'z', P.rHandZ, 2.5, 0.6);
  set('leftHand', 'x', P.lHandX, 2.5, 0.6); set('rightHand', 'x', P.rHandX, 2.5, 0.6);
  set('spine', 'x', P.spineX, fBody, 0.8); set('chest', 'x', P.chestX + P.spineX * 0.4, fBody, 0.8);
  set('spine', 'z', P.spineZ, fBody, 0.8); set('spine', 'y', P.spineY || 0, fBody, 0.8);
  set('leftShoulder', 'z', P.shoulder, fBody, 0.9); set('rightShoulder', 'z', -P.shoulder, fBody, 0.9);
  set('neck', 'x', P.headX * 0.4, fHead, 0.75); set('head', 'x', P.headX * 0.6, fHead, 0.7);
  set('neck', 'y', P.headY * 0.4, fHead, 0.75); set('head', 'y', P.headY * 0.6, fHead, 0.7);
  set('head', 'z', P.headZ, fHead, 0.7);
  set('leftUpperLeg', 'x', P.lLegX, fLeg, 0.9); set('rightUpperLeg', 'x', P.rLegX, fLeg, 0.9);
  set('leftLowerLeg', 'x', P.lKneeX, fLeg, 0.9); set('rightLowerLeg', 'x', P.rKneeX, fLeg, 0.9);
  set('leftFoot', 'x', P.lFootX, fLeg, 0.9); set('rightFoot', 'x', P.rFootX, fLeg, 0.9);
  proc.hips = { x: 0, y: 0, z: 0 };
  proc.upperChest ||= { x: 0, y: 0, z: 0 };
  const keep = 1 - (sm.layW || 0);                   // 0 — тело полностью из анимации «ложится/встаёт»
  for (const name in proc) {
    const b = bone(name); if (!b) continue;
    const e = proc[name];
    if (ADD_BONES.has(name)) {
      _q.setFromEuler(_e.set(e.x * keep, e.y * keep, e.z * keep));
      b.quaternion.multiply(_q);
    } else {
      _q.setFromEuler(_e.set(e.x, e.y, e.z));
      const w = (LEG_BONES.has(name) ? legW : armW * (1 - gW)) * keep;
      if (w > 0.001) b.quaternion.slerp(_q, Math.min(1, w));
    }
  }
  // улеглась — устраивается поудобнее: голова к нам, одна нога согнута в колене (поверх анимации)
  sm.holdW = lerp(sm.holdW || 0, S.lay === 'hold' ? 1 : 0, 1 - Math.exp(-FRAME_DT / 0.6));
  if (sm.holdW > 0.002) {
    const h = smooth(sm.holdW);
    for (const [name, x, y, z] of HOLD_ADD) {
      const b = bone(name); if (!b) continue;
      _q.setFromEuler(_e.set(x * h, y * h, z * h)); b.quaternion.multiply(_q);
    }
  }
  if (keep < 0.5) {                                   // лёжа во сне всё равно дышит — грудью
    const ch = bone('chest'); if (ch) { _q.setFromEuler(_e.set(0.03 * breath * (1 - keep), 0, 0)); ch.quaternion.multiply(_q); }
  }
  if (keep > 0.5 && !NO_AVOID) avoidBody();
  const hips = bone('hips');
  if (hips) {
    if (legW > 0.001 && sitK <= 0) {                 // стоит по своей позе — таз на своей высоте, даже если играет жест
      hips.position.x = lerp(hips.position.x, 0, legW * keep);
      hips.position.y = lerp(hips.position.y, sm.hipsBase, legW * keep);
      hips.position.z = lerp(hips.position.z, 0, legW * keep);
    }
    hips.position.y += spring('lift', P.lift, 3, 0.7) * keep;
    if (sitK > 0) {                                 // таз опускается на пол
      hips.position.x = lerp(hips.position.x, 0, sitK);
      hips.position.y = lerp(hips.position.y, SEAT_Y, sitK);
      hips.position.z = lerp(hips.position.z, 0, sitK);
    }
  }
  // лёжа: вся модель заваливается на бок вокруг таза, таз остаётся у пола — не «переворачивается вокруг ступней»
  vrm.scene.rotation.set(0, yaw, roll);
  const rollK = roll / (Math.PI / 2);
  vrm.scene.position.set(S.worldX || 0, 0, 0);
  if (roll > 0 && hips) {
    _hipsWorld.copy(hips.position).applyEuler(vrm.scene.rotation);
    vrm.scene.position.x = (S.worldX || 0) - _hipsWorld.x;
    vrm.scene.position.y = lerp(hips.position.y, LIE_Y, rollK) - _hipsWorld.y;
    vrm.scene.position.z = lerp(hips.position.z, 0, rollK) - _hipsWorld.z;
  }

  if (vrm.lookAt) {
    lookTarget.position.set((S.worldX || 0) + lx * 1.2, camera.position.y + ly * 0.6, camera.position.z);
    const free = !asleep && !S.seq;
    vrm.lookAt.target = free ? lookTarget : null;
    if (!free) { vrm.lookAt.yaw = 0; vrm.lookAt.pitch = 0; }    // взгляд прямо перед собой, не на курсор и не на тебя
  }
}

// ---------- руки не проходят сквозь тело ----------
// При загрузке «ощупываем» модель лучами: где перед и бока туловища на разной высоте.
let BODY = null;
function measureBody() {
  // Туловище от бёдер до плеч: срезы относительно кости позвоночника (а не мира) — тогда проверка работает,
  // когда она идёт по экрану, поворачивается, наклоняется, сидит и лежит.
  vrm.scene.updateMatrixWorld(true);
  const meshes = []; vrm.scene.traverse((o) => { if (o.isMesh) meshes.push(o); });
  const rc = new THREE.Raycaster();
  const spine = bone('spine');
  const P = (n) => bone(n).getWorldPosition(new THREE.Vector3());
  const hipsY = P('hips').y - 0.12, shY = P('leftUpperArm').y;
  const hipHalf = Math.abs(P('leftUpperLeg').x) + 0.07, chestHalf = Math.abs(P('leftUpperArm').x) - 0.03;
  const ys = [], front = [], back = [], half = [];
  const hit = (o, d) => { rc.set(o, d); rc.far = 4; const h = rc.intersectObjects(meshes, false); return h.length ? h[0].point : null; };
  const toLocal = (v) => spine.worldToLocal(v.clone());
  for (let y = hipsY; y <= shY - 0.03; y += 0.03) {
    let f = -1, b = 1;
    for (const x of [-0.09, -0.04, 0, 0.04, 0.09]) {
      const pf = hit(new THREE.Vector3(x, y, 2), new THREE.Vector3(0, 0, -1)); if (pf) f = Math.max(f, pf.z);
      const pb = hit(new THREE.Vector3(x, y, -2), new THREE.Vector3(0, 0, 1)); if (pb) b = Math.min(b, pb.z);
    }
    if (f < -0.9) continue;
    const u = clamp01((y - hipsY) / (shY - hipsY));
    const l = toLocal(new THREE.Vector3(0, y, 0));
    ys.push(l.y); front.push(Math.min(f, 0.28) - l.z); back.push(Math.max(b, -0.28) - l.z); half.push(lerp(hipHalf, chestHalf, u));
  }
  BODY = ys.length > 1 ? { ys, front, back, half } : null;
}
function bodyAt(y) {
  const B = BODY; if (!B || y < B.ys[0] || y > B.ys[B.ys.length - 1]) return null;
  let i = 0; while (i < B.ys.length - 2 && B.ys[i + 1] < y) i++;
  const u = (y - B.ys[i]) / (B.ys[i + 1] - B.ys[i] || 1);
  return { f: lerp(B.front[i], B.front[i + 1], u), b: lerp(B.back[i], B.back[i + 1], u), h: lerp(B.half[i], B.half[i + 1], u) };
}
// насколько точка (в координатах позвоночника) залезла в тело: 0 — снаружи; и где — спереди или сбоку
function intoBody(p, margin) {
  const b = bodyAt(p.y); if (!b) return null;
  const ox = b.h + margin - Math.abs(p.x), of = b.f + margin - p.z, ob = p.z - (b.b - margin);
  if (ox <= 0 || of <= 0 || ob <= 0) return null;
  return { depth: Math.min(ox, of, ob), side: ox < of };          // side — ближе выйти вбок, иначе — вперёд
}
const _v = new THREE.Vector3(), _w = new THREE.Vector3(), _m = new THREE.Vector3();
function avoidBody() {
  if (!BODY) return;
  const spine = bone('spine'); if (!spine) return;
  spine.updateWorldMatrix(true, false);
  for (const side of ['left', 'right']) {
    const up = bone(side + 'UpperArm'), lo = bone(side + 'LowerArm'), hand = bone(side + 'Hand');
    if (!up || !lo || !hand) continue;
    const kF = 'pushF_' + side, kS = 'pushS_' + side, out = side === 'left' ? 1 : -1;
    // вперёд — поворот плеча вокруг X, в сторону — вокруг Z (от тела); применяются последними
    up.rotation.x -= (sm[kF] || 0);
    up.rotation.z += out * (sm[kS] || 0);
    hand.updateWorldMatrix(true, false);
    const pts = [hand.getWorldPosition(_v), lo.getWorldPosition(_w)];
    pts.push(_m.copy(pts[0]).add(pts[1]).multiplyScalar(0.5));
    let hitF = 0, hitS = 0, near = false;
    for (const pw of pts) {
      const pl = spine.worldToLocal(pw.clone());
      const r = intoBody(pl, 0.02);
      if (r) { if (r.side) hitS = Math.max(hitS, r.depth); else hitF = Math.max(hitF, r.depth); }
      else if (intoBody(pl, 0.05)) near = true;
    }
    let f = sm[kF] || 0, sd = sm[kS] || 0;
    const up_ = (d) => Math.min(0.8, d * 6 + 2.4 * FRAME_DT);
    if (hitF) f = Math.min(0.8, f + up_(hitF) * FRAME_DT * 10);
    if (hitS) sd = Math.min(0.6, sd + up_(hitS) * FRAME_DT * 10);
    if (!hitF && !near) f = Math.max(0, f - 0.7 * FRAME_DT);        // свободно — медленно возвращаем
    if (!hitS && !near) sd = Math.max(0, sd - 0.7 * FRAME_DT);
    if (INSTANT && (hitF || hitS)) { f = Math.min(0.8, f + 0.3); sd = Math.min(0.6, sd + 0.2); }
    // сразу применяем новое значение в этом же кадре — рука не успевает «мелькнуть» внутри
    up.rotation.x -= f - (sm[kF] || 0);
    up.rotation.z += out * (sd - (sm[kS] || 0));
    sm[kF] = f; sm[kS] = sd;
  }
}

let nextBlink = 0, blinkT = -1;
function face(t) {
  const em = vrm.expressionManager; if (!em) return;
  const asleep = isAsleep();
  const closing = S.seq === 'closing', drowsy = S.seq === 'drowsy';
  const now = performance.now();
  let want = asleep || closing ? { relaxed: 0.4 } : drowsy ? { relaxed: 0.3 } : { ...(EMO[S.emo] || {}) };
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
  else if (closing) blink = 0.18 + 0.82 * smooth(S.seqT / 2.6);    // закрываются постепенно, уже лёжа
  else {
    if (t > nextBlink && blinkT < 0) { blinkT = t; nextBlink = t + (drowsy ? 1.6 : 2.5) + Math.random() * 3.5; }
    if (blinkT >= 0) { const p = (t - blinkT) / (drowsy ? 0.34 : 0.16); blink = p < 1 ? Math.sin(p * Math.PI) : 0; if (p >= 1) blinkT = -1; }
    if (drowsy) blink = Math.max(blink, 0.18);       // веки чуть тяжелее
  }
  em.setValue('blink', closing ? (sm.blink = blink) : ease('blink', blink, asleep ? 0.08 : 0.6));
  const talking = Date.now() - S.lipT < 350;
  const m = talking ? S.mouth : 0;
  const act = S.seqAct || S.act;
  const yawn = act === 'act-yawn' ? bell((now - (S.seqAct ? S.seqActStart : S.actStart)) / 1000, 2.5) : 0;
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
  // пикселей в метре — по самой камере, а не по высоте холста (холст обрезается по фигуре)
  const q = new THREE.Vector3(); bone('head').getWorldPosition(q); q.y += 0.1; q.project(camera);
  const ppm = Math.max(50, Math.abs((-q.y * 0.5 + 0.5) * r.height - hy) * 10);
  const dx = (x - r.left - hx) / ppm, dy = -(y - r.top - hy) / ppm;     // метры от кости головы, вверх — плюс
  // кость головы у VRoid — на уровне шеи: лицо от неё до бровей, выше — волосы и макушка
  if (Math.abs(dx) < 0.16 && dy > 0.15 && dy < 0.5) return 'head';      // гладим
  if (Math.abs(dx) < 0.11 && dy >= -0.04 && dy <= 0.15) return 'face';
  if (dy < -0.12 && dy > -0.95 && Math.abs(dx) < 0.28) return 'body';
  return '';
}

function touch(zone, ms) {
  const now = performance.now();
  if (S.touch !== zone || now > S.touchUntil) S.touchStart = now;
  S.touch = zone; S.touchUntil = now + ms;
  if (window.pywebview && window.pywebview.api && window.pywebview.api.touch) window.pywebview.api.touch(zone);
}

function setupTouch() {
  let down = null, moved = false, patTimer = null, lastX = 0, lastY = 0;
  canvas.addEventListener('mousedown', (e) => {
    down = { x: e.screenX, y: e.screenY, zone: zoneAt(e.clientX, e.clientY), t: performance.now() };
    moved = false; lastX = e.screenX; lastY = e.screenY;
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
      if (!S.dragging) {
        S.dragging = true;                                                              // тащат её
        S.goal = null; S.dir = 0; S.v = 0;
        pyCall('moved');
      }
      if (S.stage) {                                  // едет за мышкой; в мире — тоже, чтобы волосы отставали
        const dx = e.screenX - lastX, dy = e.screenY - lastY;
        S.x = Math.max(0, Math.min(S.W, S.x + dx));
        S.y = Math.max(0, Math.min(S.H - 80, S.y - dy));
        S.worldX += dx / PX_PER_M;
        placeStage();
      }
    }
    lastX = e.screenX; lastY = e.screenY;
  });
  window.addEventListener('mouseup', () => {
    if (!down) return;
    clearTimeout(patTimer);
    if (S.dragging) { S.dragging = false; touch('dropped', 10); }
    else if (!moved && down.zone && performance.now() - down.t < 350) touch(down.zone, down.zone === 'head' ? 2200 : 1600);
    down = null;
  });
}

// ---------- физика одежды и тела (spring bones) ----------
function tunePhysics() {
  const mgr = vrm.springBoneManager; if (!mgr) return;
  const raw = (n) => vrm.humanoid.getRawBoneNode(n);
  // коллайдеры-капсулы на ноги и таз: юбка и пальто не проходят сквозь тело
  const groups = [];
  const capsule = (boneName, childName, radius) => {
    const b = raw(boneName), c = raw(childName); if (!b || !c) return null;
    const shape = new VRMSpringBoneColliderShapeCapsule({ radius, offset: new THREE.Vector3(0, 0, 0),
                                                           tail: c.position.clone() });
    const col = new VRMSpringBoneCollider(shape); b.add(col); return col;
  };
  const legs = [capsule('leftUpperLeg', 'leftLowerLeg', 0.085), capsule('rightUpperLeg', 'rightLowerLeg', 0.085),
                capsule('leftLowerLeg', 'leftFoot', 0.06), capsule('rightLowerLeg', 'rightFoot', 0.06),
                capsule('hips', 'spine', 0.13)].filter(Boolean);
  const legGroup = { name: 'podruga-legs', colliders: legs };
  let n = { bust: 0, skirt: 0, coat: 0 };
  for (const j of mgr.joints) {
    const name = (j.bone && j.bone.name) || '';
    const st = j.settings;
    if (/Bust/i.test(name)) {
      // грудь: мягко, но без «желе» — быстро успокаивается
      st.stiffness = 1.0; st.dragForce = 0.32; st.gravityPower = 0.03; st.gravityDir = new THREE.Vector3(0, -1, 0);
      n.bust++;
    } else if (/Skirt/i.test(name) && !/Coat/i.test(name)) {
      st.stiffness = 0.6; st.dragForce = 0.28; st.gravityPower = 0.15;
      st.gravityDir = new THREE.Vector3(0, -1, 0);
      if (!j.colliderGroups.includes(legGroup)) j.colliderGroups.push(legGroup);
      n.skirt++;
    } else if (/Coat/i.test(name)) {
      // полы пальто: держат форму, отстают при ходьбе, не проходят сквозь ноги
      st.stiffness = 0.65; st.dragForce = 0.28; st.gravityPower = 0.18;
      st.gravityDir = new THREE.Vector3(0, -1, 0); st.hitRadius = Math.max(st.hitRadius, 0.03);
      if (!j.colliderGroups.includes(legGroup)) j.colliderGroups.push(legGroup);
      n.coat++;
    }
  }
  mgr.reset && mgr.reset();
  console.log('[3D] физика:', JSON.stringify(n), 'коллайдеров ног:', legs.length);
}

function measureBounds() {
  // реальные размеры по костям: рост (с поднятыми руками), размах рук, длина лёжа
  const P = (n) => bone(n).getWorldPosition(new THREE.Vector3());
  const sh = P('leftUpperArm'), hand = P('leftHand'), lo = P('leftLowerArm');
  const arm = sh.distanceTo(lo) + lo.distanceTo(hand) + 0.2;            // + кисть с пальцами
  const reach = Math.abs(sh.x) + arm;                                    // от центра до кончиков пальцев
  const top = Math.max((sm.headY || 1.6) + 0.12, sh.y + arm * 0.95);     // руки вверх (потягивается)
  const margin = 0.12;                                                   // волосы, рукава, пружинки
  const w = Math.ceil((reach * 2 * 0.75 + margin * 2) * PX_PER_M);       // руки в стороны не выше ~40° к горизонту
  const h = Math.ceil((top + margin) * PX_PER_M);
  const lieW = Math.ceil(((sm.headY || 1.6) + 0.4 + margin * 2) * PX_PER_M);
  const lieH = Math.ceil(0.8 * PX_PER_M);
  console.log('[3D] размеры окна по модели:', w, h, 'лёжа', lieW, lieH);
  return { w, h, lieW, lieH, reach, top };
}

// ---------- цикл ----------
let last = 0;
let lastBox = '', boxT = 0, FROZEN = false, SIM_T = 0;
function wantFps() {
  if (document.hidden) return 0;                          // окно спрятано — не рисуем
  const nowMs = Date.now();
  const going = S.goal || S.v > 0 || S.dragging || S.jump || (sm.sitK > 0 && sm.sitK < 1) || (sm.edgeK > 0 && sm.edgeK < 1) || (S.lieRaw > 0 && S.lieRaw < 1) ||
                (S.posture === 'lie' && S.lieRaw < 1) || S.seqAct;
  if (going) return 60;
  if (S.seq === 'closing') return 30;
  const active = S.touch || nowMs - S.lipT < 1500 || nowMs - S.lookT < 1500;
  if (isAsleep()) return active ? 30 : 12;                 // спит — только дыхание
  return active ? 60 : 30;                                 // просто стоит — 30 кадров хватает
}
function reportBox() {
  // прямоугольник, где она нарисована (по костям + запас) — Python делает остальное окно «прозрачным для мышки»
  const r = canvas.getBoundingClientRect();
  let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
  const v = new THREE.Vector3();
  for (const n of ['head', 'neck', 'leftHand', 'rightHand', 'leftLowerArm', 'rightLowerArm', 'leftFoot', 'rightFoot',
                   'hips', 'leftLowerLeg', 'rightLowerLeg', 'upperChest']) {
    const b = bone(n); if (!b) continue;
    b.getWorldPosition(v); v.project(camera);
    const x = (v.x * 0.5 + 0.5) * r.width, y = (-v.y * 0.5 + 0.5) * r.height;
    x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y);
  }
  const pad = 0.16 * PX_PER_M;                              // голова, волосы, рукава вокруг костей
  // с шагом 6 пикселей: дыхание и мелкие движения не гоняют лишние вызовы в Python
  const box = [Math.max(0, x0 - pad), Math.max(0, y0 - pad * 1.75), Math.min(r.width, x1 + pad), Math.min(r.height, y1 + pad * 0.4)]
    .map((a) => Math.round(a / 6) * 6);
  const key = box.join(',') + (S.stage ? ',' + Math.round(S.x / 6) + ',' + Math.round(S.y / 6) : '');
  if (key !== lastBox && window.pywebview && window.pywebview.api && window.pywebview.api.hitbox) {
    lastBox = key;
    window.pywebview.api.hitbox(box[0] + r.left, box[1] + r.top, box[2] + r.left, box[3] + r.top,
                                S.stage ? S.x : null, S.stage ? S.y : null, S.btnX ?? null, S.btnY ?? null);
  }
}
function tick(dt, t) {
  FRAME_DT = dt;
  if (S.stage) stageMove(dt);
  updatePosture(dt);
  mixerStep(dt);
  pose(t); face(t);
  placeCamera();
  vrm.update(dt);
}
function loop(now) {
  if (FROZEN) { requestAnimationFrame(loop); return; }
  const fps = wantFps();
  // ниже 60 кадров страницу незачем будить 60 раз в секунду: каждое пробуждение стоит процессора и окна
  if (fps >= 60) requestAnimationFrame(loop);
  else setTimeout(() => requestAnimationFrame(loop), fps ? Math.max(0, 1000 / fps - 9) : 400);
  // запас 3 мс: время в WebKit округлено, иначе кадр 15–16 мс считался «слишком ранним» и пропадал через один
  if (!fps || (fps >= 60 && now - last < 1000 / fps - 3)) return;
  last = now;
  const dt = Math.min(0.1, clock.getDelta()), t = clock.elapsedTime;
  if (vrm) {
    if (!S.stage) {
      const mini = document.body.classList.contains('mini');
      const fk = sm.fullK || 0, want = (mini || S.full) ? 1 : 0;
      if (Math.abs(fk - want) > 0.002) { sm.fullK = lerp(fk, want, 1 - Math.pow(0.04, dt)); fitCamera(VIEW.w, VIEW.h); }
    }
    tick(dt || 1 / 60, t);
    if (now - boxT > (S.goal || S.dragging ? 100 : 250)) { boxT = now; reportBox(); }
  }
  renderer.render(scene, camera);
}

async function init(url) {
  host = document.getElementById('char');
  canvas = document.createElement('canvas');
  canvas.id = 'vrmCanvas';
  // сглаживание выключено: на Retina (2 пикселя на точку) разницы почти нет, а видеокарта считает вчетверо больше
  renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: (window.devicePixelRatio || 1) < 1.5, powerPreference: 'low-power' });
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
  sm.hipsBase = bone('hips').position.y;
  try { tunePhysics(); } catch (e) { console.warn('[3D] физика не настроилась', e); }
  BOUNDS = measureBounds();
  buildAnims();

  host.appendChild(canvas);
  document.body.classList.add('has3d');
  resize();
  new ResizeObserver(() => { if (!S.stage) resize(); }).observe(host);
  setupTouch();
  requestAnimationFrame(loop);
  if (window.pywebview && window.pywebview.api && window.pywebview.api.fit) {
    window.pywebview.api.fit(BOUNDS.w, BOUNDS.h, BOUNDS.lieW, BOUNDS.lieH);
  }
  return true;
}

window.VRM3D = {
  ready: false,
  async start(url) {
    try { await init(url); if (window.PERSONA) setPersona(window.PERSONA); this.ready = true; console.log('[3D] модель загружена'); return true; }
    catch (e) { console.error('[3D] не загрузилась', e); return false; }
  },
  state(face, emo, act) {
    if (act !== S.act && act) S.actStart = performance.now();
    S.face = face; S.emo = emo || 'calm'; S.act = act || '';
  },
  look(dx, dy) { S.lookX = dx; S.lookY = dy; S.lookT = Date.now(); },
  mouth(v, shape) { S.mouth = v; S.lipT = Date.now(); if (shape) S.shape = shape; },
  stage(on, W, H, x, y) { if (on) stageOn(W, H, x, y); else stageOff(); },
  ground(a, b, h) { S.dock = a == null ? null : [a, b, h]; },
  walkTo(x) {
    if (!S.stage || S.jump) return;
    const l = S.support != null ? ledgeById(S.support) : null;
    if (l) x = Math.max(l[1] + 60, Math.min(l[2] - 60, x));
    S.goal = { x };
  },
  ledges(list) {                                      // [[id, x0, x1, y], …] — верхние края окон, пиксели окна
    const old = S.support != null ? ledgeById(S.support) : null;
    S.ledges = list || [];
    if (S.support == null || S.jump) return;
    const l = ledgeById(S.support);
    if (!l) return fallDown();
    if (old) { const dx = l[1] - old[1]; S.x += dx; S.worldX += dx / PX_PER_M; }   // окно сдвинули — едет вместе с ним
    S.y = l[3];
    if (S.x < l[1] - 20 || S.x > l[2] + 20) fallDown();
  },
  jumpTo(x, y, id) { if (S.stage && !S.sitting && !S.lay) startJump(x, y, id == null ? null : id); },
  support() { return S.support; },
  walkStop() {                                     // плавно дойти до ближайшей точки, где успеет остановиться
    if (S.goal) S.goal = { x: S.x + S.dir * (S.v * S.v) / (2 * ACCEL) };
  },
  sit(on) { if (on) S.posture = 'sit'; else if (S.posture === 'sit' || S.posture === 'edge') S.posture = 'stand'; },
  sitEdge(on) { if (on && S.support != null) S.posture = 'edge'; else if (S.posture === 'edge') S.posture = 'stand'; },
  lie(on) { S.posture = on ? 'lie' : (S.posture === 'lie' ? 'stand' : S.posture); },
  // засыпание по шагам: drowsy → yawn → (идёт) → down (садится, ложится, закрывает глаза); cancel — проснулась
  sleepSeq(kind) {
    if (kind === 'drowsy') S.seq = 'drowsy';
    else if (kind === 'yawn') { S.seq = 'drowsy'; S.seqAct = 'act-yawn'; S.seqActStart = performance.now(); }
    else if (kind === 'down') { S.seq = 'drowsy'; S.posture = 'lie'; S.sleepAfterLie = true; }
    else if (kind === 'cancel') { S.seq = ''; S.seqAct = ''; S.sleepAfterLie = false; S.posture = 'stand'; }
  },
  pos() { return { x: S.x, y: S.y, posture: S.posture, seq: S.seq, sitK: sm.sitK, lieK: sm.lieK, v: S.v, goal: S.goal, support: S.support, jump: !!S.jump, edgeK: sm.edgeK }; },
  gesture(name, sec) { startGesture(name, sec); },
  idle(name, sec) { if (POSES[name] || name === 'look' || name === 'sway' || name === 'rest' || name === 'foldArms') { S.idle = name; S.idleUntil = (S.t || 0) + (sec || 4); } },
  full(on) { S.full = !!on; },
  persona(m) { setPersona(m); },
  _zone(x, y) { return zoneAt(x, y); },
  _body() { return BODY; },
  // для проверки: остановить живой цикл и прокрутить время вручную (ровными шагами)
  _freeze(on) { FROZEN = on; },
  _noAvoid(on) { NO_AVOID = !!on; },
  // сколько точек рук (кисть, локоть, середина предплечья) сейчас внутри тела — для проверки
  _armHits() {
    const spine = bone('spine'); if (!spine || !BODY) return -1; spine.updateWorldMatrix(true, false);
    let n = 0;
    for (const sd of ['left', 'right']) {
      const h = bone(sd + 'Hand').getWorldPosition(new THREE.Vector3()), l = bone(sd + 'LowerArm').getWorldPosition(new THREE.Vector3());
      for (const p of [h, l, h.clone().add(l).multiplyScalar(0.5)]) if (intoBody(spine.worldToLocal(p.clone()), 0)) n++;
    }
    return n;
  },
  _step(n = 1, dt = 1 / 60) {
    for (let i = 0; i < n; i++) { SIM_T += dt; tick(dt, SIM_T); }
    renderer.render(scene, camera);
  },
  // положения костей в мире — для проверок
  _w() {
    const o = {}, v = new THREE.Vector3();
    for (const n of ['leftFoot', 'rightFoot', 'leftToes', 'rightToes', 'hips', 'head']) { const b = bone(n); if (b) { b.getWorldPosition(v); o[n] = [v.x, v.y, v.z]; } }
    o.blink = +(sm.blink || 0).toFixed(3); o.worldX = S.worldX; o.x = S.x; o.v = S.v; o.yaw = +(sm.yaw || 0).toFixed(3);
    o.sitK = sm.sitK; o.lieK = sm.lieK; o.seq = S.seq; o.rate = A.walk ? +A.walk.action.timeScale.toFixed(3) : 0;
    return o;
  },
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
    S.dragging = !!opts.drag; S.full = true; sm.fullK = 1; if (camera) fitCamera(VIEW.w, VIEW.h);
  },
};
