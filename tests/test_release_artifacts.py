import tarfile
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest

from tools import check_release_artifacts


def _write_artifacts(dist: Path, *, artifact_version: str) -> None:
    dist.mkdir()
    metadata = (f"Metadata-Version: 2.1\nName: ttsready\nVersion: {artifact_version}\n\n").encode()
    wheel_path = dist / f"ttsready-{artifact_version}-py3-none-any.whl"
    with ZipFile(wheel_path, "w") as archive:
        archive.writestr(f"ttsready-{artifact_version}.dist-info/METADATA", metadata)

    sdist_path = dist / f"ttsready-{artifact_version}.tar.gz"
    member = tarfile.TarInfo(f"ttsready-{artifact_version}/PKG-INFO")
    member.size = len(metadata)
    with tarfile.open(sdist_path, "w:gz") as archive:
        archive.addfile(member, BytesIO(metadata))


def test_release_artifact_checker_rejects_tag_version_mismatch(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    _write_artifacts(dist, artifact_version="1.2.3")
    monkeypatch.setattr(check_release_artifacts, "DIST", dist)
    monkeypatch.setenv("RELEASE_TAG", "v1.2.4")

    with pytest.raises(SystemExit, match="expected ttsready 1.2.4, found ttsready 1.2.3"):
        check_release_artifacts.main()
