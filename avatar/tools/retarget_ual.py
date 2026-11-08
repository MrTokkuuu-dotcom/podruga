"""Перекладывает анимации Quaternius Universal Animation Library (CC0) на кости VRM.
Запуск: python avatar/tools/retarget_ual.py AnimationLibrary_Godot_Standard.glb avatar/anims.json UAL2_Standard.glb

Идея: у нормализованных костей VRM в Т-позе нулевой поворот в мире. Поэтому для каждой кости берём,
насколько она повёрнута в мире относительно Т-позы источника, и переводим в поворот относительно родителя."""
import json
import struct
import sys

import numpy as np

# Стоя она держит свою позу (Idle у библиотеки — игровая стойка «наготове»), поэтому берём только ходьбу и посадку
CLIPS = {"Walk_Loop": "walk", "Sitting_Enter": "sitEnter", "Sitting_Idle_Loop": "sitIdle", "Sitting_Exit": "sitExit",
         "Sitting_Talking_Loop": "sitTalk"}
FPS = 30
BONES = {"DEF-hips": "hips", "DEF-spine.001": "spine", "DEF-spine.002": "chest", "DEF-spine.003": "upperChest",
         "DEF-neck": "neck", "DEF-head": "head"}
for s, side in (("L", "left"), ("R", "right")):
    BONES |= {f"DEF-shoulder.{s}": f"{side}Shoulder", f"DEF-upper_arm.{s}": f"{side}UpperArm",
              f"DEF-forearm.{s}": f"{side}LowerArm", f"DEF-hand.{s}": f"{side}Hand",
              f"DEF-thigh.{s}": f"{side}UpperLeg", f"DEF-shin.{s}": f"{side}LowerLeg",
              f"DEF-foot.{s}": f"{side}Foot", f"DEF-toe.{s}": f"{side}Toes",
              f"DEF-thumb.01.{s}": f"{side}ThumbMetacarpal", f"DEF-thumb.02.{s}": f"{side}ThumbProximal",
              f"DEF-thumb.03.{s}": f"{side}ThumbDistal"}
    for src, dst in (("index", "Index"), ("middle", "Middle"), ("ring", "Ring"), ("pinky", "Little")):
        BONES |= {f"DEF-f_{src}.01.{s}": f"{side}{dst}Proximal", f"DEF-f_{src}.02.{s}": f"{side}{dst}Intermediate",
                  f"DEF-f_{src}.03.{s}": f"{side}{dst}Distal"}
# кости второй библиотеки (названия как в Unreal)
BONES_UE = {"pelvis": "hips", "spine_01": "spine", "spine_02": "chest", "spine_03": "upperChest",
            "neck_01": "neck", "Head": "head"}
for s_, side in (("l", "left"), ("r", "right")):
    BONES_UE |= {f"clavicle_{s_}": f"{side}Shoulder", f"upperarm_{s_}": f"{side}UpperArm", f"lowerarm_{s_}": f"{side}LowerArm",
                 f"hand_{s_}": f"{side}Hand", f"thigh_{s_}": f"{side}UpperLeg", f"calf_{s_}": f"{side}LowerLeg",
                 f"foot_{s_}": f"{side}Foot", f"ball_{s_}": f"{side}Toes", f"thumb_01_{s_}": f"{side}ThumbMetacarpal",
                 f"thumb_02_{s_}": f"{side}ThumbProximal", f"thumb_03_{s_}": f"{side}ThumbDistal"}
    for src, dst in (("index", "Index"), ("middle", "Middle"), ("ring", "Ring"), ("pinky", "Little")):
        BONES_UE |= {f"{src}_01_{s_}": f"{side}{dst}Proximal", f"{src}_02_{s_}": f"{side}{dst}Intermediate",
                     f"{src}_03_{s_}": f"{side}{dst}Distal"}

