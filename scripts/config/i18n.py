from __future__ import annotations

from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
LANG_PACK_DIR = ROOT_DIR / "config" / "i18n"
LANG_PACK_PREFIX = "config-gui"
DEFAULT_LANGUAGE = "ko"
FALLBACK_LANGUAGE = "en"
SUPPORTED_LANGUAGES = ("ko", "en")


def language_pack_path(language: str) -> Path:
    normalized = normalize_language(language)
    return LANG_PACK_DIR / f"{LANG_PACK_PREFIX}.{normalized}.yaml"


def language_pack_paths() -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for path in sorted(LANG_PACK_DIR.glob(f"{LANG_PACK_PREFIX}.*.yaml")):
        parts = path.name.split(".")
        if len(parts) == 3 and parts[0] == LANG_PACK_PREFIX and parts[2] == "yaml":
            paths[parts[1]] = path
    return paths


def normalize_language(language: str | None) -> str:
    normalized = (language or DEFAULT_LANGUAGE).strip().lower()
    if normalized not in SUPPORTED_LANGUAGES:
        return DEFAULT_LANGUAGE
    return normalized


def read_flat_yaml(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value.startswith(("'", '"')) and value.endswith(("'", '"')) and len(value) >= 2:
            value = value[1:-1]
        data[key] = value
    return data


def load_language_pack(language: str) -> dict[str, str]:
    normalized = normalize_language(language)
    fallback = read_flat_yaml(language_pack_path(FALLBACK_LANGUAGE))
    selected = read_flat_yaml(language_pack_path(normalized))
    merged = dict(fallback)
    merged.update(selected)
    return merged


def language_pack_key_sets() -> dict[str, set[str]]:
    return {language: set(read_flat_yaml(path)) for language, path in language_pack_paths().items()}


def validate_language_pack_keys(reference_language: str = FALLBACK_LANGUAGE) -> dict[str, list[str]]:
    key_sets = language_pack_key_sets()
    reference = normalize_language(reference_language)
    reference_keys = key_sets.get(reference, set())
    missing_by_language: dict[str, list[str]] = {}
    for language, keys in sorted(key_sets.items()):
        missing = sorted(reference_keys - keys)
        extra = sorted(keys - reference_keys)
        if missing or extra:
            missing_by_language[language] = [*(f"missing:{key}" for key in missing), *(f"extra:{key}" for key in extra)]
    return missing_by_language
