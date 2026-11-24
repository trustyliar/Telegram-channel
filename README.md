# Telegram deal mirror
Watches one Telegram deals channel, swaps affiliate links to our Amazon tag, reposts to our channel.

- `bot.py` - the listener/poster. `links.py` - link resolving and tagging. `make_session.py` - one-time login helper.
- Secrets (API hash, tag, SESSION_STRING) are NEVER committed: set them as environment variables on the host.
- Deploy: host runs the `Dockerfile` as an always-on worker and redeploys on every push to `main`.
- Start with `DRY_RUN=1` (log only), then set `DRY_RUN=0` to post.
- Tests: `pip install -r requirements-dev.txt && pytest`
