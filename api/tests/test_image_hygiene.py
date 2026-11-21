"""Nothing secret may enter the API image.

Found live on 2026-11-15: the VPS deploy key had been copied to `api/app/Concierge` in the release
tree and was baked into the running image, world-readable inside the container
(`-rw-r--r-- /srv/app/Concierge`, first line `-----BEGIN OPENSSH PRIVATE KEY-----`). The API runs
as root in that container, so any code execution in the API handed over the host's root SSH key —
and the compose files mount nothing that would have prevented it walking out.

The file has been removed from the release tree and the image rebuilt. These checks keep it out.
"""
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[2]
CONTEXT = [REPO / "api" / "app", REPO / "api" / "static"]
FORBIDDEN_NAMES = {"Concierge", "Concierge.pub", "id_rsa", "id_ed25519"}
FORBIDDEN_SUFFIXES = {".pem", ".key", ".p12", ".pfx"}
FORBIDDEN_MARKERS = (b"BEGIN OPENSSH PRIVATE KEY", b"BEGIN RSA PRIVATE KEY",
                     b"BEGIN EC PRIVATE KEY", b"BEGIN PRIVATE KEY")


def _files():
    for root in CONTEXT:
        for path in root.rglob("*"):
            if path.is_file():
                yield path


def test_no_private_key_material_is_in_the_build_context():
    offenders = []
    for path in _files():
        if path.name in FORBIDDEN_NAMES or path.suffix in FORBIDDEN_SUFFIXES:
            offenders.append(str(path.relative_to(REPO)))
            continue
        try:
            head = path.read_bytes()[:4096]
        except OSError:
            continue
        if any(marker in head for marker in FORBIDDEN_MARKERS):
            offenders.append(str(path.relative_to(REPO)))
    assert not offenders, (
        "key material would be baked into the API image: " + ", ".join(offenders))


def test_the_build_ignores_exclude_key_material():
    for name in ("Containerfile.api.dockerignore",):
        body = (REPO / "scripts" / "vps" / name).read_text()
        assert "**/Concierge" in body and "*.pem" in body.replace("**/", ""), (
            f"{name} must keep key material out of the build context")
