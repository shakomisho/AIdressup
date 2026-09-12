"""Smoke tests: run with ``.venv/bin/python -m pytest`` from ``backend/``."""

from __future__ import annotations

import base64
import io
import sys
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Category, ResultStatus, TryOnResult  # noqa: E402
from app.services import tryon_service  # noqa: E402
from app.tryon import TryOnEngine, TryOnOutput, register  # noqa: E402
from app.tryon.overlay_engine import solve_placements  # noqa: E402

TERMINAL = {"completed", "failed", "cancelled"}


def _green_png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGBA", (64, 64), (0, 255, 0, 255)).save(buf, format="PNG")
    return buf.getvalue()


class BlockingFakeEngine(TryOnEngine):
    """Queued engine whose ``generate`` blocks until the test opens the gate.

    Lets a test hold the single worker busy, which is the only way to observe a
    job actually waiting in the queue.
    """

    name = "fake-queued"
    title = "Fake queued engine"
    description = "test double"
    phase = 2
    execution = "queued"

    gate = threading.Event()

    def generate(self, payload) -> TryOnOutput:
        if not self.gate.wait(timeout=10):
            raise RuntimeError("gate never opened")
        return TryOnOutput(_green_png())


register(BlockingFakeEngine())


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _poll(client, public_id: str, timeout: float = 10.0) -> dict:
    deadline = time.monotonic() + timeout
    body = {}
    while time.monotonic() < deadline:
        body = client.get(f"/api/tryon/{public_id}").json()
        if body["status"] in TERMINAL:
            return body
        time.sleep(0.02)
    raise AssertionError(f"job {public_id} never settled: {body}")


def _fake_person(width: int = 640, height: int = 480) -> str:
    img = Image.new("RGB", (width, height), (28, 30, 36))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _fake_pose() -> dict:
    """33 landmarks; only the ones the overlay uses need sensible values."""
    pts = [{"x": 0.5, "y": 0.5, "z": 0.0, "visibility": 0.9} for _ in range(33)]
    pts[3] = {"x": 0.46, "y": 0.17, "z": 0, "visibility": 0.9}   # left eye outer
    pts[6] = {"x": 0.54, "y": 0.17, "z": 0, "visibility": 0.9}   # right eye outer
    pts[7] = {"x": 0.44, "y": 0.18, "z": 0, "visibility": 0.9}   # left ear
    pts[8] = {"x": 0.56, "y": 0.18, "z": 0, "visibility": 0.9}   # right ear
    pts[11] = {"x": 0.38, "y": 0.35, "z": 0, "visibility": 0.9}  # left shoulder
    pts[12] = {"x": 0.62, "y": 0.35, "z": 0, "visibility": 0.9}  # right shoulder
    pts[23] = {"x": 0.42, "y": 0.70, "z": 0, "visibility": 0.9}  # left hip
    pts[24] = {"x": 0.58, "y": 0.70, "z": 0, "visibility": 0.9}  # right hip
    pts[27] = {"x": 0.43, "y": 0.95, "z": 0, "visibility": 0.8}  # left ankle
    pts[28] = {"x": 0.57, "y": 0.95, "z": 0, "visibility": 0.8}  # right ankle
    pts[31] = {"x": 0.39, "y": 0.99, "z": 0, "visibility": 0.8}  # left foot index
    pts[32] = {"x": 0.61, "y": 0.99, "z": 0, "visibility": 0.8}  # right foot index
    return {"landmarks": pts}


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["catalog_items"] > 0
    assert {e["name"] for e in body["engines"]} >= {"overlay", "catvton", "idm-vton"}


def test_overlay_engine_is_available(client):
    engines = {e["name"]: e for e in client.get("/api/tryon/engines").json()}
    assert engines["overlay"]["available"] is True
    assert engines["overlay"]["phase"] == 1


def test_catalog_lists_shirts(client):
    items = client.get("/api/clothing", params={"category": "shirts"}).json()
    assert items, "sample shirts missing - run scripts/generate_sample_clothes.py"
    item = items[0]
    assert item["category"] == "shirts"
    assert item["overlay"]["anchor_type"] == "torso"
    assert item["image_url"].startswith("/assets/clothes/")


