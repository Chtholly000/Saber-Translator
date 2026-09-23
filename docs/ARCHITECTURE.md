# 系统架构

状态：`CURRENT + TARGET`。每一节单独标注，未标为 `CURRENT` 的能力不能视为已经上线。

## CURRENT：主路径是 Agent 调用的原生 MTU 后端

完整页面的默认质量边界不是浏览器，也不是 Saber 自己重排的六阶段流水线，而是固定版本的
MTU 原生控制器：

```text
Agent / CLI / future Oracle job API
        │
        ▼
PageEngine (`mtu_native`)
        │ extract_page / bounded extract_pages
        ▼
Modal native MTU worker
        └─ MTU detection → OCR → textline merge
        │
        ▼
MTU extraction document
  ├─ stable region IDs
  ├─ complete TextBlock.to_dict() payloads
  └─ raw mask + working image
        │
        ▼
replaceable control-plane Translator
  └─ DeepSeek today; another adapter later
        │ one batch translation call; results keyed by page + stable region ID
        ▼
Modal native MTU worker
  └─ render_page / bounded render_pages
     rehydrate TextBlock → MTU mask refinement → inpaint → render
        │
        ▼
final.png + clean.png + mask.png + MTU-native rendered document
```

源码入口是 `src/core/page_engines/`、`src/core/native_mtu_page_contract.py`、
`workers/mtu_native/` 和 `tools/translate_page_native.py`。包装层不实现检测、OCR、文本合并、
蒙版优化、修复或排版算法；它只把非秘密配置映射到固定版本 MTU `Config`，在 MTU 原有
translation 接缝暂停一次，并分别调用原 controller 的预翻译与完成路径。翻译 API 由控制端
适配器调用，所以 GPU 不等待外部语言模型，API 凭据也不进入 Modal。

暂停时每个区域都带稳定 ID 和完整 `TextBlock.to_dict()` 字段；完成 Worker 按 ID 注入译文并
重新构造 MTU `TextBlock`，不会经过 `BubbleState`。只有明确进入 Saber 编辑器时，才允许由独立
外层 adapter 投影为 `BubbleState`；该投影不是原生流水线的中间状态。直接调用与部署边界见
`workers/mtu_native/README.md`。

模块化表示“给原模块加标准接头”：修改 `page.ocr.ocr` 选择固定版本 MTU 已支持的另一 OCR，
其余 MTU 控制器语义保持不变。完全新的 OCR 必须在 worker 内适配 MTU 的原生 OCR 接口并补齐
下游需要的文字列、方向、概率和颜色等语义，不能把中间状态降成 Saber 的框与字符串再重建。
Modal 只是图像计算执行位置；DeepSeek 是控制端 Translator 的一个实现。

## CURRENT：空白气泡页是独立的嵌字路径

已有空白对白框、且文字由 Agent 或调用者提供时，不应强迫页面经过 OCR、翻译和去字。
`tools/letter_blank_page.py` 使用 `BubbleSlotDetector` 从原图提取候选框，按稳定框 ID 匹配文字，
再交给 Saber 现有 CPU renderer 生成 PNG。当前有固定 MTU MangaLens 的 Modal GPU 适配器和本机
明暗轮廓适配器；两者均可由新检框实现替换，不改变映射/嵌字。它不插入上面的原生 MTU 半程，
也不改变完整翻译的默认路径。实页验证与误报边界见
[BLANK_BUBBLE_PAGE.md](./BLANK_BUBBLE_PAGE.md)。

## CURRENT：Saber 浏览器与六阶段组合是可选客户端/高级路径

仓库仍包含一个本地 Flask 应用配合 Vue 单页前端：

```text
Vue 浏览器界面
  ├─ Pinia 图片、气泡、会话、设置状态
  ├─ 原子步骤流水线与并行池
  └─ 精细编辑和浏览器预览
          │ HTTP / JSON / base64 image
          ▼
Flask 应用
  ├─ /api/parallel/detect
  ├─ /api/parallel/ocr
  ├─ /api/parallel/color
  ├─ /api/parallel/translate
  ├─ /api/parallel/inpaint
  ├─ /api/parallel/render
  ├─ 书架、会话和页面存储 API
  └─ 插件 before/after hooks
          │
          ▼
本进程 Python 模型、外部模型 API、文件系统
```

源码入口：

- `app.py`：Flask 创建、蓝图注册、运行目录和插件初始化。
- `src/app/api/translation/parallel_routes.py`：六个主要原子步骤 API。
- `vue-frontend/src/composables/translation/core/pipelineRegistry.ts`：不同模式的步骤链真相源。
- `vue-frontend/src/composables/translation/core/runtime.ts`：`PipelineRuntime` 与页面级 `TaskContext`。
- `vue-frontend/src/composables/translation/core/atomicSteps.ts`：步骤结果如何写回上下文。
- `src/core/config_models.py`：Python `BubbleState` 序列化模型。
- `src/core/page_storage.py`：页面图片、页面元数据和会话元数据的持久化。
- `src/core/page_pipeline.py`：不依赖 HTTP/UI 的六阶段实验编排器，直接按 profile 调用端口；
  它不是原生 MTU 默认路径。

