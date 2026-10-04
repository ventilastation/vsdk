# Maintain the documentation

The SDK owns all technical documentation. The website owns its Spanish/English
introduction and links to these pages, without copying tutorial or API prose.
[Read the Docs](https://ventilastation.readthedocs.io/) and the website's `/docs/` build the same Sphinx/MyST/Furo sources.
API pages use docstrings; tutorial steps remain executable Python files.

## Build and check

From the SDK root:

```sh
python3 -m venv .venv-docs
.venv-docs/bin/python -m pip install -r docs/requirements.txt
.venv-docs/bin/python -m sphinx -b html -W --keep-going docs /tmp/vsdk-docs-html
.venv-docs/bin/python tools/check_docs.py /tmp/vsdk-docs-html
```

Open `/tmp/vsdk-docs-html/index.html`. CI runs the same warning-strict build and
checks local generated page/anchor links, redirects, and legacy search exclusion.
Existing runtime CI continues to exercise tutorial steps and the finished game.

## Keep one clear route

- Start new developers at setup and the VS2 first-game chapter.
- Update exact API behavior in docstrings and its teaching page together.
- Keep operational/engineering details under internals, outside the tutorial.
- Mark obsolete API prose at its entrance and keep it out of search results.
- Delete superseded proposals after extracting unique decisions, requirements,
  or pending work. Git history retains their full text. Keep useful incident
  evidence in explicitly historical pages.
- Keep old published tutorial/API URLs as redirects when widening the site.
- Run external link checks separately: they depend on third-party availability.
- Document hardware verification only when there is evidence; a docs build is
  not a hardware test.

## Review of the improvement proposal

The `docs/documentation-improvement-proposal` branch was reviewed at `075993f`.
Its core recommendation—one existing Sphinx site, audience-based navigation,
VS2-first examples, and separation of current guidance from history—is applied
here. Its baseline was `f7b3a2c`; claims about unfinished ROM-width migration
were already stale by `3dd4339`, which implements width/frame bias-by-one.
The remaining hardware checks retain their stated status. The live site at
`https://ventilastation.readthedocs.io/` serves tutorial/reference URLs directly
without an `/en/latest/` prefix; redirects preserve those observed URLs.

This change deletes `vs2-api-rework-proposal.md`, `internals/vs2-api-plan.md`,
and `ota-upgrade-plan.md`; their replacements are the current reference,
[migration guide](../vs2/migration.md), [accepted decisions](../internals/vs2-decisions.md),
and [OTA reference](../internals/ota.md). It corrects teaching claims about the
framebuffer, scene sealing, dynamic tuple indexing and geometry provenance.

The proposal's larger hardware/audio/OTA runbook audit remains separate work.
Publishing those existing pages makes their scope visible; it does not certify
all of their old commands or hardware claims. Historical investigations remain
available with status labels, outside the new-game route.
