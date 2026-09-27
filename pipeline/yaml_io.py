"""Small helpers shared by every agent for reading/writing the pipeline's YAML files."""
from __future__ import annotations

import re
import yaml

_FENCE_RE = re.compile(r"^```(?:yaml)?\s*\n(.*)\n```\s*$", re.DOTALL)


def parse_llm_yaml(raw_text: str) -> dict:
    """
    Agents are instructed to output pure YAML with nothing else, but models
    sometimes wrap it in a ```yaml fence anyway. Strip that defensively,
    then parse. Raises yaml.YAMLError with the offending text attached if
    parsing fails -- callers should treat that as "the agent violated its
    contract" and surface it, not swallow it.
    """
    text = raw_text.strip()
    m = _FENCE_RE.match(text)
    if m:
        text = m.group(1)
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise yaml.YAMLError(
            f"agent response was not valid YAML after fence-stripping:\n{text[:500]}"
        ) from e


def load_yaml_file(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def dump_yaml_file(path: str, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True, width=100)
