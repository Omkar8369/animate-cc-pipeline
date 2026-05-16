"""Unit tests for Node 6 (per-frame pose estimation).

Pure-Python tests on synthetic data. No Animate, no real pose model.

Run via:
    <python> -m pytest animate_cc_pipeline/tests/test_node6_pose.py -v
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest


# ─── Schema tests ───────────────────────────────────────────────────


def test_pose_map_round_trip():
    from animate_cc_pipeline.pipeline.schemas import (
        Bbox, CharacterPose, FramePoseSet, Joint, JointSet, PoseMap,
    )

    joint = Joint(x=10, y=20, confidence=0.9)
    js = JointSet(nose=joint, neck=joint)
    cp = CharacterPose(
        identity="JETHALAL",
        bbox=Bbox(x=0, y=0, w=100, h=200),
        joints=js,
    )
    fps = FramePoseSet(frameIndex=1, characters=[cp])
    pose_map = PoseMap(schemaVersion=1, shotId="shot_001", frames={"1": fps})

    serialized = pose_map.model_dump_json()
    reloaded = PoseMap.model_validate_json(serialized)
    assert reloaded.shotId == "shot_001"
    assert len(reloaded.frames["1"].characters) == 1
    assert reloaded.frames["1"].characters[0].identity == "JETHALAL"


def test_joint_confidence_validated():
    from animate_cc_pipeline.pipeline.schemas import Joint

    Joint(x=0, y=0, confidence=0.0)  # OK
    Joint(x=0, y=0, confidence=1.0)  # OK
    with pytest.raises(Exception):
        Joint(x=0, y=0, confidence=1.5)
    with pytest.raises(Exception):
        Joint(x=0, y=0, confidence=-0.1)


def test_joints_can_be_null():
    """Joints can be None individually; consumer handles."""
    from animate_cc_pipeline.pipeline.schemas import Joint, JointSet

    js = JointSet(nose=Joint(x=0, y=0, confidence=0.9))
    assert js.nose is not None
    assert js.neck is None
    assert js.wrist_L is None


def test_pose_map_extra_fields_forbidden():
    from animate_cc_pipeline.pipeline.schemas import PoseMap

    with pytest.raises(Exception):
        PoseMap.model_validate_json(
            json.dumps({
                "schemaVersion": 1,
                "shotId": "shot_001",
                "frames": {},
                "extraField": "should fail",
            })
        )


def test_node6_result_aggregate_shape():
    from animate_cc_pipeline.pipeline.schemas import Node6Result, ShotPoseSummary

    result = Node6Result(
        schemaVersion=1,
        backend="mock",
        shots=[
            ShotPoseSummary(
                shotId="shot_001",
                framesProcessed=10,
                charactersFound=20,
                poseMapPath="/abs/path/shot_001/pose_map.json",
            ),
        ],
    )
    serialized = result.model_dump_json()
    reloaded = Node6Result.model_validate_json(serialized)
    assert reloaded.backend == "mock"
    assert len(reloaded.shots) == 1


# ─── Mock backend tests ─────────────────────────────────────────────


def test_mock_backend_returns_all_joints():
    from animate_cc_pipeline.pipeline.pose_backends.mock import MockPoseEstimator
    from animate_cc_pipeline.pipeline.schemas import Bbox

    est = MockPoseEstimator()
    image = np.zeros((400, 400, 3), dtype=np.uint8)
    bbox = Bbox(x=50, y=50, w=100, h=300)
    joints = est.estimate_pose(image, bbox)
    assert joints.nose is not None
    assert joints.neck is not None
    assert joints.shoulder_L is not None
    assert joints.shoulder_R is not None
    assert joints.ankle_L is not None
    assert joints.ankle_R is not None


def test_mock_backend_joints_are_inside_bbox():
    from animate_cc_pipeline.pipeline.pose_backends.mock import MockPoseEstimator
    from animate_cc_pipeline.pipeline.schemas import Bbox

    est = MockPoseEstimator()
    image = np.zeros((1000, 1000, 3), dtype=np.uint8)
    bbox = Bbox(x=100, y=200, w=300, h=600)
    joints = est.estimate_pose(image, bbox)

    # nose should be near the top of the bbox; ankles near the bottom
    assert bbox.y <= joints.nose.y <= bbox.y + bbox.h
    assert bbox.y <= joints.ankle_L.y <= bbox.y + bbox.h
    assert abs(joints.ankle_L.y - (bbox.y + bbox.h)) < 5  # near bottom


def test_mock_backend_name():
    from animate_cc_pipeline.pipeline.pose_backends.mock import MockPoseEstimator
    assert MockPoseEstimator().name == "mock"


def test_mock_backend_is_deterministic():
    from animate_cc_pipeline.pipeline.pose_backends.mock import MockPoseEstimator
    from animate_cc_pipeline.pipeline.schemas import Bbox

    est = MockPoseEstimator()
    bbox = Bbox(x=10, y=20, w=100, h=200)
    image = np.zeros((300, 300, 3), dtype=np.uint8)
    a = est.estimate_pose(image, bbox)
    b = est.estimate_pose(image, bbox)
    assert a.nose.x == b.nose.x
    assert a.ankle_R.y == b.ankle_R.y


# ─── Factory tests ──────────────────────────────────────────────────


def test_factory_returns_mock():
    from animate_cc_pipeline.pipeline.pose_estimator import get_pose_estimator

    est = get_pose_estimator("mock")
    assert est.name == "mock"


def test_factory_http_requires_url():
    from animate_cc_pipeline.pipeline.pose_estimator import get_pose_estimator

    with pytest.raises(ValueError, match="url"):
        get_pose_estimator("http")


def test_factory_http_constructs_with_url():
    from animate_cc_pipeline.pipeline.pose_estimator import get_pose_estimator

    est = get_pose_estimator("http", url="http://localhost:8000")
    assert est.name == "http"


def test_factory_unknown_backend_raises():
    from animate_cc_pipeline.pipeline.pose_estimator import get_pose_estimator

    with pytest.raises(ValueError, match="unknown backend"):
        get_pose_estimator("nonexistent")


def test_factory_dwpose_local_raises_if_deps_missing():
    """Unless torch/onnxruntime are installed, factory should raise
    ImportError pointing at install instructions."""
    from animate_cc_pipeline.pipeline.pose_estimator import get_pose_estimator

    # We don't expect the deps to be installed in unit-test env.
    with pytest.raises((ImportError, ModuleNotFoundError)):
        get_pose_estimator("dwpose_local")


# ─── HTTP client tests (mocked) ─────────────────────────────────────


def test_http_decode_joints_payload_full():
    from animate_cc_pipeline.pipeline.pose_backends.http_client import _decode_joints_payload

    payload = {
        "nose": {"x": 10, "y": 20, "confidence": 0.9},
        "neck": {"x": 10, "y": 30, "confidence": 0.85},
    }
    js = _decode_joints_payload(payload)
    assert js.nose is not None
    assert js.nose.x == 10
    assert js.neck is not None
    assert js.wrist_L is None  # not in payload


def test_http_decode_joints_payload_handles_missing_confidence():
    from animate_cc_pipeline.pipeline.pose_backends.http_client import _decode_joints_payload

    payload = {"nose": {"x": 10, "y": 20}}
    js = _decode_joints_payload(payload)
    assert js.nose is not None
    assert js.nose.confidence == 0.0


def test_http_decode_joints_payload_handles_garbage():
    from animate_cc_pipeline.pipeline.pose_backends.http_client import _decode_joints_payload

    payload = {"nose": "not a dict", "neck": None}
    js = _decode_joints_payload(payload)
    assert js.nose is None
    assert js.neck is None


# ─── CLI end-to-end (mock backend, synthetic data) ─────────────────


def test_cli_end_to_end_with_mock(tmp_path: Path):
    """Synthesize node5_result + character_map + 1 frame; run CLI;
    verify pose_map.json + node6_result.json produced + validate."""
    from animate_cc_pipeline.pipeline.cli_node6_pose import main as cli_main

    # Set up fake input tree
    work_dir = tmp_path / "work"
    frames_root = tmp_path / "frames"

    shot_id = "shot_001"
    shot_dir = frames_root / shot_id
    shot_dir.mkdir(parents=True)

    # Synthesize a tiny PNG frame
    from PIL import Image
    img = Image.new("RGB", (320, 240), color=(100, 150, 200))
    img.save(shot_dir / "frame_0001.png", format="PNG")
    img.save(shot_dir / "frame_0005.png", format="PNG")

    # node5_result.json + per-shot character_map.json
    n5_path = tmp_path / "node5_result.json"
    n5_path.write_text(json.dumps({
        "schemaVersion": 1,
        "shots": [{"shotId": shot_id}],
    }), encoding="utf-8")

    char_map = {
        "schemaVersion": 1,
        "shotId": shot_id,
        "keyPoses": [
            {
                "keyPoseIndex": 0,
                "sourceFrame": 1,
                "detections": [
                    {"identity": "JETHALAL", "boundingBox": {"x": 50, "y": 60, "w": 80, "h": 160}},
                    {"identity": "TAPPU", "boundingBox": {"x": 180, "y": 80, "w": 50, "h": 130}},
                ],
            },
            {
                "keyPoseIndex": 1,
                "sourceFrame": 5,
                "detections": [
                    {"identity": "JETHALAL", "boundingBox": {"x": 60, "y": 60, "w": 80, "h": 160}},
                ],
            },
        ],
    }
    (shot_dir / "character_map.json").write_text(
        json.dumps(char_map), encoding="utf-8",
    )

    # Run CLI
    exit_code = cli_main([
        "--node5-result", str(n5_path),
        "--frames-root", str(frames_root),
        "--work-dir", str(work_dir),
        "--backend", "mock",
        "--log-level", "WARN",
    ])
    assert exit_code == 0

    # Verify outputs
    pose_map_path = work_dir / shot_id / "pose_map.json"
    assert pose_map_path.exists(), f"pose_map.json missing at {pose_map_path}"

    aggregate_path = work_dir / "node6_result.json"
    assert aggregate_path.exists()

    from animate_cc_pipeline.pipeline.schemas import Node6Result, PoseMap

    pose_map = PoseMap.model_validate_json(
        pose_map_path.read_text(encoding="utf-8"),
    )
    assert pose_map.shotId == shot_id
    # 2 keyposes → 2 frames
    assert set(pose_map.frames.keys()) == {"1", "5"}
    assert len(pose_map.frames["1"].characters) == 2
    assert len(pose_map.frames["5"].characters) == 1

    aggregate = Node6Result.model_validate_json(
        aggregate_path.read_text(encoding="utf-8"),
    )
    assert aggregate.backend == "mock"
    assert len(aggregate.shots) == 1
    assert aggregate.shots[0].framesProcessed == 2
    assert aggregate.shots[0].charactersFound == 3  # 2 + 1


def test_cli_fails_on_missing_node5_result(tmp_path):
    from animate_cc_pipeline.pipeline.cli_node6_pose import main as cli_main

    exit_code = cli_main([
        "--node5-result", str(tmp_path / "missing.json"),
        "--frames-root", str(tmp_path / "frames"),
        "--work-dir", str(tmp_path / "work"),
        "--backend", "mock",
        "--log-level", "ERROR",
    ])
    assert exit_code == 1


def test_cli_http_requires_url(tmp_path):
    from animate_cc_pipeline.pipeline.cli_node6_pose import main as cli_main

    # Create a valid node5_result so we get past the input check
    n5 = tmp_path / "node5_result.json"
    n5.write_text(json.dumps({"schemaVersion": 1, "shots": []}), encoding="utf-8")

    exit_code = cli_main([
        "--node5-result", str(n5),
        "--frames-root", str(tmp_path / "frames"),
        "--work-dir", str(tmp_path / "work"),
        "--backend", "http",  # no --http-url
        "--log-level", "ERROR",
    ])
    assert exit_code == 1
