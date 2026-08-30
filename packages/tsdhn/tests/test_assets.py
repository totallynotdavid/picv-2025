import hashlib
import io
import json
import shutil
import tarfile
from pathlib import Path

import pytest

from tsdhn.assets import (
    ModelStore,
    _default_data_root,
    _download,
    _extract_model_archive,
)

# Keep the archive fixture independent from the validator's constants.
MODEL_DIRS = ("bathy", "ttt_mundo")
MODEL_FILES = (
    "pacifico.mat",
    "maper1.mat",
    "mecfoc.dat",
    "puertos.txt",
    "tidal.dat",
    "bathy/grid_a.grd",
    "bathy/xa.dat",
    "bathy/ya.dat",
    "ttt_mundo/cortado.i2",
)


def _build_model_dir(root: Path) -> Path:
    model_dir = root / "model"
    for dirname in MODEL_DIRS:
        (model_dir / dirname).mkdir(parents=True)
    for relative_name in MODEL_FILES:
        path = model_dir / relative_name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{relative_name}\n", encoding="utf-8")
    return model_dir


def _build_archive(
    tmp_path: Path, *, nested_root: str | None = "tsdhn-model-1.0.0"
) -> Path:
    model_dir = _build_model_dir(tmp_path / "src")
    archive = tmp_path / "archive.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        arcname = nested_root or "."
        tar.add(model_dir, arcname=arcname if nested_root else ".")
    return archive


class _FakeResponse(io.BytesIO):
    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


def test_download_rejects_non_https_urls(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        _download("http://example.com/model.tar.gz", tmp_path / "out.tar.gz")


def test_download_writes_the_response_body(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    payload = b"archive-bytes"

    def fake_urlopen(url: str, timeout: int) -> _FakeResponse:
        assert url == "https://example.com/model.tar.gz"
        return _FakeResponse(payload)

    monkeypatch.setattr("tsdhn.assets.urllib.request.urlopen", fake_urlopen)
    destination = tmp_path / "out.tar.gz"

    _download("https://example.com/model.tar.gz", destination)

    assert destination.read_bytes() == payload


def test_extract_model_archive_finds_a_single_nested_root(tmp_path: Path) -> None:
    archive = _build_archive(tmp_path, nested_root="tsdhn-model-1.0.0")
    target = tmp_path / "installed"

    _extract_model_archive(archive, target)

    for dirname in MODEL_DIRS:
        assert (target / dirname).is_dir()


def test_extract_model_archive_uses_manifest_when_present(tmp_path: Path) -> None:
    model_dir = _build_model_dir(tmp_path / "src")
    manifest = {"model_root": "payload/model-data"}
    nested = tmp_path / "src" / "manifest_root" / "payload" / "model-data"
    nested.parent.mkdir(parents=True)
    shutil.copytree(model_dir, nested)
    (tmp_path / "src" / "manifest_root" / "manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )

    archive = tmp_path / "archive.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(tmp_path / "src" / "manifest_root", arcname=".")

    target = tmp_path / "installed"
    _extract_model_archive(archive, target)

    for dirname in MODEL_DIRS:
        assert (target / dirname).is_dir()


def test_extract_model_archive_raises_when_no_valid_root_exists(tmp_path: Path) -> None:
    archive = tmp_path / "archive.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        empty = tmp_path / "empty.txt"
        empty.write_text("nothing here")
        tar.add(empty, arcname="empty.txt")

    with pytest.raises(RuntimeError, match="valid TSDHN model dataset"):
        _extract_model_archive(archive, tmp_path / "installed")


def test_extract_model_archive_cannot_write_outside_the_staging_directory(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "archive.tar.gz"
    payload = b"should not escape"
    with tarfile.open(archive, "w:gz") as tar:
        member = tarfile.TarInfo("../outside.txt")
        member.size = len(payload)
        tar.addfile(member, io.BytesIO(payload))

    with pytest.raises(tarfile.OutsideDestinationError):
        _extract_model_archive(archive, tmp_path / "installed")

    assert not (tmp_path / "outside.txt").exists()


def test_model_store_install_downloads_verifies_and_extracts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    archive = _build_archive(tmp_path)
    archive_bytes = archive.read_bytes()
    digest = hashlib.sha256(archive_bytes).hexdigest()

    def fake_download(url: str, destination: Path) -> None:
        destination.write_bytes(archive_bytes)

    monkeypatch.setattr("tsdhn.assets._download", fake_download)
    store = ModelStore(root=tmp_path / "data")

    dataset = store.install("1.0.0", sha256=digest)

    assert dataset.version == "1.0.0"
    assert dataset.managed
    for dirname in MODEL_DIRS:
        assert (dataset.path / dirname).is_dir()


def test_model_store_install_rejects_a_checksum_mismatch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    archive = _build_archive(tmp_path)
    archive_bytes = archive.read_bytes()

    monkeypatch.setattr(
        "tsdhn.assets._download",
        lambda url, destination: destination.write_bytes(archive_bytes),
    )
    store = ModelStore(root=tmp_path / "data")

    with pytest.raises(RuntimeError, match="checksum mismatch"):
        store.install("1.0.0", sha256="0" * 64)


def test_model_store_install_is_idempotent_without_force(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    store = ModelStore(root=tmp_path / "data")
    installed = _build_model_dir(tmp_path / "data" / "models")
    target = store.dataset_dir("1.0.0")
    installed.rename(target)

    def fail_download(url: str, destination: Path) -> None:
        raise AssertionError("should not download when already installed")

    monkeypatch.setattr("tsdhn.assets._download", fail_download)
    dataset = store.install("1.0.0", url="https://example.com/never-used.tar.gz")

    assert dataset.path == target


def test_model_store_status_reports_missing_entries(tmp_path: Path) -> None:
    store = ModelStore(root=tmp_path / "data")

    status = store.status("1.0.0")

    assert status["installed"] is False
    assert status["missing"] == [
        *(f"{dirname}/" for dirname in MODEL_DIRS),
        *MODEL_FILES,
    ]


def test_model_store_status_reports_a_valid_installed_dataset(tmp_path: Path) -> None:
    store = ModelStore(root=tmp_path / "data")
    source = _build_model_dir(tmp_path / "source")
    target = store.dataset_dir("1.0.0")
    target.parent.mkdir(parents=True)
    source.rename(target)

    assert store.status("1.0.0") == {
        "version": "1.0.0",
        "path": str(target),
        "installed": True,
        "missing": [],
    }


def test_model_store_resolve_installed_returns_none_when_absent(tmp_path: Path) -> None:
    store = ModelStore(root=tmp_path / "data")

    assert store.resolve_installed("1.0.0") is None


def test_model_store_release_asset_url_matches_the_github_release_convention() -> None:
    store = ModelStore(root=Path("unused"), repository="acme/tsdhn")

    url = store.release_asset_url("1.2.3")

    assert url == (
        "https://github.com/acme/tsdhn/releases/download/v1.2.3/"
        "tsdhn-model-v1.2.3.tar.gz"
    )


def test_default_data_root_prefers_tsdhn_data_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("TSDHN_DATA_HOME", str(tmp_path / "explicit"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))

    assert _default_data_root() == tmp_path / "explicit"


def test_default_data_root_falls_back_to_xdg_data_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("TSDHN_DATA_HOME", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))

    assert _default_data_root() == tmp_path / "xdg" / "tsdhn"