六阶段高级路径由 `src/core/pipeline_profiles.py` 组合。其内部默认 profile 是
`local_saber`，其 detect / OCR / translate / inpaint / render 都选 `local`。
显式提供 `SABER_REMOTE_CONFIG` 后还会注册 `modal_mtu_deepseek`：检测/OCR/取色/修复使用
MTU Worker，翻译使用 DeepSeek 官方 API，渲染使用 Saber CPU。配置可用不等于整条远程
组合已实测；所附 MTU Worker 的检测/OCR/取色/修补已在一张公开竖排样图上通过真实 Modal GPU
调用，同一批四条 OCR 文字也已通过独立的 DeepSeek 实际翻译调用。无界面客户端已把真实 Modal
四阶段、此前实际 DeepSeek 结果和 Saber renderer 串成一次出图，但尚未在同一运行中重新调用
DeepSeek，也没有串成浏览器任务。
五个主 API 以及可选 color API 都会通过 profile 解析后端；六阶段使用 `stage_backends/` 中
各自独立的 registry，OCR 插件不要求实现检测。`extraction_backends/` 是旧注册的兼容桥；detect/OCR 保留旧的
`extraction_backend` 参数作为过渡。Flask 仍同步等待结果；这不代表当前修复质量已达生产要求、
浏览器整链或远程任务协议已经部署验证。具体能力与验证边界见 `workers/mtu/README.md`。

Vue 是可选浏览器客户端，不是自动流水线的所有者。它可以被另一客户端（例如批处理客户端）
替换，只要后者遵守任务/API 和持久化契约；MTU 的 Qt 界面也不能直接当作 Saber 客户端嵌入。

自动任务在 `createPipelineRuntime` 启动时从 `automaticPipelineProfile` 取得并冻结 profile；五个主
步骤和取色将同一 `pipeline_profile` 发给 API，页面元数据记录 `pipelineProfile`。默认仍为
`local_saber`，浏览器设置可以选择服务器显式配置的 profile。旧的逐气泡翻译、高质量翻译和
校对尚未迁移，遇到非本地 profile 会明确拒绝。

MTU Worker v2 契约覆盖检测/OCR/取色/修复。`workers/mtu/runtime.py` 已实现对固定 MTU 窄模块的
调用和字段转换，`modal_worker_client.py` 提供惰性的认证 SDK client；独立部署定义已通过 SDK
构建并部署，固定版本 detector 与 48px OCR 已在 Modal L4 上用一张 3065×4096 竖排样图
完成真实调用。DeepSeek 是独立阶段，已用该页产生的四条 OCR 文字完成一次真实调用；这仍不覆盖
完整浏览器链路或广泛模型品质。随后无界面客户端在同一页实际执行 Modal 取色和 lama_mpe 修补，
并由 Saber CPU renderer 生成最终 PNG；结果仍有明显残字和一处排版越界，所以只是接口兼容性与
像素写回证明，不是质量验收。原子路由的本地模型导入已延迟，但完整 app.py 仍包含旧的重型依赖，
不能宣称 Oracle 轻量部署包已经完成。

`SABER_PIPELINE_CONFIG` 可声明六阶段的独立执行插件，并用 profile 继承只替换其中一步。
`src/core/pipeline_plugins/` 负责配置检查、工厂惰性导入、实例复用、串行调用、输出检查和关闭。
原有 `plugins/` before/after 中间件继续包围执行调用。两类插件均不提供持久任务/幂等协议。
安装方法、运行边界和模板以 `docs/STAGE_PLUGINS.md` 为准。

## CURRENT：状态所有权

当前前端 `TaskContext` 聚合一页处理过程中的坐标、蒙版、OCR、颜色、译文、干净背景、
最终图和 `bubbleStates`。持久化时，`page_storage.py` 将页面元数据和图片产物写入会话目录。

目前存在以下风险，后续模块化必须正面处理：

- Python `BubbleState`、TypeScript `BubbleState`、`TaskContext` 和保存 payload 存在重复字段。
- 图片通过 base64 放进同步请求，适合本地但不适合长期远程任务和大批量页面。
- 部分步骤既负责调用模型，又负责把结果投影到 UI 状态。
- `bubbleId` 和 `manualFields` 已提供本地字段锁保护，但没有 provenance、页面 revision
  比较或可见的解锁/冲突处理 UI。

## TARGET：目标部署拓扑

```text
Agent / automation
  ├─ 提交批量任务、查看状态、取得产物
  └─ 需要时才把页面交给浏览器编辑器
          │
          ▼
Oracle 控制面
  ├─ 身份、项目状态和任务状态
  ├─ 图片与工程文件存储
  ├─ 调度与失败重试
  ├─ 调用翻译 API
  └─ 导出 PNG / ZIP / PDF / CBZ
          │
          ▼
Modal GPU Worker
  ├─ 固定版本 MTU 提取半程：detection / OCR / merge
  └─ 固定版本 MTU 完成半程：mask / inpainting / rendering
          │
          ▼
固定版本的 MTU 引擎或其他模型实现
```

