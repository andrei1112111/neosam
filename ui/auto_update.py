from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path


GITHUB_API_LATEST_RELEASE = (
    "https://api.github.com/repos/andrei1112111/neosam/releases/latest"
)
REQUIRED_RELEASE_TAG_PREFIX = "release"
PENDING_UPDATE_FILE = ".update_pending.json"

STATUS_CHECKING = "проверяем наличие обновлений..."
STATUS_DOWNLOADING = "загрузка обновления..."
STATUS_DOWNLOAD_ERROR = "ошибка скачивания обновления"
STATUS_LOOKUP_ERROR = "ошибка поиска новой версии приложения"


def format_up_to_date_status(version_title: str) -> str:
    clean_title = version_title.strip()
    if not clean_title:
        clean_title = "version unknown"
    return f"✓ {clean_title}"

PRESERVED_ROOT_NAMES = {
    ".git",
    ".venv",
    ".update_pending.json",
    "VERSION",
    "my_database.db",
}

PRESERVED_RELATIVE_PATHS = {
    Path("my_database.db"),
    Path("net/.sam_identity.json"),
}

IGNORED_DIR_NAMES = {
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
}


class AutoUpdateError(RuntimeError):
    pass


class ReleaseLookupError(AutoUpdateError):
    pass


class ReleaseDownloadError(AutoUpdateError):
    pass


@dataclass(frozen=True, slots=True)
class ReleaseInfo:
    title: str
    tag_name: str
    zipball_url: str


class AutoUpdater:
    def __init__(
        self,
        *,
        project_root: Path,
        api_url: str = GITHUB_API_LATEST_RELEASE,
        required_tag_prefix: str = REQUIRED_RELEASE_TAG_PREFIX,
    ) -> None:
        self.project_root = project_root
        self.api_url = api_url
        self.required_tag_prefix = required_tag_prefix
        self.version_file = self.project_root / "VERSION"
        self.pending_file = self.project_root / PENDING_UPDATE_FILE

    def read_local_version(self) -> str:
        try:
            return self.version_file.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return ""

    def finalize_pending_update(self) -> str | None:
        if not self.pending_file.exists():
            return None

        try:
            data = json.loads(self.pending_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            self.pending_file.unlink(missing_ok=True)
            return None
        title = str(data.get("title") or "").strip()
        if title:
            self.version_file.write_text(f"{title}\n", encoding="utf-8")
        self.pending_file.unlink(missing_ok=True)
        return title or None

    def fetch_latest_release(self) -> ReleaseInfo | None:
        try:
            payload = json.loads(
                self._fetch_url_bytes(
                    self.api_url,
                    headers={
                        "Accept": "application/vnd.github+json",
                        "User-Agent": "NeoSAM-Updater",
                    },
                    timeout=15,
                ).decode("utf-8")
            )
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ReleaseDownloadError) as exc:
            raise ReleaseLookupError(str(exc)) from exc

        if not isinstance(payload, dict):
            raise ReleaseLookupError("latest release payload is not an object")

        tag_name = str(payload.get("tag_name") or "").strip()
        title = str(payload.get("name") or tag_name).strip()
        zipball_url = str(payload.get("zipball_url") or "").strip()
        if not title or not zipball_url:
            raise ReleaseLookupError("latest release payload is incomplete")

        if not tag_name.startswith(self.required_tag_prefix):
            return None

        return ReleaseInfo(
            title=title,
            tag_name=tag_name,
            zipball_url=zipball_url,
        )

    def download_and_apply_release(self, release: ReleaseInfo) -> None:
        try:
            with tempfile.TemporaryDirectory(prefix="neosam-update-") as temp_dir:
                temp_path = Path(temp_dir)
                archive_path = temp_path / "release.zip"
                extract_path = temp_path / "extract"
                extract_path.mkdir(parents=True, exist_ok=True)

                self._download_archive(release.zipball_url, archive_path)
                source_root = self._extract_archive(archive_path, extract_path)
                self._copy_release_tree(source_root, self.project_root)
                self.pending_file.write_text(
                    json.dumps({"title": release.title}, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
        except ReleaseDownloadError:
            raise
        except Exception as exc:
            raise ReleaseDownloadError(str(exc)) from exc

    def _download_archive(self, url: str, destination: Path) -> None:
        try:
            data = self._fetch_url_bytes(
                url,
                headers={"User-Agent": "NeoSAM-Updater"},
                timeout=60,
            )
            destination.write_bytes(data)
        except (urllib.error.URLError, TimeoutError, ReleaseDownloadError) as exc:
            raise ReleaseDownloadError(str(exc)) from exc

    def _fetch_url_bytes(
        self,
        url: str,
        *,
        headers: dict[str, str],
        timeout: int,
    ) -> bytes:
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except (urllib.error.URLError, TimeoutError):
            if shutil.which("curl"):
                return self._fetch_url_bytes_with_curl(
                    url,
                    headers=headers,
                    timeout=timeout,
                )
            raise

    @staticmethod
    def _fetch_url_bytes_with_curl(
        url: str,
        *,
        headers: dict[str, str],
        timeout: int,
    ) -> bytes:
        command = [
            "curl",
            "-fsSL",
            "--connect-timeout",
            str(min(timeout, 15)),
            "--max-time",
            str(timeout),
        ]
        for name, value in headers.items():
            command.extend(["-H", f"{name}: {value}"])
        command.append(url)
        try:
            completed = subprocess.run(
                command,
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.decode("utf-8", errors="ignore").strip()
            raise ReleaseDownloadError(stderr or "curl request failed") from exc
        return completed.stdout

    @staticmethod
    def _extract_archive(archive_path: Path, extract_path: Path) -> Path:
        try:
            with zipfile.ZipFile(archive_path) as archive:
                archive.extractall(extract_path)
        except zipfile.BadZipFile as exc:
            raise ReleaseDownloadError("invalid release archive") from exc

        directories = [child for child in extract_path.iterdir() if child.is_dir()]
        if not directories:
            raise ReleaseDownloadError("release archive is empty")
        return directories[0]

    def _copy_release_tree(self, source_root: Path, destination_root: Path) -> None:
        for source_path in source_root.iterdir():
            if source_path.name in PRESERVED_ROOT_NAMES:
                continue
            if source_path.name in IGNORED_DIR_NAMES:
                continue

            destination_path = destination_root / source_path.name
            if self._is_preserved_path(destination_path):
                continue
            if source_path.is_dir():
                destination_path.mkdir(parents=True, exist_ok=True)
                self._copy_release_tree(source_path, destination_path)
                continue

            destination_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, destination_path)

    def _is_preserved_path(self, path: Path) -> bool:
        try:
            relative = path.resolve().relative_to(self.project_root.resolve())
        except ValueError:
            return False
        return relative in PRESERVED_RELATIVE_PATHS
