"""Setup the collection for testing."""


import logging
import os
import sys

from pathlib import Path
from typing import Optional
from typing import Tuple

import pytest


logger = logging.getLogger(__name__)

try:
    import yaml

    HAS_YAML = True
except ImportError:
    HAS_YAML = False

try:
    from ansible import __version__

    HAS_ANSIBLE = True
except ImportError:
    HAS_ANSIBLE = False

try:
    from ansible.utils.collection_loader._collection_finder import (
        _AnsibleCollectionFinder,
    )

    HAS_COLLECTION_FINDER = True
except ImportError:
    HAS_COLLECTION_FINDER = False


def pytest_addoption(parser):
    """Add the options to the pytest command.

    :param parser: The pytest parser object
    """
    parser.addoption(
        "--inject-only",
        action="store_true",
        default=False,
        help="Only inject the current ANSIBLE_COLLECTIONS_PATHS",
    )


def pytest_configure(config: pytest.Config) -> None:
    """Configure the logger.

    :param config: The pytest configuration object
    """
    log_map = {
        0: logging.CRITICAL,
        1: logging.ERROR,
        2: logging.WARNING,
        3: logging.INFO,
        4: logging.DEBUG,
    }
    level = log_map.get(config.option.verbose)
    logging.basicConfig(level=level)
    logger.debug("Logging initialized")
    inject(config.invocation_params.dir)


def get_collection_name(start_path: Path) -> Tuple[Optional[str], Optional[str]]:
    """Get the collection namespace and name from the galaxy.yml file.

    :param start_path: The path to the root of the collection
    :returns: A tuple of the namespace and name
    """
    info_file = start_path / "galaxy.yml"
    logger.info("Looking for collection info in %s", info_file)

    try:
        with info_file.open(encoding="utf-8") as fh:
            galaxy_info = yaml.safe_load(fh)
    except FileNotFoundError:
        logger.error("No galaxy.yml file found, plugin not activated")
        return None, None

    try:
        namespace = galaxy_info["namespace"]
        name = galaxy_info["name"]
    except KeyError:
        logger.error("galaxy.yml file does not contain namespace and name")
        return None, None

    logger.debug("galaxy.yml file found, plugin activated")
    logger.info("Collection namespace: %s", namespace)
    logger.info("Collection name: %s", name)
    return namespace, name


def inject(start_path: Path) -> None:
    """Inject the collection path.

    In the case of ansible > 2.9, initialize the collection finder with the collection path
    otherwise, inject the collection path into sys.path.

    :param start_path: The path where pytest was invoked
    """
    if session.config.getoption("--inject-only"):
        logger.info("Injecting only, not installing collection finder")
        inject_only()
        return

    if not HAS_ANSIBLE:
        logger.error("ansible is not installed, plugin not activated")
        return
    if not HAS_YAML:
        logger.error("pyyaml is not installed, plugin not activated")
        return

    logger.debug("Start path: %s", start_path)
    namespace, name = get_collection_name(start_path)
    if namespace is None or name is None:
        # Tests may not being run from the root of the repo.
        return

    # Determine if the start_path is in a collections tree
    collection_tree = ("collections", "ansible_collections", namespace, name)
    if start_path.parts[-4:] == collection_tree:
        logger.info("In collection tree")
        collections_dir = start_path.parents[2]

    else:
        logger.info("Not in collection tree")
        collections_dir = start_path / "collections"
        name_dir = collections_dir / "ansible_collections" / namespace / name

        # If it's here, we will trust it was from this
        if not name_dir.is_dir():
            os.makedirs(name_dir, exist_ok=True)

            for entry in start_path.iterdir():
                if entry.name == "collections":
                    continue
                os.symlink(entry, name_dir / entry.name)

    logger.info("Collections dir: %s", collections_dir)

    # TODO: Make this a configuration option, check COLLECTIONS_PATHS
    # Add the user location for any dependencies
    paths = [str(collections_dir), "~/.ansible/collections"]
    logger.info("Paths: %s", paths)

    if HAS_COLLECTION_FINDER:
        # pylint: disable=protected-access
        _AnsibleCollectionFinder(paths=paths)._install()

    # Inject the path for the collection into sys.path
    # This is needed for import udring mock tests
    sys.path.insert(0, str(collections_dir))
    logger.debug("sys.path updated: %s", sys.path)

    # TODO: Should we install any collection dependencies as well?
    # or let the developer do that?
    # e.g. ansible-galaxy collection install etc

    # Set the environment variable as courtesy for integration tests
    env_paths = os.pathsep.join(paths)
    logger.info("Setting ANSIBLE_COLLECTIONS_PATH to %s", env_paths)
    os.environ["ANSIBLE_COLLECTIONS_PATHS"] = env_paths


def inject_only():
    """Inject the current ANSIBLE_COLLECTIONS_PATHS."""

    env_paths = os.environ.get("ANSIBLE_COLLECTIONS_PATHS", "")
    for path in env_paths.split(os.pathsep):
        if path:
            sys.path.insert(0, path)
    logger.debug("sys.path updated: %s", sys.path)
    if HAS_COLLECTION_FINDER:
        # pylint: disable=protected-access
        _AnsibleCollectionFinder(paths=env_paths)._install()
