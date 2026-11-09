"""Document and PDF analysis (document.v1, Pass 2, D25): parsed in place, never executed."""

from fastapi.testclient import TestClient

from app.core.container import AppServices
from app.services.pdf import PDF_STRUCTURE_LIMITATIONS, PDF_TEXT_LIMITATIONS
from tests.api.test_evidence import VERDICT_WORDS
from tests.fixtures.make_fixtures import FixtureSet
from tests.helpers import assert_error, upload_ok
from tests.pipeline.test_runner import records_for


def analyse_document(client: TestClient, path, options: dict | None = None) -> tuple[str, str]:
    artifact_id = upload_ok(client, path)["artifact_id"]
    payload: dict = {"artifact_id": artifact_id}
    if options is not None:
        payload["options"] = options
    response = client.post("/api/v1/analysis/document", json=payload)
    assert response.status_code == 202, response.text
    return artifact_id, response.json()["job_id"]


def test_pdf_uploads_as_a_document(client: TestClient, fixtures: FixtureSet) -> None:
    body = upload_ok(client, fixtures.pdf)
    assert body["media_type"] == "document"
    assert body["mime_type"] == "application/pdf"

    detail = client.get(f"/api/v1/artifacts/{body['artifact_id']}").json()
    assert detail["media_type"] == "document"
    assert detail["width"] is None and detail["height"] is None


