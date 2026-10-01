"""SafetyEye API server: camera workers, incident log, live websocket, dashboard."""
from __future__ import annotations

import asyncio
import csv
import glob
import io
import json
import os
import sqlite3
import threading
import time
from collections import Counter, defaultdict

import cv2
import numpy as np
from fastapi import FastAPI, File, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from detector import ROOT, SafetyEngine
from messages import MESSAGES

DATA = os.path.join(ROOT, "data")
SNAPS = os.path.join(DATA, "snapshots")
os.makedirs(SNAPS, exist_ok=True)
DB = os.path.join(DATA, "safetyeye.db")
COOLDOWN = float(os.environ.get("SAFETYEYE_COOLDOWN", 30))
FRAME_SECONDS = float(os.environ.get("SAFETYEYE_FRAME_SECONDS", 2.5))

CAMERAS = {
    "cam-1": {"name": "Gate A · Entry", "source": os.path.join(ROOT, "samples", "cam-1")},
    "cam-2": {"name": "Scaffold · Zone B", "source": os.path.join(ROOT, "samples", "cam-2")},
    "cam-3": {"name": "Yard · Zone C", "source": os.path.join(ROOT, "samples", "cam-3")},
}

engine = SafetyEngine()
engine.set_zone("cam-2", [[(0.55, 0.5), (0.95, 0.5), (0.95, 0.86), (0.55, 0.86)]])

lock = threading.Lock()
latest: dict[str, dict] = {}
last_alert: dict[tuple, float] = {}
pending_events: list[dict] = []


def db():
    con = sqlite3.connect(DB, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


with db() as con:
    con.execute(
        """create table if not exists incidents(
        id integer primary key autoincrement, ts real, cam text, type text, severity text,
        worker integer, snapshot text, acked integer default 0)"""
    )
    con.execute("create table if not exists samples(ts real, cam text, workers int, compliance int)")


def frames_from(source: str):
    """Yield frames forever from a folder of images or a video file."""
    while True:
        if os.path.isdir(source):
            files = sorted(glob.glob(os.path.join(source, "*.jpg")) + glob.glob(os.path.join(source, "*.png")))
            for f in files:
                img = cv2.imread(f)
                if img is not None:
                    yield img
        else:
            cap = cv2.VideoCapture(source)
            ok, img = cap.read()
            while ok:
                yield img
                ok, img = cap.read()
            cap.release()


def handle_result(cam: str, frame: np.ndarray, result: dict):
    annotated = engine.draw(frame, result)
    ok, jpg = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 82])
    now = time.time()
    new = []
    with db() as con:
        con.execute("insert into samples values(?,?,?,?)", (now, cam, result["count"], result["compliance"]))
        for v in result["violations"]:
            key = (cam, v["type"], v["worker"])
            if now - last_alert.get(key, 0) < COOLDOWN:
                continue
            last_alert[key] = now
            snap = f"{cam}-{int(now * 1000)}-{v['type']}.jpg"
            with open(os.path.join(SNAPS, snap), "wb") as fh:
                fh.write(jpg.tobytes())
            cur = con.execute(
                "insert into incidents(ts,cam,type,severity,worker,snapshot) values(?,?,?,?,?,?)",
                (now, cam, v["type"], v["severity"], v["worker"], snap),
            )
            new.append({"id": cur.lastrowid, "ts": now, "cam": cam, "camName": CAMERAS.get(cam, {}).get("name", cam),
                        "type": v["type"], "severity": v["severity"], "worker": v["worker"] + 1, "snapshot": snap})
    with lock:
        latest[cam] = {"jpg": jpg.tobytes(), "result": result, "ts": now}
        pending_events.extend(new)


def camera_worker(cam: str, source: str):
    for frame in frames_from(source):
        t0 = time.time()
        try:
            handle_result(cam, frame, engine.analyze(frame, cam))
        except Exception as e:  # keep the camera alive
            print("camera error", cam, e)
        time.sleep(max(0.05, FRAME_SECONDS - (time.time() - t0)))


app = FastAPI(title="SafetyEye")


@app.on_event("startup")
def start_cameras():
    if os.environ.get("SAFETYEYE_NO_CAMERAS"):
        return
    for i, (cam, cfg) in enumerate(CAMERAS.items()):
        if os.path.exists(cfg["source"]):
            threading.Timer(i * 0.8, lambda c=cam, s=cfg["source"]: threading.Thread(target=camera_worker, args=(c, s), daemon=True).start()).start()


@app.get("/api/cameras")
def cameras():
    with lock:
        return [{"id": c, "name": cfg["name"], **({k: latest[c]["result"][k] for k in ("count", "compliance")} if c in latest else {"count": 0, "compliance": 100})}
                for c, cfg in CAMERAS.items()]


