---
name: x-search
description: Search public X posts using a configured SocialData API key. Use for requests to find or research X posts; follow the user's requested source and scope.
---

# X search

Run `python3 scripts/search.py 'search terms'` from this skill directory. It returns one page of normalized posts and a cursor for the next page. Use `--cursor` to continue and `--type Top` for popular results. Search operators can be included in the query. Each page may incur a charge; fetch only what the request needs. SocialData returns about 20 results per page and does not support a server-side result limit.

The helper reads `SOCIALDATA_API_KEY` or, on macOS, Keychain coordinates from the private profile `~/.config/personal-skills/profiles/x-search/keychain.json` (`service` and `account`). Never print or commit the key. If configuration is missing, explain the setup needed.

Report 402 (balance) and 429 (rate limit) distinctly. A successful empty result is not proof that no matching posts exist. If coverage matters and the user has not restricted the source, check another available search method such as agent-reach and identify the source. Cite individual post URLs and distinguish results from inference.
