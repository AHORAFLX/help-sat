"""
migrate_author_bridge.py
========================
Puente ligero para lanzar author_articles.py al finalizar migrate.py
reutilizando las categorías ya resueltas por migrate.
"""

from __future__ import annotations

import subprocess
import sys
import os
from pathlib import Path
from typing import Iterable, Optional


def run_author_articles(
    category_names: Iterable[str],
    output_dir: Path,
    env_file: Path,
    connection_string: str = "",
) -> int:
    """
    Ejecuta author_articles.py con una lista concreta de categorías.
    Las categorías deben venir ya resueltas a nombre exacto.
    """
    unique_categories: list[str] = []
    for name in category_names:
        clean = str(name or "").strip()
        if clean and clean not in unique_categories:
            unique_categories.append(clean)

    if not unique_categories:
        return 0

    script_path = Path(__file__).resolve().parent / "author_articles.py"
    cmd = [
        sys.executable,
        "-u",
        str(script_path),
        "--env-file",
        str(env_file),
        "--output-dir",
        str(output_dir),
        "--categories",
        *unique_categories,
    ]

    if connection_string.strip():
        cmd.extend(["--connection-string", connection_string.strip()])

    print("[*] Ejecutando author_articles.py con las categorías resueltas de migrate...")
    print(f"[*] Categorías reenviadas: {', '.join(unique_categories)}")

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    completed = subprocess.run(cmd, check=False, env=env)
    return int(completed.returncode or 0)

