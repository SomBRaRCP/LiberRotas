"""Exporta os contratos OpenAPI público e administrativo sem iniciar o servidor."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Literal

from .app import create_app
from .config import ServerSettings

Scope = Literal["public", "internal"]


def export_openapi(output: Path, *, scope: Scope = "public") -> Path:
    settings = ServerSettings(environment="development", docs_enabled=True)
    app = create_app(settings)
    schema = app.state.public_openapi() if scope == "public" else app.state.internal_openapi()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


def _default_output(scope: Scope) -> Path:
    if scope == "internal":
        return Path("docs/openapi-liberrotas-internal-v0.5.0a2.json")
    return Path("docs/openapi-liberrotas-public-v0.5.0a2.json")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Exporta um contrato OpenAPI da TRQ-BEC LiberRotas")
    parser.add_argument(
        "--scope",
        choices=("public", "internal"),
        default="public",
        help="Contrato a exportar: público ou administrativo",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Caminho do arquivo JSON; quando omitido, usa o nome versionado do escopo",
    )
    args = parser.parse_args(argv)
    scope: Scope = args.scope
    path = export_openapi(args.output or _default_output(scope), scope=scope)
    print(path.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
