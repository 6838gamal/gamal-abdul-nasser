---
name: Site settings startup sync
description: Correct order for syncing seo_settings from config at app lifespan startup.
---

## Rule
In `app/main.py` lifespan, the correct order is:
1. Run an UPSERT (raw SQL `INSERT ... ON CONFLICT DO UPDATE`) for core identity keys (site_name, site_author, site_description).
2. THEN call `load_site_settings(db)` to load all settings from DB into cache.
3. THEN call `_apply_to_templates()`.

**Why:** If `load_site_settings` is called first (or after a save_site_settings that uses ORM), the cache gets populated with stale DB values, overwriting any in-memory updates. The UPSERT approach writes directly to DB so the subsequent load picks up the fresh values.

**How to apply:** The ORM `existing.value = val` approach without explicit dirty-marking can silently skip UPDATEs. Use `text()` UPSERT for startup bootstrapping of critical config values.
