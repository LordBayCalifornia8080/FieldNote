"""Build a source-only ZIP using an explicit allowlist; exclude local data and dependencies."""

import hashlib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = {
    "README.md",
    "LICENSE",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "CHANGELOG.md",
    "THIRD_PARTY.md",
    "pyproject.toml",
    "requirements.lock",
    "requirements-dev.lock",
    "Dockerfile",
    "compose.yaml",
    ".env.example",
    ".gitignore",
    ".dockerignore",
    ".gitattributes",
    "package.json",
    "package-lock.json",
}
SOURCE_DIRS = {"fieldnotes", "docs", "scripts", "tests", ".github"}
EXTENSIONS = {".py", ".sql", ".js", ".mjs", ".html", ".css", ".svg", ".md", ".yml", ".yaml"}


def package(destination=None):
    destination = Path(destination or ROOT.parent / "fieldnotes-0.1.0-source.zip")
    paths = sorted(
        p
        for p in ROOT.rglob("*")
        if p.is_file()
        and (
            p.relative_to(ROOT).as_posix() in ROOT_FILES
            or (
                p.relative_to(ROOT).parts[0] in SOURCE_DIRS
                and p.suffix in EXTENSIONS
                and "__pycache__" not in p.parts
            )
        )
    )
    manifest = "".join(
        f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(ROOT).as_posix()}\n"
        for p in paths
    )
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in paths:
            archive.write(path, "fieldnotes/" + path.relative_to(ROOT).as_posix())
        archive.writestr("fieldnotes/SHA256SUMS", manifest)
        assert archive.testzip() is None
    print(f"{destination.name}: {len(paths) + 1} files, {destination.stat().st_size:,} bytes")
    return destination


if __name__ == "__main__":
    package()
