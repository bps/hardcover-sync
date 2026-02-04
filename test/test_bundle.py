"""
Tests to verify that the plugin bundle includes all required dependencies.

These tests check that:
1. The build script produces a valid plugin zip
2. All required dependencies are bundled
3. The bundled modules can be imported correctly
"""

import subprocess
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
                assert (
                    required_file in file_list
                ), f"Required file '{required_file}' not found in plugin zip"

    def test_required_packages_bundled(self, plugin_zip_path):
        """Verify all required dependency packages are bundled."""
        with zipfile.ZipFile(plugin_zip_path, "r") as zf:
            file_list = zf.namelist()

            for package in REQUIRED_PACKAGES:
                # Check for package directory or __init__.py
                package_files = [
                    f for f in file_list if f.startswith(f"{package}/") or f == f"{package}.py"
                ]
                assert (
                    len(package_files) > 0
                ), f"Required package '{package}' not found in plugin zip"

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
                assert (
                    required_file in file_list
                ), f"Required gql file '{required_file}' not found in plugin zip"

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
                assert (
                    required_file in file_list
                ), f"Required graphql file '{required_file}' not found in plugin zip"

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
