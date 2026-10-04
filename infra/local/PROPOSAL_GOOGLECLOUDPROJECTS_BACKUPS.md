# Proposal: Add scheduled backups + restore-drill to GoogleCloudProjects (core owner)

**Scope:** Core infrastructure (GoogleCloudProjects), not app-tickets-backend. This is a proposal (opsx-propose style) — do not implement in this repo.

## Problem statement recap
- Core runs shared PostgreSQL (`postgres-gci`, owner GoogleCloudProjects) and MinIO (`minio-acme`, owned by assync project under GoogleCloudProjects). 
- App-tickets local rebuild dropped its own DB; lesson: destructive ops need backup+restore verification before execution. 
- Request: scheduled backups (yes). Responsibility: core responsibility (not API). Prod guidance given.

## Proposed changes (GoogleCloudProjects/core + ops)

### 1. Inventory + current state
- postgres-gci: archive_mode=off, wal_level=replica, no WAL archiving. Backups bind-mount empty (`core/postgres-gci/backups`).
- Need durable off-host backup location (separate from PG data volume). Retention policy.

### 2. PostgreSQL backups
- Daily logical backup (low traffic window, e.g. 02:00): `pg_dumpall -U <admin>` or per-DB `pg_dump -Fc` for tenant DBs (allows selective restore). 
- Before any destructive shared-state change: mandatory ad-hoc backup with restore verification.
- Enable PITR only if required: set `archive_mode=on`, `wal_level=logical`/appropriate, durable `archive_command` to off-host storage (separate failure domain). Changing PG config requires restart + care for shared tenants.

### 3. Restore drill (must verify)
- Weekly (or before releases): restore latest dump into fresh empty DB `restore_drill_<ts>` (never over running). 
- Compare row counts per table (source vs restored). Check logs: no unexpected ERRORs (filter benign). Record counts+exit+log.
- Gate: 7.1–7.4 from verifying-a-deployment gate catalog.

### 4. MinIO
- Treat objects as separate failure domain. Schedule sync to off-host (e.g. restic/rclone) with retention. Not substitute for DB.

### 5. Scheduling
- systemd timers (preferred) on core host, or cron with logging. Not in containers. 
- Scripts: `/opt/backups/pg-backup.sh`, `/opt/backups/pg-restore-drill.sh`, `/opt/backups/minio-backup.sh`, logs to journald/syslog, alert on failure.

### 6. Safety guards
- Dumps mode 600, written to path not on PG data volume. 
- Restore always creates new DB name; script refuses if target is running/live DB name.
- Pre-backup check + post-verify required.

### 7. Retention (suggest)
- Daily: 30d, Weekly: 12w, Monthly: 12m (tune per RPO). Encrypt at rest, off-host.

### 8. Implementation phases
- P0: codify scripts + restore-drill (no config change yet if PITR deferred)
- P1: enable archiving if PITR needed (shared-tenancy impact review)
- P2: timers + alerting + runbook

### Decision needed
- PITR required? (affects archive_mode change). Default: no (logical dumps + tested restore) to minimize shared-core disruption.

## Acceptance
- `pg_dump` taken before any destructive op, restore verified into fresh DB, drill weekly, logs/alerts working, off-host storage confirmed.
