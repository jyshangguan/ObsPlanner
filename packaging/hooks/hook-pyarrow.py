"""Package only the PyArrow runtime needed by Streamlit's core serializer."""

from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_dynamic_libs,
    collect_submodules,
)


_OPTIONAL_MODULES = (
    "pyarrow._acero",
    "pyarrow._azurefs",
    "pyarrow._csv",
    "pyarrow._dataset",
    "pyarrow._dataset_orc",
    "pyarrow._dataset_parquet",
    "pyarrow._dataset_parquet_encryption",
    "pyarrow._feather",
    "pyarrow._flight",
    "pyarrow._fs",
    "pyarrow._gcsfs",
    "pyarrow._hdfs",
    "pyarrow._json",
    "pyarrow._orc",
    "pyarrow._parquet",
    "pyarrow._parquet_encryption",
    "pyarrow._s3fs",
    "pyarrow._substrait",
)


def _is_runtime_module(name: str) -> bool:
    return "tests" not in name and not name.startswith(_OPTIONAL_MODULES)


def _is_core_binary(source: str) -> bool:
    name = Path(source).name
    if name.startswith("libarrow_flight") or name.startswith("libarrow_python_flight"):
        return False
    if name.startswith("libarrow_python_parquet_encryption"):
        return False
    if name.endswith((".so", ".pyd")) and not name.startswith("lib."):
        return False
    return True


hiddenimports = collect_submodules("pyarrow", filter=_is_runtime_module)
datas = []
binaries = [
    item for item in collect_dynamic_libs("pyarrow") if _is_core_binary(item[0])
]
