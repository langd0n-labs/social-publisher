#!/usr/bin/env python3
"""Credential-only smoke tests. Never creates a post or prints secret values."""

import json
import os
import urllib.request


def request(url, payload, headers=None):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.load(response)


def get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.load(response)


def main():
    buffer = request(
        "https://api.buffer.com",
        {"query": "query { account { id } }"},
        {"Authorization": f"Bearer {os.environ['BUFFER_API_KEY']}"},
    )
    account_id = buffer.get("data", {}).get("account", {}).get("id")
    print(f"BUFFER_AUTH_OK account={account_id}" if account_id else "BUFFER_AUTH_FAILED")

    bsky = request(
        "https://bsky.social/xrpc/com.atproto.server.createSession",
        {"identifier": os.environ["BLUESKY_HANDLE"], "password": os.environ["BSKY_APP_PASSWORD"]},
    )
    did = bsky.get("did")
    handle = bsky.get("handle")
    print(f"BLUESKY_AUTH_OK handle={handle} did={did}" if did else "BLUESKY_AUTH_FAILED")

    mastodon = get(
        os.environ["MASTODON_API_BASE_URL"].rstrip("/") + "/api/v1/accounts/verify_credentials",
        {"Authorization": f"Bearer {os.environ['MASTODON_ACCESS_TOKEN']}"},
    )
    print(f"MASTODON_AUTH_OK acct={mastodon.get('acct')} id={mastodon.get('id')}" if mastodon.get("id") else "MASTODON_AUTH_FAILED")


if __name__ == "__main__":
    main()
