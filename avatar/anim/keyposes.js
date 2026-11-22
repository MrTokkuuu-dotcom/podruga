// Ключевые позы и переходы, где важно, где стоят ступни и ладони: сидит боком (ноги вместе), садится, встаёт.
// Ноги и опорные руки ставятся IK (ik.js): задаём таз, точки ступней/ладоней и куда смотрят колени/локти.
// Координаты — пространство модели для «эталонного» тела (нога 0,8 м); под конкретную модель масштабируются.
// side = +1: ноги уложены влево от неё (+X), опора на правую руку; side = -1 — зеркально.
import * as THREE from 'three';
import { createChain, solve, modelPos, endQuat, resetChain } from './ik.js';

const REF_LEG = 0.8;
const smooth = (x) => { x = Math.max(0, Math.min(1, x)); return x * x * (3 - 2 * x); };
const lerp = (a, b, k) => a + (b - a) * k;
const lerp3 = (a, b, k) => [lerp(a[0], b[0], k), lerp(a[1], b[1], k), lerp(a[2], b[2], k)];

// Ключ: hp — таз [x,y,z], hr — поворот таза [x,y,z] (рад), L/R — ступни { f: точка, n: куда колено },
// hl/hr2 — ладони { f, n, w } (w — вес IK руки, 0 — руки по обычной позе), P — добавки к позе корпуса и головы.
// Значения — для side = +1. 'cap' — взять то, что было в начале перехода.
export const SIDE_SIT_KEYS = [
  { k: 0, hp: 'cap', hr: 'cap', L: 'cap', R: 'cap', hl: { w: 0 }, hrt: { w: 0 }, P: {} },
  // подготовка: сначала ладони ложатся на подол спереди
  { k: 0.12, hp: { d: [0, 0, 0] }, hr: [0.02, 0, 0], L: 'cap', R: 'cap',
    hl: { f: [0.03, 0.6, 0.11], n: [0.6, -0.2, -1], w: 1 }, hrt: { f: [-0.03, 0.6, 0.11], n: [-0.6, -0.2, -1], w: 1 },
    P: { spineX: 0.08, headX: -0.06 } },
  // присела, колени вместе и чуть влево, ладони держат подол
  { k: 0.32, hp: [-0.01, 0.58, -0.07], hr: [0.18, 0.12, 0], L: { f: 'standIn', n: [-0.1, 0, 1] }, R: { f: 'standIn', n: [0.35, 0, 1] },
    hl: { f: [0.025, 0.43, 0.13], n: [0.6, -0.2, -1], w: 1 }, hrt: { f: [-0.025, 0.43, 0.13], n: [-0.6, -0.2, -1], w: 1 },
    P: { spineX: 0.3, headX: -0.15, spineY: -0.08 } },
  // опускается боком: таз вправо и вниз, колени влево, правая рука тянется к полу, левая держит подол
  { k: 0.56, hp: [-0.05, 0.33, -0.08], hr: [0.05, 0.28, 0.08], L: { f: [0.14, 0.05, -0.12], n: [0.35, -0.2, 1] }, R: { f: [0.04, 0.05, -0.08], n: [0.6, -0.2, 1] },
    hl: { f: [0.03, 0.27, 0.15], n: [0.6, 0, -1], w: 1 }, hrt: { f: [-0.26, 0.06, 0.06], n: [-1, 0.2, -0.8], w: 1 },
    P: { spineX: 0.2, headX: -0.1, spineZ: 0.06, spineY: -0.2 } },
  // таз на полу, ноги укладываются влево
  { k: 0.76, hp: [-0.06, 0.18, -0.05], hr: [-0.06, 0.4, 0.13], L: { f: [0.3, 0.05, -0.15], n: [0.4, -0.3, 1] }, R: { f: [0.2, 0.05, -0.07], n: [0.5, -0.3, 1] },
    hl: { f: [0.02, 0.17, 0.18], n: [0.6, 0.2, -1], w: 1 }, hrt: { f: [-0.31, 0.02, 0.0], n: [-1, 0.2, -0.8], w: 1 },
    P: { spineX: 0.08, spineZ: 0.11, spineY: -0.3, headZ: -0.07 } },
  // «доседает» чуть ниже итога
  { k: 0.88, hp: [-0.06, 0.125, -0.03], hr: [-0.04, 0.52, 0.17], L: { f: [0.37, 0.05, -0.14], n: [0.35, -0.3, 1] }, R: { f: [0.27, 0.06, -0.04], n: [0.45, -0.3, 1] },
    hl: { f: [0.015, 0.145, 0.17], n: [0.7, 0.3, -1], w: 1 }, hrt: { f: [-0.32, 0.01, -0.03], n: [-1, 0.2, -0.8], w: 1 },
    P: { spineX: 0.02, spineZ: 0.13, spineY: -0.34, headZ: -0.09, headX: -0.03 } },
  { k: 1, hp: [-0.06, 0.14, -0.03], hr: [-0.04, 0.5, 0.15], L: { f: [0.37, 0.05, -0.14], n: [0.35, -0.3, 1] }, R: { f: [0.27, 0.06, -0.04], n: [0.45, -0.3, 1] },
    hl: { f: [0.015, 0.15, 0.17], n: [0.7, 0.3, -1], w: 1 }, hrt: { f: [-0.32, 0.01, -0.03], n: [-1, 0.2, -0.8], w: 1 },
    P: { spineX: 0.02, spineZ: 0.11, spineY: -0.33, headZ: -0.1, headX: -0.04 } },
];
export const SIDE_SIT_POSE = SIDE_SIT_KEYS[SIDE_SIT_KEYS.length - 1];

