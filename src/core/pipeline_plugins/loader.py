"""Data-only registration; plugin code is imported only on its first execution.

Configuration is operator-owned Python code selection, never browser input.
Changes take effect on process restart, not halfway through an active job.
"""

import atexit
from copy import deepcopy
from dataclasses import dataclass
from importlib import import_module
import inspect
import json
import os
import re
from threading import Lock

from src.core.pipeline_profiles import (
    PIPELINE_STAGES, OPTIONAL_PIPELINE_STAGES, get_pipeline_profile,
    register_pipeline_profile, registered_pipeline_profiles, unregister_pipeline_profile,
)
from src.core.stage_backends import (
    register_stage_backend, registered_stage_backends, unregister_stage_backend,
)

STAGES = PIPELINE_STAGES + OPTIONAL_PIPELINE_STAGES
FACTORY_PATTERN = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*:[A-Za-z_]\w*")


def _name(value):
    if not isinstance(value, str):
        raise ValueError("插件和方案名称必须是字符串")
    name = value.strip().lower().replace("-", "_")
    if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
        raise ValueError("插件和方案名称只能含英文字母、数字、下划线，且以字母开头")
    return name


class LazyStagePlugin:
    """One cached implementation per registration and process, serialized calls."""

    def __init__(self, stage, name, factory, options):
        self.stage, self.name = stage, name
        self._factory, self._options = factory, deepcopy(options)
        self._instance = None
        self._lock = Lock()
        self._closed = False

    def execute(self, *args, **kwargs):
        from .validation import validate_result

        with self._lock:
            if self._closed:
                raise RuntimeError(f"阶段插件已关闭: {self.stage}/{self.name}")
            if self._instance is None:
                try:
                    module, attribute = self._factory.split(":")
                    factory = getattr(import_module(module), attribute)
                    instance = factory(**deepcopy(self._options))
                    if not callable(getattr(instance, "execute", None)):
                        raise TypeError("plugin must implement execute")
                    self._instance = instance
                except Exception:
                    raise RuntimeError(f"阶段插件加载失败: {self.stage}/{self.name}；检查模块、依赖和配置") from None
            try:
                result = self._instance.execute(*args, **kwargs)
                if inspect.isawaitable(result):
                    if inspect.iscoroutine(result):
                        result.close()
                    raise TypeError("synchronous stage port required")
            except Exception:
                # SDK exceptions may embed credentials or request/image content.
                raise RuntimeError(f"阶段插件执行失败: {self.stage}/{self.name}") from None
            validate_result(self.stage, result, args)
            return result

    def close(self):
        with self._lock:
            if self._closed:
                return
            self._closed = True
            instance, self._instance = self._instance, None
            close = getattr(instance, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    # Cleanup must not leak provider messages or skip other plugins.
                    pass


@dataclass
class PluginInstallation:
    plugins: list
    profiles: tuple
    _closed: bool = False

    def close(self):
        if self._closed:
            return
        self._closed = True
        for name in self.profiles:
            unregister_pipeline_profile(name)
        for plugin in self.plugins:
            unregister_stage_backend(plugin.stage, plugin.name)
            plugin.close()


def configure_pipeline_plugins(config):
    """Validate the whole composition before registering anything; no imports/I/O.

    A trusted factory is ``python.module:callable`` and returns an object with a
    synchronous ``execute`` method. A plugin implements exactly one stage.
    """
    if not isinstance(config, dict) or set(config) - {"schema_version", "plugins", "profiles"}:
        raise ValueError("流水线插件配置字段无效")
    if type(config.get("schema_version")) is not int or config["schema_version"] != 1:
        raise ValueError("流水线插件配置需要 schema_version: 1")
    entries, profiles = config.get("plugins", []), config.get("profiles", {})
    if not isinstance(entries, list) or not isinstance(profiles, dict):
        raise ValueError("plugins 必须是数组，profiles 必须是对象")
    available = {stage: set(registered_stage_backends(stage)) for stage in STAGES}
    plugins = []
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) - {"stage", "name", "factory", "options"}:
            raise ValueError("插件声明字段无效")
        stage = entry.get("stage")
        if not isinstance(stage, str) or stage not in STAGES:
            raise ValueError("插件必须声明一个支持的 stage")
        name = _name(entry.get("name"))
        if name in available[stage]:
            raise ValueError(f"阶段插件名称冲突: {stage}/{name}")
        factory = entry.get("factory")
        options = entry.get("options", {})
        if not isinstance(factory, str) or not FACTORY_PATTERN.fullmatch(factory):
            raise ValueError("factory 必须是 python.module:callable")
        if not isinstance(options, dict):
            raise ValueError("插件 options 必须是非秘密 JSON 对象")
        try:
            json.dumps(options, allow_nan=False)
        except (ValueError, TypeError):
            raise ValueError("插件 options 必须是有限值 JSON 数据") from None
        plugins.append(LazyStagePlugin(stage, name, factory, options))
        available[stage].add(name)

    definitions = {}
    for name, definition in profiles.items():
        name = _name(name)
        if name in definitions or name in registered_pipeline_profiles():
            raise ValueError(f"流水线方案名称冲突: {name}")
        if not isinstance(definition, dict) or set(definition) - {"extends", "stages"}:
            raise ValueError("方案只支持 extends 和 stages")
        definitions[name] = definition
    resolved = {}

    def resolve(name, visiting):
        if name in resolved:
            return resolved[name]
        if name in visiting:
            raise ValueError("流水线方案存在循环继承")
        definition = definitions[name]
        base = definition.get("extends")
        stages = {}
        if base is not None:
            base = _name(base)
            if base in definitions:
                stages.update(resolve(base, visiting | {name}))
            else:
                inherited = get_pipeline_profile(base)
                stages.update({stage: inherited.backend_for(stage) for stage in STAGES})
        overrides = definition.get("stages", {})
        if not isinstance(overrides, dict) or set(overrides) - set(STAGES):
            raise ValueError("方案 stages 包含未知阶段")
        stages.update({stage: _name(backend) for stage, backend in overrides.items()})
        if set(PIPELINE_STAGES) - set(stages):
            raise ValueError(f"方案 {name} 未定义所有核心阶段，也未继承完整方案")
        stages.setdefault("color", "local")
        for stage, backend in stages.items():
            if backend not in available[stage]:
                raise ValueError(f"方案引用未注册的阶段插件: {stage}/{backend}")
        resolved[name] = stages
        return stages

    for name in definitions:
        resolve(name, set())
    installed_plugins, installed_profiles = [], []
    try:
        for plugin in plugins:
            register_stage_backend(plugin.stage, plugin.name, lambda _, plugin=plugin: plugin)
            installed_plugins.append(plugin)
        for name, stages in resolved.items():
            register_pipeline_profile(name, stages)
            installed_profiles.append(name)
    except Exception:
        PluginInstallation(installed_plugins, tuple(installed_profiles)).close()
        raise
    return PluginInstallation(plugins, tuple(resolved))


def configure_pipeline_plugins_from_env():
    path = os.environ.get("SABER_PIPELINE_CONFIG")
    if path:
        with open(path, encoding="utf-8") as handle:
            installation = configure_pipeline_plugins(json.load(handle))
        atexit.register(installation.close)
        return installation
    return None
