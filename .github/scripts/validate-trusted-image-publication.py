#!/usr/bin/env python3
"""Validate a trusted image publication artifact emitted by canonical CI."""

from __future__ import annotations

import argparse
import importlib.util
from io import BytesIO
import json
from pathlib import Path
import re
import stat
import sys
from collections.abc import Mapping
from typing import Any, BinaryIO, NoReturn, cast
from zipfile import BadZipFile, ZIP_DEFLATED, ZIP_STORED, ZipFile

# Reuse the request parser's bounded file and ZIP implementation so both trusted
# artifacts have one security boundary for filesystem and archive handling.
_REQUEST_VALIDATOR_PATH = Path(__file__).with_name("validate-trusted-deploy-request.py")
_REQUEST_VALIDATOR_SPEC = importlib.util.spec_from_file_location(
    "trusted_artifact_request_validator", _REQUEST_VALIDATOR_PATH
)
if _REQUEST_VALIDATOR_SPEC is None or _REQUEST_VALIDATOR_SPEC.loader is None:
    raise RuntimeError("unable to load trusted artifact security helpers")
_request_validator = importlib.util.module_from_spec(_REQUEST_VALIDATOR_SPEC)
_REQUEST_VALIDATOR_SPEC.loader.exec_module(_request_validator)
MAX_ARCHIVE_BYTES = _request_validator.MAX_ARCHIVE_BYTES
MAX_REQUEST_BYTES = _request_validator.MAX_REQUEST_BYTES
RequestValidationError = _request_validator.RequestValidationError
_read_archive_payload = _request_validator._read_archive_payload
_read_bounded = _request_validator._read_bounded
_read_regular_file = _request_validator._read_regular_file
_validate_archive_container = _request_validator._validate_archive_container
_validate_archive_member_name = _request_validator._validate_archive_member_name

SCHEMA_VERSION = "trusted-image-publication/v1"
PUBLICATION_FILE = "trusted-image-publication.json"
PUBLICATION_FIELDS = (
    "schema_version",
    "repository",
    "workflow_id",
    "run_id",
    "run_attempt",
    "deploy_sha",
    "image_tag",
    "images",
)
IMAGE_NAMES = ("web", "api", "worker")
IMAGE_FIELDS = ("repository", "digest")
_IMAGE_PACKAGES = {
    "web": "ai-reader-web",
    "api": "ai-reader-api",
    "worker": "ai-reader-worker",
}
_SHA_PATTERN = re.compile(r"[0-9a-f]{40}")
_DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
_POSITIVE_INTEGER_PATTERN = re.compile(r"[1-9][0-9]*")
_REPOSITORY_PATTERN = re.compile(r"[^/\s]+/[^/\s]+")

Publication = dict[str, Any]


class PublicationValidationError(ValueError):
    """An input failed the publication contract without exposing its contents."""


def _reject(reason: str) -> NoReturn:
    raise PublicationValidationError(reason)


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _reject("publication JSON contains duplicate keys")
        result[key] = value
    return result


def _reject_json_constant(_: str) -> NoReturn:
    _reject("publication JSON contains a non-standard number")


def _validated_string(value: object, *, field: str) -> str:
    if type(value) is not str or not value:
        _reject(f"{field} must be a non-empty string")
    text = cast(str, value)
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in text):
        _reject("publication fields must not contain control characters")
    return text


def validate_publication(
    publication: object, *, expected_repository: str
) -> Publication:
    """Validate and normalize one decoded trusted publication object."""
    if _REPOSITORY_PATTERN.fullmatch(expected_repository) is None:
        _reject("expected repository must use the owner/repository format")
    if not isinstance(publication, Mapping):
        _reject("publication JSON must be an object")
    values = cast(Mapping[str, object], publication)
    if set(values) != set(PUBLICATION_FIELDS):
        _reject("publication JSON keys do not match the trusted publication schema")

    normalized: Publication = {}
    for field in PUBLICATION_FIELDS[:-1]:
        normalized[field] = _validated_string(values[field], field=field)

    images_raw = values["images"]
    if not isinstance(images_raw, Mapping):
        _reject("images must be an object")
    images = cast(Mapping[str, object], images_raw)
    if set(images) != set(IMAGE_NAMES):
        _reject("images keys must be exactly web, api, and worker")

    normalized_images: dict[str, dict[str, str]] = {}
    expected_registry = f"ghcr.io/{expected_repository.lower()}"
    for image_name in IMAGE_NAMES:
        image_raw = images[image_name]
        if not isinstance(image_raw, Mapping):
            _reject(f"images.{image_name} must be an object")
        image = cast(Mapping[str, object], image_raw)
        if set(image) != set(IMAGE_FIELDS):
            _reject(f"images.{image_name} keys do not match the image schema")
        repository = _validated_string(
            image["repository"], field=f"images.{image_name}.repository"
        )
        digest = _validated_string(image["digest"], field=f"images.{image_name}.digest")
        expected_image_repository = f"{expected_registry}/{_IMAGE_PACKAGES[image_name]}"
        if repository != expected_image_repository:
            _reject(f"images.{image_name}.repository mismatch")
        if _DIGEST_PATTERN.fullmatch(digest) is None:
            _reject(f"images.{image_name}.digest must be a lowercase sha256 digest")
        normalized_images[image_name] = {"repository": repository, "digest": digest}
    normalized["images"] = normalized_images

    if normalized["schema_version"] != SCHEMA_VERSION:
        _reject("unsupported trusted publication schema")
    if normalized["repository"] != expected_repository:
        _reject("publication repository mismatch")
    for field in ("workflow_id", "run_id", "run_attempt"):
        if _POSITIVE_INTEGER_PATTERN.fullmatch(normalized[field]) is None:
            _reject(f"{field} must be a canonical positive integer string")
    deploy_sha = normalized["deploy_sha"]
    if _SHA_PATTERN.fullmatch(deploy_sha) is None:
        _reject("deploy_sha must be a 40-character lowercase hexadecimal SHA")
    if normalized["image_tag"] != f"sha-{deploy_sha}":
        _reject("image_tag must equal sha-<deploy_sha>")

    return normalized


