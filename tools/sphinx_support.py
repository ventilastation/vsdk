"""Publication glue shared by Read the Docs and the website documentation build."""
from pathlib import Path
import html
import posixpath
import re
from urllib.parse import quote, urlsplit


# Published URLs from the former docs/vs2 source root stay usable.
VS2_PAGES = (
    'glossary', 'going-further', 'design-notes',
    'tutorial/index', 'tutorial/first-game', 'tutorial/display', 'tutorial/sprites',
    'tutorial/pools', 'tutorial/tilemaps-and-text', 'tutorial/scenes-and-input',
    'tutorial/budgets', 'reference/index', 'reference/scene', 'reference/drawables',
    'reference/services', 'reference/errors',
)
REDIRECTS = {name: 'vs2/' + name for name in VS2_PAGES}
REDIRECTS['guides/browser'] = 'guides/desktop'


def source_links(app, docname, source):
    """Link repo files outside the Sphinx root to their actual GitHub source.

    Markdown paths remain relative for GitHub readers. Published documents remain
    local; repository-only documents link to their Markdown on GitHub.
    """
    docs = Path(app.srcdir).resolve()
    repo = docs.parent
    parent = (docs / docname).parent

    def replace(match):
        raw = match.group(1)
        target = raw.strip('<>')
        parsed = urlsplit(target)
        if parsed.scheme or target.startswith('#'):
            return match.group(0)
        path = (parent / parsed.path).resolve()
        if not path.exists():
            return match.group(0)  # Do not conceal broken links.
        if path.is_relative_to(docs):
            if path.is_dir():
                for index in ('README.md', 'index.md'):
                    if (path / index).is_file():
                        path = path / index
                        break
            docname = path.relative_to(docs).with_suffix('').as_posix()
            if docname in app.env.found_docs:
                relative = posixpath.relpath(path, parent)
                return '](' + relative + ('#' + parsed.fragment if parsed.fragment else '') + ')'
        if not path.is_relative_to(repo):
            return match.group(0)
        kind = 'tree' if path.is_dir() else 'blob'
        url = 'https://github.com/ventilastation/vsdk/' + kind + '/main/' + quote(path.relative_to(repo).as_posix())
        return '](' + url + ('#' + parsed.fragment if parsed.fragment else '') + ')'

    source[0] = re.sub(r'\]\((<[^>]+>|[^)\s]+)\)', replace, source[0])


def exclude_obsolete_search(app, env):
    for docname in env.found_docs:
        if docname.startswith('legacy/'):
            env.metadata[docname]['nosearch'] = True


def obsolete_robots(app, pagename, templatename, context, doctree):
    if pagename.startswith('legacy/'):
        context['metatags'] += '<meta name="robots" content="noindex">'


def write_redirects(app, exception):
    if exception or app.builder.name != 'html':
        return
    output = Path(app.outdir)
    for old, new in REDIRECTS.items():
        target = output / (new + '.html')
        if not target.is_file():
            raise RuntimeError('Redirect destination was not built: ' + new)
        path = output / (old + '.html')
        if old in app.env.found_docs:
            raise RuntimeError('Redirect would replace a real document: ' + old)
        path.parent.mkdir(parents=True, exist_ok=True)
        url = posixpath.relpath(new + '.html', posixpath.dirname(old) or '.')
        escaped = html.escape(url, quote=True)
        path.write_text(
            '<!doctype html><html lang="en"><meta charset="utf-8">'
            '<meta name="robots" content="noindex">'
            '<meta http-equiv="refresh" content="0; url=' + escaped + '">'
            '<title>Documentation moved</title><p>This page moved to '
            '<a href="' + escaped + '">the current documentation</a>.</p>'
            '<script>location.replace(' + repr(url) + ' + location.hash);</script></html>')


def setup(app):
    app.connect('source-read', source_links)
    app.connect('env-updated', exclude_obsolete_search)
    app.connect('html-page-context', obsolete_robots)
    app.connect('build-finished', write_redirects)
    return {'parallel_read_safe': True, 'parallel_write_safe': True}
