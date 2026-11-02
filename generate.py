"""Render the project README from the JSON catalog."""

from __future__ import annotations

import argparse
import re
import socket
import sys
import urllib.error
import urllib.request
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Annotated

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    ValidationError,
    model_validator,
)


ROOT = Path(__file__).resolve().parent
DATA_FILE = ROOT / "data" / "resources.json"
TEMPLATE_FILE = ROOT / "templates" / "README.md.j2"
OUTPUT_FILE = ROOT / "README.md"
MAX_DESCRIPTION_LENGTH = 80
SHORT_DESCRIPTION_SECTIONS = frozenset({"Web Calculators"})
LINK_TIMEOUT_SECONDS = 20
LINK_WORKERS = 16
BROWSER_RETRY_DELAY_MS = 4000
# Many vendor sites reject scripted requests, so only these count as dead.
DEAD_LINK_STATUSES = frozenset({404, 410})
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)


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

    @model_validator(mode="after")
    def check_unique_urls(self) -> Catalog:
        """Reject resources linked more than once, as awesome-lint does."""
        seen: dict[str, str] = {}
        duplicates: list[str] = []

        def visit(sections: tuple[Section, ...]) -> None:
            for section in sections:
                for item in section.items:
                    key = re.sub(r"^https?://(www\.)?", "", str(item.url).lower()).rstrip("/")
                    if key in seen:
                        duplicates.append(
                            f"{item.url} in {section.title!r} (already in {seen[key]!r})"
                        )
                    else:
                        seen[key] = section.title
                visit(section.sections)

        visit(self.sections)
        if duplicates:
            raise ValueError("duplicate resource URLs: " + "; ".join(duplicates))
        return self

    @model_validator(mode="after")
    def check_short_descriptions(self) -> Catalog:
        """Keep descriptions in length-limited sections to one short line."""
        too_long: list[str] = []

        def visit(sections: tuple[Section, ...]) -> None:
            for section in sections:
                for item in section.items:
                    if len(item.description) > MAX_DESCRIPTION_LENGTH:
                        too_long.append(
                            f"{item.name!r} in {section.title!r} "
                            f"({len(item.description)} chars)"
                        )
                visit(section.sections)

        visit(tuple(s for s in self.sections if s.title in SHORT_DESCRIPTION_SECTIONS))
        if too_long:
            raise ValueError(
                f"descriptions longer than {MAX_DESCRIPTION_LENGTH} characters: "
                + "; ".join(too_long)
            )
        return self


def iter_resources(sections: tuple[Section, ...]) -> Iterator[Resource]:
    for section in sections:
        yield from section.items
        yield from iter_resources(section.sections)


class LinkChecker:
    """Request every resource URL and report the ones that are not live."""

    def __init__(
        self,
        timeout: float = LINK_TIMEOUT_SECONDS,
        workers: int = LINK_WORKERS,
    ) -> None:
        self.timeout = timeout
        self.workers = workers

    def probe(self, url: str) -> tuple[bool, str] | None:
        """Return None if live, else (is_dead, reason)."""
        request = urllib.request.Request(url, headers={"User-Agent": BROWSER_USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                response.read(1)
            return None
        except urllib.error.HTTPError as error:
            return error.code in DEAD_LINK_STATUSES, f"HTTP {error.code}"
        except urllib.error.URLError as error:
            # Only "no such host" is dead; temporary DNS and connection failures are not.
            reason = error.reason
            dead = isinstance(reason, socket.gaierror) and reason.errno == socket.EAI_NONAME
            return dead, str(reason)
        except (TimeoutError, OSError) as error:
            return False, type(error).__name__

    def probe_in_browser(self, urls: list[str]) -> dict[str, tuple[bool, str] | None]:
        """Retry URLs in headless Chromium, which passes most bot filters."""
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright

        def visit(page, url: str) -> int:
            response = page.goto(url, wait_until="domcontentloaded", timeout=self.timeout * 1000)
            return response.status if response else 0

        results: dict[str, tuple[bool, str] | None] = {}
        with sync_playwright() as playwright:
            # The full Chromium build runs the new headless mode, which fewer bot filters reject.
            browser = playwright.chromium.launch(channel="chromium")
            context = browser.new_context(user_agent=BROWSER_USER_AGENT, locale="en-US")
            page = context.new_page()
            for url in urls:
                try:
                    status = visit(page, url)
                    if status >= 400:
                        # Give challenge pages time to set their cookie, then retry once.
                        page.wait_for_timeout(BROWSER_RETRY_DELAY_MS)
                        status = visit(page, url)
                except PlaywrightError as error:
                    results[url] = False, f"browser: {str(error).splitlines()[0]}"
                    continue
                if status < 400:
                    results[url] = None
                else:
                    results[url] = status in DEAD_LINK_STATUSES, f"browser HTTP {status}"
            browser.close()
        return results

    def run(self, catalog: Catalog) -> int:
        resources = list(iter_resources(catalog.sections))
        with ThreadPoolExecutor(self.workers) as executor:
            results = list(executor.map(lambda r: self.probe(str(r.url)), resources))

        retry = [str(r.url) for r, result in zip(resources, results) if result and not result[0]]
        if retry:
            try:
                browser_results = self.probe_in_browser(retry)
            except ImportError:
                print("note: install playwright to recheck blocked links in a browser")
            else:
                results = [
                    browser_results.get(str(r.url), result)
                    for r, result in zip(resources, results)
                ]

        dead = warned = 0
        for resource, result in zip(resources, results):
            if result is None:
                continue
            is_dead, reason = result
            label = "dead" if is_dead else "warning"
            print(f"{label}: {resource.name} <{resource.url}> ({reason})", file=sys.stderr)
            dead += is_dead
            warned += not is_dead

        print(f"Checked {len(resources)} links: {dead} dead, {warned} unverified")
        return 1 if dead else 0


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
    parser.add_argument(
        "--check-links",
        action="store_true",
        help="request every resource URL and fail if any is dead (404/410/unknown host)",
    )
    args = parser.parse_args()

    try:
        if args.check_links:
            return LinkChecker().run(ReadmeGenerator().load_catalog())
        return ReadmeGenerator().run(check=args.check)
    except (OSError, ValidationError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