# родитель в иерархии VRM (пальцы — от кисти цепочкой)
VRM_PARENT = {"spine": "hips", "chest": "spine", "upperChest": "chest", "neck": "upperChest", "head": "neck"}
for side in ("left", "right"):
    VRM_PARENT |= {f"{side}Shoulder": "upperChest", f"{side}UpperArm": f"{side}Shoulder",
                   f"{side}LowerArm": f"{side}UpperArm", f"{side}Hand": f"{side}LowerArm",
                   f"{side}UpperLeg": "hips", f"{side}LowerLeg": f"{side}UpperLeg", f"{side}Foot": f"{side}LowerLeg",
                   f"{side}Toes": f"{side}Foot", f"{side}ThumbMetacarpal": f"{side}Hand",
                   f"{side}ThumbProximal": f"{side}ThumbMetacarpal", f"{side}ThumbDistal": f"{side}ThumbProximal"}
    for f in ("Index", "Middle", "Ring", "Little"):
        VRM_PARENT |= {f"{side}{f}Proximal": f"{side}Hand", f"{side}{f}Intermediate": f"{side}{f}Proximal",
                       f"{side}{f}Distal": f"{side}{f}Intermediate"}


def qmul(a, b):
    x1, y1, z1, w1 = a
    x2, y2, z2, w2 = b
    return np.array([w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2, w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
                     w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2, w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2])


def qinv(q):
    return np.array([-q[0], -q[1], -q[2], q[3]]) / np.dot(q, q)


def qrot(q, v):
    return qmul(qmul(q, np.array([v[0], v[1], v[2], 0.0])), qinv(q))[:3]


def slerp(a, b, t):
    d = np.dot(a, b)
    if d < 0:
        b, d = -b, -d
    if d > 0.9995:
        r = a + (b - a) * t
    else:
        th = np.arccos(d)
        r = (np.sin((1 - t) * th) * a + np.sin(t * th) * b) / np.sin(th)
    return r / np.linalg.norm(r)


class Glb:
    def __init__(self, path):
        with open(path, "rb") as f:
            f.read(12)
            n, _ = struct.unpack("<I4s", f.read(8))
            self.g = json.loads(f.read(n))
            m, _ = struct.unpack("<I4s", f.read(8))
            self.bin = f.read(m)
        self.names = [x.get("name", "") for x in self.g["nodes"]]
        self.parent = {}
        for i, x in enumerate(self.g["nodes"]):
            for c in x.get("children", []):
                self.parent[c] = i

    def acc(self, i):
        a = self.g["accessors"][i]
        bv = self.g["bufferViews"][a["bufferView"]]
        n = {"SCALAR": 1, "VEC3": 3, "VEC4": 4}[a["type"]]
        assert a["componentType"] == 5126
        off = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
        return np.frombuffer(self.bin, np.float32, a["count"] * n, off).reshape(-1, n).astype(float)

    def clip(self, name):
        anim = next(a for a in self.g["animations"] if a["name"] == name)
        tr = {}
        for c in anim["channels"]:
            s = anim["samplers"][c["sampler"]]
            tr[(c["target"]["node"], c["target"]["path"])] = (self.acc(s["input"]).ravel(), self.acc(s["output"]))
        return tr

    def local(self, tr, node, t):
        x = self.g["nodes"][node]

        def sample(path, dflt):
            k = (node, path)
            if k not in tr:
                return np.array(x.get(path, dflt), float)
            ts, vs = tr[k]
            if t <= ts[0]:
                return vs[0]
            if t >= ts[-1]:
                return vs[-1]
            i = int(np.searchsorted(ts, t)) - 1
            u = (t - ts[i]) / (ts[i + 1] - ts[i])
            return slerp(vs[i], vs[i + 1], u) if path == "rotation" else vs[i] * (1 - u) + vs[i + 1] * u
        return sample("translation", [0, 0, 0]), sample("rotation", [0, 0, 0, 1])

    def world(self, tr, t):
        """Мировые повороты и положения всех узлов в момент t."""
        out = {}

        def get(n):
            if n in out:
                return out[n]
            p, r = self.local(tr, n, t)
            if n in self.parent:
                pp, pr = get(self.parent[n])
                out[n] = (pp + qrot(pr, p), qmul(pr, r))
            else:
                out[n] = (p, r)
            return out[n]
        for n in range(len(self.names)):
            get(n)
        return out


