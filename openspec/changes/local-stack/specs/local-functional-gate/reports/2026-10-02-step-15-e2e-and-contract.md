# Step 15 — E2E applicability and API contract

Date: 2026-10-02

## 15.1 Marked N/A, with justification

**End-to-end testing is N/A for this change.**

- The frontend is a separate React Native project in a separate repository. No
  test written here could execute it, and a change with no UI surface has no UI
  surface to drive.
- This change adds no endpoint and alters no response schema. The only user of
  the API in this repository is the test suite and the local gate, and both were
  executed by hand and by script respectively (steps 13 and 14).

The gate is what stands in for E2E here, and it was run repeatedly rather than
once: §13.7 rebuild, the clean cycle after the photo-leak fix, the run that
confirmed byte stability across cycles, and the run in §14.9.

## 15.2 The committed spec needs no re-export

```
$ PYTHONPATH=. venv/bin/python scripts/export_openapi.py --check
OpenAPI specification is up to date.
```

## 15.3 The contract is untouched against HEAD

```
$ git status --porcelain docs/api-spec.json
(no output — unmodified)
```

A structural comparison of `HEAD:docs/api-spec.json` against the working copy:

```
structural equality (parsed JSON): True
paths: 33 -> 33
```

No path added, removed, or altered. The change is confined to how the local
environment is built and brought up; it does not reach the API surface.

> Note: diffing the raw text of the two files shows ~3158 changed lines purely
> because redirecting the script's stdout produces minified JSON while the
> committed artifact is written with `indent=2`. Comparing parsed JSON is the
> correct comparison here, and `git status` settles it independently: the file is
> not modified at all.
