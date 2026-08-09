#!/usr/bin/env python3
"""Publish PhiGraph paper v2 as a new Zenodo version (InvenioRDM API)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
ZENODO_DIR = ROOT / "paper" / "zenodo"
METADATA_PATH = ROOT / "paper" / "zenodo_metadata.json"
BASE_URL = "https://zenodo.org"
LATEST_RECORD_ID = "21689514"
ORCID = "0009-0001-8797-9789"

UPLOAD_FILES = (
    "PhiGraph_Paper_v2_draft.pdf",
    "PhiGraph_Paper_v2_draft.docx",
    "main.tex",
    "references.bib",
    "LICENSE.md",
    "zenodo_metadata.json",
    "PhiGraph_Paper_v2_readable.md",
)

JSON_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/vnd.inveniordm.v1+json",
}
OCTET_HEADERS = {
    "Content-Type": "application/octet-stream",
}


def _auth_headers(token: str, extra: dict | None = None) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    if extra:
        headers.update(extra)
    return headers


def _session(token: str) -> requests.Session:
    session = requests.Session()
    session.headers.update(_auth_headers(token, JSON_HEADERS))
    return session


def _load_legacy_metadata() -> dict:
    with METADATA_PATH.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload["metadata"]


def _invenio_metadata(legacy: dict) -> dict:
    keywords = legacy.get("keywords") or []
    related = []
    for item in legacy.get("related_identifiers") or []:
        related.append(
            {
                "identifier": item["identifier"],
                "scheme": "url" if item["identifier"].startswith("http") else "doi",
                "relation_type": {"id": item["relation"].lower()},
                "resource_type": {"id": item.get("resource_type", "software")},
            }
        )
    notes = legacy.get("notes")
    description = legacy["description"]
    if notes:
        description = f"{description}\n\n{notes}"
    return {
        "title": legacy["title"],
        "publication_date": legacy["publication_date"],
        "description": description,
        "resource_type": {"id": "publication-preprint"},
        "creators": [
            {
                "person_or_org": {
                    "family_name": "Calmels von Dem Knesebeck",
                    "given_name": "Walter",
                    "name": "Calmels von Dem Knesebeck, Walter",
                    "type": "personal",
                    "identifiers": [{"scheme": "orcid", "identifier": ORCID}],
                },
                "affiliations": [{"name": "TUCH Systems"}],
            }
        ],
        "keywords": [{"keyword": kw} for kw in keywords],
        "languages": [{"id": legacy.get("language", "eng"), "title": {"en": "English"}}],
        "license": {"id": legacy.get("license", "cc-by-4.0")},
        "publisher": "Zenodo",
        "related_identifiers": related,
    }


def _ensure_new_version_draft(session: requests.Session, record_id: str) -> dict:
    parent_id = "21689513"
    versions_url = f"{BASE_URL}/api/records/{record_id}/versions"
    parent = session.get(f"{BASE_URL}/api/records/{parent_id}", headers=JSON_HEADERS)
    if parent.ok:
        latest_draft_api = parent.json().get("links", {}).get("latest_draft")
        if latest_draft_api:
            draft = session.get(latest_draft_api, headers=JSON_HEADERS)
            draft.raise_for_status()
            print(f"Reusing existing draft: {latest_draft_api}")
            return draft.json()
        # Fall back: search versions for latest draft record id.
        versions = session.get(
            f"{BASE_URL}/api/records/{parent_id}/versions",
            headers=JSON_HEADERS,
            params={"sort": "version", "size": 5},
        )
        if versions.ok:
            for hit in versions.json().get("hits", {}).get("hits", []):
                if hit.get("is_draft") or hit.get("status") == "draft":
                    draft_url = hit["links"].get("self") or hit["links"].get("draft")
                    if draft_url:
                        draft = session.get(
                            draft_url if "/draft" in draft_url else f"{draft_url}/draft",
                            headers=JSON_HEADERS,
                        )
                        if draft.ok:
                            print(f"Reusing existing draft: {draft.url}")
                            return draft.json()

    create = session.post(versions_url, headers=JSON_HEADERS)
    if create.status_code == 400:
        draft_probe = session.get(
            f"{BASE_URL}/api/records/21865341/draft",
            headers=JSON_HEADERS,
        )
        if draft_probe.ok and draft_probe.json().get("is_draft"):
            print(f"Reusing existing draft: {draft_probe.url}")
            return draft_probe.json()
    if create.status_code == 400 and "draft version already exists" in create.text.lower():
        parent = session.get(f"{BASE_URL}/api/records/{parent_id}", headers=JSON_HEADERS)
        parent.raise_for_status()
        latest_draft_api = parent.json()["links"]["latest_draft"]
        draft = session.get(latest_draft_api, headers=JSON_HEADERS)
        draft.raise_for_status()
        print(f"Reusing existing draft: {latest_draft_api}")
        return draft.json()
    create.raise_for_status()
    body = create.json()
    if body.get("is_draft"):
        print(f"Created new version draft: {body['links']['self']}")
        return body
    draft_url = body["links"].get("latest_draft") or body["links"]["self"]
    draft = session.get(draft_url, headers=JSON_HEADERS)
    draft.raise_for_status()
    print(f"Created new version draft: {draft_url}")
    return draft.json()


def _clear_draft_files(session: requests.Session, draft: dict) -> None:
    files_url = draft["links"]["files"]
    listing = session.get(files_url, headers=JSON_HEADERS)
    listing.raise_for_status()
    for entry in listing.json().get("entries", []):
        delete_url = entry["links"]["self"]
        deleted = session.delete(delete_url, headers=JSON_HEADERS)
        deleted.raise_for_status()
        print(f"Removed inherited file: {entry['key']}")


def _upload_file(session: requests.Session, token: str, files_url: str, path: Path) -> None:
    init = session.post(files_url, headers=JSON_HEADERS, json=[{"key": path.name}])
    if init.status_code == 400 and "already exists" in init.text.lower():
        delete_url = f"{files_url}/{path.name}"
        deleted = session.delete(delete_url, headers=JSON_HEADERS)
        deleted.raise_for_status()
        init = session.post(files_url, headers=JSON_HEADERS, json=[{"key": path.name}])
    init.raise_for_status()
    entries = init.json()["entries"]
    entry = next((item for item in entries if item["key"] == path.name), entries[0])
    commit_url = entry["links"]["commit"]
    with path.open("rb") as handle:
        uploaded = session.put(
            entry["links"]["content"],
            headers=_auth_headers(token, OCTET_HEADERS),
            data=handle,
        )
    uploaded.raise_for_status()
    committed = session.post(commit_url, headers=JSON_HEADERS)
    if committed.status_code == 404:
        listing = session.get(files_url, headers=JSON_HEADERS)
        listing.raise_for_status()
        for item in listing.json().get("entries", []):
            if item["key"] == path.name and item.get("status") == "completed":
                print(f"Uploaded: {path.name} ({path.stat().st_size} bytes, already committed)")
                return
    committed.raise_for_status()
    print(f"Uploaded: {path.name} ({path.stat().st_size} bytes)")


def _update_draft(session: requests.Session, draft: dict, metadata: dict, preview_key: str) -> dict:
    draft_url = draft["links"]["self"]
    body: dict = {
        "access": {"record": "public", "files": "public"},
        "files": {"enabled": True},
        "metadata": metadata,
    }
    if draft.get("pids"):
        body["pids"] = draft["pids"]
    updated = session.put(draft_url, headers=JSON_HEADERS, json=body)
    updated.raise_for_status()
    result = updated.json()
    preview = session.put(
        draft_url,
        headers=JSON_HEADERS,
        json={
            "access": {"record": "public", "files": "public"},
            "files": {"enabled": True, "default_preview": preview_key},
            "metadata": metadata,
            **({"pids": result["pids"]} if result.get("pids") else {}),
        },
    )
    preview.raise_for_status()
    return preview.json()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Publish the draft after upload (default: leave as draft for review).",
    )
    parser.add_argument(
        "--record-id",
        default=LATEST_RECORD_ID,
        help=f"Latest published record id (default: {LATEST_RECORD_ID}).",
    )
    args = parser.parse_args()

    token = os.environ.get("ZENODO_ACCESS_TOKEN", "").strip()
    if not token:
        print(
            "Missing ZENODO_ACCESS_TOKEN.\n"
            "Create one at https://zenodo.org/account/settings/applications/new/\n"
            "  scopes: deposit:write, deposit:actions\n"
            "Then run:\n"
            "  $env:ZENODO_ACCESS_TOKEN='...'\n"
            "  py -3 scripts/upload_zenodo_paper_v2.py --publish",
            file=sys.stderr,
        )
        return 1

    missing = [name for name in UPLOAD_FILES if not (ZENODO_DIR / name).exists()]
    if missing:
        print(f"Missing files in {ZENODO_DIR}: {', '.join(missing)}", file=sys.stderr)
        print("Run: powershell -ExecutionPolicy Bypass -File paper/build.ps1", file=sys.stderr)
        return 1

    session = _session(token)
    legacy = _load_legacy_metadata()
    metadata = _invenio_metadata(legacy)
    draft = _ensure_new_version_draft(session, args.record_id)
    _clear_draft_files(session, draft)
    files_url = draft["links"]["files"]
    for name in UPLOAD_FILES:
        _upload_file(session, token, files_url, ZENODO_DIR / name)
    draft = _update_draft(session, draft, metadata, "PhiGraph_Paper_v2_draft.pdf")

    draft_html = draft["links"].get("self_html") or draft["links"].get("self")
    print(f"Draft ready: {draft_html}")

    if not args.publish:
        print("Draft saved (not published). Re-run with --publish when ready.")
        return 0

    publish_url = draft["links"]["publish"]
    published = session.post(publish_url, headers=JSON_HEADERS)
    published.raise_for_status()
    body = published.json()
    doi = body.get("pids", {}).get("doi", {}).get("identifier") or body.get("doi")
    record_url = body.get("links", {}).get("self_html") or body.get("links", {}).get("record_html")
    print(f"Published: {record_url}")
    if doi:
        print(f"Version DOI: https://doi.org/{doi}")
        print(f"Concept DOI: https://doi.org/10.5281/zenodo.21689513")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
