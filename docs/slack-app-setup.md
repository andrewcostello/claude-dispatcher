# Setting up the Slack notification webhook

The dispatcher pushes events to Slack via an [incoming webhook][1]. This
file shows how to get one in ~3 minutes using the bundled app manifest
at `docs/slack-app-manifest.json`.

## Step 1 — Create the app from the manifest

1. Go to <https://api.slack.com/apps>
2. Click **Create New App** → **From a manifest**
3. Pick the workspace you want notifications in
4. Paste the contents of [`slack-app-manifest.json`](./slack-app-manifest.json)
5. Click **Next**, review, **Create**

The app is created with one scope (`incoming-webhook`) and no other
permissions. It can't read messages, can't see channels, can't post on
its own behalf — only the webhook URL can post, and only to the channel
that authorised it.

## Step 2 — Install + get the webhook URL

1. In the app's sidebar, click **Incoming Webhooks**
2. Click **Add New Webhook to Workspace** at the bottom
3. Pick the channel the dispatcher should post to (e.g. `#dispatcher-events`)
4. Click **Allow**
5. Slack shows the new webhook URL — copy it. It looks like
   `https://hooks.slack.com/services/T01XXX/B08YYY/aBcDeFgH...`

**That URL IS the secret** — anyone with it can post to your channel.
Treat it like a password.

## Step 3 — Tell the dispatcher about it

Prefer the env-var form over the CLI flag so the URL never lands in
your shell history:

```bash
export DISPATCHER_SLACK_WEBHOOK='https://hooks.slack.com/services/T01XXX/B08YYY/aBcDeFgH...'

dispatcher run tasks.yaml --mode unattended --cross-family-panel auto
```

For permanent setup, add the export to `~/.zshrc` / `~/.bashrc` / your
shell rc.

You can verify the wiring with a tiny smoke run — any quick dispatcher
invocation will fire a `run_complete` notification at exit.

## Step 4 (optional) — Also enable ntfy.sh

The two channels stack — events fan out to both. ntfy.sh has zero
account setup; just pick a topic name only you know:

```bash
export DISPATCHER_NTFY_TOPIC='andrew-dispatcher-3a7b'  # unguessable
# Already exported DISPATCHER_SLACK_WEBHOOK above
```

Install the ntfy app on your phone (App Store / Play Store / F-Droid),
add the same topic name as a subscription, and you'll get push to
phone as well as the Slack channel.

## Reading the events

Each event is a single message with a header (the event title), a
markdown section (task key, run id, reason, etc.), and a context block
with tags + a click-to-open link. The link is a `file://` URL pointing
at the per-task `summary.md` or the tasks YAML on the machine where the
dispatcher ran. Slack will render it as `open context` text; clicking
it on a workstation that mounts the same filesystem opens the file in
your default editor.

| Event | When |
|-------|------|
| `task_blocked` | Any task ends in `Blocked` status. |
| `awaiting_pr_approval` | The Tasker parked at the Critical/financial PR gate. |
| `run_complete` | The dispatch loop exited. Counts + first 10 blocked reasons inline. |
| `worker_exception` | A worker thread raised an unhandled exception. Should be rare. |

## Extending the app for back-channel approval (not built yet)

To allow approving / rejecting PR gates directly from the Slack message
(action buttons that post back to the dispatcher), the manifest would
need to change:

1. Set `settings.interactivity.is_enabled` to `true`
2. Set `settings.interactivity.request_url` to your dispatcher's
   listener URL (must be public HTTPS — use Cloudflare Tunnel or ngrok
   for dev)
3. Add `chat:write` to `oauth_config.scopes.bot` so the bot can post
   the action-button messages (the incoming-webhook form is
   message-only and doesn't carry interactivity)

The dispatcher itself would also need to grow an HTTP listener that
verifies Slack signing secrets, parses `payload`, and writes a small
status file the supervised gate can poll. That listener is not built;
file an issue if you start hitting the PR gate often enough to want it.

[1]: https://api.slack.com/messaging/webhooks
