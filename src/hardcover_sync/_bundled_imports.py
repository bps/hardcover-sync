"""Import bundled dependencies through Calibre's plugin namespace."""

import importlib
import importlib.abc
import importlib.util
import sys
from importlib.machinery import ModuleSpec
from types import ModuleType

# Top-level packages installed by gql[requests] and included in the plugin ZIP.
_BUNDLED_DEPENDENCIES = frozenset(
    {
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
)
_FINDER_MARKER = "hardcover_sync_bundled_dependencies"


class _AliasLoader(importlib.abc.Loader):
    """Alias a dependency loaded through Calibre's plugin namespace."""

    def __init__(self, module: ModuleType) -> None:
        self.module = module

    def create_module(self, spec: ModuleSpec) -> None:
        return None

    def exec_module(self, module: ModuleType) -> None:
        # Re-export without executing the module twice. The namespaced module can
        # still be initializing during a circular import, so forward attributes
        # that were not present when this alias was created.
        module.__dict__.update(self.module.__dict__)
        module.__dict__["__getattr__"] = lambda name: getattr(self.module, name)
        module.__dict__["__dir__"] = lambda: dir(self.module)


class BundledDependencyFinder(importlib.abc.MetaPathFinder):
    """Resolve only this plugin's bundled third-party dependencies."""

    marker = _FINDER_MARKER

    def __init__(self, plugin_package: str) -> None:
        self.plugin_package = plugin_package

    def find_spec(
        self,
        fullname: str,
        path: object = None,
        target: ModuleType | None = None,
    ) -> ModuleSpec | None:
        root_name = fullname.partition(".")[0]
        if root_name not in _BUNDLED_DEPENDENCIES:
            return None

        namespaced_name = f"{self.plugin_package}.{fullname}"
        try:
            namespaced_spec = importlib.util.find_spec(namespaced_name)
        except (ImportError, AttributeError, ValueError):
            return None
        if namespaced_spec is None:
            return None

        module = importlib.import_module(namespaced_name)
        is_package = hasattr(module, "__path__")
        spec = importlib.util.spec_from_loader(
            fullname,
            _AliasLoader(module),
            origin=namespaced_spec.origin,
            is_package=is_package,
        )
        if spec is not None and is_package:
            spec.submodule_search_locations = module.__path__
        return spec


def install_bundled_dependency_finder(plugin_package: str) -> None:
    """Install a current, plugin-specific finder without changing ``sys.path``."""
    sys.meta_path[:] = [
        finder for finder in sys.meta_path if getattr(finder, "marker", None) != _FINDER_MARKER
    ]
    # Prefer packages already supplied by the host. The finder is a fallback for
    # dependencies that are only available inside this plugin's ZIP.
    sys.meta_path.append(BundledDependencyFinder(plugin_package))
