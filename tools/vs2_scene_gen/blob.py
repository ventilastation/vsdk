"""The embedded scene-model blob.

Spec: "Embed the workspace as a base64+zlib blob in a trailing comment of
the generated file, so source cannot get separated from output and it
survives copy, ``git mv`` and packaging."

**Comment prefix: ``# scene-model:``, not ``# blocks:``.** The proposal's
own worked example uses ``# blocks: ...`` for a *Blockly workspace* blob
(T17, not yet built). This package's blob carries a JSON **scene model**
(:mod:`model`), a different, earlier-stage artifact -- attaching Behaviors
to declared pools/sprites, not a block program. The proposal explicitly
invites exactly this call ("adapt the comment prefix if you think a
scene-model blob should be visually distinct from a future Blockly
workspace blob, your call, document it"): keeping the two prefixes
distinct means a future T17 can tell at a glance, from the trailing
comment alone, which generator produced a given file, and a scene file
that has *both* a scene-model blob and (once T17 lands) an attached
Blockly-driven ``update()`` companion is unambiguous either way.
"""

import base64
import json
import zlib


def encode_blob(model):
    """``model`` (a plain JSON-able dict) -> the base64 text carried after
    ``# scene-model: `` -- ``sort_keys`` makes this (and therefore the
    whole generated file) deterministic: the same model always encodes to
    the same bytes, regardless of the dict's own construction order."""
    canonical = json.dumps(model, sort_keys=True, separators=(",", ":")).encode("utf-8")
    compressed = zlib.compress(canonical, 9)
    return base64.b64encode(compressed).decode("ascii")


def decode_blob(blob_text):
    """Inverse of :func:`encode_blob`: the exact model dict that produced
    ``blob_text``."""
    compressed = base64.b64decode(blob_text.encode("ascii"))
    canonical = zlib.decompress(compressed)
    return json.loads(canonical.decode("utf-8"))