def test_document_pipeline_runs_its_stages(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    _, job_id = analyse_document(client, fixtures.pdf)
    job = client.get(f"/api/v1/analysis/jobs/{job_id}").json()

    assert job["pipeline"] == "document.v1"
    assert [stage["stage"] for stage in job["stages"]] == [
        "hashes",
        "metadata",
        "pdf_structure",
        "pdf_text",
        "pdf_images",
        "structural",
        "duplicates",
    ]
    assert job["status"] in ("completed", "completed_with_errors")


def test_structure_reports_declared_facts_without_validating_them(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    artifact_id, _ = analyse_document(client, fixtures.pdf)
    section = client.get(f"/api/v1/artifacts/{artifact_id}/evidence").json()["pdf_structure"]

    assert section["pdf_version"] == "1.7"
    assert section["object_count"] == 5
    assert section["page_count"] == 1
    assert section["eof_markers"] == 1
    assert section["incremental_updates"] == 0
    assert section["encrypted"] is False
    assert section["signature_count"] == 0
    assert section["provenance"]["classification"] == "OBSERVED"

    text = " ".join(PDF_STRUCTURE_LIMITATIONS).lower()
    assert "does not validate pdf signatures" in text
    assert "never reports a document as signed and valid" in text
    assert "not a finding of wrongdoing" in text


def test_a_second_save_is_reported_as_an_ordinary_incremental_update(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    artifact_id, _ = analyse_document(client, fixtures.pdf_updated)
    section = client.get(f"/api/v1/artifacts/{artifact_id}/evidence").json()["pdf_structure"]

    assert section["eof_markers"] == 2
    assert section["incremental_updates"] == 1
    limitations = " ".join(section["provenance"]["limitations"]).lower()
    assert "not that it was tampered with" in limitations


def test_javascript_and_actions_are_counted_as_structure(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    artifact_id, _ = analyse_document(client, fixtures.pdf_scripted)
    section = client.get(f"/api/v1/artifacts/{artifact_id}/evidence").json()["pdf_structure"]

    markers = section["markers"]
    assert markers["javascript"] >= 1
    assert markers["open_action"] >= 1
    assert markers["interactive_form"] >= 1
    # Reported as presence counts, with no judgement attached.
    assert VERDICT_WORDS.search(" ".join(section["notes"])) is None


def test_text_is_extracted_and_labelled_provisional(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    artifact_id, _ = analyse_document(client, fixtures.pdf)
    section = client.get(f"/api/v1/artifacts/{artifact_id}/evidence").json()["pdf_text"]

    assert "Vestigo fixture document" in section["text"]
    assert section["character_count"] == len(section["text"])
    assert section["streams_read"] == 1
    # Image streams are skipped, not counted as failures.
    assert section["streams_failed"] == 0
    assert section["streams_skipped"] >= 1
    assert section["provenance"]["classification"] == "DERIVED"

    text = " ".join(PDF_TEXT_LIMITATIONS).lower()
    assert "provisional, best-effort text, not a verified transcription" in text
    assert "an empty result does not mean the page has no text" in text
    kinds = {file["kind"] for file in section["provenance"]["derived_files"]}
    assert "pdf_text" in kinds


def test_an_image_only_document_says_the_pages_are_not_blank(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    artifact_id, _ = analyse_document(client, fixtures.pdf_scripted)
    section = client.get(f"/api/v1/artifacts/{artifact_id}/evidence").json()["pdf_text"]

    assert section["text"] == ""
    assert any("does not mean the pages are blank" in note for note in section["notes"])


def test_embedded_jpeg_is_extracted_byte_for_byte(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    artifact_id, _ = analyse_document(client, fixtures.pdf)
    section = client.get(f"/api/v1/artifacts/{artifact_id}/evidence").json()["pdf_images"]

    assert section["extracted"] == 1
    (image,) = section["images"]
    assert image["encoding"] == "DCTDecode"
    assert (image["width"], image["height"]) == (640, 480)

    served = client.get(f"/api/v1/artifacts/{artifact_id}/derived/{image['derived_file_id']}/content")
    assert served.status_code == 200
    # The stored stream, unchanged: identical to the JPEG the fixture embedded.
    assert served.content == fixtures.jpeg.read_bytes()


def test_document_duplicates_are_byte_identical_only(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    first, _ = analyse_document(client, fixtures.pdf)
    second, job_id = analyse_document(client, fixtures.pdf)
    section = client.get(f"/api/v1/artifacts/{second}/evidence").json()["duplicates"]

    assert [match["artifact_id"] for match in section["matches"]] == [first]
    assert section["matches"][0]["match_type"] == "exact_file"
    limitations = " ".join(section["provenance"]["limitations"]).lower()
    assert "byte-identical only" in limitations
    assert "says nothing about which copy came first" in limitations
    assert job_id

    # A re-saved copy of the same document has different bytes and does not match.
    third, _ = analyse_document(client, fixtures.pdf_updated)
    other = client.get(f"/api/v1/artifacts/{third}/evidence").json()["duplicates"]
    assert other["matches"] == []


def test_wrong_endpoint_for_a_document_is_refused(client: TestClient, fixtures: FixtureSet) -> None:
    artifact_id = upload_ok(client, fixtures.pdf)["artifact_id"]
    assert_error(
        client.post("/api/v1/analysis/image", json={"artifact_id": artifact_id}),
        422,
        "WRONG_MEDIA_TYPE",
    )
    image_id = upload_ok(client, fixtures.jpeg)["artifact_id"]
    assert_error(
        client.post("/api/v1/analysis/document", json={"artifact_id": image_id}),
        422,
        "WRONG_MEDIA_TYPE",
    )


def test_document_stages_can_be_switched_off(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    _, job_id = analyse_document(
        client,
        fixtures.pdf,
        {
            "metadata": True,
            "pdf_structure": True,
            "pdf_text": False,
            "pdf_images": False,
            "structural": True,
            "duplicate_search": True,
        },
    )
    skipped = {record.stage for record in records_for(services, job_id) if record.status == "skipped"}
    assert skipped == {"pdf_text", "pdf_images"}


def test_the_original_document_is_never_modified(
    client: TestClient, services: AppServices, fixtures: FixtureSet
) -> None:
    before = fixtures.pdf.read_bytes()
    artifact_id, _ = analyse_document(client, fixtures.pdf)
    assert fixtures.pdf.read_bytes() == before

    served = client.get(f"/api/v1/artifacts/{artifact_id}/content")
    assert served.status_code == 200
    assert served.content == before
