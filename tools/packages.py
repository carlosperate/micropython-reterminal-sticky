#!/usr/bin/env python3
# Writes each lib/ package's package.json from its manifest.py, so a mip install from GitHub gets
# the files, version and dependencies the firmware freezes. With --check it writes nothing and
# fails if a package.json is stale, or a package imports another lib/ package without require().

import argparse
import ast
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB = os.path.join(ROOT, "lib")
MPY_DIR = os.path.join(ROOT, "micropython")
REPO = "github:carlosperate/micropython-reterminal-sticky"

sys.path.append(os.path.join(MPY_DIR, "tools"))
import manifestfile


class Manifest(manifestfile.ManifestFile):
    def __init__(self):
        path_vars = {
            "MPY_DIR": MPY_DIR,
            "MPY_LIB_DIR": os.path.join(MPY_DIR, "lib/micropython-lib"),
        }
        super().__init__(manifestfile.MODE_COMPILE, path_vars)
        self.add_library("sticky-lib", LIB)
        self.requires = []

    # The package's own requirements, not theirs.
    def require(self, name, *args, **kwargs):
        if len(self._metadata) == 1:
            self.requires.append(name)
        super().require(name, *args, **kwargs)


def imported_names(path):
    with open(path) as f:
        tree = ast.parse(f.read(), path)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from (alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            yield node.module.split(".")[0]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="write nothing, report stale files")
    args = parser.parse_args()

    paths = sorted(root for root, _, files in os.walk(LIB) if "manifest.py" in files)
    found = {}
    for path in paths:
        manifest = Manifest()
        manifest.execute(os.path.join(path, "manifest.py"))
        found[path] = (
            manifest,
            [f for f in manifest.files() if f.metadata is manifest.metadata()],
        )

    # Top-level module names each package installs.
    provides = {
        path: {f.target_path.split("/")[0].removesuffix(".py") for f in files}
        for path, (_, files) in found.items()
    }
    by_name = {os.path.basename(path): path for path in paths}

    errors = []
    for path, (manifest, files) in found.items():
        rel = os.path.relpath(path, ROOT)
        urls = []
        for f in files:
            source = os.path.relpath(f.full_path, path)
            if source.startswith(".."):
                source = REPO + "/" + os.path.relpath(f.full_path, ROOT)
            urls.append([f.target_path, source])
        deps = []
        for name in manifest.requires:
            if name in by_name:
                deps.append([REPO + "/" + os.path.relpath(by_name[name], ROOT), "HEAD"])
            else:
                deps.append([name, "latest"])
        package = {"urls": sorted(urls), "deps": deps, "version": manifest.metadata().version}

        for f in files:
            for name in set(imported_names(f.full_path)) - provides[path]:
                owners = [os.path.basename(p) for p in paths if name in provides[p]]
                if owners and not set(owners) & set(manifest.requires):
                    source = os.path.relpath(f.full_path, ROOT)
                    errors.append("{}: imports {} without require()".format(source, name))

        text = json.dumps(package, indent=2) + "\n"
        target = os.path.join(path, "package.json")
        current = open(target).read() if os.path.exists(target) else None
        if current != text:
            if args.check:
                errors.append("{}/package.json is stale: run make packages".format(rel))
            else:
                with open(target, "w") as f:
                    f.write(text)

    for error in errors:
        print(error)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
