# 模块边界与依赖规则

状态：原生 MTU 整页包装、六阶段高级端口和插件配置为 `CURRENT`；持久远程任务/版本写回仍为
`TARGET`。

## 所有权表

| 区域 | 当前入口 | 拥有的事实 | 可以依赖 | 禁止承担 |
| --- | --- | --- | --- | --- |
| Vue 浏览器客户端与状态 | `vue-frontend/src/` | 用户交互、即时预览、当前页面编辑状态 | 版本化 API 类型、领域字段 | 模型加载、云凭据、服务器文件路径 |
| 浏览器流水线编排 | `vue-frontend/src/composables/translation/core/` | 可选编辑器中的步骤顺序、模式、页面上下文投影 | 原子步骤客户端、稳定编辑器类型 | 默认整页后端、具体 OCR/GPU SDK |
| 原生整页引擎 | `src/core/page_engines/`、`src/core/native_mtu_page_contract.py`、`tools/translate_page_native.py` | Agent 单页/有界批量入口、提取/翻译/完成编排、页面与区域 ID、版本契约、原子文件产物 | 惰性传输 client、Translator adapter、MTU-native 文档 | MTU 图像算法重实现、Vue、凭据持久化、BubbleState 中间态 |
| 空白气泡嵌字 | `src/core/blank_bubble_page.py`、`tools/letter_blank_page.py` | 候选框、原图绑定、框 ID→已有文字映射、独立成品 | 可替换 `BubbleSlotDetector`、现有 Saber render 端口 | OCR/翻译/去字、改变原生 MTU 翻译半程、书架或 Oracle 状态 |
| 原生 MTU Worker | `workers/mtu_native/` | 固定版本 controller 的提取/完成包装、MTU Config 映射、TextBlock 序列化与重建 | pinned MTU `MangaTranslator` 与内部对象 | 调用翻译 API、Saber 阶段重编排、项目/书架真相、请求内凭据 |
| 六阶段实验编排 | `src/core/page_pipeline.py`、`tools/translate_page.py` | profile 解析、BubbleState 组装、混合阶段实验和文件产物 | 阶段端口/注册表、编辑器领域类型 | 声称等同原生 MTU 质量、Flask/Vue、凭据持久化 |
| Flask 路由 | `src/app/api/` | HTTP 验证、错误映射、调用应用服务 | 端口/服务、序列化器 | 模型实现细节、长期任务状态 |
| 编辑器领域状态 | `src/core/config_models.py`、前端类型 | 可编辑气泡文字、几何、样式、OCR 元数据 | 纯数据类型 | 充当原生 MTU 中间状态、Flask、Modal、数据库客户端 |
| 当前算法实现 | `src/core/detection.py`、`ocr.py`、`inpainting.py`、`rendering.py`、`translation.py` | Saber 现有本地行为 | 领域类型、模型接口 | UI/书架所有权 |
| 自动流水线 profile | `src/core/pipeline_profiles.py` | 一次自动运行的五个核心阶段及可选 color 的后端选择 | 稳定后端名、阶段名 | 模型设置、凭据、UI 状态、步骤顺序 |
| 后端端口与注册 | `src/core/stage_backends/` | 六阶段各自独立的执行选择；extraction_backends 只作旧代码兼容桥 | 纯 Python callable/协议、profile 解析结果 | Flask request、Pinia、磁盘会话 |
| 执行插件装配 | `src/core/pipeline_plugins/` | 非秘密配置、显式工厂、惰性实例、输出检查和关闭 | 阶段端口、profile、受信任插件模块 | 自动扫描/执行用户代码、页面持久化、云部署 |
| 插件中间件 | `src/plugins/`、`plugins/` | 步骤前后 payload/result 扩展 | 公开插件上下文 | 模型生命周期、任务队列、核心状态替代 |
| 页面持久化 | `src/core/page_storage.py` | 会话路径、页面图片和元数据原子写入 | 版本化领域文档 | 模型推理和 UI 组件 |
| 书架 | `src/core/bookshelf_manager.py` 与相应 API/store | 书、章节、标签与章节会话关系 | 页面持久化接口 | GPU 调度细节 |
| staged MTU Worker 契约与适配器 | `src/core/mtu_worker_contract.py`、`src/core/extraction_backends/mtu_modal.py`、`src/core/stage_backends/mtu_*.py` | 六阶段高级路径中的 detect/OCR/color/inpaint JSON 转换 | PIL、Saber OCR 类型、注入的传输 client | 声称保留完整 MTU 上下文、凭据或 `TextBlock` 泄漏到上层 |
| staged Modal Worker | `src/core/modal_worker_client.py`、`workers/mtu/` | 阶段式 Worker 生命周期和固定上游镜像配方 | 阶段端口、版本化 JSON 契约 | 原生整页默认、项目真相、书架真相、浏览器凭据 |

