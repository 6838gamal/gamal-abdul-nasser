---
name: Jinja2 quirks in this project
description: Non-obvious Jinja2 limitations that cause 500 errors.
---

## No enumerate filter
Jinja2 does not have a built-in `enumerate` filter. Using `items | enumerate` raises `No filter named 'enumerate'` and causes a 500.

**Fix:** Use `loop.index` (1-based) or `loop.index0` (0-based) inside a `{% for %}` block instead.

**How to apply:** Any time you need the loop counter in a Jinja2 template, use `{{ loop.index }}` or `{{ loop.index0 }}`. To use it in Alpine.js `:class` or `@click` bindings, capture it with `{% set idx = loop.index %}` before the element, then reference `{{ idx }}`.
