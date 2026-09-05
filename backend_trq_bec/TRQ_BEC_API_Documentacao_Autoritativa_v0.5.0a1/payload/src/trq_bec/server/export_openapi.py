"""Export the authoritative TRQ-BEC OpenAPI contract without starting the server."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .app import create_app
from .config import ServerSettings


def export_openapi(output: Path) -> Path:
    settings = ServerSettings(environment="development", docs_enabled=True)
    schema = create_app(settings).openapi()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export the TRQ-BEC LiberRotas OpenAPI contract")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/openapi-liberrotas-v0.5.0a1.json"),
        help="JSON output path",
    )
    args = parser.parse_args(argv)
    path = export_openapi(args.output)
    print(path.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
