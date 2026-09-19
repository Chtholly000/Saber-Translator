# 系统架构

状态：`CURRENT + TARGET`。每一节单独标注，未标为 `CURRENT` 的能力不能视为已经上线。

## CURRENT：当前代码怎样运行

Saber 当前是一个本地 Flask 应用配合 Vue 单页前端：

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

当前 `src/core/pipeline_profiles.py` 已建立自动流水线的组合点。默认内置的完整 profile 是
`local_saber`，其 detect / OCR / translate / inpaint / render 都选 `local`。
显式提供 `SABER_REMOTE_CONFIG` 后还会注册 `modal_mtu_deepseek`：检测/OCR/取色/修复使用
MTU Worker，翻译使用 DeepSeek 官方 API，渲染使用 Saber CPU。配置可用不等于云端已实测。
五个主 API 以及可选 color API 都会通过 profile 解析后端；detect/OCR 使用 `extraction_backends/` 接缝，
color/translate/inpaint/render 使用各自的 `stage_backends/` registry。detect/OCR 保留旧的
`extraction_backend` 参数作为过渡。Flask 仍同步等待结果；这不代表 Modal、MTU 或远程任务已经
部署验证。具体能力与验证边界见 `workers/mtu/README.md`。

Vue 是当前浏览器客户端，不是自动流水线的所有者。它可以被另一客户端（例如批处理客户端）
替换，只要后者遵守任务/API 和持久化契约；MTU 的 Qt 界面也不能直接当作 Saber 客户端嵌入。

自动任务在 `createPipelineRuntime` 启动时从 `automaticPipelineProfile` 取得并冻结 profile；五个主
步骤和取色将同一 `pipeline_profile` 发给 API，页面元数据记录 `pipelineProfile`。默认仍为
`local_saber`，浏览器设置可以选择服务器显式配置的 profile。旧的逐气泡翻译、高质量翻译和
校对尚未迁移，遇到非本地 profile 会明确拒绝。

MTU Worker v2 契约覆盖检测/OCR/取色/修复。`workers/mtu/runtime.py` 已实现对固定 MTU 窄模块的
调用和字段转换，`modal_worker_client.py` 提供惰性的认证 SDK client；独立部署定义已通过 SDK
导入验证，尚未构建云镜像或执行真实 GPU 推理。原子路由的本地模型导入已延迟，但完整 app.py
仍包含旧的重型依赖，不能宣称 Oracle 轻量部署包已经完成。

插件系统只在步骤执行前后改写 payload/result。插件不能安全地承担模型生命周期、远程任务、
幂等重试或大型图片传输，因此插件与后端适配器必须保持不同概念。

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
浏览器
  ├─ 书架、章节和项目
  ├─ 气泡/文字/样式精细编辑
  └─ 快速预览
          │
          ▼
Oracle 控制面
  ├─ 身份、项目状态和任务状态
  ├─ 图片与工程文件存储
  ├─ 调度与失败重试
  ├─ 调用翻译 API
  └─ 导出 PNG / ZIP / PDF / CBZ
          │
          ├──────────────► OpenAI-compatible API（例如 DeepSeek）
          │                         翻译
          ▼
Modal GPU Worker
  ├─ detection
  ├─ OCR
  ├─ inpainting
  └─ 可选的高质量最终 rendering
          │
          ▼
固定版本的 MTU 引擎或其他模型实现
```

职责划分：

- 浏览器拥有交互和即时预览，不拥有最终持久状态。
- Oracle 拥有项目、任务和产物引用，但不安装 CUDA/PyTorch GPU 栈。
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

## TARGET：三层可替换性

模块化分成三个互不混淆的维度：

1. 阶段端口：`Detector`、`OcrEngine`、可选 `ColorExtractor`、`Translator`、`Inpainter`、`Renderer`。
2. 执行适配器：`local`、`modal`、`http_api`。
3. 展示/控制客户端：Vue 浏览器、批处理 CLI、或其他遵守 API 的客户端。

例如 `MTU OCR on Modal` 是“OCR 阶段端口 + Modal 执行适配器 + MTU 实现”的组合。
更换 OCR 模型只改变配置和适配器注册，不改变路由、书架、编辑器或页面格式。

完整 profile 把五个核心阶段和可选 color 的已注册适配器组合成一次**自动运行**。它不是视觉工作流编辑器，
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

- Modal 镜像实际构建、真实权重/GPU 品质验证、持久模型缓存。
- 异步远程任务队列、超时/取消传播、幂等与页面 revision 写回。
- 完整 Saber 控制面的 GPU 依赖剥离与 Oracle 轻量运行包。
- DeepSeek 专用配置界面；现有 OpenAI-compatible 能力是否足够仍需验证。
- 版本化的跨语言项目 schema、字段 provenance、页面 revision 和人工锁管理 UI。
- Oracle 部署、备份和恢复方案。

## CURRENT：独立抽字与嵌字客户端

`tools/extract_text.py` 只调用 detect/OCR 端口并导出气泡 JSON；`tools/typeset.py` 直接消费
图片与 BubbleState JSON，只调用 render 端口。后者已用真实 Saber CPU 渲染器验证空白图出字，
不依赖前面四步。AI 可以生成文字/坐标 JSON，浏览器编辑器不是调用这些能力的必需条件。
