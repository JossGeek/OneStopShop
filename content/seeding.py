import json
import re
import uuid
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
TASK2_SEED_PATH = ROOT_DIR / "seed_data" / "task2" / "OSS_Mapping_Seed.json"
TASK3_SAMPLE_PATH = ROOT_DIR / "seed_data" / "task3" / "OSS_Sample_Offers.json"

PLACEHOLDER_PATTERN = re.compile(r"^\{([a-zA-Z0-9_]+)\}$")
UUID_NAMESPACE = uuid.UUID("7fb7cb8f-9536-41f6-a908-80fa31d8dc2d")

FICTIONAL_OFFER_PLACEHOLDERS = {
    "{offer_006}",
    "{offer_015}",
    "{offer_016}",
    "{offer_017}",
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_task2_seed() -> dict[str, Any]:
    return load_json(TASK2_SEED_PATH)


def load_task3_samples() -> dict[str, Any]:
    return load_json(TASK3_SAMPLE_PATH)


def uuid_from_token(token: str) -> uuid.UUID:
    return uuid.uuid5(UUID_NAMESPACE, token)


def resolve_uuid(value: str) -> uuid.UUID:
    match = PLACEHOLDER_PATTERN.match(value)
    if match:
        return uuid_from_token(match.group(1))
    return uuid.UUID(value)
