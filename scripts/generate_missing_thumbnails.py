#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, cast

import yaml
from PIL import Image, ImageOps

from plugin_resolution import INDEX_YAML_NAME, PLUGINS_DIR, REPO_ROOT, is_reserved_plugin_dirname

INDEX_JSON_PATH = REPO_ROOT / "index.json"
PROMPT_TEMPLATE_PATH = REPO_ROOT / "scripts" / "thumbnail_prompt.md"
GENERATED_THUMBNAILS_DIR = REPO_ROOT / "generated" / "thumbnails"
OPENROUTER_SCRIPT_PATH = REPO_ROOT / "scripts" / "openrouter_image_gen.py"
DEFAULT_MODEL = "google/gemini-3.1-flash-image-preview"


class ThumbnailGenerationError(Exception):
    pass


def _fail(message: str) -> None:
    raise ThumbnailGenerationError(message)


def _load_index_plugins() -> dict[str, dict[str, Any]]:
    if not INDEX_JSON_PATH.exists():
        return {}
    loaded: Any = None
    try:
        loaded = json.loads(INDEX_JSON_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        _fail(f"Unable to parse {INDEX_JSON_PATH.name}: {e}")
    if not isinstance(loaded, dict):
        _fail(f"{INDEX_JSON_PATH.name} must contain a JSON object")
    plugins = loaded.get("plugins")
    if not isinstance(plugins, dict):
        return {}
    return {str(k): cast(dict[str, Any], v) for k, v in plugins.items() if isinstance(k, str) and isinstance(v, dict)}


def _plugin_dirnames() -> list[str]:
    if not PLUGINS_DIR.exists():
        return []
    names: list[str] = []
    for path in sorted(PLUGINS_DIR.iterdir(), key=lambda item: item.name):
        if not path.is_dir():
            continue
        if is_reserved_plugin_dirname(path.name):
            continue
        if not (path / INDEX_YAML_NAME).exists():
            continue
        names.append(path.name)
    return names


def _load_plugin_meta(plugin_name: str) -> dict[str, Any]:
    plugin_yaml_path = PLUGINS_DIR / plugin_name / INDEX_YAML_NAME
    loaded: Any = None
    try:
        loaded = yaml.safe_load(plugin_yaml_path.read_text(encoding="utf-8"))
    except Exception as e:
        _fail(f"Invalid YAML for plugin '{plugin_name}': {e}")
    if not isinstance(loaded, dict):
        _fail(f"{plugin_yaml_path.relative_to(REPO_ROOT)} must contain a YAML mapping/object")
    return cast(dict[str, Any], loaded)


def _plugin_has_repo_thumbnail(plugin_name: str) -> bool:
    plugin_dir = PLUGINS_DIR / plugin_name
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        if (plugin_dir / f"thumbnail{ext}").exists():
            return True
    return False


def _generated_thumbnail_path(plugin_name: str) -> Path:
    return GENERATED_THUMBNAILS_DIR / plugin_name / "thumbnail.jpg"


def _plugins_missing_index_thumbnail() -> list[str]:
    index_plugins = _load_index_plugins()
    missing: list[str] = []
    for plugin_name in _plugin_dirnames():
        index_entry = index_plugins.get(plugin_name)
        if isinstance(index_entry, dict) and isinstance(index_entry.get("thumbnail"), str) and index_entry.get("thumbnail"):
            continue
        if _plugin_has_repo_thumbnail(plugin_name):
            continue
        missing.append(plugin_name)
    return missing


def _prompt_template() -> str:
    if not PROMPT_TEMPLATE_PATH.exists():
        _fail(f"Missing prompt template: {PROMPT_TEMPLATE_PATH.relative_to(REPO_ROOT)}")
    return PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")


def _render_prompt(template: str, plugin_name: str, plugin_description: str) -> str:
    return template.replace("{{PLUGIN_NAME}}", plugin_name.strip()).replace("{{PLUGIN_DESCRIPTION}}", plugin_description.strip())


def _find_generated_source(tmpdir: Path) -> Path:
    candidates = sorted(tmpdir.glob("raw_image*"))
    files = [candidate for candidate in candidates if candidate.is_file()]
    if not files:
        _fail("Image generation did not produce an output file")
    return files[0]


def _generate_raw_image(prompt: str, output_prefix: Path) -> Path:
    model = os.environ.get("OPENROUTER_IMAGE_MODEL", "").strip() or DEFAULT_MODEL
    cmd = [sys.executable, str(OPENROUTER_SCRIPT_PATH), model, prompt, str(output_prefix)]
    result = subprocess.run(cmd, cwd=REPO_ROOT, check=False)
    if result.returncode != 0:
        _fail(f"OpenRouter image generation failed with exit code {result.returncode}")
    return _find_generated_source(output_prefix.parent)


def _save_resized_jpeg(source_path: Path, destination_path: Path) -> None:
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source_path) as image:
        converted = image.convert("RGB")
        fitted = ImageOps.fit(converted, (256, 256), method=Image.Resampling.LANCZOS)
        fitted.save(destination_path, format="JPEG", quality=75, optimize=True)


def _max_generated_thumbnails() -> int | None:
    raw = os.environ.get("MAX_GENERATED_THUMBNAILS", "").strip()
    if not raw:
        return None
    value = 0
    try:
        value = int(raw)
    except ValueError as e:
        _fail(f"MAX_GENERATED_THUMBNAILS must be an integer: {e}")
    if value < 0:
        _fail("MAX_GENERATED_THUMBNAILS must be non-negative")
    return value


def main() -> int:
    template = _prompt_template()
    plugin_names = _plugins_missing_index_thumbnail()
    max_generated = _max_generated_thumbnails()
    if not plugin_names:
        print("No missing thumbnails to generate.")
        return 0
    if max_generated == 0:
        print("MAX_GENERATED_THUMBNAILS=0 specified. Nothing to generate.")
        return 0

    generated = 0
    skipped = 0
    failed: list[str] = []

    for plugin_dir_name in plugin_names:
        if max_generated is not None and generated >= max_generated:
            print(f"Reached MAX_GENERATED_THUMBNAILS={max_generated}. Stopping generation.")
            break
        destination_path = _generated_thumbnail_path(plugin_dir_name)
        if destination_path.exists():
            print(f"Skipping existing generated thumbnail: {destination_path.relative_to(REPO_ROOT)}")
            skipped += 1
            continue
        try:
            meta = _load_plugin_meta(plugin_dir_name)
            title_value = meta.get("title")
            display_name = title_value.strip() if isinstance(title_value, str) and title_value.strip() else plugin_dir_name
            description_value = meta.get("description")
            description = description_value.strip() if isinstance(description_value, str) else ""
            prompt = _render_prompt(template, display_name, description)
            with tempfile.TemporaryDirectory() as tmp:
                tmpdir = Path(tmp)
                raw_source = _generate_raw_image(prompt, tmpdir / "raw_image")
                _save_resized_jpeg(raw_source, destination_path)
            generated += 1
            print(f"Generated thumbnail: {destination_path.relative_to(REPO_ROOT)}")
        except Exception as e:
            failed.append(plugin_dir_name)
            print(f"ERROR: plugin={plugin_dir_name}: {e}")

    print(f"Done. generated={generated} skipped={skipped} failed={len(failed)} total={len(plugin_names)}")
    if failed:
        print("Failed plugins:")
        for plugin_name in failed:
            print(f"- {plugin_name}")
        return 1
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ThumbnailGenerationError as e:
        print(f"ERROR: {e}")
        raise SystemExit(1)