## 当前主路径依赖方向

```text
Agent / CLI / future job API
   ↓
PageEngine + native page contract
   ├─ extract → execution adapter → pinned MTU detector / OCR / merge
   ├─ translate → replaceable control-plane Translator
   └─ render → execution adapter → pinned MTU mask / inpainter / renderer
```

主路径只在 MTU 原有 translation 接缝暂停。提取 Worker 返回稳定 ID、完整
`TextBlock.to_dict()`、raw mask 和工作图；Translator 只读 `id + text` 并返回 `id + translation`；
完成 Worker 重建 TextBlock 后继续原生 mask/inpaint/render。编辑器 adapter 是终点旁支，不得插入
这两个 native 半程之间。

## 六阶段高级路径依赖方向

```text
UI / API
   ↓
应用编排
   ↓
领域契约 + 阶段端口
   ↑
local / modal / api 执行适配器
   ↑
Saber 本地实现 / MTU / DeepSeek / 其他模型
```

在六阶段高级路径中，领域契约不能反向导入具体适配器。具体适配器可以导入供应商 SDK，但必须把返回值转换成
Saber 的稳定结果类型后再交给上层。

浏览器 Vue、MTU Qt 或将来的命令行批处理器都是**展示/控制客户端**，不是 pipeline stage
或后端适配器。它们可以调用同一任务/API 契约并各自决定怎样显示、批量提交或预览；不能把
自己的组件状态、窗口对象或 MTU `TextBlock` 变成项目真相。

`page_pipeline.py` 是高级应用层编排而不是原生 adapter：它只解析一个完整 profile，然后通过六个
registry 调用端口。它适合刻意混合或只跑部分步骤，不得作为完整漫画翻译的原生质量默认。

## 阶段端口

每一步都有独立窄接口，具体调用签名和结果格式见 `STAGE_PLUGINS.md`：

| 端口 | 最小职责 | 主要输出 |
| --- | --- | --- |
| `Detector` | 从页面找文字区域和文字蒙版 | 区域、角度、多边形、方向、文本行、mask |
| `OcrEngine` | 对给定区域识别原文 | 与区域一一对应的 OCR 结果 |
| `Translator` | 翻译一组有稳定 ID 的文本 | 与输入 ID 对应的译文和警告 |
| `Inpainter` | 用区域/mask 生成干净背景 | clean image、可选修复 mask |
| `ColorExtractor` | 从已知文本区域提取前景/背景颜色 | 与区域对应的 RGB 颜色 |
| `Renderer` | 用干净背景和气泡状态生成成品 | final image、规范化后的气泡状态 |

共享远程客户端不等于共享领域接口。例如 `ModalWorkerClient` 可以同时支持 detect、ocr、
inpaint，但调用它的三个适配器仍分别实现自己的端口。

## 适配器注册规则

- 注册名是稳定配置值，例如 `local`、`modal_mtu`、`deepseek`，不是界面显示文案。
- 注册表导入时不得加载模型、下载权重、读取秘密或建立网络连接。
- 重型初始化必须惰性执行并可在 worker 生命周期内缓存。
- 适配器返回统一错误分类：配置错误、不可重试输入错误、可重试远程错误、资源不足和取消。
- 适配器不得直接写书架或页面文件；写回由应用层在版本检查后完成。
- 后端名称、模型版本、耗时和置信度可以作为 provenance 保存，但不得改变核心字段语义。
- MTU Worker 请求必须携带明确契约版本和阶段名；图片、区域与非敏感选项是唯一输入。
  Worker 不能接收调用方 API Key、授权头、签名 URL 或 MTU 内部对象。响应缺失区域、阶段不符、
  mask 尺寸不符时，适配器必须失败，不得将本地模型作为隐式 fallback。

