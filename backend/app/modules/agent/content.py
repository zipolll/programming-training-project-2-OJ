"""Stable identity of complete authoring content, including code and test data."""

import hashlib
import json

from backend.app.modules.agent.models import GeneratedProblem


def content_hash(generated: GeneratedProblem | None) -> str:
    value = generated.model_dump(mode="json") if generated is not None else None
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()
