# MTU 上游集成说明

状态：上游审计和 Worker 适配代码为 `CURRENT`；真实云镜像/GPU 输出验证仍为 `TARGET`。

## 固定版本

- 上游：`https://github.com/hgmzhn/manga-translator-ui`
- 审计 revision：`f0307a063214f915f2b1d6e5cd3233f3bf78339f`
- 对应 tag：`v3.0.4`
- 许可证：GPL-3.0；模型权重可能有额外许可证限制，部署前逐项核对。

不要依赖浮动 `main`。实现适配器时必须在构建文件中固定 revision 或不可变镜像摘要，并在
本文记录升级后的 revision。

## 上游文档现状

MTU 有较完整的 README、`doc/DEVELOPMENT.md`、工作流说明、双语 Wiki 蓝图和大量 changelog。
这些文档适合使用和维护 MTU，但没有为 Saber 定义稳定的跨仓库 detection/OCR/inpaint/render
契约，也没有根 `AGENTS.md`。因此 Saber 不能把 MTU 内部对象当作自己的持久格式。

升级时优先阅读 MTU 的当前开发说明和对应版本 changelog；历史 changelog 只作证据。

## 可复用模块

在 v3.0.4 中，核心能力主要位于：

- `manga_translator/detection/`：检测实现和注册映射。
- `manga_translator/ocr/`：OCR 实现和调度。
- `manga_translator/translators/`：翻译器注册和链式调度。
- `manga_translator/inpainting/`：修复模型和调度。
- `manga_translator/rendering/`：排版、富文本和渲染。
- `manga_translator/utils/textblock.py`：MTU 内部文字区域对象。
- `manga_translator/manga_translator.py`：完整流水线编排。
- `manga_translator/server/routes/translation.py`：完整翻译、导入/导出以及部分处理 API。

MTU 的配置枚举和注册表是内部实现事实，不是 Saber 的用户配置 schema。`TextBlock` 也只能在
MTU adapter 内部存在。

### v3.0.4 架构审计结论

MTU 的 `detection/__init__.py`、`ocr/__init__.py`、`inpainting/__init__.py` 与
`translators/__init__.py` 都有“名称/枚举 → 实现类”的内部注册映射，并提供惰性 `prepare`、
`dispatch`、缓存和 `unload`。`rendering/__init__.py` 同样按 `Renderer` 配置选择渲染器。
这正是 Saber 可以借鉴的**按阶段注册、惰性加载、worker 内缓存**模式。

但这些注册表是 MTU 代码内的固定枚举，不是可跨进程发现的插件协议；完整执行顺序、可变
`Context`、中间对象和错误处理仍集中在约五千行的 `manga_translator/manga_translator.py`。
其 Qt `desktop_qt_ui` 与 editor 模块也直接依赖 MTU `TextBlock` 和配置，属于 MTU 自己的客户端，
不是可替换的 Saber 编辑器接口。故 MTU 应提供模型实现，不能成为 Saber 的项目控制器、持久化
格式、自动流水线或浏览器客户端。

## 推荐接入方式

首选在 Modal Worker 中以固定版本 Python 依赖调用 MTU 的窄模块，并在 worker 边界完成转换：

```text
Saber stage request
  → MTU adapter
  → pinned MTU detector/OCR/textline merger/inpainter
  → normalize coordinates, masks, text and styles
  → Saber stage response
```

不推荐把 MTU 的完整 Web/桌面 UI 带进 Saber，也不推荐直接调用它的完整翻译 API后再拆结果，
因为那会重复 Saber 已有的编排、翻译和项目状态。

可以先用完整 MTU API 做一次性对照测试，但生产适配器应使用我们需要的最小阶段入口。

Saber 的自动 profile 仅在各阶段 adapter 已注册并通过契约测试后才引用它们。当前可选的
`modal_mtu_deepseek` 组合 MTU 的 detect/OCR/color/inpaint adapter 和独立 DeepSeek 翻译 adapter，
并保留 Saber renderer。profile 不能直接指向 MTU 完整 controller，也不能把 MTU Qt editor 当作
profile 的一项。

### CURRENT：Worker v2 接缝

`src/core/mtu_worker_contract.py`、`src/core/extraction_backends/mtu_modal.py` 和
`src/core/stage_backends/mtu_*.py` 定义 detect/OCR/color/inpaint 的受测接缝。
`workers/mtu/runtime.py` 只调用该 revision 的 `detection.dispatch`、`ocr.dispatch`、
`textline_merge.dispatch` 和 `inpainting.dispatch`；`workers/mtu/modal_app.py` 是固定 revision 与
CUDA 依赖组的部署配方。控制进程的 `modal_worker_client.py` 只在真正执行时才导入 Modal SDK，
`remote_bootstrap.py` 只在显式非秘密配置存在时注册 profile。

Worker 请求/响应使用 `saber-mtu-worker/v2`；严禁把 API Key、签名 artifact URL、HTTP response、
Modal object、Pydantic Config 或 `TextBlock` 放进 payload。OCR/color 必须按 `region-N` ID 对齐并完整
返回；detect 的可选 mask 和 inpaint 返回图必须与输入同尺寸且为 base64 PNG。离线 fixture 覆盖横排、
竖排、旋转框、空页、mask 尺寸不符、顺序反转与凭据隔离；真实 Worker 接入仍须执行相同类型的 GPU
fixture，不能把离线结果当成模型质量证明。

## 禁止做法

- 把 `manga_translator/` 整目录复制进本仓库。
- 从 MTU `main` 动态安装而不固定 commit/tag。
- 让 MTU `TextBlock`、Pydantic Config 或磁盘工程文件泄漏到 Saber UI/持久层。
- 让 MTU 自己保存 Saber 书架或覆盖页面 revision。
- 在 Oracle 控制面安装整套 MTU GPU 依赖。
- 未核对模型权重许可证就打包或持久缓存权重。

## 字段转换重点

适配器测试至少覆盖：

- 原图像素坐标与缩放恢复；
- 多边形、角度、横排/竖排方向；
- 文本行与气泡的归属；
- mask 模式、尺寸和阈值；
- OCR 空结果、置信度和引擎名称；
- MTU rich text 与 Saber 普通文本/样式的可表达范围；
- 字体回退、行距、描边、旋转和自动字号；
- 没有区域、部分失败、取消和显存不足。

不能无损映射的字段必须显式降级并写入 warning，不能静默丢弃。

## 升级流程

1. 记录旧 revision、目标 revision 和目标版本 changelog。
2. 比较上述模块的注册表、公共函数签名、`TextBlock`、mask 和渲染行为。
3. 在隔离 worker 环境构建目标版本，不在 Oracle 上试装 GPU 依赖。
4. 运行固定 fixture：至少包括横排、竖排、旋转框、空页、复杂气泡和手动气泡。
5. 比较规范化 JSON、mask 尺寸和渲染图；确认人工字段不被改写。
6. 更新 adapter、契约测试、本文件 revision 和模型许可证记录。
7. 通过后再切换 backend profile；保留可回退的旧镜像摘要。
