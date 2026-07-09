"""Per-app API selection guard.

Games may use either the legacy ``ventilastation.sprites`` API or the new
top-level ``vs2`` API. Mixing both inside one game is intentionally rejected so
the renderer can choose one memory model for that game.
"""

_current_slug = None
_declared_api = None
_claimed_by_slug = {}


def begin_app(slug, declared_api=None):
    global _current_slug, _declared_api
    _current_slug = slug
    _declared_api = declared_api
    if slug is not None and declared_api:
        existing = _claimed_by_slug.get(slug)
        if existing is not None and existing != declared_api:
            raise ImportError(
                "App %s declared API %s but already imported %s"
                % (slug, declared_api, existing)
            )


def current_app():
    return _current_slug


def claim(api_name, module_name):
    slug = _current_slug
    if slug is None:
        return
    if _declared_api and _declared_api != api_name:
        raise ImportError(
            "App %s declares API %s but %s imports %s"
            % (slug, _declared_api, module_name, api_name)
        )
    existing = _claimed_by_slug.get(slug)
    if existing is None:
        _claimed_by_slug[slug] = api_name
        return
    if existing != api_name:
        raise ImportError(
            "App %s cannot mix APIs: already using %s, tried %s from %s"
            % (slug, existing, api_name, module_name)
        )


def claimed_api(slug=None):
    if slug is None:
        slug = _current_slug
    return _claimed_by_slug.get(slug)


def reset():
    global _current_slug, _declared_api
    _current_slug = None
    _declared_api = None
    _claimed_by_slug.clear()
