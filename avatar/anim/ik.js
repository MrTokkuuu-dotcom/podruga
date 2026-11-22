// Аналитическая IK двух костей (бедро–голень, плечо–предплечье) для нормализованных костей VRM.
// Всё считается в пространстве модели (vrm.scene): пол y=0, она смотрит на +Z.
// В покое нормализованные кости без поворота, поэтому направление кости = положение ребёнка у родителя.
import * as THREE from 'three';

const _m1 = new THREE.Matrix4(), _m2 = new THREE.Matrix4(), _q = new THREE.Quaternion(), _pq = new THREE.Quaternion();
const _a = new THREE.Vector3(), _b = new THREE.Vector3(), _c = new THREE.Vector3(), _d = new THREE.Vector3();
const _sceneQ = new THREE.Quaternion(), _sceneInv = new THREE.Matrix4();

function basis(out, x, y, z) { return out.makeBasis(x, y, z); }

// rest: { a: ось кости в покое, p: куда уходит сустав при сгибе (колено — вперёд, локоть — назад), h: a×p }
function restFrame(a, p) {
  const A = a.clone().normalize();
  const P = p.clone().sub(A.clone().multiplyScalar(p.dot(A))).normalize();
  return { a: A, p: P, h: A.clone().cross(P).normalize() };
}

// Поворот, переводящий рамку покоя (a, p, h) в нужную (d, q, h2) — кватернион в пространстве модели.
function frameQuat(rest, d, q, out) {
  const h = d.clone().cross(q).normalize();
  basis(_m1, d, q, h);
  basis(_m2, rest.a, rest.p, rest.h).transpose();
  return out.setFromRotationMatrix(_m1.multiply(_m2));
}

// Поворот кости в пространстве модели (через мировые матрицы, без vrm.scene)
function modelQuat(node, scene, out) {
  node.getWorldQuaternion(out);
  scene.getWorldQuaternion(_sceneQ);
  return out.premultiply(_sceneQ.invert());
}
function modelPos(node, scene, out) {
  node.getWorldPosition(out);
  scene.updateWorldMatrix(true, false);
  _sceneInv.copy(scene.matrixWorld).invert();
  return out.applyMatrix4(_sceneInv);
}

// Поставить кости так, чтобы их модельный поворот стал Q (с весом w от текущего)
function setModelQuat(node, scene, Q, w) {
  modelQuat(node.parent, scene, _pq);
  _q.copy(_pq).invert().multiply(Q);
  if (w >= 0.999) node.quaternion.copy(_q); else node.quaternion.slerp(_q, w);
  node.updateMatrixWorld(true);
}

export function createChain(bone, scene, upperName, lowerName, endName, pole, endTipName) {
  const up = bone(upperName), lo = bone(lowerName), end = bone(endName);
  if (!up || !lo || !end) return null;
  const L1 = lo.position.length(), L2 = end.position.length();
  const rUp = restFrame(lo.position, pole), rLo = restFrame(end.position, pole);
  let rEnd = null;
  const tip = endTipName && bone(endTipName);
  if (tip) {                                         // рамка кисти/ступни: «вперёд» — к носку/пальцам, «верх» — +Y
    const f = tip.position.clone().normalize();
    rEnd = { f, u: new THREE.Vector3(0, 1, 0).sub(f.clone().multiplyScalar(f.y)).normalize() };
  }
  return { up, lo, end, L1, L2, rUp, rLo, rEnd, scene };
}