def test_every_category_keyed_table_covers_the_enum():
    """Several tables are keyed by category string and can only be spotted
    drifting at runtime, in the engine, long after a category is added."""
    from app.config import get_settings
    from app.services.catalog import CATEGORY_DEFAULTS, CATEGORY_LABELS
    from app.models import SLUG_PREFIX
    from app.tryon.catvton_engine import CLOTH_TYPES
    from app.tryon.idm_vton_engine import MASK_REGIONS

    expected = {c.value for c in Category}
    assert set(get_settings().categories) == expected
    assert set(CLOTH_TYPES) == expected
    assert set(MASK_REGIONS) == expected
    for table in (CATEGORY_DEFAULTS, CATEGORY_LABELS, SLUG_PREFIX):
        assert set(table) == set(Category)


def test_categories_cover_the_whole_enum(client):
    cats = {c["category"]: c["count"] for c in client.get("/api/clothing/categories").json()}
    assert set(cats) == {c.value for c in Category}
    assert cats["shirts"] >= 1


def test_static_garment_is_served(client):
    item = client.get("/api/clothing", params={"category": "shirts"}).json()[0]
    resp = client.get(item["image_url"])
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"


def test_session_lifecycle(client):
    created = client.post(
        "/api/sessions", json={"user_agent": "pytest", "frame_width": 640, "frame_height": 480}
    ).json()
    public_id = created["public_id"]
    updated = client.patch(
        f"/api/sessions/{public_id}", json={"avg_fps": 42.5, "frames_processed": 300, "ended": True}
    ).json()
    assert updated["avg_fps"] == 42.5
    assert updated["ended_at"] is not None


def test_tryon_overlay_and_cache(client):
    shirt = client.get("/api/clothing", params={"category": "shirts"}).json()[0]
    payload = {
        "clothing_id": shirt["id"],
        "person_image": _fake_person(),
        "engine": "overlay",
        "pose_landmarks": _fake_pose(),
    }
    first = client.post("/api/tryon", json=payload)
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["status"] == "completed"
    assert body["cached"] is False
    assert client.get(body["output_url"]).status_code == 200

    second = client.post("/api/tryon", json=payload).json()
    assert second["cached"] is True
    assert second["public_id"] == body["public_id"]


def test_tryon_rejects_bad_image(client):
    shirt = client.get("/api/clothing", params={"category": "shirts"}).json()[0]
    resp = client.post(
        "/api/tryon",
        json={"clothing_id": shirt["id"], "person_image": "x" * 64},
    )
    assert resp.status_code == 422


def test_phase2_engine_reports_unavailable(client):
    shirt = client.get("/api/clothing", params={"category": "shirts"}).json()[0]
    resp = client.post(
        "/api/tryon",
        json={
            "clothing_id": shirt["id"],
            "person_image": _fake_person(),
            "engine": "catvton",
            "pose_landmarks": _fake_pose(),
        },
    )
    assert resp.status_code == 503
    assert "CatVTON" in resp.json()["detail"]


def test_engines_report_execution_mode(client):
    engines = {e["name"]: e for e in client.get("/api/tryon/engines").json()}
    assert engines["overlay"]["execution"] == "inline"
    assert engines["catvton"]["execution"] == "queued"


