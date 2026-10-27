#!/usr/bin/env python3
"""Run the two local product-search backends without starting an MCP server."""

import argparse
import json
import os
from pathlib import Path
import sys

# Ensure execution in dedicated python environment containing cn_scraper_mcp
settings_path = Path.home() / '.config/personal-skills/settings.json'
SETTINGS = json.loads(settings_path.read_text()).get('shop_search', {}) if settings_path.exists() else {}
VENV_PYTHON = os.environ.get('PERSONAL_SKILLS_SHOP_PYTHON', SETTINGS.get('python', ''))
if sys.executable != VENV_PYTHON and os.path.exists(VENV_PYTHON):
    try:
        import cn_scraper_mcp
    except ImportError:
        os.execv(VENV_PYTHON, [VENV_PYTHON, os.path.abspath(__file__)] + sys.argv[1:])



def main():
    parser = argparse.ArgumentParser(description="Search JD or Taobao product listings")
    parser.add_argument("platform", choices=("jd", "taobao"))
    parser.add_argument("keyword")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    try:
        from cn_scraper_mcp.validation import validate_keyword, validate_limit
        keyword = validate_keyword(args.keyword)
        limit = validate_limit(args.limit)
        if args.platform == "jd":
            bridge = SETTINGS.get('jd_client_dir')
            if not bridge or not (Path(bridge).expanduser() / 'client.py').is_file():
                raise RuntimeError('Configure an existing JD bridge before using the explicit legacy route')
            sys.path.insert(0, str(Path(bridge).expanduser()))
            from client import search

            result = search(keyword, limit)
        else:
            from cn_scraper_mcp.engines.taobao import TaobaoEngine

            result = TaobaoEngine().search(keyword, limit=limit)
        print(json.dumps(result, ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"platform": args.platform, "error": "Search backend unavailable or failed (" + type(exc).__name__ + "); inspect the configured backend privately"}, ensure_ascii=False))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