// target — куда поставить конец (ступню/кисть), poleDir — куда смотрит колено/локоть (модельные координаты).
// endFwd/endUp — как повернуть ступню/кисть (необязательно). w — вес поверх текущей позы.
export function solve(ch, target, poleDir, w = 1, endFwd = null, endUp = null) {
  if (!ch || w <= 0.001) return;
  const { up, lo, end, L1, L2, scene } = ch;
  up.parent.updateMatrixWorld(true);
  const H = modelPos(up, scene, _a);
  const toT = _b.copy(target).sub(H);
  let D = toT.length();
  const maxD = (L1 + L2) * 0.9995, minD = Math.abs(L1 - L2) + 1e-3;
  D = Math.max(minD, Math.min(maxD, D));
  const u = toT.normalize();
  // плоскость сгиба: куда смотрит колено/локоть. Если подсказка почти вдоль ноги — она неустойчива,
  // тогда держимся прошлого кадра (иначе бедро «щёлкает» в зеркальное положение)
  const pn = poleDir.clone().normalize();
  const v = _c.copy(pn).sub(u.clone().multiplyScalar(pn.dot(u)));
  const strong = v.length();
  if (ch.prevV) {
    const pv = ch.prevV.clone().sub(u.clone().multiplyScalar(ch.prevV.dot(u)));
    if (pv.lengthSq() > 1e-6) {
      pv.normalize();
      const k = Math.min(1, strong / 0.45);              // слабая подсказка — больше прошлого кадра
      if (strong < 1e-4 || v.dot(pv) / strong < 0.2) v.copy(pv);   // колено не может за кадр перескочить на другую сторону
      else v.normalize().lerp(pv, 1 - k);
    }
  }
  if (v.lengthSq() < 1e-8) v.set(0, 0, 1).sub(u.clone().multiplyScalar(u.z));
  v.normalize();
  (ch.prevV ||= new THREE.Vector3()).copy(v);
  const x = (L1 * L1 - L2 * L2 + D * D) / (2 * D), y = Math.sqrt(Math.max(0, L1 * L1 - x * x));
  const K = H.clone().add(u.clone().multiplyScalar(x)).add(v.clone().multiplyScalar(y));
  const T = H.clone().add(u.clone().multiplyScalar(D));
  const d1 = K.clone().sub(H).normalize(), d2 = T.clone().sub(K).normalize();
  const h = u.clone().cross(v).normalize();                    // ось сгиба: не зависит от того, куда «падает» колено при тугом сгибе
  if (h.lengthSq() < 1e-8) h.copy(ch.rUp.h);                    // нога прямая — шарнир как в покое
  const q1 = h.clone().cross(d1).normalize(), q2 = h.clone().cross(d2).normalize();
  setModelQuat(up, scene, frameQuat(ch.rUp, d1, q1, new THREE.Quaternion()), w);
  setModelQuat(lo, scene, frameQuat(ch.rLo, d2, q2, new THREE.Quaternion()), w);
  if (endFwd && endFwd.isQuaternion) {
    setModelQuat(end, scene, endFwd, w);
  } else if (endFwd && ch.rEnd) {
    const f = endFwd.clone().normalize();
    const uu = (endUp || new THREE.Vector3(0, 1, 0)).clone().sub(f.clone().multiplyScalar((endUp || new THREE.Vector3(0, 1, 0)).dot(f))).normalize();
    const s = f.clone().cross(uu);
    basis(_m1, f, uu, s);
    const s0 = ch.rEnd.f.clone().cross(ch.rEnd.u);
    basis(_m2, ch.rEnd.f, ch.rEnd.u, s0).transpose();
    setModelQuat(end, scene, new THREE.Quaternion().setFromRotationMatrix(_m1.multiply(_m2)), w);
  }
}

// Модельный поворот конца (ступни/кисти), при котором «вперёд» = fwd, «верх» = up
export function endQuat(ch, fwd, up, out = new THREE.Quaternion()) {
  const f = fwd.clone().normalize();
  const uu = up.clone().sub(f.clone().multiplyScalar(up.dot(f))).normalize();
  basis(_m1, f, uu, f.clone().cross(uu));
  const s0 = ch.rEnd.f.clone().cross(ch.rEnd.u);
  basis(_m2, ch.rEnd.f, ch.rEnd.u, s0).transpose();
  return out.setFromRotationMatrix(_m1.multiply(_m2));
}
export function resetChain(ch) { if (ch) ch.prevV = null; }

export { modelPos, modelQuat };
