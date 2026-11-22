#!/usr/bin/env python3
"""Create a private Clang 21 resource-header overlay for TensorFlow ROCm builds.

Never modifies /usr/lib/llvm-21. Reuses unmodified resource files via symlinks.
Pass --copt=-resource-dir=<overlay> to Bazel when validating the overlay.
"""
import argparse
from pathlib import Path

MACROS = {
    "#define _ISNANd std::isnan": "#define _ISNANd __ocml_isnan_f64",
    "#define _ISNANf std::isnan": "#define _ISNANf __ocml_isnan_f32",
    "#define _ISINFd std::isinf": "#define _ISINFd __ocml_isinf_f64",
    "#define _ISINFf std::isinf": "#define _ISINFf __ocml_isinf_f32",
}
HEADER = "__clang_cuda_complex_builtins.h"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("/usr/lib/llvm-21/lib/clang/21"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = args.source.resolve(strict=True)
    output = args.output.expanduser().absolute()
    if output == source or source in output.parents or output in source.parents:
        parser.error("Overlay must be outside the system Clang resource directory")
    original = (source / "include" / HEADER).read_text()
    modified = original
    for before, after in MACROS.items():
        if original.count(before) != 1:
            parser.error(f"Expected exactly one occurrence of {before!r}")
        modified = modified.replace(before, after, 1)
    if output.exists() and not output.is_dir():
        parser.error("Overlay path is not a directory")
    output.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        if item.name != "include":
            destination = output / item.name
            if not destination.exists() and not destination.is_symlink():
                destination.symlink_to(item)
    include = output / "include"
    include.mkdir(exist_ok=True)
    for item in (source / "include").iterdir():
        if item.name != HEADER:
            destination = include / item.name
            if not destination.exists() and not destination.is_symlink():
                destination.symlink_to(item)
    destination = include / HEADER
    if destination.is_symlink():
        parser.error("Refusing to overwrite a symlink for the patched header")
    destination.write_text(modified)
    print(f"Created private Clang resource overlay: {output}")
    print(f"Patched only {HEADER}: four HIP classification macros")
    print("System LLVM files remain unchanged.")


if __name__ == "__main__":
    main()
