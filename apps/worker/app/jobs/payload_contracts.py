from __future__ import annotations

from collections.abc import Mapping
from typing import Literal
import logging


CURRENT_PAYLOAD_VERSION = 1
LEGACY_PAYLOAD_VERSION = 0
DEFAULT_ALGORITHM_VERSION = "b4.v1"
LOGGER = logging.getLogger(__name__)

PayloadGeneration = Literal["legacy", "v1"]


def validate_payload_version(
    payload: Mapping[str, object],
    *,
    job_type: str,
) -> PayloadGeneration:
    """Return the explicit generation while keeping queued legacy jobs readable.

    Jobs can outlive the producer revision that created them. Missing versions are
    therefore an explicit, temporary v0 compatibility path; any supplied value
    must be the current integer contract so a future payload is never misread.
    """
    if "payload_version" not in payload:
        LOGGER.warning(
            "worker legacy payload accepted: job_type=%s payload_version=%s",
            job_type,
            LEGACY_PAYLOAD_VERSION,
        )
        return "legacy"

    value = payload["payload_version"]
    if type(value) is not int or value != CURRENT_PAYLOAD_VERSION:
        raise ValueError(
            f"{job_type} payload_version must be {CURRENT_PAYLOAD_VERSION}"
        )
    return "v1"
