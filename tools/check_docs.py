#!/usr/bin/env python3
"""Check local HTML destinations/anchors and legacy visibility after Sphinx builds."""
from html.parser import HTMLParser
from pathlib import Path
import sys
from urllib.parse import unquote, urlsplit

import json
from sphinx_support import REDIRECTS


class Page(HTMLParser):
    def __init__(self, path):
        super().__init__(convert_charrefs=True)
        self.ids = set()
        self.links = []
        self.noindex = False
        self.feed(path.read_text())

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            self.ids.add(attrs['id'])
        if tag == 'meta' and attrs.get('name') == 'robots':
            self.noindex = 'noindex' in attrs.get('content', '')
        for name in ('href', 'src'):
            if attrs.get(name):
                self.links.append(attrs[name])


def check(output):
    output = output.resolve()
    pages = {path: Page(path) for path in output.rglob('*.html')}
    errors = []
    for path, page in pages.items():
        for link in page.links:
            parsed = urlsplit(link)
            if parsed.scheme or parsed.netloc:
                continue
            target = (path.parent / unquote(parsed.path)).resolve() if parsed.path else path
            if target.is_dir():
                target /= 'index.html'
            if not target.is_file():
                errors.append(f'{path.relative_to(output)}: missing {link}')
            elif parsed.fragment and target in pages and unquote(parsed.fragment) not in pages[target].ids:
                errors.append(f'{path.relative_to(output)}: missing anchor {link}')
    for old, new in REDIRECTS.items():
        if not (output / (old + '.html')).is_file() or not (output / (new + '.html')).is_file():
            errors.append('Missing compatibility redirect: ' + old)
    index = (output / 'searchindex.js').read_text()
    data = json.loads(index.removeprefix('Search.setIndex(').removesuffix(')'))
    for i, name in enumerate(data['docnames']):
        if name.startswith(('legacy/', 'internals/history/')):
            if data['titles'][i]:
                errors.append('Obsolete document remains searchable: ' + name)
            if not pages[output / (name + '.html')].noindex:
                errors.append('Missing noindex on obsolete document: ' + name)
    if errors:
        raise SystemExit('\n'.join(sorted(set(errors))))
    print(f'Checked {len(pages)} HTML pages, local links/anchors, {len(REDIRECTS)} redirects and obsolete search exclusion.')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: python tools/check_docs.py HTML_DIRECTORY')
    check(Path(sys.argv[1]))
