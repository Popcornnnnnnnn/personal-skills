---
name: shop-search
description: "Search JD and Taobao/Tmall using the author's Neo-first browser preference and an explicitly configured signed-search backend; report prices as observed leads."
---

# JD and Taobao search

Search only the named platform, or both when comparison is requested without a platform choice. This is a search workflow; do not add items to a cart or purchase. Treat observed prices as leads to verify on the linked product page before a purchase decision.

For JD, follow `agent-browser`, using BrowserOS neo by default. Read rendered search results and return product names, displayed prices and source links. Report login/verification or incomplete coverage honestly. Do not silently change browser profiles.

Taobao/Tmall can use the optional `scripts/search.py` adapter when `cn_scraper_mcp` and its legitimate signed-in backend are configured. Run it with the configured Python interpreter, for example `python3 scripts/search.py taobao "关键词" --limit 10`. The adapter validates query/limit and prints JSON; it does not export or import cookies.

The author's optional legacy JD adapter requires an explicitly configured existing bridge and an explicit request to use it. Its installation location comes from local settings; absence is an error rather than permission to start a browser bridge, extract credentials or install a backend. Browser operations continue to follow the current browser choice.

Inspect the configured backend before relying on its coverage. A backend error or suspicious price must remain visible in the result. Installation, login changes, opening individual product pages beyond the requested scope and purchases are separate actions.

## Local owner context

If `~/.config/personal-skills/profiles/shop-search/SKILL.md` exists, read it once for this task's private destinations, environment and established constraints. Keep that profile local. Verify changing facts live; a saved profile does not grant new access or authorize an unrelated action. Without a configured profile, resolve the required inputs from the current request and authorized tools; never invent the author's account or destination.
