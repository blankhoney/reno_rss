#!/usr/bin/env python3
"""Validate the data-only trusted deploy request artifact."""

from __future__ import annotations

import argparse
from io import BytesIO
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import stat
import struct
import sys
from collections.abc import Mapping
from typing import Any, BinaryIO, NoReturn, cast
import zlib
from zipfile import BadZipFile, ZIP_DEFLATED, ZIP_STORED, ZipFile


SCHEMA_VERSION = "trusted-deploy-request/v1"
REQUEST_FIELDS = (
    "schema_version",
    "request_type",
    "environment",
    "image_tag",
    "deploy_sha",
)
REQUEST_FIELD_SET = frozenset(REQUEST_FIELDS)
REQUEST_TYPES = frozenset(("deploy", "rollback"))
ENVIRONMENTS = frozenset(("staging", "prod"))
ARCHIVE_REQUEST_FILES = {
    "trusted-deploy-request.json": "deploy",
    "trusted-rollback-request.json": "rollback",
}
MAX_REQUEST_BYTES = 64 * 1024
MAX_COMPRESSED_BYTES = 64 * 1024
MAX_ARCHIVE_BYTES = 1024 * 1024
MAX_CENTRAL_DIRECTORY_BYTES = 64 * 1024
MAX_ARCHIVE_ENTRIES = 16
_EOCD_STRUCT = struct.Struct("<4s4H2LH")
_SHA_PATTERN = re.compile(r"[0-9a-f]{40}")
_IMAGE_TAG_PATTERN = re.compile(r"sha-[0-9a-f]{40}")


Request = dict[str, str]


class RequestValidationError(ValueError):
    """An input failed the trusted request contract without exposing its contents."""


def _reject(reason: str) -> NoReturn:
    raise RequestValidationError(reason)


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _reject("request JSON contains duplicate keys")
        result[key] = value
    return result


def _reject_json_constant(_: str) -> NoReturn:
    _reject("request JSON contains a non-standard number")


def validate_request(request: object) -> Request:
    """Validate and normalize one decoded trusted request object."""
    if not isinstance(request, Mapping):
        _reject("request JSON must be an object")
    request_values = cast(Mapping[str, object], request)
    if set(request_values) != REQUEST_FIELD_SET:
        _reject("request JSON keys do not match the trusted request schema")

    values: Request = {}
    for field in REQUEST_FIELDS:
        raw_value = request_values[field]
        if type(raw_value) is not str:
            _reject("request fields must be non-empty strings")
        value = cast(str, raw_value)
        if not value:
            _reject("request fields must be non-empty strings")
        if any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
            _reject("request fields must not contain control characters")
        values[field] = value

    schema_version = values["schema_version"]
    request_type = values["request_type"]
    environment = values["environment"]
    image_tag = values["image_tag"]
    deploy_sha = values["deploy_sha"]

    if schema_version != SCHEMA_VERSION:
        _reject("unsupported trusted request schema")
    if request_type not in REQUEST_TYPES:
        _reject("request_type must be deploy or rollback")
    if environment not in ENVIRONMENTS:
        _reject("environment must be staging or prod")
    if _SHA_PATTERN.fullmatch(deploy_sha) is None:
        _reject("deploy_sha must be a 40-character lowercase hexadecimal SHA")
    if _IMAGE_TAG_PATTERN.fullmatch(image_tag) is None:
        _reject("image_tag must use the sha-<40 lowercase hexadecimal> format")
    if image_tag != f"sha-{deploy_sha}":
        _reject("image_tag must equal deploy_sha")

    return values