def test_queued_engine_returns_202_then_completes(client):
    shirt = client.get("/api/clothing", params={"category": "shirts"}).json()[0]
    BlockingFakeEngine.gate.set()  # do not block this one
    resp = client.post(
        "/api/tryon",
        json={
            "clothing_id": shirt["id"],
            "person_image": _fake_person(320, 240),
            "engine": "fake-queued",
            "pose_landmarks": _fake_pose(),
        },
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["status"] == "pending"
    assert body["output_url"] is None

    done = _poll(client, body["public_id"])
    assert done["status"] == "completed", done
    assert done["progress"] == 1.0
    assert client.get(done["output_url"]).status_code == 200


def test_queued_cache_hit_skips_the_queue(client):
    """A cached result must come back 200 even for a queued engine."""
    shirt = client.get("/api/clothing", params={"category": "shirts"}).json()[0]
    payload = {
        "clothing_id": shirt["id"],
        "person_image": _fake_person(321, 241),
        "engine": "fake-queued",
        "pose_landmarks": _fake_pose(),
    }
    BlockingFakeEngine.gate.set()
    first = client.post("/api/tryon", json=payload)
    assert first.status_code == 202
    _poll(client, first.json()["public_id"])

    second = client.post("/api/tryon", json=payload)
    assert second.status_code == 200, "cache hit must not be queued"
    assert second.json()["cached"] is True


def test_queue_serializes_and_pending_job_can_be_cancelled(client):
    """Depth is 1: the second job waits, so it can still be cancelled."""
    shirt = client.get("/api/clothing", params={"category": "shirts"}).json()[0]
    BlockingFakeEngine.gate.clear()

    def post(width: int):
        return client.post(
            "/api/tryon",
            json={
                "clothing_id": shirt["id"],
                "person_image": _fake_person(width, 240),
                "engine": "fake-queued",
                "pose_landmarks": _fake_pose(),
            },
        ).json()

    busy = post(400)      # worker picks this up and blocks on the gate
    waiting = post(401)   # FIFO behind it, so still PENDING

    cancelled = client.post(f"/api/tryon/{waiting['public_id']}/cancel").json()
    assert cancelled["status"] == "cancelled"
    assert cancelled["cancelled"] is True

    BlockingFakeEngine.gate.set()
    assert _poll(client, busy["public_id"])["status"] == "completed"
    # The worker reaches the cancelled job and must not produce an image.
    settled = _poll(client, waiting["public_id"])
    assert settled["status"] == "cancelled"
    assert settled["output_url"] is None


def test_reaper_fails_orphaned_jobs(client):
    shirt = client.get("/api/clothing", params={"category": "shirts"}).json()[0]
    with SessionLocal() as db:
        orphan = TryOnResult(
            clothing_item_id=shirt["id"],
            engine="fake-queued",
            status=ResultStatus.PROCESSING,
            input_hash="deadbeef" * 8,
        )
        db.add(orphan)
        db.commit()
        public_id = orphan.public_id

        assert tryon_service.reap_orphans(db) >= 1

    body = client.get(f"/api/tryon/{public_id}").json()
    assert body["status"] == "failed"
    assert "interrupted" in body["error"]


def test_settings_roundtrip(client):
    assert client.delete("/api/settings").json()["values"]["mirror"] is True
    updated = client.put("/api/settings", json={"values": {"mirror": False, "nope": 1}}).json()
    assert updated["values"]["mirror"] is False
    assert "nope" not in updated["values"]
    client.delete("/api/settings")


@pytest.mark.parametrize(
    "anchor,expected_count",
    [("torso", 1), ("hips", 1), ("head", 1), ("eyes", 1), ("feet", 2)],
)
def test_placement_solver(anchor, expected_count):
    pts = _fake_pose()["landmarks"]
    places = solve_placements(pts, 640, 480, anchor, 2.0, 0.0, 0.0, 0.0)
    assert len(places) == expected_count
    for p in places:
        assert p.width > 0
        assert 0 <= p.cx <= 640 * 1.5


def test_placement_scales_with_shoulder_width():
    pts = _fake_pose()["landmarks"]
    narrow = solve_placements(pts, 640, 480, "torso", 2.0, 0, 0, 0)[0]
    pts[11] = {"x": 0.25, "y": 0.35, "z": 0, "visibility": 0.9}
    pts[12] = {"x": 0.75, "y": 0.35, "z": 0, "visibility": 0.9}
    wide = solve_placements(pts, 640, 480, "torso", 2.0, 0, 0, 0)[0]
    assert wide.width > narrow.width * 1.9


def test_eyes_anchor_is_mirror_equivariant():
    """The eye line is an *undirected* axis, so its perpendicular has two
    candidates. Pick by left/right landmark order and a selfie feed renders the
    glasses upside down; this pins the shoulder-based disambiguation."""
    pts = _fake_pose()["landmarks"]
    # Head tilted: the subject's left eye rides higher than the right.
    pts[3] = {"x": 0.45, "y": 0.14, "z": 0, "visibility": 0.9}
    pts[6] = {"x": 0.55, "y": 0.20, "z": 0, "visibility": 0.9}
    upright = solve_placements(pts, 640, 480, "eyes", 1.6, 0, 0, 0)[0]

    for p in pts:
        p["x"] = 1.0 - p["x"]
    mirrored = solve_placements(pts, 640, 480, "eyes", 1.6, 0, 0, 0)[0]

    # A tilt, not a 180-degree flip, and the mirror only negates the roll.
    assert abs(upright.angle) < 45
    assert mirrored.angle == pytest.approx(-upright.angle, abs=1e-6)
