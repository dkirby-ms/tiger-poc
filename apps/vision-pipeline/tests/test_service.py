from pathlib import Path

import pytest

cv2 = pytest.importorskip("cv2")

from frame_grabber.service import GrabberConfig, sample_interval, sampled_frames


def test_sample_interval_selects_expected_source_stride() -> None:
    assert sample_interval(30, 5) == 6
    assert sample_interval(15, 30) == 1


def test_sample_interval_rejects_invalid_rates() -> None:
    with pytest.raises(ValueError):
        sample_interval(0, 5)


def test_sampled_frames_reads_a_recorded_video_fixture(tmp_path: Path) -> None:
    fixture_path = tmp_path / "recorded-fixture.mp4"
    writer = cv2.VideoWriter(
        str(fixture_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        10,
        (32, 24),
    )
    if not writer.isOpened():
        pytest.skip("OpenCV MP4 encoder is unavailable")
    for frame_number in range(10):
        frame = __import__("numpy").full((24, 32, 3), frame_number, dtype="uint8")
        writer.write(frame)
    writer.release()

    capture = cv2.VideoCapture(str(fixture_path))
    selected = list(sampled_frames(capture, 2))
    capture.release()

    assert [index for index, _ in selected] == [0, 5]


def test_file_configuration_is_supported() -> None:
    config = GrabberConfig(
        source="/media/sample.mp4",
        source_type="file",
        camera_id="recorded-camera",
        sample_rate=2,
        output_url="http://pre-processor:8080/frames",
    )
    assert config.source_type == "file"