"""Xuất đặc tả API ra docs/openapi.yaml: python -m scripts.export_openapi"""
from pathlib import Path

import yaml

from app.main import app

TARGET = Path(__file__).resolve().parents[2] / "docs" / "openapi.yaml"


def render() -> str:
    return yaml.safe_dump(app.openapi(), allow_unicode=True, sort_keys=False)


if __name__ == "__main__":
    TARGET.write_text(render(), encoding="utf-8")
