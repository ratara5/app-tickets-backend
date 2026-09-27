# AI-Harness Deployment Prompt — VPS Backend Runbook

> **This file is a pointer, not a second runbook.** The executable procedure now lives in the
> `deploying-backend-vps` skill (`ai-specs/skills/deploying-backend-vps/`, exposed to agents as
> `.opencode/skills/deploying-backend-vps`). The commands live in
> `docs/deployment-guide.md` §2. Do not paste a copy of the runbook into a chat: a stale copy
> is how a deployment ends up running commands that were fixed months ago.

## How to use it

1. Fill in the values table below. The agent cannot invent a domain, a password or a bucket
   name, and must stop rather than guess.
2. On the VPS, with the repository checked out, invoke the skill and let it drive
   `docs/deployment-guide.md` step by step.
3. Supervise. The skill stops at every failed gate and reports; it never improvises a fix on a
   box that other applications depend on.

## Values table (human fills every row before you start)

| Value | Value to use |
|---|---|
| `VPS_IP` | _HUMAN_FILLS_ |
| `VPS_USER` / SSH target | _HUMAN_FILLS_ |
| `API_DOMAIN` | _HUMAN_FILLS_ (A record → this VPS) |
| `MEDIA_DOMAIN` | _HUMAN_FILLS_ (A record → this VPS; the app signs URLs with it) |
| `ACME_EMAIL` | _HUMAN_FILLS_ (optional with ACME zero-issue) |
| `DB_NAME` | `db_gestiket_acme` |
| `DB_USER` / `DB_PASSWORD` | `gestiket_app` / _HUMAN_FILLS_ |
| `MINIO_DEFAULT_BUCKET` | `acme-uploads` |
| `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` | _HUMAN_FILLS_ (bucket-scoped, never root) |
| `MINIO_ADMIN` / `MINIO_PASSWORD` | _HUMAN_FILLS_ (bootstrap only, stays on the box) |
| Install path | `/opt/app-tickets` |
| Phone on cellular for the off-box gate | _HUMAN_CONFIRMS_AVAILABLE_ |

## Supervisor checklist

- [ ] Values table complete, `MEDIA_DOMAIN` decided (changing it later breaks every URL already
      delivered to a client)
- [ ] `deploying-backend-vps` skill available to the agent
- [ ] PostgreSQL backup exists **before** the agent touches shared state
- [ ] Agent reports each gate with real command output, not assertions
- [ ] Tenancy diff clean: only this app's database, bucket and containers changed
- [ ] Off-box gate passed from a phone on cellular: login, a photo, and a PDF
- [ ] Report produced from the skill's report template, with masked secrets

## What the agent is never allowed to do

- `docker rm`, rename, recreate or restart `postgres-gci` or `minio-acme`
- publish 5432, 9000 or 9001, "just to test it"
- put MinIO or PostgreSQL root credentials in `.env`, a commit, or the chat
- run `init.sql` or `alembic upgrade head` (singular) to create a database — see the measured
  defects in `docs/deployment-guide.md` §2.2 and the tickets listed at the end of that file
- source `.env` in a shell (`set -a; . .env` corrupts the JSON in `ALLOWED_TYPES`)
- continue past a failed gate, or "try a variation" of a runbook command on a shared box
