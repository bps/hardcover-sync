"""
Tests to verify that the plugin bundle includes all required dependencies.

These tests check that:
1. The build script produces a valid plugin zip
2. All required dependencies are bundled
3. The bundled modules can be imported correctly
"""

import importlib
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

# Required top-level packages that must be bundled
REQUIRED_PACKAGES = [
    "gql",
    "graphql",
    "requests",
]

# Required files at the plugin root level
REQUIRED_PLUGIN_FILES = [
    "__init__.py",
    "_bundled_imports.py",
    "action.py",
    "api.py",
    "config.py",
    "queries.py",
    "matcher.py",
    "cache.py",
    "plugin-import-name-hardcover_sync.txt",
]


@pytest.fixture(scope="module")
def plugin_zip_path():
    """Build the plugin and return the path to the zip file."""
    project_root = Path(__file__).parent.parent

    # Run the build script
    result = subprocess.run(  # noqa: S603
        ["bash", "scripts/bundle.sh"],  # noqa: S607
        cwd=project_root,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        pytest.fail(f"Build script failed:\n{result.stderr}")

    # Find the built zip
    dist_dir = project_root / "dist"
    zip_files = list(dist_dir.glob("hardcover-sync-*.zip"))

    if not zip_files:
        pytest.fail("No plugin zip file found in dist/")

    return zip_files[0]


class TestBundledDependencies:
    """Tests for verifying bundled dependencies."""

    def test_zip_file_exists(self, plugin_zip_path):
        """Verify the plugin zip file was created."""
        assert plugin_zip_path.exists()
        assert plugin_zip_path.suffix == ".zip"

    def test_zip_is_valid(self, plugin_zip_path):
        """Verify the zip file is valid and can be opened."""
        with zipfile.ZipFile(plugin_zip_path, "r") as zf:
            # Check that we can read the file list
            file_list = zf.namelist()
            assert len(file_list) > 0

    def test_required_plugin_files_present(self, plugin_zip_path):
        """Verify all required plugin files are present at the root level."""
        with zipfile.ZipFile(plugin_zip_path, "r") as zf:
            file_list = zf.namelist()

            for required_file in REQUIRED_PLUGIN_FILES:
                assert required_file in file_list, (
                    f"Required file '{required_file}' not found in plugin zip"
                )

    def test_required_packages_bundled(self, plugin_zip_path):
        """Verify all required dependency packages are bundled."""
        with zipfile.ZipFile(plugin_zip_path, "r") as zf:
            file_list = zf.namelist()

            for package in REQUIRED_PACKAGES:
                # Check for package directory or __init__.py
                package_files = [
                    f for f in file_list if f.startswith(f"{package}/") or f == f"{package}.py"
                ]
                assert len(package_files) > 0, (
                    f"Required package '{package}' not found in plugin zip"
                )

    def test_dependency_import_manifest_matches_bundle(self, plugin_zip_path):
        """Verify every bundled Python dependency can be resolved by the import hook."""
        from hardcover_sync._bundled_imports import _BUNDLED_DEPENDENCIES

        plugin_modules = {
            "__init__",
            "_bundled_imports",
            "_version",
            "action",
            "api",
            "cache",
            "config",
            "matcher",
            "models",
            "queries",
            "sync",
        }
        plugin_directories = {"dialogs", "images"}

        with zipfile.ZipFile(plugin_zip_path, "r") as zf:
            roots = {name.split("/", 1)[0] for name in zf.namelist() if "/" in name}
            roots.update(
                Path(name).stem
                for name in zf.namelist()
                if "/" not in name and name.endswith(".py")
            )

        dependency_roots = roots - plugin_modules - plugin_directories
        assert dependency_roots == _BUNDLED_DEPENDENCIES

    def test_gql_package_complete(self, plugin_zip_path):
        """Verify the gql package has all required submodules."""
        required_gql_files = [
            "gql/__init__.py",
            "gql/client.py",
            "gql/gql.py",
            "gql/graphql_request.py",
            "gql/transport/__init__.py",
            "gql/transport/requests.py",
        ]

        with zipfile.ZipFile(plugin_zip_path, "r") as zf:
            file_list = zf.namelist()

            for required_file in required_gql_files:
                assert required_file in file_list, (
                    f"Required gql file '{required_file}' not found in plugin zip"
                )

    def test_graphql_core_package_complete(self, plugin_zip_path):
        """Verify the graphql-core package has required submodules."""
        required_graphql_files = [
            "graphql/__init__.py",
            "graphql/language/__init__.py",
            "graphql/type/__init__.py",
        ]

        with zipfile.ZipFile(plugin_zip_path, "r") as zf:
            file_list = zf.namelist()

            for required_file in required_graphql_files:
                assert required_file in file_list, (
                    f"Required graphql file '{required_file}' not found in plugin zip"
                )

    def test_no_test_files_bundled(self, plugin_zip_path):
        """Verify test files are not included in the bundle."""
        with zipfile.ZipFile(plugin_zip_path, "r") as zf:
            file_list = zf.namelist()

            test_files = [f for f in file_list if "test" in f.lower()]
            # Filter out legitimate files from dependencies that might contain "test" in the name
            allowed_patterns = [
                "requests",  # requests library internals
                "latest",  # version files
                "anyio",  # anyio has _testing.py and pytest_plugin.py
                "pytest",  # pytest plugin files in dependencies
                "_testing",  # common pattern in libraries
            ]
            test_files = [
                f for f in test_files if not any(allowed in f for allowed in allowed_patterns)
            ]

            assert len(test_files) == 0, f"Test files should not be bundled: {test_files}"

    def test_no_pycache_bundled(self, plugin_zip_path):
        """Verify __pycache__ directories are not included."""
        with zipfile.ZipFile(plugin_zip_path, "r") as zf:
            file_list = zf.namelist()

            pycache_files = [f for f in file_list if "__pycache__" in f]
            assert len(pycache_files) == 0, f"__pycache__ should not be bundled: {pycache_files}"

    def test_no_dist_info_bundled(self, plugin_zip_path):
        """Verify .dist-info directories are not included."""
        with zipfile.ZipFile(plugin_zip_path, "r") as zf:
            file_list = zf.namelist()

            dist_info_files = [f for f in file_list if ".dist-info" in f]
            assert len(dist_info_files) == 0, f".dist-info should not be bundled: {dist_info_files}"


class TestBundleImports:
    """Tests that verify imports work correctly from the bundle."""

    def test_plugin_import_does_not_modify_sys_path(self):
        """Verify plugin initialization leaves the global module search path unchanged."""
        import hardcover_sync

        original_path = sys.path.copy()
        importlib.reload(hardcover_sync)

        assert sys.path == original_path

    def test_dependency_finder_ignores_unbundled_modules(self):
        """Verify the import hook is limited to exact bundled package names."""
        from hardcover_sync._bundled_imports import BundledDependencyFinder

        finder = BundledDependencyFinder("hardcover_sync")

        assert finder.find_spec("gqlfoo") is None
        assert finder.find_spec("graphql_ws_next") is None
        assert finder.find_spec("prefs") is None
        assert finder.find_spec("config") is None
        assert finder.find_spec("unrelated") is None

    def test_dependency_finder_installation_is_idempotent(self):
        """Verify plugin reloads leave only one current dependency finder."""
        from hardcover_sync._bundled_imports import (
            _FINDER_MARKER,
            install_bundled_dependency_finder,
        )

        original_meta_path = sys.meta_path.copy()
        try:
            install_bundled_dependency_finder("hardcover_sync")
            install_bundled_dependency_finder("hardcover_sync")
            matching_finders = [
                finder
                for finder in sys.meta_path
                if getattr(finder, "marker", None) == _FINDER_MARKER
            ]
            assert len(matching_finders) == 1
        finally:
            sys.meta_path[:] = original_meta_path

    def test_api_module_imports(self):
        """Verify the api module can be imported with its dependencies."""
        # This tests that gql and other dependencies are available
        from hardcover_sync.api import (
            HardcoverAPI,
            HardcoverAPIError,
            AuthenticationError,
            Book,
            User,
            UserBook,
        )

        # Verify classes exist
        assert HardcoverAPI is not None
        assert HardcoverAPIError is not None
        assert AuthenticationError is not None
        assert Book is not None
        assert User is not None
        assert UserBook is not None

    def test_gql_imports_work(self):
        """Verify gql can be imported directly."""
        from gql import Client, gql
        from gql.graphql_request import GraphQLRequest

        assert Client is not None
        assert gql is not None
        assert GraphQLRequest is not None

    def test_graphql_core_imports_work(self):
        """Verify graphql-core can be imported."""
        from graphql import parse, DocumentNode

        assert parse is not None
        assert DocumentNode is not None

    def test_requests_imports_work(self):
        """Verify requests can be imported."""
        import requests

        assert requests.get is not None
        assert requests.post is not None
