# Current VS2 design decisions

**Status:** implemented API revision 2. This is a summary of accepted decisions,
not a future rollout plan. The generated [API reference](../vs2/reference/index.md)
and runtime source define exact behavior.

- Scenes own layers, and layers create and own drawables. Projections belong to
  layers. Creation order within a layer determines draw order.
- `build()` creates the display graph; sealing prevents adding render objects
  during `update()`. It does not prevent arbitrary Python allocations.
- Pools reserve sprite capacity; labels use tilemaps. Current target budgets
  are exposed through `vs2.limits`, not frozen by an old proposal.
- Scene transitions are queued; after one is requested, no further game callbacks
  run that tick. Timers belong to the current showing and are discarded on exit
  or suspension. A re-entered scene runs a fresh `build()`.
- Music and base output follow the app across scene transitions and reset when
  returning to the launcher. Idle/back behavior has runtime defaults.
- Glyph maps belong in asset manifests. Geometry is read through `vs2.display`.
- V1 remains compatible for existing games, with an API guard against mixing V1
  and VS2. New games declare `api_revision: 2`.

The superseded rollout/rework proposals described a prototype API and obsolete
milestones. Their complete text remains in Git history before this change.
The early OTA A/B proposal is also deleted; [OTA](ota.md) describes the current
single-MicroPython-partition architecture.

## Work that is still separate

Deletion of proposals does not claim hardware acceptance, deployment, or every
original product request is complete. Keep [hardware acceptance](vs2-hardware-acceptance.md)
as a verification gate. Orthogonal bitmap layers from
[issue #112](https://github.com/ventilastation/vsdk/issues/112) are not part of the
current documented drawable surface. Future behaviors/editor work has its own
branches and must not be advertised as a shipped API here.
