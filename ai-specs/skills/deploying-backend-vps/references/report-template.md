# Deployment Report — <client> / <host>

**Date:** <YYYY-MM-DD> · **Executed by:** <agent + human supervisor> · **Duration:** <minutes>
**Change type:** <first deployment | release <tag> | credential rotation | media host change | rollback>

## Values used (secrets masked)

| Value | Used | Masked |
|---|---|---|
| Server | | n/a |
| API host | | n/a |
| Media host | | n/a |
| Shared network | | n/a |
| PostgreSQL container / image | | n/a |
| Object storage container / image | | n/a |
| Database / role | | n/a |
| Bucket / user / policy | | n/a |
| Database password | | `****` |
| Storage access key | | `AKIA…****` |
| App secret key | | `****` |
| Storage console published? | no (managed with `mc` from inside the container) | n/a |

## Phase outcomes

| Phase | Action | Gate | Result | Evidence |
|---|---|---|---|---|
| 0 | Discover shared estate | containers, network, ports, images confirmed | | one line |
| 1 | Attach to the shared network | existing endpoints unchanged | | |
| 2 | Role + database | role is not superuser, cannot see other databases | | |
| 2 | Schema | table count matches the code; history consistent; `upgrade` is a no-op | | |
| 2 | Seed | idempotent re-run changed nothing | | |
| 3 | User + bucket + policy + credentials | `mc` shows the app's bucket only | | |
| 3 | CORS | set only if a browser client talks to storage directly | | |
| 4 | Config + start | `docker compose config` clean; both services healthy | | |
| 5.1 | Tenancy before / after | no foreign object missing | | |
| 5.2 | Backup | dump exists, non-empty, `chmod 600` | | |
| 5.3 | Schema | as phase 2 | | |
| 5.4 | Health | in-network and public | | |
| 5.5 | Media round-trip | upload, download, compare, delete | | |
| 5.6 | No data ports | only the proxy publishes ports | | |
| 6 | Rollback rehearsed | previous image tag restarts and passes 5.4/5.5 | | |

## Stopped for

| Phase | Reason | Decision taken | Resumed after |
|---|---|---|---|
| | | | |

## Success criteria

- [ ] API schema reachable over TLS from a network that is not the server
- [ ] Login works in the client
- [ ] A photo uploaded from the client loads back on the client's network
- [ ] A generated document downloads
- [ ] A second upload above the multipart threshold succeeds
- [ ] No public port other than the proxy's
- [ ] Storage endpoint equals the client-facing media host; no root credentials in config
- [ ] Other tenants' databases, buckets, volumes and containers unchanged
- [ ] An off-box backup exists, and a restore has been rehearsed

## Next actions (owner, deadline)

1. Rotate the storage service-account key and the database password on a schedule
   (<owner>, <date>).
2. Rehearse a media restore from the off-box backup (<owner>, <date>).
3. Move the next release to a tagged commit and rehearse the rollback (<owner>, <date>).
4. Close any defect the deployment exposed (<owner>, <date>).
