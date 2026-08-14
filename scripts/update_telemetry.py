"""Generate the local GitHub telemetry panel for the VELI profile.

The script deliberately uses only Python's standard library. It reads public
GitHub REST API endpoints, renders a self-contained SVG, and writes it to the
profile repository. A GITHUB_TOKEN is optional locally and is supplied by the
workflow through GitHub Actions' built-in token.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = "https://api.github.com"
DEFAULT_USERNAME = "oovelianoo"
USER_AGENT = "veli-profile-telemetry/1.0"


def xml_escape(value: Any) -> str:
    """Escape a value for use in SVG text or attributes."""

    return html.escape(str(value), quote=True)


def fetch_json(url: str, token: str | None) -> tuple[Any, str]:
    """Fetch one GitHub API response and return its JSON plus Link header."""

    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=25) as response:
            payload = response.read().decode("utf-8")
            return json.loads(payload), response.headers.get("Link", "")
    except HTTPError as error:
        raise RuntimeError(f"GitHub API returned HTTP {error.code} for {url}") from error
    except URLError as error:
        raise RuntimeError(f"Could not reach GitHub API: {error.reason}") from error


def next_page(link_header: str) -> str | None:
    """Return the URL marked rel=next in a GitHub Link header."""

    for item in link_header.split(","):
        if 'rel="next"' not in item:
            continue
        candidate = item.split(";", 1)[0].strip()
        if candidate.startswith("<") and candidate.endswith(">"):
            return candidate[1:-1]
    return None


def fetch_collection(path: str, token: str | None) -> list[dict[str, Any]]:
    """Fetch all pages of a list endpoint."""

    query = urlencode({"per_page": 100})
    url = f"{API_ROOT}{path}&{query}" if "?" in path else f"{API_ROOT}{path}?{query}"
    items: list[dict[str, Any]] = []
    while url:
        payload, link_header = fetch_json(url, token)
        if not isinstance(payload, list):
            raise RuntimeError(f"Expected a collection from {url}")
        items.extend(item for item in payload if isinstance(item, dict))
        url = next_page(link_header)
    return items


def parse_timestamp(value: str | None) -> datetime | None:
    """Parse GitHub's ISO timestamp into an aware UTC datetime."""

    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def format_number(value: int) -> str:
    """Keep numbers compact and readable in the narrow SVG cards."""

    return f"{value:,}".replace(",", "·")


def collect_stats(username: str, token: str | None) -> dict[str, Any]:
    """Collect transparent public signals for one GitHub account."""

    user_payload, _ = fetch_json(f"{API_ROOT}/users/{username}", token)
    if not isinstance(user_payload, dict):
        raise RuntimeError("GitHub returned an unexpected user payload")

    repositories = fetch_collection(f"/users/{username}/repos?sort=updated&direction=desc", token)
    events = fetch_collection(f"/users/{username}/events/public", token)

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=30)
    recent_events: list[dict[str, Any]] = []
    for event in events:
        created_at = parse_timestamp(event.get("created_at"))
        if created_at and created_at >= cutoff:
            event["_created_at"] = created_at
            recent_events.append(event)

    language_counts = Counter(
        str(repository.get("language"))
        for repository in repositories
        if repository.get("language") and not repository.get("fork", False)
    )

    event_days = {
        event["_created_at"].date()
        for event in recent_events
        if isinstance(event.get("_created_at"), datetime)
    }
    push_events = sum(event.get("type") == "PushEvent" for event in recent_events)
    latest_event = max(
        (event["_created_at"] for event in recent_events if isinstance(event.get("_created_at"), datetime)),
        default=None,
    )

    buckets: list[dict[str, Any]] = []
    bucket_days = 5
    for index in range(6):
        start = now - timedelta(days=(6 - index) * bucket_days)
        end = start + timedelta(days=bucket_days)
        count = sum(
            start <= event["_created_at"] < end
            for event in recent_events
            if isinstance(event.get("_created_at"), datetime)
        )
        buckets.append({"label": start.strftime("%d/%m"), "count": count})

    total_language_signal = sum(language_counts.values())
    language_mix = [
        {"name": name, "percent": round((count / total_language_signal) * 100)}
        for name, count in language_counts.most_common(3)
    ]
    if not language_mix:
        language_mix = [{"name": "NO PUBLIC SIGNAL", "percent": 0}]

    return {
        "username": username,
        "public_repos": int(user_payload.get("public_repos", 0)),
        "followers": int(user_payload.get("followers", 0)),
        "active_days": len(event_days),
        "push_events": push_events,
        "language_mix": language_mix,
        "activity_buckets": buckets,
        "last_activity": latest_event.strftime("%Y-%m-%d") if latest_event else "NO RECENT FEED",
        "sync_date": now.strftime("%Y-%m-%d UTC"),
    }