@app.get("/api/frame/{cam}")
def frame(cam: str):
    with lock:
        item = latest.get(cam)
    if not item:
        return Response(status_code=204)
    return Response(item["jpg"], media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@app.get("/stream/{cam}")
async def stream(cam: str):
    async def gen():
        last = 0
        while True:
            with lock:
                item = latest.get(cam)
            if item and item["ts"] != last:
                last = item["ts"]
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + item["jpg"] + b"\r\n"
            await asyncio.sleep(0.1)

    return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.get("/api/incidents")
def incidents(limit: int = 50):
    with db() as con:
        rows = con.execute("select * from incidents order by id desc limit ?", (limit,)).fetchall()
    return [dict(r) | {"camName": CAMERAS.get(r["cam"], {}).get("name", r["cam"]), "worker": r["worker"] + 1} for r in rows]


@app.post("/api/incidents/{iid}/ack")
def ack(iid: int):
    with db() as con:
        con.execute("update incidents set acked=1 where id=?", (iid,))
    return {"ok": True}


@app.get("/api/stats")
def stats():
    since = time.time() - 24 * 3600
    with db() as con:
        inc = con.execute("select ts,type,cam,acked from incidents where ts>?", (since,)).fetchall()
        smp = con.execute("select ts,workers,compliance from samples where ts>? order by ts", (since,)).fetchall()
    by_type = Counter(r["type"] for r in inc)
    by_cam = Counter(r["cam"] for r in inc)
    # compliance trend in 1-minute buckets
    buckets = defaultdict(list)
    for r in smp:
        buckets[int(r["ts"] // 60) * 60].append(r["compliance"])
    trend = [{"t": k, "v": round(sum(v) / len(v))} for k, v in sorted(buckets.items())][-30:]
    open_ = sum(1 for r in inc if not r["acked"])
    with lock:
        live = [latest[c]["result"] for c in latest]
    workers = sum(r["count"] for r in live)
    comp = round(sum(r["compliance"] * max(r["count"], 1) for r in live) / max(sum(max(r["count"], 1) for r in live), 1)) if live else 100
    return {"byType": by_type, "byCam": {CAMERAS[c]["name"]: n for c, n in by_cam.items() if c in CAMERAS},
            "trend": trend, "total": len(inc), "open": open_, "workers": workers, "compliance": comp}


@app.get("/api/report")
def report():
    """Plain-language shift report generated from today's incidents."""
    s = stats()
    by = s["byType"]
    lines = [f"Shift safety summary — {time.strftime('%d %b %Y, %H:%M')}",
             f"Live PPE compliance across cameras: {s['compliance']}% with {s['workers']} workers in view.",
             f"{s['total']} incidents logged in the last 24h, {s['open']} still unacknowledged."]
    if by:
        top, n = max(by.items(), key=lambda kv: kv[1])
        lines.append(f"Most frequent violation: {MESSAGES['en'][top]['title']} ({n} times).")
    if s["byCam"]:
        hot, n = max(s["byCam"].items(), key=lambda kv: kv[1])
        lines.append(f"Hotspot: {hot} with {n} incidents — schedule a toolbox talk and PPE check at this point.")
    if by.get("no_helmet"):
        lines.append("Action: station a helmet dispenser at the entry gate and enforce a no-helmet-no-entry rule.")
    if by.get("zone"):
        lines.append("Action: add physical barricades / signage to restricted zones that saw intrusions.")
    if by.get("fall"):
        lines.append("Action: review fall incidents immediately and check first-aid response time.")
    return {"text": "\n".join(lines)}


@app.get("/api/report.csv")
def report_csv():
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "time", "camera", "type", "severity", "worker", "acknowledged"])
    for r in incidents(10000):
        w.writerow([r["id"], time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(r["ts"])), r["camName"], r["type"], r["severity"], r["worker"], bool(r["acked"])])
    return Response(buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=safetyeye-incidents.csv"})


@app.get("/api/zones/{cam}")
def get_zone(cam: str):
    return engine.zones.get(cam, [])


@app.post("/api/zones/{cam}")
async def set_zone(cam: str, polys: list[list[list[float]]]):
    engine.set_zone(cam, [[tuple(p) for p in poly] for poly in polys])
    return {"ok": True}


@app.post("/api/analyze")
async def analyze(file: UploadFile = File(...), cam: str = "upload"):
    img = cv2.imdecode(np.frombuffer(await file.read(), np.uint8), cv2.IMREAD_COLOR)
    res = engine.analyze(img, cam)
    if cam in CAMERAS or cam == "webcam":
        handle_result(cam, img, res)
    ok, jpg = cv2.imencode(".jpg", engine.draw(img, res))
    import base64
    return {"result": res, "image": "data:image/jpeg;base64," + base64.b64encode(jpg.tobytes()).decode()}


@app.get("/api/messages")
def messages():
    return MESSAGES


@app.websocket("/ws")
async def ws(sock: WebSocket):
    await sock.accept()
    sent = 0
    with lock:
        sent = len(pending_events)
    try:
        while True:
            with lock:
                events = pending_events[sent:]
                sent = len(pending_events)
                cams = {c: {k: v["result"][k] for k in ("count", "compliance", "violations")} | {"ts": v["ts"]} for c, v in latest.items()}
            await sock.send_text(json.dumps({"cams": cams, "events": events}))
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        pass


app.mount("/snapshots", StaticFiles(directory=SNAPS), name="snapshots")
app.mount("/", StaticFiles(directory=os.path.join(ROOT, "web"), html=True), name="web")