# из второй библиотеки (Universal Animation Library 2, тоже CC0): «лежит → встаёт»; задом наперёд — «ложится»
CLIPS2 = {"LayToIdle": "layUp", "Idle_FoldArms_Loop": "foldArms", "Yes": "yes", "Idle_No_Loop": "no",
          "NinjaJump_Start": "jumpStart", "NinjaJump_Idle_Loop": "jumpAir", "NinjaJump_Land": "jumpLand"}


def main(src, dst, src2=None):
    out = convert(src, CLIPS, BONES)
    if src2:
        out2 = convert(src2, CLIPS2, BONES_UE)
        out["clips"].update(out2["clips"])
    with open(dst, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    print("записано", dst)


def convert(src, clips, bones):
    g = Glb(src)
    idx = {n: i for i, n in enumerate(g.names)}
    by = {v: k for k, v in bones.items()}                       # кость VRM → имя в источнике
    rest = g.world(g.clip("A_TPose"), 0.0)
    hip_rest = rest[idx[by["hips"]]][0][1]
    v = rest[idx[by["leftHand"]]][0] - rest[idx[by["leftUpperArm"]]][0]
    print("Т-поза источника: левая рука", np.round(v, 3), "| высота таза", round(hip_rest, 3))
    src_to_vrm = {idx[k]: v for k, v in bones.items() if k in idx}
    out = {"fps": FPS, "bones": sorted(set(src_to_vrm.values()), key=lambda b: (b != "hips", b)), "clips": {}}
    for name, key in clips.items():
        tr = g.clip(name)
        dur = max(ts[-1] for ts, _ in tr.values())
        n = max(2, int(round(dur * FPS)) + 1)
        frames = {b: [] for b in out["bones"]}
        pos = []
        feet = []
        for f in range(n):
            t = dur * f / (n - 1)
            w = g.world(tr, t)
            delta = {}
            for node, bone in src_to_vrm.items():
                delta[bone] = qmul(w[node][1], qinv(rest[node][1]))
            for bone in out["bones"]:
                q = delta[bone]
                par = VRM_PARENT.get(bone)
                if par:
                    q = qmul(qinv(delta[par]), q)
                q = q / np.linalg.norm(q)
                if frames[bone] and np.dot(frames[bone][-1], q) < 0:      # без рывка на другую сторону сферы
                    q = -q
                frames[bone].append(q)
            pos.append(w[idx[by["hips"]]][0] / hip_rest)
            feet.append((w[idx[by["leftFoot"]]][0] / hip_rest, w[idx[by["rightFoot"]]][0] / hip_rest))
        clip = {"dur": round(float(dur), 4), "n": n, "pos": [round(float(x), 4) for p in pos for x in p],
                "q": {b: [round(float(x), 4) for q in frames[b] for x in q] for b in out["bones"]
                      if max(np.linalg.norm(q[:3]) for q in frames[b]) > 1e-3}}
        if key.startswith("walk"):
            # скорость шага: сколько опорная ступня проезжает назад за секунду (в высотах таза)
            F = np.array(feet)                                        # кадр, нога, xyz
            dtf = dur / (n - 1)
            vs = []
            for leg in (0, 1):
                low = F[:, leg, 1] < np.percentile(F[:, leg, 1], 40)
                dz = np.diff(F[:, leg, 2]) / dtf
                vs.extend(np.abs(dz[low[:-1]]))
            clip["speed"] = round(float(np.median(vs)), 4)
            print(key, "скорость ступни на опоре", clip["speed"], "высот таза/с")
        print(f"{key:12s} {dur:.2f} с, кадров {n}, таз {np.round(np.mean(pos, axis=0), 3)}, костей {len(clip['q'])}")
        out["clips"][key] = clip
    return out


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
