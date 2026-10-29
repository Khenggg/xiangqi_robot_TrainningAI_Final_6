"""Run unittest discovery while refusing accidental real HTTP in test fixtures."""
import argparse
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pattern', default='test_*.py')
    args = parser.parse_args()
    forbidden = []

    def deny_http(*args, **kwargs):
        # Do not print Authorization headers or token-bearing URLs.
        forbidden.append('unmocked HTTP request')
        raise AssertionError('Offline tests attempted HTTP; mock the provider in the fixture.')

    with patch.object(requests.sessions.Session, 'request', side_effect=deny_http):
        suite = unittest.defaultTestLoader.discover(str(ROOT / 'tests'), pattern=args.pattern)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    if forbidden:
        print(f'Offline guard blocked {len(forbidden)} unmocked HTTP request(s).', file=sys.stderr)
    return 0 if result.wasSuccessful() and not forbidden else 1


if __name__ == '__main__':
    raise SystemExit(main())
