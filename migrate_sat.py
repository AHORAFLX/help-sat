"""
migrate_sat.py
==============
Wrapper específico para descargar todo el producto SAT reutilizando migrate.py.

Ventajas:
- fija el filtro `--product SAT`
- conserva el puente a author_articles.py que ya vive dentro de migrate.py
- evita duplicar la lógica principal de generación

Uso:
    python migrate_sat.py
    python migrate_sat.py --output-dir . --clean-output
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Descarga todo el producto SAT reutilizando migrate.py."
    )
    parser.add_argument(
        "--connection-string",
        default="",
        help="ODBC Connection string de SQL Server",
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Archivo .env con la connection string",
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Directorio base donde se generará la carpeta docs",
    )
    parser.add_argument(
        "--clean-output",
        action="store_true",
        help="Borrar output antes de generar",
    )
    args = parser.parse_args()

    script_path = Path(__file__).resolve().parent / "migrate.py"
    cmd = [
        sys.executable,
        "-u",
        str(script_path),
        "--env-file",
        str(args.env_file),
        "--output-dir",
        str(args.output_dir),
        "--product",
        "SAT",
    ]

    if args.connection_string.strip():
        cmd.extend(["--connection-string", args.connection_string.strip()])

    if args.clean_output:
        cmd.append("--clean-output")

    print("=====================================================")
    print(" Lanzando migrate.py específico para el producto SAT ")
    print("=====================================================")
    print(f"[*] Output: {Path(args.output_dir).resolve()}")
    print(f"[*] Comando: {' '.join(cmd)}")

    completed = subprocess.run(cmd, check=False)
    return int(completed.returncode or 0)


if __name__ == "__main__":
    raise SystemExit(main())
