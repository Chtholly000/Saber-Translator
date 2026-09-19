"""Opt-in Modal transport, scoped by the SDK to the operator's own workspace."""

from threading import Lock


class ModalWorkerClient:
    def __init__(self, app_name, class_name="MtuWorker", environment_name=None):
        self.app_name = app_name
        self.class_name = class_name
        self.environment_name = environment_name
        self._worker = None
        self._lock = Lock()

    def execute(self, payload):
        try:
            if self._worker is None:
                with self._lock:
                    if self._worker is None:
                        import modal
                        kwargs = {"environment_name": self.environment_name} if self.environment_name else {}
                        self._worker = modal.Cls.from_name(self.app_name, self.class_name, **kwargs)()
            return self._worker.execute.remote(dict(payload))
        except ImportError:
            raise RuntimeError("远程执行需要安装 requirements-remote.txt 中的 Modal SDK") from None
        except Exception:
            raise RuntimeError("MTU Worker 调用失败；请检查 Modal 部署、认证与 Worker 日志") from None
