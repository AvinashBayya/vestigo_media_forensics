from app.services.keyframes import select_keyframes
from app.services.scenes import SceneChange


def times(frames) -> list[float]:
    return [frame.timestamp for frame in frames]


def reasons(frames) -> list[str]:
    return [frame.reason for frame in frames]


def test_first_frame_plus_scenes_plus_uniform_fill() -> None:
    frames = select_keyframes(9.0, [SceneChange(3.02, 0.58), SceneChange(6.02, 0.82)], max_keyframes=40)

    assert len(frames) == 8
    assert [frame.seq for frame in frames] == list(range(1, 9))
    assert times(frames) == sorted(times(frames))
    assert frames[0].timestamp == 0.0
    assert frames[0].reason == "first_frame"
    assert reasons(frames).count("scene_change") == 2
    assert reasons(frames).count("uniform_sample") == 5
    scene_frames = [frame for frame in frames if frame.reason == "scene_change"]
    assert {frame.timestamp for frame in scene_frames} == {3.02, 6.02}
    assert {frame.scene_score for frame in scene_frames} == {0.58, 0.82}


def test_static_video_fills_uniformly() -> None:
    frames = select_keyframes(4.0, [], max_keyframes=40)
    assert len(frames) == 8
    assert reasons(frames) == ["first_frame"] + ["uniform_sample"] * 7
    gaps = [b - a for a, b in zip(times(frames), times(frames)[1:], strict=False)]
    assert all(gap >= 0.25 for gap in gaps)


def test_cap_keeps_first_frame_and_highest_scores() -> None:
    scenes = [SceneChange(float(t), score) for t, score in [(1, 0.4), (2, 0.9), (3, 0.5), (4, 0.8)]]
    frames = select_keyframes(10.0, scenes, max_keyframes=3)

    assert len(frames) == 3
    assert frames[0].reason == "first_frame"
    assert {frame.timestamp for frame in frames[1:]} == {2.0, 4.0}  # the two highest scores
    assert times(frames) == sorted(times(frames))


def test_candidates_near_an_existing_frame_are_dropped() -> None:
    frames = select_keyframes(9.0, [SceneChange(0.1, 0.9), SceneChange(5.0, 0.5)], max_keyframes=40)
    assert 0.1 not in times(frames)  # within 0.25 s of the first frame
    assert 5.0 in times(frames)


def test_scene_change_at_the_very_end_is_pulled_inside_the_margin() -> None:
    frames = select_keyframes(9.0, [SceneChange(9.0, 0.9)], max_keyframes=40)
    assert max(times(frames)) <= 8.8


def test_zero_duration_still_selects_the_first_frame() -> None:
    frames = select_keyframes(0.0, [], max_keyframes=40)
    assert times(frames) == [0.0]
    assert reasons(frames) == ["first_frame"]
