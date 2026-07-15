"""Render the project README from the JSON catalog."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Annotated

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, ValidationError


ROOT = Path(__file__).resolve().parent
DATA_FILE = ROOT / "data" / "resources.json"
TEMPLATE_FILE = ROOT / "templates" / "README.md.j2"
OUTPUT_FILE = ROOT / "README.md"


class CatalogModel(BaseModel):
    """Shared validation rules for catalog data objects."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_min_length=1,
        str_strip_whitespace=True,
        url_preserve_empty_path=True,
    )


class Resource(CatalogModel):
    """A linked civil-engineering resource."""

    name: str
    url: HttpUrl
    description: str


class Section(CatalogModel):
    """A catalog section which may recursively contain child sections."""

    title: str
    items: tuple[Resource, ...] = ()
    sections: tuple[Section, ...] = ()


class Catalog(CatalogModel):
    """The complete data model used to render the README."""

    title: str
    description: str
    sections: Annotated[tuple[Section, ...], Field(min_length=1)]


class ReadmeGenerator:
    """Load, validate, and render the JSON resource catalog."""

    def __init__(
        self,
        data_file: Path = DATA_FILE,
        template_file: Path = TEMPLATE_FILE,
        output_file: Path = OUTPUT_FILE,
    ) -> None:
        self.data_file = data_file
        self.template_file = template_file
        self.output_file = output_file
        self.environment = self._create_environment()

    def _create_environment(self) -> Environment:
        environment = Environment(
            loader=FileSystemLoader(self.template_file.parent),
            undefined=StrictUndefined,
            autoescape=False,
            keep_trailing_newline=True,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        environment.filters["github_anchor"] = self.github_anchor
        return environment

    @staticmethod
    def github_anchor(value: str) -> str:
        """Return the anchor GitHub uses for the headings in this catalog."""
        value = value.strip().lower()
        value = re.sub(r"[^\w\- ]", "", value, flags=re.UNICODE)
        return value.replace(" ", "-")

    def load_catalog(self) -> Catalog:
        return Catalog.model_validate_json(self.data_file.read_text(encoding="utf-8"))

    def render(self) -> str:
        template = self.environment.get_template(self.template_file.name)
        return template.render(catalog=self.load_catalog()).rstrip() + "\n"

    def is_current(self, rendered: str) -> bool:
        current = (
            self.output_file.read_text(encoding="utf-8")
            if self.output_file.exists()
            else ""
        )
        return current == rendered

    def write(self, rendered: str) -> None:
        self.output_file.write_text(rendered, encoding="utf-8", newline="\n")

    def run(self, check: bool = False) -> int:
        rendered = self.render()
        if check:
            if not self.is_current(rendered):
                print("README.md is out of date; run: python generate.py", file=sys.stderr)
                return 1
            print("README.md is up to date")
            return 0

        self.write(rendered)
        print(
            f"Rendered {self.output_file.relative_to(ROOT)} "
            f"from {self.data_file.relative_to(ROOT)}"
        )
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if README.md does not match the rendered catalog",
    )
    args = parser.parse_args()

    try:
        return ReadmeGenerator().run(check=args.check)
    except (OSError, ValidationError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