职责划分：

- Agent/自动化是常规调用者；浏览器只拥有可选交互和即时预览，不拥有最终持久状态。
- Oracle 拥有项目、任务、产物引用和翻译 API adapter，但不安装 CUDA/PyTorch GPU 栈。
- Modal 拥有短生命周期计算和模型缓存，不拥有书架或工程真相。
- 外部模型 API 只返回某一步结果，不获得覆盖整个项目状态的权力。
- GitHub 的 Saber fork 是应用代码真相源；Oracle 运维配置属于独立私有运维仓库。

## TARGET：流水线是可选步骤图

完整翻译只是其中一条路径：

```text
detect → ocr → translate → inpaint → render
```

以下路径必须是一等公民：

```text
手动嵌字：导入图片 → 手动画框/输入文字 → render
只抽字：detect → ocr → export
只去字：detect/手动蒙版 → inpaint → export
重新翻译：已保存原文 → translate → render
重新排版：已保存气泡与译文 → render
```

颜色提取、术语抽取、保存和导出属于可选能力，不应迫使所有路径运行完整链路。

## CURRENT：高级阶段插件与三层职责

六阶段高级组合的模块化分成三个互不混淆的维度；它不能替代上面的原生整页默认：

1. 阶段端口：`Detector`、`OcrEngine`、可选 `ColorExtractor`、`Translator`、`Inpainter`、`Renderer`。
2. 执行适配器：`local`、`modal`、`http_api`。
3. 展示/控制客户端：Vue 浏览器、批处理 CLI、或其他遵守 API 的客户端。

例如 `MTU OCR on Modal` 是“OCR 阶段端口 + Modal 执行适配器 + MTU 实现”的组合。
切换已适配 OCR 只改变配置；新模型添加一个插件模块和配置项，不改变路由、书架、编辑器或页面格式。
六阶段执行端口已可独立替换；Vue 等客户端仍通过 API 替换，不是可热插拔的 UI 插件。

完整 staged profile 把五个核心阶段和可选 color 的已注册适配器组合成一次**高级自动运行**。它不是视觉工作流编辑器，
也不是另一套编排引擎：步骤图仍由 pipeline controller 拥有。这样可以把 GPU、API 模型和
渲染器整体换掉，同时保留“打开页面后自动处理并出图”的行为。

多个阶段可以共享同一个底层客户端和模型容器，但对上层仍暴露独立契约。这样既能在 Modal
复用已加载模型，又不会把检测与 OCR 永久绑死。

## TARGET：远程任务边界

本地开发可以继续同步调用。远程模式应使用可重试的任务协议：

```text
提交任务 → 返回 job_id → 查询/接收状态 → 获取版本化结果 → 原子写回页面
```

图片应逐步从请求内 base64 迁移为受控 artifact 引用。任务必须带 `project_id`、`page_id`、
`stage`、输入版本和幂等键，防止重试时重复覆盖人工修改。

## 尚未实施

- Modal 取色/修复已完成单张竖排样图兼容性验证；仍缺多方向、多背景品质验证、参数调优和持久模型缓存。
- 异步远程任务队列、超时/取消传播、幂等与页面 revision 写回。
- 完整 Saber 控制面的 GPU 依赖剥离与 Oracle 轻量运行包。
- DeepSeek 专用配置界面；现有 OpenAI-compatible 能力是否足够仍需验证。
- 版本化的跨语言项目 schema、字段 provenance、页面 revision 和人工锁管理 UI。
- Oracle 部署、备份和恢复方案。

## CURRENT：独立抽字、嵌字与整页客户端

`tools/extract_text.py` 只调用 detect/OCR 端口并导出气泡 JSON；`tools/typeset.py` 直接消费
图片与 BubbleState JSON，只调用 render 端口。后者已用真实 Saber CPU 渲染器验证空白图出字，
不依赖前面四步。AI 可以生成文字/坐标 JSON，浏览器编辑器不是调用这些能力的必需条件。

原生整页默认客户端是 `tools/translate_page_native.py`；它通过 `mtu_native` page engine 调用
完整 MTU controller，输出 final/clean/mask 和 MTU-native `page.json`，不启动 Flask/Vue。
重复 `--image` 时它使用有界批量协议：默认每 4 页一次 GPU 提取/完成，批次文本只调用
一次 Translator；每页 MTU Context 仍完全隔离。

`tools/translate_page.py` 是六阶段端口的无界面实验客户端。它通过
`src/core/page_pipeline.py` 固定执行 detect → OCR → 可选 color → translate → inpaint → render，
但每一步的实现仍完全由所选 profile 决定。成功后一次性输出 `clean.png`、`final.png` 和包含
BubbleState、阶段 backend/耗时及相对 artifact 名称的 `page.json`；失败时不会创建目标输出目录。
该 CLI 不导入 Flask/Vue，也不把完整流水线重新塞进某个模型 adapter。
