"""SafetyEye detection engine.

Runs two YOLO models per frame:
  * PPE model (fine-tuned YOLO11n on Construction-PPE) -> helmet / vest / gloves / boots / goggles + negatives
  * Pose model (YOLO11n-pose) -> people + keypoints for fall detection
and turns raw detections into per-worker safety status and violations.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, field, asdict

import cv2
import numpy as np
from ultralytics import YOLO

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PPE_WEIGHTS = os.environ.get("SAFETYEYE_PPE", os.path.join(ROOT, "models", "ppe.pt"))
POSE_WEIGHTS = os.environ.get("SAFETYEYE_POSE", os.path.join(ROOT, "models", "yolo11n-pose.pt"))

# rules that are enforced per site profile
REQUIRED = {"helmet", "vest"}

COLORS = {  # BGR
    "ok": (120, 220, 60),
    "bad": (60, 60, 240),
    "warn": (40, 190, 255),
    "zone": (255, 120, 60),
    "item": (230, 200, 80),
}


@dataclass
class Worker:
    box: list[float]
    conf: float
    has: set = field(default_factory=set)
    missing: set = field(default_factory=set)
    fallen: bool = False
    in_zone: bool = False

    @property
    def status(self) -> str:
        if self.fallen or self.in_zone or self.missing:
            return "bad"
        return "ok"

    def to_dict(self):
        d = asdict(self)
        d["has"] = sorted(self.has)
        d["missing"] = sorted(self.missing)
        d["status"] = self.status
        return d


def _overlap(inner, outer) -> float:
    """fraction of `inner` box area that lies inside `outer`."""
    x1, y1 = max(inner[0], outer[0]), max(inner[1], outer[1])
    x2, y2 = min(inner[2], outer[2]), min(inner[3], outer[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    area = max(1e-6, (inner[2] - inner[0]) * (inner[3] - inner[1]))
    return inter / area


def _iou(a, b) -> float:
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / max(ua, 1e-6)


def _is_fallen(kpts: np.ndarray | None, box) -> bool:
    """Torso close to horizontal (shoulder-hip vector angle) or very wide box."""
    w, h = box[2] - box[0], box[3] - box[1]
    if kpts is not None and len(kpts) >= 13:
        sh = kpts[[5, 6]]
        hp = kpts[[11, 12]]
        if (sh[:, 2] > 0.4).all() and (hp[:, 2] > 0.4).all():
            s = sh[:, :2].mean(0)
            p = hp[:, :2].mean(0)
            dx, dy = p[0] - s[0], p[1] - s[1]
            angle = abs(math.degrees(math.atan2(dy, dx)))  # 90 = upright
            if angle < 35 or angle > 145:
                return True
    return w > h * 1.6 and h > 20


class SafetyEngine:
    def __init__(self, conf: float = 0.35):
        self.ppe = YOLO(PPE_WEIGHTS)
        self.pose = YOLO(POSE_WEIGHTS)
        self.conf = conf
        self.names = self.ppe.names
        # restricted zones per camera: list of polygons in normalized coords
        self.zones: dict[str, list[list[tuple[float, float]]]] = {}

    def set_zone(self, cam: str, polys):
        self.zones[cam] = polys

    def analyze(self, frame: np.ndarray, cam: str = "cam-1"):
        h, w = frame.shape[:2]
        ppe_res = self.ppe.predict(frame, conf=self.conf, imgsz=416, verbose=False)[0]
        pose_res = self.pose.predict(frame, conf=0.4, imgsz=416, verbose=False)[0]

        items = []
        workers: list[Worker] = []
        for b, c, k in zip(ppe_res.boxes.xyxy.tolist(), ppe_res.boxes.conf.tolist(), ppe_res.boxes.cls.tolist()):
            name = self.names[int(k)]
            if name == "Person":
                workers.append(Worker(box=b, conf=c))
            elif name != "none":
                items.append((name, b, c))

        # merge pose people (better recall) with PPE-model persons
        kp_all = pose_res.keypoints.data.cpu().numpy() if pose_res.keypoints is not None else []
        for i, b in enumerate(pose_res.boxes.xyxy.tolist()):
            match = next((wk for wk in workers if _iou(wk.box, b) > 0.45), None)
            if match is None:
                if float(pose_res.boxes.conf[i]) < 0.6:
                    continue  # pose-only people need strong evidence
                match = Worker(box=b, conf=float(pose_res.boxes.conf[i]))
                workers.append(match)
            match.fallen = _is_fallen(kp_all[i] if len(kp_all) > i else None, match.box)

        # assign PPE items to the worker that contains them the most
        for name, b, c in items:
            best, score = None, 0.5
            for wk in workers:
                o = _overlap(b, wk.box)
                if o > score:
                    best, score = wk, o
            if best is None:
                continue
            if name.startswith("no_"):
                best.missing.add(name[3:].replace("goggle", "goggles"))
            else:
                best.has.add(name)

        # ignore tiny / far-away people: PPE can't be judged reliably
        workers = [wk for wk in workers if (wk.box[3] - wk.box[1]) >= 0.12 * h or wk.has]
        for wk in workers:
            for req in REQUIRED:
                if req not in wk.has:
                    wk.missing.add(req)
            wk.missing -= wk.has
            wk.missing &= REQUIRED  # only enforce site-required gear
            # feet point inside a restricted zone?
            fx, fy = (wk.box[0] + wk.box[2]) / 2 / w, wk.box[3] / h
            for poly in self.zones.get(cam, []):
                if cv2.pointPolygonTest(np.array(poly, np.float32), (fx, fy), False) >= 0:
                    wk.in_zone = True

        violations = []
        for i, wk in enumerate(workers):
            for m in sorted(wk.missing):
                violations.append({"type": f"no_{m}", "worker": i, "severity": "high" if m == "helmet" else "medium"})
            if wk.fallen:
                violations.append({"type": "fall", "worker": i, "severity": "critical"})
            if wk.in_zone:
                violations.append({"type": "zone", "worker": i, "severity": "high"})

        n = len(workers)
        ok = sum(1 for wk in workers if wk.status == "ok")
        return {
            "cam": cam,
            "workers": [wk.to_dict() for wk in workers],
            "items": [{"name": nm, "box": b, "conf": c} for nm, b, c in items],
            "violations": violations,
            "count": n,
            "compliance": round(100 * ok / n) if n else 100,
        }

    def draw(self, frame: np.ndarray, result: dict) -> np.ndarray:
        out = frame.copy()
        h, w = out.shape[:2]
        overlay = out.copy()
        for poly in self.zones.get(result["cam"], []):
            pts = (np.array(poly) * [w, h]).astype(np.int32)
            cv2.fillPoly(overlay, [pts], COLORS["zone"])
        out = cv2.addWeighted(overlay, 0.18, out, 0.82, 0)
        for poly in self.zones.get(result["cam"], []):
            pts = (np.array(poly) * [w, h]).astype(np.int32)
            cv2.polylines(out, [pts], True, COLORS["zone"], 2)

        for it in result["items"]:
            x1, y1, x2, y2 = map(int, it["box"])
            col = COLORS["bad"] if it["name"].startswith("no_") else COLORS["item"]
            cv2.rectangle(out, (x1, y1), (x2, y2), col, 1)
        for i, wk in enumerate(result["workers"]):
            x1, y1, x2, y2 = map(int, wk["box"])
            col = COLORS[wk["status"]]
            cv2.rectangle(out, (x1, y1), (x2, y2), col, 2)
            if wk["fallen"]:
                label = "FALL DETECTED"
            elif wk["in_zone"]:
                label = "RESTRICTED ZONE"
            elif wk["missing"]:
                label = "NO " + " / ".join(m.upper() for m in wk["missing"])
            else:
                label = "PPE OK"
            label = f"W{i + 1} {label}"
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
            ty = y1 if y1 - th - 8 >= 0 else y1 + th + 8  # keep label on-screen
            cv2.rectangle(out, (x1, ty - th - 8), (x1 + tw + 8, ty), col, -1)
            cv2.putText(out, label, (x1 + 4, ty - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
        return out
