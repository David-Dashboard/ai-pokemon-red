"""Generic 4-connected component labelling for numpy-only blob detection.

Extracted here so multiple modules can reuse it without core importing games/
(which would violate the import-boundary contract).

The same algorithm exists in games/pokemon_red/saliency._clusters but that
module is game-specific. This is the canonical core version.
"""
from __future__ import annotations


def connected_components(pixel_set: set) -> list[set]:
    """4-connected components of a set of (x, y) pixel coords.

    Parameters
    ----------
    pixel_set:
        A set of (x, y) integer tuples (column, row) representing foreground pixels.

    Returns
    -------
    list[set]
        One set per connected component; each set contains (x, y) tuples.
    """
    seen: set = set()
    out: list[set] = []
    for start in pixel_set:
        if start in seen:
            continue
        comp: set = set()
        stack = [start]
        while stack:
            p = stack.pop()
            if p in comp or p not in pixel_set:
                continue
            comp.add(p)
            seen.add(p)
            x, y = p
            stack += [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
        out.append(comp)
    return out
