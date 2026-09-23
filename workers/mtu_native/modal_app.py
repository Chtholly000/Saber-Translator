"""Explicit deployment recipe for the pinned native MTU image worker.

Deploying or invoking this app can incur Modal charges. Importing this module
does not deploy it. Translation APIs run outside this GPU worker.
"""

from pathlib import Path

import modal


REVISION = "f0307a063214f915f2b1d6e5cd3233f3bf78339f"
ROOT = Path(__file__).resolve().parents[2]
image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("git", "fontconfig", "fonts-noto-cjk")
    .pip_install("uv")
    .run_commands(
        "git init /opt/mtu",
        "git -C /opt/mtu remote add origin https://github.com/hgmzhn/manga-translator-ui.git",
        f"git -C /opt/mtu fetch --depth=1 origin {REVISION}",
        f"git -C /opt/mtu checkout --detach {REVISION}",
        "uv sync --project /opt/mtu --frozen --no-default-groups --group cuda12.6 --no-install-project",
    )
    .apt_install(
        "libgl1",
        "libegl1",
        "libglib2.0-0",
        "libgomp1",
        "libmecab2",
        "libxkbcommon0",
        "libdbus-1-3",
    )
    .env({
        "PYTHONPATH": "/opt/mtu/.venv/lib/python3.12/site-packages:/opt/mtu:/root",
        "QT_QPA_PLATFORM": "offscreen",
    })
)
for relative in (
    "workers/__init__.py",
    "workers/mtu_native/__init__.py",
    "workers/mtu_native/runtime.py",
    "src/core/native_mtu_page_contract.py",
    "src/core/mtu_worker_contract.py",
    "src/core/ocr_types.py",
):
    image = image.add_local_file(ROOT / relative, "/root/" + relative)

app = modal.App("saber-mtu-native-f0307a0")


@app.cls(
    image=image,
    gpu="L4",
    timeout=900,
    scaledown_window=60,
    min_containers=0,
    max_containers=1,
)
class MtuNativeWorker:
    @modal.enter()
    def initialize(self):
        import logging
        from loguru import logger

        # Upstream OCR can log recognized text at INFO. Keep private pages out
        # of routine worker logs.
        logging.disable(logging.WARNING)
        logger.remove()
        from workers.mtu_native.runtime import MtuNativeWorkerRuntime

        self.runtime = MtuNativeWorkerRuntime()

    @modal.method()
    async def execute(self, payload):
        return await self.runtime.execute(payload)
