from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.main import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Export the FastAPI OpenAPI schema.")
    parser.add_argument("--out", required=True, help="Path to write the OpenAPI JSON schema.")
    args = parser.parse_args()

    output_path = Path(args.out)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    schema = create_app().openapi()
    output_path.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
