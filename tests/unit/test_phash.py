import re

from app.services.duplicates import FrameHash, LibraryEntry, find_matches
from app.services.phash import compute_phash, hamming_distance
from tests.fixtures.make_fixtures import FixtureSet


def test_phash_is_a_64_bit_hex_value(fixtures: FixtureSet) -> None:
    result = compute_phash(fixtures.jpeg)

    assert re.fullmatch(r"[0-9a-f]{16}", result.value)
    assert result.frames == 1


def test_identical_images_produce_the_same_hash(fixtures: FixtureSet) -> None:
    assert compute_phash(fixtures.jpeg).value == compute_phash(fixtures.jpeg).value
    # Same pixels in different formats.
    assert compute_phash(fixtures.png).value == compute_phash(fixtures.tiff).value


def test_similar_images_produce_close_hashes(fixtures: FixtureSet) -> None:
    base = compute_phash(fixtures.jpeg).value

    assert hamming_distance(base, compute_phash(fixtures.near_duplicate).value) <= 10
    assert 1 <= hamming_distance(base, compute_phash(fixtures.edited).value) <= 10
    assert hamming_distance(base, compute_phash(fixtures.unrelated).value) > 10


def test_exif_orientation_is_applied_before_hashing(fixtures: FixtureSet) -> None:
    oriented = compute_phash(fixtures.oriented)

    assert hamming_distance(compute_phash(fixtures.jpeg).value, oriented.value) <= 2
    assert any("EXIF orientation 6" in note for note in oriented.normalization)


def test_hamming_distance() -> None:
    assert hamming_distance("0000000000000000", "0000000000000000") == 0
    assert hamming_distance("0000000000000000", "ffffffffffffffff") == 64
    assert hamming_distance("8000000000000001", "0000000000000000") == 2


def test_find_matches_classifies_and_orders_matches() -> None:
    own_sha = "a" * 64
    own_hash = "0000000000000000"
    library = [
        LibraryEntry("art_far", "b" * 64, "image", (FrameHash("ffffffffffffffff"),)),
        LibraryEntry("art_near", "c" * 64, "image", (FrameHash("000000000000000f"),)),
        LibraryEntry("art_same_look", "d" * 64, "image", (FrameHash("0000000000000000"),)),
        LibraryEntry("art_exact_unanalysed", own_sha, "image"),
        LibraryEntry("art_unanalysed", "e" * 64, "image"),
    ]

    result = find_matches(own_sha, [FrameHash(own_hash)], library, threshold=10)

    assert [(m.artifact_id, m.match_type, m.distance) for m in result.matches] == [
        ("art_exact_unanalysed", "exact_file", 0),
        ("art_same_look", "visually_identical", 0),
        ("art_near", "near", 4),
    ]
    assert result.matches[2].similarity == round(1 - 4 / 64, 4)
    assert result.library_size == 5
    assert result.compared == 3


def test_find_matches_pairs_each_query_frame_with_its_best_counterpart() -> None:
    # A video query (three keyframes) against a video entry (two keyframes) and an image entry.
    own = [
        FrameHash("0000000000000000", 1, 0.0),
        FrameHash("00000000000000ff", 2, 3.0),
        FrameHash("ffffffffffffffff", 3, 6.0),
    ]
    video = LibraryEntry(
        "art_video",
        "b" * 64,
        "video",
        (FrameHash("0000000000000003", 1, 1.0), FrameHash("00000000000000ff", 2, 4.0)),
    )
    image = LibraryEntry("art_image", "c" * 64, "image", (FrameHash("0000000000000000"),))

    result = find_matches("a" * 64, own, [video, image], threshold=10)

    by_id = {match.artifact_id: match for match in result.matches}
    video_match = by_id["art_video"]
    assert video_match.match_type == "visually_identical"  # seq 2 pairs exactly
    assert video_match.matched_frame_count == 2  # query frame 3 matched nothing
    pairs = {pair.query_seq: pair for pair in video_match.frame_matches}
    assert pairs[1].matched_seq == 1 and pairs[1].distance == 2
    assert pairs[1].query_timestamp == 0.0 and pairs[1].matched_timestamp == 1.0
    assert pairs[2].matched_seq == 2 and pairs[2].distance == 0

    image_match = by_id["art_image"]
    # Frame detail is kept because the query side is a video: frames 1 (d=0) and 2 (d=8) both
    # pair with the image; frame 3 is beyond the threshold.
    assert image_match.matched_frame_count == 2
    pairs = {pair.query_seq: pair for pair in image_match.frame_matches}
    assert pairs[1].distance == 0 and pairs[1].matched_seq is None
    assert pairs[2].distance == 8 and pairs[2].matched_timestamp is None


def test_image_to_image_matches_keep_the_plain_shape() -> None:
    entry = LibraryEntry("art_other", "b" * 64, "image", (FrameHash("0000000000000001"),))
    result = find_matches("a" * 64, [FrameHash("0000000000000000")], [entry], threshold=10)
    [match] = result.matches
    assert match.matched_frame_count is None
    assert match.frame_matches is None
