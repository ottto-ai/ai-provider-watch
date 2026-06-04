from __future__ import annotations

import shutil
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py as _build_py

APW_PACKAGE_DATA_DIRS = ("data", "registries", "schemas", "sources")


class build_py(_build_py):
    def run(self) -> None:
        super().run()
        self._apw_data_outputs: list[str] = []
        project_root = Path(__file__).resolve().parent
        package_data_root = Path(self.build_lib) / "ai_provider_watch" / "_data"
        if package_data_root.exists():
            shutil.rmtree(package_data_root)
        package_data_root.mkdir(parents=True)
        for dirname in APW_PACKAGE_DATA_DIRS:
            source = project_root / dirname
            target = package_data_root / dirname
            shutil.copytree(source, target)
            self._apw_data_outputs.extend(
                str(path) for path in target.rglob("*") if path.is_file()
            )

    def get_outputs(self, include_bytecode: int = 1) -> list[str]:
        return super().get_outputs(include_bytecode) + getattr(self, "_apw_data_outputs", [])


setup(cmdclass={"build_py": build_py})