def validate_request_bytes(payload: bytes) -> Request:
    """Decode UTF-8 JSON and validate it against the trusted request schema."""
    if len(payload) > MAX_REQUEST_BYTES:
        _reject("request JSON exceeds the size limit")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        _reject("request JSON must be UTF-8")

    try:
        decoded = json.loads(
            text,
            object_pairs_hook=_object_without_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except RequestValidationError:
        raise
    except (json.JSONDecodeError, RecursionError, ValueError):
        _reject("request JSON is invalid")
    return validate_request(decoded)


def _read_bounded(stream: BinaryIO, limit: int, *, error: str) -> bytes:
    try:
        payload = stream.read(limit + 1)
    except (OSError, ValueError):
        _reject(error)
    if not isinstance(payload, bytes) or len(payload) > limit:
        _reject(error)
    return payload


def _read_regular_file(path: str | Path, limit: int, *, error: str) -> bytes:
    fd = -1
    try:
        nofollow = getattr(os, "O_NOFOLLOW", None)
        if nofollow is None:
            _reject("request input safe-open is unavailable")
        fd = os.open(
            os.fspath(path),
            os.O_RDONLY | os.O_NONBLOCK | nofollow,
        )
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            _reject("request input must be a regular file")
        with os.fdopen(fd, "rb", closefd=True) as stream:
            fd = -1
            return _read_bounded(stream, limit, error=error)
    except RequestValidationError:
        raise
    except (OSError, ValueError):
        _reject("unable to read request input")
    finally:
        if fd >= 0:
            try:
                os.close(fd)
            except OSError:
                pass


def validate_request_file(path: str | Path) -> Request:
    """Read and validate a plain JSON file, or ``-`` for stdin."""
    if str(path) == "-":
        payload = _read_bounded(
            cast(BinaryIO, getattr(sys.stdin, "buffer", sys.stdin)),
            MAX_REQUEST_BYTES,
            error="request JSON exceeds the size limit or cannot be read",
        )
    else:
        payload = _read_regular_file(
            path,
            MAX_REQUEST_BYTES,
            error="request JSON exceeds the size limit or cannot be read",
        )
    return validate_request_bytes(payload)


def _validate_archive_member_name(name: str) -> None:
    if "\x00" in name:
        _reject("archive member path is invalid")
    if "\\" in name:
        _reject("archive member path must not contain backslashes")
    if name.startswith("/") or PurePosixPath(name).is_absolute():
        _reject("archive member path must not be absolute")
    windows_name = PureWindowsPath(name)
    if windows_name.drive or windows_name.root:
        _reject("archive member path must not be absolute")
    if ".." in name.split("/"):
        _reject("archive member path must not contain parent traversal")


def _validate_archive_container(payload: bytes) -> None:
    if len(payload) > MAX_ARCHIVE_BYTES:
        _reject("request artifact exceeds the archive size limit")
    if len(payload) < _EOCD_STRUCT.size:
        _reject("request artifact is not a valid ZIP archive")

    minimum_eocd_offset = max(0, len(payload) - _EOCD_STRUCT.size - 0xFFFF)
    eocd_offset = payload.rfind(bytes.fromhex("504b0506"))
    if eocd_offset < minimum_eocd_offset:
        _reject("request artifact is not a valid ZIP archive")
    try:
        (
            signature,
            disk_number,
            central_directory_disk,
            entries_on_disk,
            entries_total,
            central_directory_size,
            central_directory_offset,
            comment_length,
        ) = _EOCD_STRUCT.unpack_from(payload, eocd_offset)
    except struct.error:
        _reject("request artifact is not a valid ZIP archive")

    if signature != bytes.fromhex("504b0506"):
        _reject("request artifact is not a valid ZIP archive")
    if eocd_offset + _EOCD_STRUCT.size + comment_length != len(payload):
        _reject("request artifact is not a valid ZIP archive")
    if disk_number != 0 or central_directory_disk != 0:
        _reject("request artifact must be a single-disk ZIP archive")
    if entries_on_disk != entries_total:
        _reject("request artifact has inconsistent entry counts")
    if entries_total > MAX_ARCHIVE_ENTRIES:
        _reject("request artifact has too many entries")
    if central_directory_size > MAX_CENTRAL_DIRECTORY_BYTES:
        _reject("request artifact central directory exceeds the size limit")
    if (
        entries_total in (0xFFFF,)
        or central_directory_size == 0xFFFFFFFF
        or central_directory_offset == 0xFFFFFFFF
    ):
        _reject("request artifact ZIP64 metadata is not supported")
    if central_directory_offset + central_directory_size != eocd_offset:
        _reject("request artifact central directory bounds are invalid")


def _read_archive_payload(archive: ZipFile, member: Any) -> bytes:
    declared_size = member.file_size
    compressed_size = member.compress_size
    if declared_size <= 0 or declared_size > MAX_REQUEST_BYTES:
        _reject("archive member has an invalid uncompressed size")
    if compressed_size < 0 or compressed_size > MAX_COMPRESSED_BYTES:
        _reject("archive member has an invalid compressed size")

    chunks: list[bytes] = []
    total_size = 0
    try:
        with archive.open(member, "r") as source:
            while True:
                chunk = source.read(min(8192, MAX_REQUEST_BYTES - total_size + 1))
                if not chunk:
                    break
                total_size += len(chunk)
                if total_size > MAX_REQUEST_BYTES:
                    _reject("archive member expands beyond the size limit")
                chunks.append(chunk)
    except RequestValidationError:
        raise
    except (BadZipFile, EOFError, OSError, RuntimeError, ValueError, zlib.error):
        _reject("archive member failed integrity checks")

    if total_size != declared_size:
        _reject("archive member size does not match its content")
    return b"".join(chunks)


def validate_request_zip_bytes(payload: bytes) -> Request:
    """Validate one in-memory ZIP artifact emitted by a request workflow."""
    _validate_archive_container(payload)
    try:
        archive = ZipFile(BytesIO(payload), "r")
    except (BadZipFile, OSError, ValueError):
        _reject("request artifact is not a valid ZIP archive")

    with archive:
        try:
            members = archive.infolist()
        except (BadZipFile, OSError, ValueError):
            _reject("request artifact is not a valid ZIP archive")
        if len(members) != 1:
            _reject("request artifact must contain exactly one file")

        member = members[0]
        _validate_archive_member_name(member.filename)
        if member.is_dir() or member.filename.endswith("/") or member.external_attr & 0x10:
            _reject("request artifact must not contain a directory")
        mode = member.external_attr >> 16
        file_type = stat.S_IFMT(mode)
        if file_type not in (0, stat.S_IFREG):
            _reject("request artifact must contain a regular file")
        if member.compress_type not in (ZIP_STORED, ZIP_DEFLATED):
            _reject("archive member uses an unsupported compression method")
        if member.flag_bits & 0x1:
            _reject("request artifact must not contain an encrypted file")

        expected_type = ARCHIVE_REQUEST_FILES.get(member.filename)
        if expected_type is None:
            _reject("request artifact contains an unexpected file")
        payload = _read_archive_payload(archive, member)
        request = validate_request_bytes(payload)
        if request["request_type"] != expected_type:
            _reject("request filename does not match request_type")
        return request


def validate_request_zip(path: str | Path) -> Request:
    """Validate a ZIP artifact file, or ``-`` for stdin."""
    if str(path) == "-":
        payload = _read_bounded(
            cast(BinaryIO, getattr(sys.stdin, "buffer", sys.stdin)),
            MAX_ARCHIVE_BYTES,
            error="request artifact exceeds the archive size limit or cannot be read",
        )
    else:
        payload = _read_regular_file(
            path,
            MAX_ARCHIVE_BYTES,
            error="request artifact exceeds the archive size limit or cannot be read",
        )
    return validate_request_zip_bytes(payload)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate a trusted deploy request")
    parser.add_argument(
        "--artifact-zip",
        action="store_true",
        help="interpret input as a downloaded trusted request ZIP artifact",
    )
    parser.add_argument(
        "input",
        nargs="?",
        type=Path,
        default=Path("-"),
        help="path to the request JSON or ZIP artifact (default: stdin)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        request = validate_request_zip(args.input) if args.artifact_zip else validate_request_file(args.input)
    except RequestValidationError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(json.dumps(request, ensure_ascii=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
