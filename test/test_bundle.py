"""Tests for the distributable Calibre plugin bundle."""

import subprocess
import zipfile
from pathlib import Path

import pytest

REQUIRED_PLUGIN_FILES = [
    "__init__.py",
    "action.py",
    "api.py",
    "cache.py",
    "config.py",
    "matcher.py",
    "models.py",
    "queries.py",
    "sync.py",
    "plugin-import-name-hardcover_sync.txt",
]

REMOVED_DEPENDENCIES = {
    "anyio",
    "backoff",
    "certifi",
    "charset_normalizer",
    "exceptiongroup",
    "gql",
    "graphql",
    "idna",
    "multidict",
    "propcache",
    "requests",
    "requests_toolbelt",
    "typing_extensions",
    "urllib3",
    "yarl",
}


@pytest.fixture(scope="module")
def plugin_zip_path():
    """Build the plugin and return the path to the ZIP file."""
    project_root = Path(__file__).parent.parent
    result = subprocess.run(  # noqa: S603
        ["bash", "scripts/bundle.sh"],  # noqa: S607
        cwd=project_root,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        pytest.fail(f"Build script failed:\n{result.stderr}")

    zip_files = list((project_root / "dist").glob("hardcover-sync-*.zip"))
    if not zip_files:
        pytest.fail("No plugin ZIP file found in dist/")
    return zip_files[0]


class TestBundleContents:
    def test_zip_is_valid(self, plugin_zip_path):
        """Verify the build produced a readable ZIP file."""
        assert plugin_zip_path.exists()
        assert plugin_zip_path.suffix == ".zip"
        with zipfile.ZipFile(plugin_zip_path) as plugin_zip:
            assert plugin_zip.namelist()

    def test_required_plugin_files_present(self, plugin_zip_path):
        """Verify all required plugin files are at the ZIP root."""
        with zipfile.ZipFile(plugin_zip_path) as plugin_zip:
            names = set(plugin_zip.namelist())

        for required_file in REQUIRED_PLUGIN_FILES:
            assert required_file in names, f"Required file {required_file!r} not found"

    def test_third_party_dependencies_are_not_bundled(self, plugin_zip_path):
        """Verify the plugin no longer ships conflicting dependency packages."""
        with zipfile.ZipFile(plugin_zip_path) as plugin_zip:
            roots = {name.split("/", 1)[0] for name in plugin_zip.namelist()}

        bundled_dependencies = roots & REMOVED_DEPENDENCIES
        assert not bundled_dependencies, (
            f"Third-party dependencies should not be bundled: {bundled_dependencies}"
        )

    def test_removed_import_hook_is_not_bundled(self, plugin_zip_path):
        """Verify the obsolete process-wide import hook is absent."""
        with zipfile.ZipFile(plugin_zip_path) as plugin_zip:
            assert "_bundled_imports.py" not in plugin_zip.namelist()

    def test_no_test_files_bundled(self, plugin_zip_path):
        """Verify project tests are excluded from the plugin."""
        with zipfile.ZipFile(plugin_zip_path) as plugin_zip:
            test_files = [name for name in plugin_zip.namelist() if "test" in name.lower()]

        assert not test_files, f"Test files should not be bundled: {test_files}"

    def test_no_build_metadata_bundled(self, plugin_zip_path):
        """Verify caches and package-manager metadata are excluded."""
        with zipfile.ZipFile(plugin_zip_path) as plugin_zip:
            names = plugin_zip.namelist()

        unwanted = [
            name
            for name in names
            if "__pycache__" in name
            or ".dist-info" in name
            or ".egg-info" in name
            or name.endswith((".pyc", ".pyo"))
        ]
        assert not unwanted, f"Build metadata should not be bundled: {unwanted}"


class TestBundleImports:
    def test_api_module_imports_without_third_party_dependencies(self):
        """Verify the API and its public model types import successfully."""
        from hardcover_sync.api import (
            AuthenticationError,
            Book,
            HardcoverAPI,
            HardcoverAPIError,
            User,
            UserBook,
        )

        assert HardcoverAPI is not None
        assert HardcoverAPIError is not None
        assert AuthenticationError is not None
        assert Book is not None
        assert User is not None
        assert UserBook is not None