def validate_publication_bytes(payload: bytes, *, expected_repository: str) -> Publication:
    """Decode UTF-8 JSON and validate the trusted publication schema."""
    if len(payload) > MAX_REQUEST_BYTES:
        _reject("publication JSON exceeds the size limit")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        _reject("publication JSON must be UTF-8")
    try:
        decoded = json.loads(
            text,
            object_pairs_hook=_object_without_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except PublicationValidationError:
        raise
    except (json.JSONDecodeError, RecursionError, ValueError):
        _reject("publication JSON is invalid")
    return validate_publication(decoded, expected_repository=expected_repository)


def validate_publication_file(
    path: str | Path, *, expected_repository: str
) -> Publication:
    """Read and validate a plain publication JSON file, or ``-`` for stdin."""
    if str(path) == "-":
        payload = _read_bounded(
            cast(BinaryIO, getattr(sys.stdin, "buffer", sys.stdin)),
            MAX_REQUEST_BYTES,
            error="publication JSON exceeds the size limit or cannot be read",
        )
    else:
        payload = _read_regular_file(
            path,
            MAX_REQUEST_BYTES,
            error="publication JSON exceeds the size limit or cannot be read",
        )
    return validate_publication_bytes(payload, expected_repository=expected_repository)


def validate_publication_zip_bytes(
    payload: bytes, *, expected_repository: str
) -> Publication:
    """Validate one downloaded publication ZIP artifact."""
    try:
        _validate_archive_container(payload)
    except RequestValidationError as error:
        _reject(str(error).replace("request artifact", "publication artifact"))
    try:
        archive = ZipFile(BytesIO(payload), "r")
    except (BadZipFile, OSError, ValueError):
        _reject("publication artifact is not a valid ZIP archive")

    with archive:
        try:
            members = archive.infolist()
        except (BadZipFile, OSError, ValueError):
            _reject("publication artifact is not a valid ZIP archive")
        if len(members) != 1:
            _reject("publication artifact must contain exactly one file")
        member = members[0]
        try:
            _validate_archive_member_name(member.filename)
        except RequestValidationError as error:
            _reject(str(error))
        if member.is_dir() or member.filename.endswith("/") or member.external_attr & 0x10:
            _reject("publication artifact must not contain a directory")
        mode = member.external_attr >> 16
        if stat.S_IFMT(mode) not in (0, stat.S_IFREG):
            _reject("publication artifact must contain a regular file")
        if member.compress_type not in (ZIP_STORED, ZIP_DEFLATED):
            _reject("archive member uses an unsupported compression method")
        if member.flag_bits & 0x1:
            _reject("publication artifact must not contain an encrypted file")
        if member.filename != PUBLICATION_FILE:
            _reject("publication artifact contains an unexpected file")
        try:
            publication_payload = _read_archive_payload(archive, member)
        except RequestValidationError as error:
            _reject(str(error))
        return validate_publication_bytes(
            publication_payload, expected_repository=expected_repository
        )


def validate_publication_zip(
    path: str | Path, *, expected_repository: str
) -> Publication:
    """Read and validate a publication ZIP artifact file, or ``-`` for stdin."""
    if str(path) == "-":
        payload = _read_bounded(
            cast(BinaryIO, getattr(sys.stdin, "buffer", sys.stdin)),
            MAX_ARCHIVE_BYTES,
            error="publication artifact exceeds the size limit or cannot be read",
        )
    else:
        payload = _read_regular_file(
            path,
            MAX_ARCHIVE_BYTES,
            error="publication artifact exceeds the size limit or cannot be read",
        )
    return validate_publication_zip_bytes(payload, expected_repository=expected_repository)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate a trusted image publication")
    parser.add_argument(
        "--expected-repository",
        required=True,
        help="trusted GitHub owner/repository identity",
    )
    parser.add_argument(
        "--artifact-zip",
        action="store_true",
        help="interpret input as a downloaded publication ZIP artifact",
    )
    parser.add_argument(
        "input",
        nargs="?",
        type=Path,
        default=Path("-"),
        help="path to the publication JSON or ZIP artifact (default: stdin)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.artifact_zip:
            publication = validate_publication_zip(
                args.input, expected_repository=args.expected_repository
            )
        else:
            publication = validate_publication_file(
                args.input, expected_repository=args.expected_repository
            )
    except (PublicationValidationError, RequestValidationError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(json.dumps(publication, ensure_ascii=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