def metric_card(x: int, label: str, value: str, sublabel: str, accent: str) -> str:
    """Render one metric card."""

    return f"""
    <rect x="{x}" y="76" width="260" height="88" rx="10" fill="#0d1522" stroke="#26384f" />
    <rect x="{x + 20}" y="96" width="3" height="42" rx="1.5" fill="{accent}" />
    <text x="{x + 38}" y="101" class="mono" font-size="10" letter-spacing="1.5" fill="#71839d">{xml_escape(label)}</text>
    <text x="{x + 38}" y="130" class="mono" font-size="24" font-weight="700" letter-spacing="0.8" fill="#f4f8ff">{xml_escape(value)}</text>
    <text x="{x + 38}" y="151" class="mono" font-size="10" letter-spacing="1.2" fill="{accent}">{xml_escape(sublabel)}</text>
    """


def render_svg(stats: dict[str, Any]) -> str:
    """Render the self-contained telemetry SVG."""

    username = xml_escape(stats["username"])
    metric_markup = "".join(
        [
            metric_card(32, "PUBLIC REPOSITORIES", format_number(stats["public_repos"]), "PUBLIC SIGNAL", "#42e8b4"),
            metric_card(310, "FOLLOWERS", format_number(stats["followers"]), "NETWORK SIGNAL", "#32d9ff"),
            metric_card(588, "ACTIVE DAYS / 30D", format_number(stats["active_days"]), "ACTIVITY FEED", "#c4b5fd"),
            metric_card(866, "PUSH EVENTS / 30D", format_number(stats["push_events"]), "RECENT SHIPPING", "#f3c969"),
        ]
    )

    buckets = stats["activity_buckets"]
    max_bucket = max((int(bucket["count"]) for bucket in buckets), default=0)
    activity_markup: list[str] = []
    for index, bucket in enumerate(buckets):
        x = 86 + index * 104
        count = int(bucket["count"])
        height = 10 if max_bucket == 0 else 14 + round((count / max_bucket) * 54)
        y = 302 - height
        activity_markup.append(
            f"""
            <rect x="{x}" y="{y}" width="54" height="{height}" rx="4" fill="#32d9ff" fill-opacity="0.72">
            <animate attributeName="fill-opacity" values="0.46;0.82;0.46" dur="4.8s" begin="{index * 0.2:.1f}s" repeatCount="indefinite" />
            </rect>
            <text x="{x + 27}" y="{y - 8}" text-anchor="middle" class="mono" font-size="10" fill="#a9b7cb">{count}</text>
            <text x="{x + 27}" y="323" text-anchor="middle" class="mono" font-size="10" fill="#71839d">{xml_escape(bucket['label'])}</text>
            """
        )

    language_markup: list[str] = []
    for index, language in enumerate(stats["language_mix"]):
        y = 235 + index * 39
        percent = int(language["percent"])
        width = round(220 * percent / 100)
        color = ["#42e8b4", "#32d9ff", "#c4b5fd"][index % 3]
        language_markup.append(
            f"""
            <text x="842" y="{y}" class="mono" font-size="12" fill="#e7eef9">{xml_escape(language['name'])}</text>
            <text x="1138" y="{y}" text-anchor="end" class="mono" font-size="11" fill="{color}">{percent}%</text>
            <path d="M842 {y + 13}H1062" stroke="#24364c" />
            <path d="M842 {y + 13}H{842 + width}" stroke="{color}" stroke-width="2" stroke-linecap="round" />
            """
        )

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 390" role="img" aria-labelledby="title desc">
  <title id="title">GitHub telemetry for {username}</title>
  <desc id="desc">Public repository, follower, recent activity, push event, and primary language signals for the VELI profile.</desc>
  <defs>
    <linearGradient id="telemetry-bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#090f19" />
      <stop offset="1" stop-color="#111326" />
    </linearGradient>
    <linearGradient id="telemetry-edge" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#42e8b4" />
      <stop offset="0.54" stop-color="#32d9ff" />
      <stop offset="1" stop-color="#c4b5fd" />
    </linearGradient>
    <style>
      .mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace; }}
    </style>
  </defs>

  <rect width="1200" height="390" rx="16" fill="url(#telemetry-bg)" />
  <rect x="1" y="1" width="1198" height="388" rx="15" fill="none" stroke="#263449" stroke-width="2" />
  <text x="32" y="35" class="mono" font-size="11" letter-spacing="2" fill="#71839d">VELI / GITHUB TELEMETRY</text>
  <text x="1168" y="35" text-anchor="end" class="mono" font-size="11" letter-spacing="1.5" fill="#42e8b4">SYNC / {xml_escape(stats['sync_date'])}</text>
  <path d="M32 52H1168" stroke="#263449" />
  <path d="M32 52H344" stroke="url(#telemetry-edge)" stroke-width="2" stroke-linecap="round" />

  <g class="mono">
    {metric_markup}

    <rect x="32" y="190" width="740" height="152" rx="10" fill="#0d1522" stroke="#26384f" />
    <text x="56" y="218" font-size="10" letter-spacing="1.7" fill="#32d9ff">ACTIVITY / LAST 30 DAYS</text>
    <text x="748" y="218" text-anchor="end" font-size="10" letter-spacing="1.2" fill="#71839d">EVENT FEED / {xml_escape(stats['last_activity'])}</text>
    <path d="M66 302H708" stroke="#26384f" />
    {''.join(activity_markup)}

    <rect x="800" y="190" width="368" height="152" rx="10" fill="#0d1522" stroke="#26384f" />
    <text x="824" y="218" font-size="10" letter-spacing="1.7" fill="#c4b5fd">LANGUAGE SIGNAL</text>
    <text x="1144" y="218" text-anchor="end" font-size="10" letter-spacing="1.2" fill="#71839d">PRIMARY MIX</text>
    {''.join(language_markup)}
  </g>

  <path d="M32 362H1168" stroke="#263449" />
  <circle cx="44" cy="376" r="4" fill="#42e8b4">
    <animate attributeName="opacity" values="0.35;1;0.35" dur="3.6s" repeatCount="indefinite" />
  </circle>
  <text x="58" y="380" class="mono" font-size="10" letter-spacing="1.5" fill="#71839d">{username} / PUBLIC API / TRANSPARENT SIGNALS</text>
</svg>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", default=DEFAULT_USERNAME, help="GitHub username to inspect")
    parser.add_argument(
        "--output",
        default=str(ROOT / "assets" / "telemetry.svg"),
        help="Output SVG path (defaults to assets/telemetry.svg)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    try:
        stats = collect_stats(args.username, token)
        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = ROOT / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(render_svg(stats), encoding="utf-8", newline="\n")
    except RuntimeError as error:
        print(f"telemetry update failed: {error}", file=sys.stderr)
        return 1

    print(
        f"updated {output_path} — {stats['public_repos']} repos, "
        f"{stats['followers']} followers, sync {stats['sync_date']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
