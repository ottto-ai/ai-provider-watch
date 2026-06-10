# SPDX-FileCopyrightText: 2026 AI Provider Watch maintainers
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from ai_provider_watch import api


def main() -> None:
    events = api.load_remote_events(ref="main", min_severity="medium", limit=10)
    freshness = api.load_remote_json_feed("freshness", ref="data-2026.06.10")
    ndjson = api.load_remote_text_feed("events.ndjson", ref="data-2026.06.10")
    url = api.remote_feed_url("events.ndjson", ref="data-2026.06.10")

    print(url)
    for event in events:
        print(event["id"], event["title"])
    print(f"{freshness['release_id']} {len(ndjson.splitlines())} ndjson rows")


if __name__ == "__main__":
    main()

