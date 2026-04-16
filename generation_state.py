from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

STATE_FILE_NAME = "generation_state.json"
RUN_STATE_FILE_NAME = ".generation_run_state.json"


def parse_iso_datetime(value: str) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None

    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt


def format_utc_timestamp(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def get_state_path(output_dir: Path) -> Path:
    return output_dir / STATE_FILE_NAME


def get_run_state_path(output_dir: Path) -> Path:
    return output_dir / RUN_STATE_FILE_NAME


def load_generation_state(output_dir: Path) -> dict[str, Any]:
    return _read_json(
        get_state_path(output_dir),
        {"meta": {}, "articles": {}},
    )


def get_last_generated_at(state: dict[str, Any]) -> Optional[datetime]:
    meta = state.get("meta") or {}
    return parse_iso_datetime(meta.get("last_generated_at") or "")


def reset_run_state(output_dir: Path) -> None:
    run_state_path = get_run_state_path(output_dir)
    if run_state_path.exists():
        run_state_path.unlink()


def should_generate_article(
    state: dict[str, Any],
    article_id: str,
    source_updated_at: str,
    output_path: Optional[Path] = None,
) -> bool:
    if output_path is not None and not output_path.exists():
        return True

    articles = state.get("articles") or {}
    entry = articles.get(str(article_id))
    if not entry:
        return True

    if str(entry.get("source_updated_at") or "") != str(source_updated_at or ""):
        return True

    last_generated_at = get_last_generated_at(state)
    source_updated_dt = parse_iso_datetime(source_updated_at)
    if last_generated_at is None or source_updated_dt is None:
        return True

    return source_updated_dt > last_generated_at


def record_generated_article(
    output_dir: Path,
    article_id: str,
    *,
    title: str,
    product: str,
    category_id: str,
    category_name: str,
    folder_id: str,
    folder_name: str,
    path: str,
    source_updated_at: str,
) -> None:
    run_state_path = get_run_state_path(output_dir)
    payload = _read_json(run_state_path, {"articles": {}})
    payload.setdefault("articles", {})
    payload["articles"][str(article_id)] = {
        "title": title,
        "product": product,
        "category_id": category_id,
        "category_name": category_name,
        "folder_id": folder_id,
        "folder_name": folder_name,
        "path": path,
        "source_updated_at": source_updated_at,
    }
    _write_json(run_state_path, payload)


def finalize_generation_state(output_dir: Path, executed_at: Optional[str] = None) -> str:
    state_path = get_state_path(output_dir)
    run_state_path = get_run_state_path(output_dir)

    state = _read_json(state_path, {"meta": {}, "articles": {}})
    run_state = _read_json(run_state_path, {"articles": {}})

    state.setdefault("meta", {})
    state.setdefault("articles", {})

    if not executed_at:
        executed_at = format_utc_timestamp(datetime.now(timezone.utc))

    for article_id, entry in (run_state.get("articles") or {}).items():
        merged = dict(entry or {})
        merged["last_generated_at"] = executed_at
        state["articles"][str(article_id)] = merged

    state["meta"]["last_generated_at"] = executed_at
    _write_json(state_path, state)

    if run_state_path.exists():
        run_state_path.unlink()

    return executed_at
