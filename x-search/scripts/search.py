#!/usr/bin/env python3
"""Fetch one SocialData search page without exposing the API key."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request


def credential():
    key = os.environ.get('SOCIALDATA_API_KEY', '').strip()
    if key:
        return key
    profile = Path.home() / '.config/personal-skills/profiles/x-search/keychain.json'
    try:
        config = json.loads(profile.read_text())
        result = subprocess.run(
            ['security', 'find-generic-password', '-s', config['service'],
             '-a', config['account'], '-w'],
            capture_output=True, text=True, check=True,
        )
        return result.stdout.strip()
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        raise ValueError('Set SOCIALDATA_API_KEY or configure the private Keychain profile.') from None


def normalize(tweet):
    user = tweet.get('user') or {}
    ident = tweet.get('id_str') or str(tweet.get('id', ''))
    username = user.get('screen_name')
    return {
        'id': ident,
        'url': f'https://x.com/{username}/status/{ident}' if username and ident else None,
        'author': {'username': username, 'name': user.get('name')},
        'created_at': tweet.get('tweet_created_at'),
        'text': tweet.get('full_text') or tweet.get('text'),
        'metrics': {name: tweet.get(source) for name, source in (
            ('likes', 'favorite_count'), ('reposts', 'retweet_count'),
            ('replies', 'reply_count'), ('quotes', 'quote_count'),
            ('views', 'views_count'), ('bookmarks', 'bookmark_count'))},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('query')
    parser.add_argument('--cursor')
    parser.add_argument('--type', choices=('Latest', 'Top'), default='Latest')
    args = parser.parse_args()
    if not args.query.strip():
        parser.error('query must not be empty')
    params = {'query': args.query, 'type': args.type}
    if args.cursor:
        params['cursor'] = args.cursor
    try:
        key = credential()
        if not key:
            raise ValueError('SocialData API key is empty.')
        request = urllib.request.Request(
            'https://api.socialdata.tools/twitter/search?' + urllib.parse.urlencode(params),
            headers={'Authorization': 'Bearer ' + key, 'Accept': 'application/json'},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.load(response)
        if not isinstance(data.get('tweets'), list):
            raise ValueError('Unexpected SocialData response: missing tweets list.')
        print(json.dumps({'posts': [normalize(t) for t in data['tweets']],
                          'next_cursor': data.get('next_cursor')}, ensure_ascii=False))
    except urllib.error.HTTPError as exc:
        message = {402: 'SocialData balance is insufficient.',
                   429: 'SocialData rate limit reached; retry later.'}.get(exc.code, f'SocialData returned HTTP {exc.code}.')
        print(message, file=sys.stderr)
        return 1
    except (ValueError, OSError, urllib.error.URLError) as exc:
        print(f'Search failed: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
