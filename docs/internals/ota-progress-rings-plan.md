# OTA progress rings — original request (plan)

Status as of 2026-07-26: **implemented per the spec below and confirmed
visible on real hardware, but blocked on a sprite-buffer corruption bug**
that makes the rings render as glitchy noise instead of clean bands during
real partition writes. See
[ota-ring-sprite-corruption.md](ota-ring-sprite-corruption.md) for the bug
and hand-off instructions — that is the actual next step, not this file.
This file exists so the original request survives independently of any one
implementation attempt.

The as-built reference doc (data flow, file list, ring color table) lives
in [ota.md](ota.md)'s "On-device progress display" section. This file is
the request as given, kept verbatim so a future rewrite has the real spec
to work from instead of reverse-engineering it from code or from ota.md's
description of whatever was actually built.

## The ask, verbatim

Opening request:

> great. let's work on showing the progress of the OTA in the LEDs.
> currently the progress was coded but never actually worked, the LEDs
> kept showing the Starfield. with the new framebuffers in internal ram,
> the flash writing should not block the CPU, so let's try again to inform
> the progress with some informative text while doing the ota

Follow-up answering a clarifying question about scope (both recovery and
in-place paths, exact ring semantics):

> do the same for both paths:
> - use the rings formed by leaving turned on a couple of LEDs to report
>   progress and activity
> - turn only the outermost leds blue while connecting to wifi
> - calculate the number of blocks to write in all partitions that need to
>   be written
> - show percentage of writing progress of all partitions as a 50% gray
>   ring closing in. 0% outmost, 99% innermost
> - show activity as a simultaneous 10% yellow ring that goes in and out,
>   changing position after each write operation
> - for OTA files, calculate the total of bytes
> - similar white and green rings for percentage progress and write
>   operations.
> - the white ring always takes precedence over the other colors if they
>   sit in the same position

(A second clarifying question was answered with: "what I just wrote above
should answer this" — i.e. no additional scope beyond the above.)

Validation instruction, establishing hardware screenshots as the required
proof rather than code review or host-side tests alone:

> you can test this by watching the display output via the workbench.
> There are scripts in tool to do this. Please put a few screenshots here
> to show me

After the first round of screenshots showed no visible rings at all (the
starfield was silently drawing over them — see below):

> in the first three screenshot you shared I can't see any rings. this
> sounds like the same issue I had before: the old upgrader did not show
> any rings at all. instead it showed the Starfield that was interrupted
> often as the flash was being written. Please use vs2 for the upgrade
> sequences, disable the Starfield always, and make it your goal to show
> me screenshots of the fixed display during upgrades with clearly visible
> gray, yellow, green and blue rings in each step of the process

And, after a second round of screenshots showed rings that were now
visible but visually corrupted:

> the screenshots show all glitchy, the sprites might have been replaced
> with any other memory content. please write down my original request as
> a plan to be implemented in the internal docs, commit the changes so
> far, and write down instructions so I can ask another agent to work on
> that

## Normalized spec

One ring per kind of information, all shown simultaneously, each occupying
a single LED radius (there's no glyph/font renderer in this codebase — see
`vsdk_ota_rings.py`'s own docstring for why a value can only be conveyed by
*which row* lights up):

| Ring | Color | Meaning |
|---|---|---|
| outermost LED only | blue | connecting to WiFi |
| radius, 0%=outermost / 99%=innermost | 50% gray | fraction of blocks written, across every partition that needs writing this session |
| radius, bounces in/out one LED per block write | 10% yellow | tier 2/3 "it's alive" activity pulse |
| radius, 0%=outermost / 99%=innermost | white | fraction of bytes synced, across every LFS file that needs syncing this session |
| radius, bounces in/out one LED per HTTP chunk | green | tier 1 activity pulse |

Rules:
- Applies identically to both update paths: recovery/factory OTA and the
  normal in-place (`ota_start`) OTA.
- White always wins when two rings land on the same LED (explicit
  requirement). The rest of the stacking order was left to implementation
  judgment.
- "Total" (the ring's denominator) is computed once upfront: total blocks
  across partitions whose stored hash doesn't match the manifest, total
  bytes across files whose cache entry doesn't match.