export const SIDE_SIT_EXIT_KEYS = [
  { k: 0, hp: 'cap', hr: 'cap', L: 'cap', R: 'cap', hl: 'cap', hrt: 'cap', P: 'cap' },
  // оттолкнулась правой рукой, таз поднимается, колени ещё влево
  { k: 0.35, hp: [-0.05, 0.33, -0.08], hr: [0.05, 0.28, 0.08], L: { f: [0.14, 0.05, -0.12], n: [0.35, -0.2, 1] }, R: { f: [0.04, 0.05, -0.08], n: [0.6, -0.2, 1] },
    hl: { f: [0.03, 0.28, 0.2], n: [0.6, 0, -1], w: 1 }, hrt: { f: [-0.24, 0.07, 0.06], n: [-1, 0.2, -0.8], w: 1 },
    P: { spineX: 0.22, headX: -0.08, spineZ: 0.06, spineY: -0.2 } },
  // присела, колени вместе, ладони у подола
  { k: 0.65, hp: [-0.01, 0.58, -0.07], hr: [0.18, 0.12, 0], L: { f: 'standIn', n: [-0.1, 0, 1] }, R: { f: 'standIn', n: [0.35, 0, 1] },
    hl: { f: [0.025, 0.43, 0.13], n: [0.6, -0.2, -1], w: 1 }, hrt: { f: [-0.025, 0.43, 0.13], n: [-0.6, -0.2, -1], w: 1 },
    P: { spineX: 0.26, headX: -0.1, spineY: -0.08 } },
  { k: 1, hp: 'stand', hr: [0, 0, 0], L: { f: 'stand', n: [0, 0, 1] }, R: { f: 'stand', n: [0, 0, 1] }, hl: { w: 0 }, hrt: { w: 0 }, P: {} },
];

