#!/usr/bin/env python3
"""Schedule Buffer posts and publish Bluesky/Mastodon rows from social-schedule.csv."""

import csv
import datetime as dt
import json
import os
import sys
import urllib.request
import argparse
import time
from zoneinfo import ZoneInfo
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = Path(os.environ.get("SOCIAL_SCHEDULE_CSV", ROOT / "content-workspace/social-exports/social-schedule.csv"))
STATE_PATH = Path(os.environ.get("SOCIAL_STATE_FILE", ROOT / "content-workspace/social-exports/social-publisher-state.json"))
BUFFER_URL = os.environ.get("BUFFER_API_URL", "https://api.buffer.com")
BUFFER_KEY = os.environ.get("BUFFER_API_KEY")
DRY_RUN = os.environ.get("SOCIAL_DRY_RUN", "0") == "1"
LATE_WINDOW = dt.timedelta(minutes=int(os.environ.get("SOCIAL_LATE_WINDOW_MINUTES", "15")))
POST_DELAY_SECONDS = int(os.environ.get("SOCIAL_POST_DELAY_SECONDS", "30"))
BUFFER_USE_QUEUE = os.environ.get("BUFFER_USE_QUEUE", "0").lower() in {"1", "true", "yes", "on"}
BUFFER_MAX_SCHEDULED = int(os.environ.get("BUFFER_MAX_SCHEDULED_PER_CHANNEL", "10"))
BUFFER_SCHEDULED_COUNTS = {}

BUFFER_CHANNELS = {
    "linkedin": os.environ.get("BUFFER_CHANNEL_LINKEDIN"),
    "x": os.environ.get("BUFFER_CHANNEL_X"),
    "facebook": os.environ.get("BUFFER_CHANNEL_FACEBOOK"),
}


def load_state():
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {"rows": {}}


def save_state(state):
    if DRY_RUN:
        return
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2) + "\n")
    temporary.replace(STATE_PATH)


def row_key(row):
    return "|".join((row["date"], row["time_et"], row["slug"], row["channel"]))


def parse_when(row):
    return dt.datetime.fromisoformat(
        f'{row["date"]}T{row["time_et"]}:00'
    ).replace(tzinfo=ZoneInfo("America/New_York"))


def tracked_text(row):
    """Add stable Umami-friendly UTM parameters to the canonical blog URL."""
    url = row["url"]
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update({
        "utm_source": row["channel"].lower(),
        "utm_medium": "social",
        "utm_campaign": row["slug"],
        "utm_content": row["channel"].lower(),
    })
    tracked = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
    return row["text"].replace(url, tracked)


def buffer_request(query, variables):
    request = urllib.request.Request(
        BUFFER_URL,
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"Bearer {BUFFER_KEY}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read())
    if payload.get("errors"):
        raise RuntimeError(payload["errors"])
    return payload["data"]


def buffer_scheduled_count(channel_id):
    if channel_id in BUFFER_SCHEDULED_COUNTS:
        return BUFFER_SCHEDULED_COUNTS[channel_id]
    orgs = buffer_request("query { account { organizations { id } } }", {})
    organization_ids = [org["id"] for org in orgs["account"]["organizations"]]
    count = 0
    for organization_id in organization_ids:
        result = buffer_request("""
        query($organization: OrganizationId!, $channel: ChannelId!) {
          posts(first: 100, input: {
            organizationId: $organization
            filter: { status: [scheduled], channelIds: [$channel] }
          }) { edges { node { id } } }
        }
        """, {"organization": organization_id, "channel": channel_id})
        count += len(result["posts"]["edges"])
    BUFFER_SCHEDULED_COUNTS[channel_id] = count
    return count


def buffer_schedule(row, channel_id, immediate=False):
    query = """
    mutation CreatePost($input: CreatePostInput!) {
      createPost(input: $input) {
        ... on PostActionSuccess { post { id dueAt status } }
        ... on MutationError { message }
      }
    }
    """
    variables = {"input": {
        "text": tracked_text(row),
        "channelId": channel_id,
        "schedulingType": "automatic",
        "mode": "shareNow" if immediate else ("addToQueue" if BUFFER_USE_QUEUE else "customScheduled"),
    }}
    if row["channel"].lower() == "facebook":
        variables["input"]["metadata"] = {"facebook": {"type": "post"}}
    if not immediate and not BUFFER_USE_QUEUE:
        variables["input"]["dueAt"] = parse_when(row).astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    return buffer_request(query, variables)


def post_bluesky(row):
    from atproto import Client
    client = Client()
    client.login(os.environ["BLUESKY_HANDLE"], os.environ["BSKY_APP_PASSWORD"])
    return client.send_post(text=tracked_text(row))


def post_mastodon(row):
    from mastodon import Mastodon
    client = Mastodon(
        api_base_url=os.environ["MASTODON_API_BASE_URL"],
        access_token=os.environ["MASTODON_ACCESS_TOKEN"],
    )
    return client.status_post(tracked_text(row), idempotency_key=row_key(row))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--now", help="Publish one slug immediately to Buffer channels")
    args = parser.parse_args()
    if not CSV_PATH.exists():
        raise SystemExit(f"CSV not found: {CSV_PATH}")
    state = load_state()
    now = dt.datetime.now(dt.timezone.utc)
    changed = False
    with CSV_PATH.open(newline="") as handle:
        rows = list(csv.DictReader(handle))

    for row in rows:
        key = row_key(row)
        if key in state["rows"]:
            continue
        service = row["channel"].lower()
        when = parse_when(row)
        if service in BUFFER_CHANNELS:
            if not BUFFER_KEY or not BUFFER_CHANNELS[service]:
                print(f"SKIP {key}: Buffer credentials/channel mapping incomplete", file=sys.stderr)
                continue
            immediate = args.now == row["slug"]
            if args.now and not immediate:
                continue
            if not args.now and when <= now:
                print(f"SKIP {key}: Buffer schedule is in the past", file=sys.stderr)
                continue
            scheduled = 0
            if not immediate:
                scheduled = buffer_scheduled_count(BUFFER_CHANNELS[service])
                if scheduled >= BUFFER_MAX_SCHEDULED:
                    print(f"SKIP {key}: Buffer channel already has {scheduled} scheduled posts (limit {BUFFER_MAX_SCHEDULED})", file=sys.stderr)
                    continue
            print(f"BUFFER {key} -> {when.isoformat()}")
            if not DRY_RUN:
                result = buffer_schedule(row, BUFFER_CHANNELS[service], immediate=immediate)
                state["rows"][key] = {"backend": "buffer", "result": result}
                changed = True
                if not immediate:
                    BUFFER_SCHEDULED_COUNTS[BUFFER_CHANNELS[service]] = scheduled + 1
                if POST_DELAY_SECONDS:
                    time.sleep(POST_DELAY_SECONDS)
        elif service in {"bluesky", "mastodon"}:
            immediate = args.now == row["slug"]
            if not immediate and when > now:
                continue
            if not immediate and now - when > LATE_WINDOW:
                print(f"SKIP {key}: outside late-post window", file=sys.stderr)
                continue
            print(f"POST {key}")
            if not DRY_RUN:
                result = post_bluesky(row) if service == "bluesky" else post_mastodon(row)
                state["rows"][key] = {"backend": service, "result": str(result)}
                changed = True
                if POST_DELAY_SECONDS:
                    time.sleep(POST_DELAY_SECONDS)
        else:
            print(f"SKIP {key}: unsupported channel {service}", file=sys.stderr)
    if changed:
        save_state(state)


if __name__ == "__main__":
    main()
