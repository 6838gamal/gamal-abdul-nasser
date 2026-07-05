---
name: Env vars override pydantic defaults
description: Replit environment variables always override pydantic-settings class defaults; must update both.
---

## Rule
When changing a value that is controlled by a pydantic `Settings` class (e.g. `APP_NAME`, `SITE_AUTHOR`), editing the Python class default is NOT enough if a Replit environment variable with the same name exists — the env var wins.

**Why:** pydantic-settings reads environment variables before class defaults. The Replit platform injects env vars set via `setEnvVars` into the process environment.

**How to apply:** Always check `env | grep KEY_NAME` before assuming a class default will take effect. If an env var exists, update it via `setEnvVars({ environment: "shared", values: { KEY: "new_value" } })` in addition to (or instead of) editing the class default.
