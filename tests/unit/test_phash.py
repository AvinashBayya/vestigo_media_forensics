import re

from app.services.duplicates import LibraryEntry, find_matches
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
        LibraryEntry("art_far", "b" * 64, "ffffffffffffffff"),
        LibraryEntry("art_near", "c" * 64, "000000000000000f"),
        LibraryEntry("art_same_look", "d" * 64, "0000000000000000"),
        LibraryEntry("art_exact_unanalysed", own_sha, None),
        LibraryEntry("art_unanalysed", "e" * 64, None),
    ]

    result = find_matches(own_sha, own_hash, library, threshold=10)

    assert [(m.artifact_id, m.match_type, m.distance) for m in result.matches] == [
        ("art_exact_unanalysed", "exact_file", 0),
        ("art_same_look", "visually_identical", 0),
        ("art_near", "near", 4),
    ]
    assert result.matches[2].similarity == round(1 - 4 / 64, 4)
    assert result.library_size == 5
    assert result.compared == 3
