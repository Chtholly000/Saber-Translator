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

当前 `src/core/extraction_backends/` 已为检测与 OCR 建立一个很小的执行后端边界：
`local` 仍是唯一内置实现，Flask 仍同步等待结果。它是迁移接缝，不代表 Modal 或 MTU
适配器已经实现。

插件系统只在步骤执行前后改写 payload/result。插件不能安全地承担模型生命周期、远程任务、
幂等重试或大型图片传输，因此插件与后端适配器必须保持不同概念。

## CURRENT：状态所有权

当前前端 `TaskContext` 聚合一页处理过程中的坐标、蒙版、OCR、颜色、译文、干净背景、
最终图和 `bubbleStates`。持久化时，`page_storage.py` 将页面元数据和图片产物写入会话目录。

目前存在以下风险，后续模块化必须正面处理：

- Python `BubbleState`、TypeScript `BubbleState`、`TaskContext` 和保存 payload 存在重复字段。
- 图片通过 base64 放进同步请求，适合本地但不适合长期远程任务和大批量页面。
- 部分步骤既负责调用模型，又负责把结果投影到 UI 状态。
- 人工编辑与模型结果缺少统一的字段级来源/锁定规则。

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

## TARGET：两层模块化

模块化分成两个互不混淆的维度：

1. 阶段端口：`Detector`、`OcrEngine`、`Translator`、`Inpainter`、`Renderer`。
2. 执行适配器：`local`、`modal`、`http_api`。

例如 `MTU OCR on Modal` 是“OCR 阶段端口 + Modal 执行适配器 + MTU 实现”的组合。
更换 OCR 模型只改变配置和适配器注册，不改变路由、书架、编辑器或页面格式。

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

- Modal Worker 与远程任务队列。
- MTU Python 适配器及其字段转换测试。
- DeepSeek 专用配置界面；现有 OpenAI-compatible 能力是否足够仍需验证。
- 版本化的跨语言项目 schema 和人工字段锁。
- Oracle 部署、备份和恢复方案。
