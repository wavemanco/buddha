"""Real synthetic installed-file metadata; no image or confinement claim."""

import hashlib
from pathlib import Path

from buddha.releases import _json

INVENTORY_COUNT = 24_043  # Public nb02c3b-runtime-environment.json inventory count.
ENVIRONMENT_BYTES_FLOOR = 4_013_984  # Retained opaque sizing target, not its contents.

_HELPER = b"""import hashlib
from pathlib import Path

def collect_audit():
    root = Path(__file__).parent / "venv"
    inventory = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise RuntimeError("synthetic image contains a link")
        if path.is_file():
            raw = path.read_bytes()
            inventory[path.relative_to(root).as_posix()] = {
                "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)
            }
    return {"format": "buddha.review.nb02c3-installed-runtime.v1", "inventory": inventory}
"""


def _members(count):
    yield "lib/python3.13/site-packages/fixture.py", b"# Synthetic installed fixture module.\n"
    for index in range(count - 1):
        yield (
            "lib/python3.13/site-packages/scale_fixture/data/"
            f"package_{index // 1000:02d}/record_{index:05d}.dat",
            f"Synthetic installed resource {index:05d}.\n".encode(),
        )


def build_environment(image_root, *, inventory_count=INVENTORY_COUNT):
    """Create a fresh fixture image tree before selections/owners; return its record.

    Keep image_root outside the selected component roots and study. The helper
    and manifest correspond to this synthetic tree, never a real Docker image.
    Optional generated-module declarations are omitted; inventory rows supply
    the comparable metadata size without opaque or ignored padding fields.
    """
    if not isinstance(image_root, Path) or not image_root.is_absolute():
        raise ValueError("synthetic image needs an absolute Path")
    if type(inventory_count) is not int or not 1 <= inventory_count <= INVENTORY_COUNT:
        raise ValueError("synthetic inventory count exceeds its bounded public target")
    if image_root != image_root.resolve():
        raise ValueError("synthetic image path must have one physical spelling")
    image_root.mkdir()  # A supplied or already prepared image is never rewritten.
    venv, inventory, directories = image_root / "venv", {}, set()
    for name, raw in _members(inventory_count):
        path = venv / name
        if path.parent not in directories:
            path.parent.mkdir(parents=True, exist_ok=True)
            directories.add(path.parent)
        with path.open("xb") as stream:
            stream.write(raw)
        inventory[name] = {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
    manifest = _json(
        {"format": "buddha.review.nb02c3-installed-runtime.v1", "inventory": inventory}
    )
    for name, raw in (("runtime-prepare.py", _HELPER), ("runtime-manifest.json", manifest)):
        with (image_root / name).open("xb") as stream:
            stream.write(raw)
    result = {
        "helper_sha256": hashlib.sha256(_HELPER).hexdigest(),
        "manifest_sha256": hashlib.sha256(manifest).hexdigest(),
        "inventory": inventory,
    }
    if inventory_count == INVENTORY_COUNT and len(_json(result)) < ENVIRONMENT_BYTES_FLOOR:
        raise AssertionError("synthetic environment is smaller than its declared sizing target")
    return result
