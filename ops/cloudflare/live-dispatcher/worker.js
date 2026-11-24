// SPDX-FileCopyrightText: 2026 Ottto Inc.
// SPDX-License-Identifier: Apache-2.0

const OWNER = "ottto-ai";
const REPO = "ai-provider-watch";
const EVENT_TYPE = "apw-live-publish";
const GITHUB_API_VERSION = "2022-11-28";

export default {
  async scheduled(event, env, ctx) {
    ctx.waitUntil(dispatchLivePublisher(env, event.scheduledTime));
  },

  async fetch() {
    return Response.json({
      ok: true,
      service: "apw-live-dispatcher",
      dispatch_event_type: EVENT_TYPE,
    });
  },
};

async function dispatchLivePublisher(env, scheduledTime) {
  const token = env.GITHUB_DISPATCH_TOKEN;
  if (!token) {
    throw new Error("GITHUB_DISPATCH_TOKEN Worker secret is not configured");
  }

  const response = await fetch(`https://api.github.com/repos/${OWNER}/${REPO}/dispatches`, {
    method: "POST",
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      "User-Agent": "apw-live-dispatcher/1.0",
      "X-GitHub-Api-Version": GITHUB_API_VERSION,
    },
    body: JSON.stringify({
      event_type: EVENT_TYPE,
      client_payload: {
        source: "cloudflare-workers-cron",
        scheduled_time_ms: scheduledTime,
        dispatched_at: new Date().toISOString(),
      },
    }),
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`GitHub repository_dispatch failed: ${response.status} ${body.slice(0, 500)}`);
  }
}
