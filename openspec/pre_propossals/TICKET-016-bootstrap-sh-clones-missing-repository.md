# Bug: bootstrap.sh clones a repository that does not exist in this tree

## Metadata

- **Summary**: the root bootstrap script clones `gtk-companies/gtk-base`, which is not present in this repository, so it fails before it configures anything
- **Issue Type**: Bug
- **Project**: app-tickets-backend
- **Priority**: Medium
- **Labels**: tooling, deployment

## Description

`bootstrap.sh` is the script a new developer is expected to run first. At line 128 it
clones a repository that is not part of this tree:

```bash
git clone .../gtk-companies/gtk-base
```

The reference does not resolve, and there is no vendored copy, submodule or
configuration in this repository that would make it succeed. The script therefore
cannot complete, which means the documented first-run path is broken.

**Impact:** a new developer or a new environment cannot bootstrap the way the
repository says to. Since the same script's purpose is to make setup reproducible, this
undermines the one step that matters most on day one. Anyone who has worked around it has
done so by hand, in a way the repository does not record.

## Reproduction

```bash
grep -n "git clone" bootstrap.sh
# line 128 clones gtk-companies/gtk-base
./bootstrap.sh          # → clone failure, non-zero exit
```

## Acceptance criteria

- `./bootstrap.sh` completes on a clean checkout, or the missing dependency is
  declared, vendored, or the step is removed.
- Whatever the script clones, if anything, is pinned to a commit or tag rather than a
  moving branch.
- The script is idempotent: running it on an already-configured checkout does not
  destroy or duplicate existing local configuration.

## Notes

- Deployment to the VPS must not use this script as written; the runbook
  (`docs/deployment-guide.md`) provisions the database, MinIO and the stack directly
  instead.
- Because the script is the documented entry point, consider whether the environment
  bootstrap belongs in version control at all, or should be a documented sequence of
  commands like the rest of the deployment guide.
