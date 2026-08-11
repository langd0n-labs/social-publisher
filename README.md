# Social publisher

This repository publishes scheduled social posts from a CSV. It runs in a
Podman container, typically from a systemd user timer, with credentials injected
at runtime by Bitwarden Secrets Manager via `bws run`.

- Buffer API: schedules LinkedIn, X, and Facebook rows.
- Direct APIs: publishes due Bluesky and Mastodon rows.
- The state file records completed rows and prevents duplicate retries.
- `SOCIAL_DRY_RUN=1` prints actions without publishing or writing state.
- `SOCIAL_LATE_WINDOW_MINUTES` prevents an offline machine from dumping old
  missed posts onto Bluesky/Mastodon when it comes back.
- Blog links receive UTM parameters at publish time for attribution.

## Configuration

Secret environment variables, supplied at runtime (do not commit values):

- `BUFFER_API_KEY`
- `BSKY_APP_PASSWORD`
- `MASTODON_ACCESS_TOKEN`

Non-secret environment variables:

- `BUFFER_CHANNEL_LINKEDIN`, `BUFFER_CHANNEL_X`, `BUFFER_CHANNEL_FACEBOOK` — Buffer channel IDs.
- `BLUESKY_HANDLE` — Bluesky handle.
- `MASTODON_API_BASE_URL` — Mastodon instance URL.
- `BUFFER_API_URL` — Buffer API URL; defaults to `https://api.buffer.com`.
- `SOCIAL_SCHEDULE_CSV` — input CSV path.
- `SOCIAL_STATE_FILE` — state JSON path.
- `SOCIAL_DRY_RUN` — set to `1` for dry-run mode.
- `SOCIAL_LATE_WINDOW_MINUTES` — late-post window; defaults to `15`.
- `SOCIAL_POST_DELAY_SECONDS` — delay between posts; defaults to `30`.
- `BUFFER_USE_QUEUE` — set to `1` to use Buffer's next available queue slot;
  defaults to `0`, preserving explicit CSV schedule times.
- `BUFFER_MAX_SCHEDULED_PER_CHANNEL` — Buffer queue limit; defaults to `10`.
- `SOCIAL_PUBLISHER_IMAGE` — container image name.
- `SOCIAL_PUBLISHER_DATA_DIR` — directory mounted as `/data` by the container wrapper.
- `BWS_PROJECT_ID` — **required**, no default. Your Bitwarden Secrets Manager
  project id.
- `BWS_TOKEN_FILE` — path to the Bitwarden Secrets Manager access token;
  defaults to `~/.config/bws-tokens/social-publisher.token`.
- `BWS_BIN` — path to the `bws` binary; defaults to `~/.local/bin/bws`.

Copy `social-publisher.env.example` to a local configuration file and fill in
non-secret values. Use app passwords/tokens, never account passwords.

## Input CSV

The schedule file (`social-schedule.csv`) must contain columns `date`,
`time_et`, `slug`, `channel`, and `text`. Dates and times are interpreted in
the `America/New_York` timezone, including DST changes.

```csv
date,time_et,slug,channel,text
2026-08-10,09:30,example-post,linkedin,"A scheduled post"
```

## Buffer free-plan constraint

Buffer's free plan allows at most 10 scheduled posts per channel. The publisher
counts existing scheduled posts before each submission and skips rows that
would exceed `BUFFER_MAX_SCHEDULED_PER_CHANNEL`, for both explicit-time and
queue-mode submissions.

## Systemd deployment

The shipped `.service` and `.timer` files contain example paths. Copy them to
your `~/.config/systemd/user/`, then point `ExecStart`, `EnvironmentFile`, and
your `bws` project/configuration at your own checkout and Bitwarden project.
Do not assume the example directory layout fits your machine.

The timer runs every five minutes. Direct posts are sent when due and within
the late window; missed posts are skipped rather than dumped late. The state
file makes each row/channel combination idempotent. Use `--now <slug>` for an
intentional manual release.

This was built for the author's thought-leadership publishing workflow, but is
intended to be reusable for any content schedule.

## Acknowledgments

Direct-publish support is built on these open-source projects:

- [atproto](https://github.com/MarshalX/atproto) (MarshalX) — Bluesky/AT
  Protocol client.
- [Mastodon.py](https://github.com/halcy/Mastodon.py) (halcy) — Mastodon API
  client.

LinkedIn/X/Facebook scheduling goes through the [Buffer](https://buffer.com)
API rather than a direct client library.
