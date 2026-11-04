from app.services.scenes import parse_scene_output

SAMPLE = """frame:0    pts:38694   pts_time:3.022969
lavfi.scene_score=0.578790
frame:1    pts:77094   pts_time:6.022969
lavfi.scene_score=0.815763
"""


def test_parse_scene_output_pairs_times_with_scores() -> None:
    changes = parse_scene_output(SAMPLE)
    assert [(c.time, c.score) for c in changes] == [(3.023, 0.5788), (6.023, 0.8158)]


def test_parse_scene_output_ignores_noise_and_orphan_lines() -> None:
    assert parse_scene_output("") == []
    assert parse_scene_output("lavfi.scene_score=0.9\n") == []  # a score with no frame line
    noisy = "something else\nframe:0 pts:1 pts_time:1.0\nunrelated\nlavfi.scene_score=0.5\n"
    assert [(c.time, c.score) for c in parse_scene_output(noisy)] == [(1.0, 0.5)]
    # A frame line without a score does not inherit the next frame's score.
    dropped = "frame:0 pts:1 pts_time:1.0\nframe:1 pts:2 pts_time:2.0\nlavfi.scene_score=0.7\n"
    assert [(c.time, c.score) for c in parse_scene_output(dropped)] == [(2.0, 0.7)]
