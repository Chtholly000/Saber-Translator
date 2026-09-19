"""Explicit deployment recipe: modal deploy -m workers.mtu.modal_app.

Deploying or invoking this app may incur Modal charges. Importing it does not
deploy it. The image uses the audited MTU revision and its frozen dependency lock.
"""

from pathlib import Path
import modal

REVISION = "f0307a063214f915f2b1d6e5cd3233f3bf78339f"
ROOT = Path(__file__).resolve().parents[2]
image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("git")
    .pip_install("uv")
    .run_commands(
        "git init /opt/mtu",
        "git -C /opt/mtu remote add origin https://github.com/hgmzhn/manga-translator-ui.git",
        f"git -C /opt/mtu fetch --depth=1 origin {REVISION}",
        f"git -C /opt/mtu checkout --detach {REVISION}",
        "uv sync --project /opt/mtu --frozen --no-default-groups --group cuda12.6 --no-install-project",
    )
    # Keep runtime libraries after the large Python/CUDA layer so a small
    # system-library adjustment does not invalidate the dependency download.
    .apt_install(
        "libgl1",
        "libegl1",
        "libglib2.0-0",
        "libgomp1",
        "libmecab2",
        "libxkbcommon0",
        "libdbus-1-3",
    )
    .env({"PYTHONPATH": "/opt/mtu/.venv/lib/python3.12/site-packages:/opt/mtu:/root"})
)
for relative in ("workers/__init__.py", "workers/mtu/__init__.py", "workers/mtu/runtime.py",
                 "src/core/mtu_worker_contract.py", "src/core/ocr_types.py"):
    image = image.add_local_file(ROOT / relative, "/root/" + relative)

app = modal.App("saber-mtu-f0307a0")


@app.cls(image=image, gpu="L4", timeout=600, scaledown_window=60,
         min_containers=0, max_containers=1)
class MtuWorker:
    @modal.enter()
    def initialize(self):
        import logging
        from loguru import logger
        # Upstream OCR logs include recognized text at INFO. Keep it out of logs.
        logging.disable(logging.WARNING)
        logger.remove()
        from workers.mtu.runtime import MtuWorkerRuntime
        self.runtime = MtuWorkerRuntime()

    @modal.method()
    async def execute(self, payload):
        return await self.runtime.execute(payload)