// На краю окна: y — от края (край = 0). Колени вместе, щиколотки скрещены, ладони на краю по бокам.
export const EDGE_SIT_KEYS = [
  { k: 0, hp: 'cap', hr: 'cap', L: 'cap', R: 'cap', hl: { w: 0 }, hrt: { w: 0 }, P: {} },
  { k: 0.15, hp: { d: [0, 0, 0] }, hr: [0.02, 0, 0], L: 'cap', R: 'cap',
    hl: { f: [0.03, 0.6, 0.11], n: [0.6, -0.2, -1], w: 1 }, hrt: { f: [-0.03, 0.6, 0.11], n: [-0.6, -0.2, -1], w: 1 },
    P: { spineX: 0.08, headX: -0.06 } },
  // присела над краем, колени вместе
  { k: 0.45, hp: [0, 0.5, -0.06], hr: [0.2, 0, 0], L: { f: 'standIn', n: [-0.3, 0, 1] }, R: { f: 'standIn', n: [0.3, 0, 1] },
    hl: { f: [0.025, 0.4, 0.13], n: [0.6, -0.2, -1], w: 1 }, hrt: { f: [-0.025, 0.4, 0.13], n: [-0.6, -0.2, -1], w: 1 },
    P: { spineX: 0.25, headX: -0.12 } },
  // садится на край, ноги уходят вперёд и вниз, ладони — на край по бокам
  { k: 0.72, hp: [0, 0.13, -0.01], hr: [0.02, 0, 0], L: { f: [0.02, -0.18, 0.24], n: [-0.25, 0.2, 1] }, R: { f: [-0.02, -0.18, 0.24], n: [0.25, 0.2, 1] },
    hl: { f: [0.17, 0.01, 0.0], n: [1, 0.2, -0.6], w: 1 }, hrt: { f: [-0.17, 0.01, 0.0], n: [-1, 0.2, -0.6], w: 1 },
    P: { spineX: 0.12, headX: -0.06 } },
  { k: 0.88, hp: [0, 0.055, 0.02], hr: [-0.12, 0, 0], L: { f: [-0.01, -0.4, 0.3], n: [-0.25, 0.3, 1] }, R: { f: [0.03, -0.42, 0.26], n: [0.25, 0.3, 1] },
    hl: { f: [0.19, 0.005, 0.0], n: [1, 0.2, -0.6], w: 1 }, hrt: { f: [-0.19, 0.005, 0.0], n: [-1, 0.2, -0.6], w: 1 },
    P: { spineX: 0.06, headX: -0.04 } },
  { k: 1, hp: [0, 0.07, 0.02], hr: [-0.1, 0, 0], L: { f: [-0.01, -0.4, 0.3], n: [-0.25, 0.3, 1] }, R: { f: [0.03, -0.42, 0.26], n: [0.25, 0.3, 1] },
    hl: { f: [0.19, 0.005, 0.0], n: [1, 0.2, -0.6], w: 1 }, hrt: { f: [-0.19, 0.005, 0.0], n: [-1, 0.2, -0.6], w: 1 },
    P: { spineX: 0.05, headX: -0.05 } },
];
export const EDGE_SIT_EXIT_KEYS = [
  { k: 0, hp: 'cap', hr: 'cap', L: 'cap', R: 'cap', hl: 'cap', hrt: 'cap', P: 'cap' },
  // оттолкнулась ладонями, ноги обратно на край
  { k: 0.35, hp: [0, 0.42, -0.06], hr: [0.22, 0, 0], L: { f: 'standIn', n: [-0.3, 0, 1] }, R: { f: 'standIn', n: [0.3, 0, 1] },
    hl: { f: [0.025, 0.36, 0.13], n: [0.6, -0.2, -1], w: 1 }, hrt: { f: [-0.025, 0.36, 0.13], n: [-0.6, -0.2, -1], w: 1 },
    P: { spineX: 0.25, headX: -0.1 } },
  { k: 0.7, hp: [0, 0.62, -0.04], hr: [0.12, 0, 0], L: { f: 'standIn', n: [-0.2, 0, 1] }, R: { f: 'standIn', n: [0.2, 0, 1] },
    hl: { f: [0.03, 0.52, 0.12], n: [0.6, -0.2, -1], w: 1 }, hrt: { f: [-0.03, 0.52, 0.12], n: [-0.6, -0.2, -1], w: 1 },
    P: { spineX: 0.12, headX: -0.05 } },
  { k: 1, hp: 'stand', hr: [0, 0, 0], L: { f: 'stand', n: [0, 0, 1] }, R: { f: 'stand', n: [0, 0, 1] }, hl: { w: 0 }, hrt: { w: 0 }, P: {} },
];
const KEYS = { enter: SIDE_SIT_KEYS, exit: SIDE_SIT_EXIT_KEYS, edgeEnter: EDGE_SIT_KEYS, edgeExit: EDGE_SIT_EXIT_KEYS };

const MIRROR_P = { spineZ: -1, spineY: -1, headZ: -1, headY: -1 };

