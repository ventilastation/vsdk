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
        self.text = []
        self.edit_control = False
        self.feed(path.read_text())

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'edit-this-page' in attrs.get('class', '').split():
            self.edit_control = True
        if 'id' in attrs:
            self.ids.add(attrs['id'])
        if tag == 'meta' and attrs.get('name') == 'robots':
            self.noindex = 'noindex' in attrs.get('content', '')
        for name in ('href', 'src'):
            if attrs.get(name):
                self.links.append(attrs[name])

    def handle_data(self, text):
        self.text.append(text)


def check(output):
    output = output.resolve()
    pages = {path: Page(path) for path in output.rglob('*.html')}
    errors = []
    for path, page in pages.items():
        name = path.relative_to(output).as_posix()
        if name.startswith('internals/') or name in ('README.html', 'guides/documentation.html', 'vs2/migration.html'):
            errors.append('Repository-only or removed document was published: ' + name)
        if page.edit_control:
            errors.append('Browser editing control was published: ' + name)
        text = ' '.join(page.text)
        for phrase in ('Ventilastation VS2', 'Removed VS2 prototype', 'Migrating older games'):
            if phrase in text:
                errors.append(f'{name}: obsolete public content {phrase}')
        for link in page.links:
            parsed = urlsplit(link)
            if parsed.path == '/emulator/' or parsed.path.endswith('/guides/browser.html'):
                errors.append(f'{path.relative_to(output)}: hidden browser launch link {link}')
            if parsed.scheme or parsed.netloc:
                continue
            target = (path.parent / unquote(parsed.path)).resolve() if parsed.path else path
            if target == output / 'guides/browser.html':
                errors.append(f'{path.relative_to(output)}: hidden browser guide link {link}')
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
        if name.startswith('internals/') or name in ('README', 'guides/documentation', 'vs2/migration'):
            errors.append('Repository-only or removed document remains in search: ' + name)
        if name.startswith('legacy/'):
            if data['titles'][i]:
                errors.append('Obsolete document remains searchable: ' + name)
            if not pages[output / (name + '.html')].noindex:
                errors.append('Missing noindex on obsolete document: ' + name)
    for name in ('index.html', 'vs2/index.html'):
        if 'Ventilastation API' not in ' '.join(pages[output / name].text):
            errors.append('Missing public API title: ' + name)
    if errors:
        raise SystemExit('\n'.join(sorted(set(errors))))
    print(f'Checked {len(pages)} HTML pages, local links/anchors, {len(REDIRECTS)} redirects and obsolete search exclusion.')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: python tools/check_docs.py HTML_DIRECTORY')
    check(Path(sys.argv[1]))