## staged 自动 profile

`src/core/pipeline_profiles.py` 是自动流水线的**组合点**。一个 profile 必须完整声明
`detect`、`ocr`、`translate`、`inpaint`、`render` 的后端名；它不决定步骤顺序，也不包含
API Key、模型参数或界面配置。应用启动时可用纯数据注册完整 profile；注册动作不得加载模型或
连接远程服务，实际可用性仍由对应的 stage adapter registry 验证。

在 staged 子系统内部，内置默认 profile 是 `local_saber`，五个核心阶段都指向 `local`，可选 color 也默认走 local。
当服务器通过 `SABER_REMOTE_CONFIG` 显式装配时，`remote_bootstrap.py` 才注册
`modal_mtu_deepseek`：detect/OCR/color/inpaint 为 `modal_mtu`，translate 为 `deepseek`，render
仍为 `local`。注册不会连接云端；profile 出现在列表中也不是健康检查或真实 GPU 验证。检测和 OCR
允许 `detector_backend` 或 `ocr_backend` 临时覆盖，color/translate/inpaint/render 分别允许
`color_backend`、`translator_backend`、`inpainter_backend`、`renderer_backend` 覆盖；旧
`extraction_backend` 仍兼容，但冲突必须明确报错。profile 或后端未注册时必须失败，绝不能悄悄
回退成本地模型。

六阶段统一使用独立的 `stage_backends` registry；旧 extraction 注册会桥接成 detect/ocr 两个端口。
`SABER_PIPELINE_CONFIG` 通过显式工厂配置新增插件和派生 profile，不需要修改启动代码。
远程实现已有离线端到端 fixture，但尚不等同于上游权重、GPU、冷启动和
云镜像的实测结果；新增其他 profile 仍必须先实现对应阶段端口、适配器和契约测试，不能只把名称
写进配置表来假装已经可用。

`automaticPipelineProfile` 是当前浏览器设置中的 profile 名；`createPipelineRuntime` 在任务启动时
将它规范化并冻结为 `pipelineProfile`，随后原子步骤都只传这个 runtime 值。它同时写入页面元数据
作为本次生成的 provenance。设置页从服务器读取已注册 profile；显示远程 profile 仅表示服务器
配置存在，不能替代部署/质量验证。

## 两类插件

中间件插件（原 `plugins/`）：清洗 OCR 文本、追加提示词、过滤检测框、统一样式、审计某一步结果。

阶段执行插件（`pipeline_plugins/`）：实现一个后端适配器，更换检测/OCR/修复/嵌字算法、
把计算从本机迁往 Modal，或调用新的模型 API。新增实现只需要插件模块和服务器配置，
加载和生命周期由公共装配器管理。详细规则以 `STAGE_PLUGINS.md` 为准。

插件可以包围适配器调用，但不应自己创建不可见的第二套任务系统。

## 改动落点

- 改步骤顺序：先改 `pipelineRegistry.ts` 及其测试，再核对顺序/并行两套执行器；不要用 profile
  偷偷承载步骤图。
- 改原生 OCR/修补/排字模型：优先修改 server-owned MTU Config 选择；新实现必须适配 MTU 原生
  模块接口并保留完整下游语义。改翻译模型只替换控制端 Translator adapter。
- 改原生整页执行位置：新增 PageEngine execution adapter，不复制 MTU controller 或阶段逻辑。
- 改 staged 实验使用的模型/执行位置：新增或调整 stage adapter，再新增完整 profile 和契约测试；
  浏览器客户端不应知道供应商 SDK。
- 改气泡字段：同时核对 Python/TypeScript 模型、API 序列化、保存/加载、迁移和渲染。
- 新增模型：增加插件模块和配置项，不在路由中增加供应商条件树。
- 新增执行位置：增加执行适配器和配置映射，不复制阶段业务逻辑。
- 改持久化：先定义 schema 版本与迁移，不用运行时对象直接覆盖旧文件。
