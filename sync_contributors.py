"""Sync GitHub repository contributors into contributing.md."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
CONTRIBUTING_FILE = ROOT / "contributing.md"
DEFAULT_REPOSITORY = "QuantumNovice/awesome-civil-engineering"
START_MARKER = "<!-- github-contributors:start -->"
END_MARKER = "<!-- github-contributors:end -->"
API_VERSION = "2022-11-28"
PER_PAGE = 100
REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
LOGIN_PATTERN = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$"
)
PROFILE_PATTERN = re.compile(
    r"https://github\.com/"
    r"([A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?)"
    r"(?=[\s)/?#]|$)",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class Contributor:
    """A GitHub user associated with commits in the repository."""

    login: str
    profile_url: str


def parse_contributors(payload: Any) -> tuple[Contributor, ...]:
    """Validate an API page and return its human GitHub accounts."""
    if not isinstance(payload, list):
        raise ValueError("GitHub contributor response was not a list")

    contributors: dict[str, Contributor] = {}
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("GitHub contributor response contained an invalid item")

        login = item.get("login")
        account_type = item.get("type")
        if (
            account_type == "Bot"
            or not isinstance(login, str)
            or login.casefold().endswith("[bot]")
        ):
            continue
        if not LOGIN_PATTERN.fullmatch(login):
            raise ValueError(f"GitHub returned an invalid contributor login: {login!r}")

        key = login.casefold()
        contributors[key] = Contributor(
            login=login,
            profile_url=f"https://github.com/{login}",
        )

    return tuple(contributors.values())


def fetch_contributors(
    repository: str,
    token: str | None = None,
) -> tuple[Contributor, ...]:
    """Fetch every page of contributors for an owner/repository name."""
    if not REPOSITORY_PATTERN.fullmatch(repository):
        raise ValueError("repository must have the form owner/name")

    contributors: dict[str, Contributor] = {}
    page = 1
    while True:
        url = (
            f"https://api.github.com/repos/{repository}/contributors"
            f"?per_page={PER_PAGE}&page={page}"
        )
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "awesome-civil-engineering-contributor-sync",
            "X-GitHub-Api-Version": API_VERSION,
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"

        request = Request(url, headers=headers)
        with urlopen(request, timeout=30) as response:
            raw_body = response.read()

        payload = json.loads(raw_body) if raw_body else []
        page_contributors = parse_contributors(payload)
        for contributor in page_contributors:
            contributors[contributor.login.casefold()] = contributor

        if len(payload) < PER_PAGE:
            break
        page += 1

    return tuple(
        sorted(
            contributors.values(),
            key=lambda contributor: contributor.login.casefold(),
        )
    )


def _marker_positions(document: str) -> tuple[int, int]:
    """Return the contributor marker positions, rejecting malformed documents."""
    if document.count(START_MARKER) != 1 or document.count(END_MARKER) != 1:
        raise ValueError(
            "contributing.md must contain exactly one contributor marker pair"
        )

    start = document.index(START_MARKER)
    end = document.index(END_MARKER)
    if start >= end:
        raise ValueError("contributor markers are in the wrong order")
    return start, end


def manual_github_logins(document: str) -> frozenset[str]:
    """Find manually maintained GitHub profiles outside the generated block."""
    start, end = _marker_positions(document)
    manual_text = document[:start] + document[end + len(END_MARKER) :]
    return frozenset(
        match.group(1).casefold()
        for match in PROFILE_PATTERN.finditer(manual_text)
    )


def render_contributors(contributors: tuple[Contributor, ...]) -> str:
    """Render a stable Markdown list."""
    return "\n".join(
        f"- [@{contributor.login}]({contributor.profile_url})"
        for contributor in contributors
    )


def sync_document(
    document: str,
    contributors: tuple[Contributor, ...],
) -> str:
    """Replace the generated block without touching manual acknowledgements."""
    manual_logins = manual_github_logins(document)
    generated = tuple(
        contributor
        for contributor in contributors
        if contributor.login.casefold() not in manual_logins
    )
    body = render_contributors(generated)
    if not body:
        body = "_No additional GitHub contributors._"

    start, end = _marker_positions(document)
    before = document[: start + len(START_MARKER)].rstrip()
    after = document[end:].lstrip()
    return f"{before}\n{body}\n{after}"


def run(
    repository: str,
    contributing_file: Path = CONTRIBUTING_FILE,
    token: str | None = None,
    check: bool = False,
) -> int:
    """Fetch contributors and either update or check the Markdown file."""
    current = contributing_file.read_text(encoding="utf-8")
    updated = sync_document(
        current,
        fetch_contributors(repository, token=token),
    )

    if check:
        if current != updated:
            print(
                f"{contributing_file.name} is out of date; run: "
                f"python sync_contributors.py --repository {repository}",
                file=sys.stderr,
            )
            return 1
        print(f"{contributing_file.name} is up to date")
        return 0

    if current == updated:
        print(f"{contributing_file.name} is already up to date")
        return 0

    contributing_file.write_text(updated, encoding="utf-8", newline="\n")
    print(
        f"Updated {contributing_file.name} from GitHub repository contributors"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository",
        default=os.environ.get("GITHUB_REPOSITORY", DEFAULT_REPOSITORY),
        help=(
            "GitHub owner/repository "
            f"(defaults to {DEFAULT_REPOSITORY})"
        ),
    )
    parser.add_argument(
        "--file",
        type=Path,
        default=CONTRIBUTING_FILE,
        help="contributor Markdown file to update",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail instead of writing when the contributor list is out of date",
    )
    args = parser.parse_args()

    try:
        return run(
            repository=args.repository,
            contributing_file=args.file,
            token=os.environ.get("GITHUB_TOKEN"),
            check=args.check,
        )
    except (HTTPError, URLError, OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