export function createSitLayer(bone, scene, hipsBase) {
  const legL = createChain(bone, scene, 'leftUpperLeg', 'leftLowerLeg', 'leftFoot', new THREE.Vector3(0, 0, 1), 'leftToes');
  const legR = createChain(bone, scene, 'rightUpperLeg', 'rightLowerLeg', 'rightFoot', new THREE.Vector3(0, 0, 1), 'rightToes');
  const armL = createChain(bone, scene, 'leftUpperArm', 'leftLowerArm', 'leftHand', new THREE.Vector3(0, 0, -1), 'leftMiddleProximal');
  const armR = createChain(bone, scene, 'rightUpperArm', 'rightLowerArm', 'rightHand', new THREE.Vector3(0, 0, -1), 'rightMiddleProximal');
  if (!legL || !legR) return null;
  const s = (legL.L1 + legL.L2) / REF_LEG;                       // масштаб под рост модели
  // где стоят ступни в её обычной позе (покой: ноги прямые) — в пространстве модели
  const hipL = bone('leftUpperLeg').position, hipR = bone('rightUpperLeg').position;
  const footY = bone('leftFoot').getWorldPosition(new THREE.Vector3()).y - scene.getWorldPosition(new THREE.Vector3()).y;
  const stand = { L: [hipL.x, Math.max(0.03, footY), hipL.z + 0.02], R: [hipR.x, Math.max(0.03, footY), hipR.z + 0.02] };
  let cap = null, side = 1;

  const sc = (v) => [v[0] * s * side, v[1] * s, v[2] * s];
  const scDir = (v) => [v[0] * side, v[1], v[2]];
  const rot = (r) => [r[0], r[1] * side, r[2] * side];

  function capture(prevP, yOff) {
    const hips = bone('hips');
    const e = new THREE.Euler().setFromQuaternion(hips.quaternion);
    const p = (n) => { const v = modelPos(bone(n), scene, new THREE.Vector3()); return [v.x, v.y - yOff, v.z]; };
    cap = { hp: [hips.position.x, hips.position.y - yOff, hips.position.z], hr: [e.x, e.y, e.z],
            L: { f: p('leftFoot'), n: [0, 0, 1] }, R: { f: p('rightFoot'), n: [0, 0, 1] },
            hl: { f: p('leftHand'), n: [0, 0, -1], w: 0 }, hrt: { f: p('rightHand'), n: [0, 0, -1], w: 0 }, P: prevP || {} };
  }
  // значения ключа (с учётом side, масштаба, «как было» и «как стоит»), для ног — свои стороны с учётом зеркала
  function val(key, field) {
    let v = key[field];
    if (v === 'cap') return { cap: true, v: cap[field] };
    return { cap: false, v };
  }
  function footOf(key, which) {          // which: 'L' | 'R' — её левая/правая нога; при side=-1 данные ног меняются местами
    const src = side > 0 ? which : (which === 'L' ? 'R' : 'L');
    const r = val(key, src);
    if (r.cap) return cap[which];
    const f = r.v.f === 'stand' ? stand[which] : r.v.f === 'standIn' ? [stand[which][0] * 0.7, stand[which][1], stand[which][2]] : sc(r.v.f);
    return { f, n: scDir(r.v.n) };
  }
  function handOf(key, which) {          // 'hl' — её левая, 'hrt' — правая
    const src = side > 0 ? which : (which === 'hl' ? 'hrt' : 'hl');
    const r = val(key, src);
    if (r.cap) return cap[which];
    if (!r.v.f) return { f: null, n: [0, 0, -1], w: r.v.w || 0 };
    return { f: sc(r.v.f), n: scDir(r.v.n), w: r.v.w };
  }
  function hipsOf(key) {
    const p = val(key, 'hp'), r = val(key, 'hr');
    const P = p.cap ? cap.hp : p.v === 'stand' ? [0, hipsBase, 0] : p.v.d ? [cap.hp[0] + p.v.d[0] * s * side, cap.hp[1] + p.v.d[1] * s, cap.hp[2] + p.v.d[2] * s] : sc(p.v);
    return { p: P, r: r.cap ? cap.hr : rot(r.v) };
  }
  function pOf(key) {
    const r = val(key, 'P'); if (r.cap) return cap.P;
    const o = {};
    for (const f in r.v) o[f] = r.v[f] * (side < 0 && MIRROR_P[f] ? -1 : 1);
    return o;
  }

  const V = (a) => new THREE.Vector3(a[0], a[1], a[2]);
  let keys = SIDE_SIT_KEYS, lastP = {};
  const _hl = new THREE.Vector3();
  return {
    stand, scale: s,
    // придержать подол спереди ладонями (присед перед прыжком, приземление): точка — в осях таза
    hem(w) {
      if (w < 0.01) return;
      const hips = bone('hips'); hips.updateMatrixWorld(true);
      scene.updateWorldMatrix(true, false);
      const inv = new THREE.Matrix4().copy(scene.matrixWorld).invert();
      for (const [ch, x, nx] of [[armL, 0.035, 0.6], [armR, -0.035, -0.6]]) {
        if (!ch) continue;
        _hl.set(x * s, -0.13 * s, 0.15 * s); hips.localToWorld(_hl); _hl.applyMatrix4(inv);
        const pole = new THREE.Vector3(nx, -0.2, -1).applyQuaternion(hips.getWorldQuaternion(new THREE.Quaternion()));
        solve(ch, _hl.clone(), pole.normalize(), w);
      }
    },
    get side() { return side; },
    // kind: 'enter' | 'exit' (сидит боком на полу), 'edgeEnter' | 'edgeExit' (на краю окна)
    // yOff — где сейчас «пол» позы в пространстве модели (на краю окна модель опущена на EDGE_DROP)
    begin(kind, sd, prevP, yOff = 0) {
      if (sd) side = sd;
      for (const c of [legL, legR, armL, armR]) resetChain(c);
      capture(prevP || lastP, yOff);
      keys = KEYS[kind] || SIDE_SIT_KEYS;
    },
    // k — доля перехода 0..1. Возвращает добавки к позе корпуса/головы (P) — их применяет основной код.
    // apply(k) вызывать после того, как основная поза поставлена, и до vrm.update().
    pose(k) {
      let i = 0; while (i < keys.length - 2 && k > keys[i + 1].k) i++;
      const a = keys[i], b = keys[i + 1], u = smooth((k - a.k) / (b.k - a.k));
      const pa = pOf(a), pb = pOf(b), P = {};
      for (const f of new Set([...Object.keys(pa), ...Object.keys(pb)])) P[f] = lerp(pa[f] || 0, pb[f] || 0, u);
      lastP = P;
      return { a, b, u, P };
    },
    // opts: W — вес всего слоя (плавно включить/выключить), yOff — где «пол» позы, swing — { L: [dx,dy,dz], R } болтает ногами
    apply(st, opts = {}) {
      const { a, b, u } = st;
      const W = opts.W ?? 1, yOff = opts.yOff || 0, swing = opts.swing;
      if (W < 0.001) return;
      const hips = bone('hips');
      const ha = hipsOf(a), hb = hipsOf(b);
      const hp = lerp3(ha.p, hb.p, u), hr = lerp3(ha.r, hb.r, u);
      hips.position.lerp(new THREE.Vector3(hp[0], hp[1] + yOff, hp[2]), W);
      hips.quaternion.slerp(new THREE.Quaternion().setFromEuler(new THREE.Euler(hr[0], hr[1], hr[2])), W);
      hips.updateMatrixWorld(true);
      for (const [which, ch] of [['L', legL], ['R', legR]]) {
        const fa = footOf(a, which), fb = footOf(b, which);
        const f = lerp3(fa.f, fb.f, u), n = lerp3(fa.n, fb.n, u);
        if (swing && swing[which]) for (let i = 0; i < 3; i++) f[i] += swing[which][i] * s;
        const fy = f[1];
        f[1] += yOff;
        solve(ch, V(f), V(n).normalize(), W);
        // ступня: стоит — ровно на полу носком туда, куда колено; лежит на полу — вытянута вдоль голени подъёмом вниз;
        // висит (край окна) — расслаблена, носок чуть вниз. Между ними — плавный поворот (slerp), без переворотов.
        if (ch.rEnd) {
          const knee = modelPos(ch.lo, scene, new THREE.Vector3()), foot = modelPos(ch.end, scene, new THREE.Vector3());
          const along = foot.clone().sub(knee).normalize();
          const kneeFwd = V(n); kneeFwd.y = 0; if (kneeFwd.lengthSq() < 1e-6) kneeFwd.set(0, 0, 1); kneeFwd.normalize();
          const flat = endQuat(ch, kneeFwd, new THREE.Vector3(0, 1, 0));
          const lie = endQuat(ch, along, new THREE.Vector3(0, -1, 0).sub(along.clone().multiplyScalar(-along.y)).lengthSq() > 1e-6 ? new THREE.Vector3(0, -1, 0) : new THREE.Vector3(0, 0, 1));
          const hang = endQuat(ch, along.clone().multiplyScalar(0.6).add(kneeFwd), kneeFwd.clone().negate().add(new THREE.Vector3(0, 0.3, 0)));
          const lying = smooth((0.12 * s - fy + 0.1 * smooth((0.34 * s - hp[1]) / (0.14 * s))) / 0.18);   // таз опускается к полу — ступни ложатся
          const hanging = smooth((-fy - 0.05 * s) / (0.12 * s));
          const q = flat.clone().slerp(lie, lying * (1 - hanging)).slerp(hang, hanging);
          solve(ch, V(f), V(n).normalize(), W, q);
        }
      }
      for (const [which, ch] of [['hl', armL], ['hrt', armR]]) {
        if (!ch) continue;
        const A = handOf(a, which), B = handOf(b, which);
        const w = lerp(A.w || 0, B.w || 0, u) * W;
        if (w < 0.01) continue;
        const cur = modelPos(ch.end, scene, new THREE.Vector3());
        const fa = A.f || [cur.x, cur.y - yOff, cur.z], fb = B.f || [cur.x, cur.y - yOff, cur.z];
        const f = lerp3(fa, fb, u), n = lerp3(A.n, B.n, u);
        const onFloor = f[1] < 0.06 * s;
        f[1] += yOff;
        const out = which === 'hl' ? 1 : -1;
        solve(ch, V(f), V(n).normalize(), w,
              onFloor ? new THREE.Vector3(out * 0.8, 0, 0.6) : null, onFloor ? new THREE.Vector3(0, 1, 0) : null);
      }
    },
  };
}
