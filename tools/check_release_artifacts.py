import os
import tarfile
from email import policy
from email.parser import BytesParser
from pathlib import Path
from zipfile import ZipFile

DIST = Path("dist")


def read_metadata(path: Path) -> tuple[str | None, str | None]:
    if path.suffix == ".whl":
        with ZipFile(path) as archive:
            metadata_paths = [
                name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
            ]
            if len(metadata_paths) != 1:
                raise ValueError(f"{path}: expected one .dist-info/METADATA file")
            content = archive.read(metadata_paths[0])
    else:
        with tarfile.open(path, "r:gz") as archive:
            metadata_files = [
                member
                for member in archive.getmembers()
                if (
                    member.isfile()
                    and member.name.count("/") == 1
                    and member.name.endswith("/PKG-INFO")
                )
            ]
            if len(metadata_files) != 1:
                raise ValueError(f"{path}: expected one PKG-INFO file")
            metadata_file = archive.extractfile(metadata_files[0])
            if metadata_file is None:
                raise ValueError(f"{path}: could not read PKG-INFO")
            content = metadata_file.read()

    metadata = BytesParser(policy=policy.default).parsebytes(content)
    return metadata.get("Name"), metadata.get("Version")


def main() -> None:
    release_tag = os.environ.get("RELEASE_TAG", "")
    if not release_tag:
        raise SystemExit("RELEASE_TAG is required")
    expected_version = release_tag.removeprefix("v")

    wheels = sorted(DIST.glob("*.whl"))
    sdists = sorted(DIST.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise SystemExit(
            f"Expected one wheel and one .tar.gz source distribution in {DIST}, "
            f"found {len(wheels)} wheel(s) and {len(sdists)} source distribution(s)"
        )

    for artifact in [*wheels, *sdists]:
        try:
            name, version = read_metadata(artifact)
        except (OSError, tarfile.TarError, ValueError) as error:
            raise SystemExit(f"Invalid release artifact {artifact}: {error}") from error
        if name != "ttsready" or version != expected_version:
            raise SystemExit(
                f"{artifact}: expected ttsready {expected_version}, found {name} {version}"
            )
        print(f"Validated {artifact}: {name} {version}")


if __name__ == "__main__":
    main()
