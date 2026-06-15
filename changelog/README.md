# Changelog

One file per product release, named `<version>.md` (e.g. `0.2.0.md`). The
filename **is** the version, so each file's body is just that release's notes —
no version header needed. Files whose name does not parse as a version (like
this `README.md`) are ignored by the Version console tab.

These notes are what admins see under **Console → Version**, newest first. The
version is independent of the `tdmcp` package version in
`pyproject.toml`.

## How to release

1. Bump the repo-root `VERSION` file.
2. Add `changelog/<version>.md` with the **admin upgrade notes** — what admins
   must do when pulling this release (migrations, new env vars, manual steps) —
   plus the usual Added / Changed / Fixed sections.
3. Commit, tag (`git tag v<version>`), and push the tag.
4. Publish a GitHub Release for the tag. The "update available" indicator
   compares the latest GitHub Release tag against the running `VERSION`.

## Template

```markdown
# X.Y.Z — YYYY-MM-DD

## Upgrade notes for admins
- e.g. Run `docker compose run --rm web python web/manage.py migrate`
- e.g. New required env var `FOO` in docker-compose.yml

## Changed
-

## Fixed
-
```
