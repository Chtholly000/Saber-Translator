# 模块边界与依赖规则

状态：当前路径为 `CURRENT`；目标端口和适配器规则为 `TARGET`。

## 所有权表

| 区域 | 当前入口 | 拥有的事实 | 可以依赖 | 禁止承担 |
| --- | --- | --- | --- | --- |
| Vue 编辑器与状态 | `vue-frontend/src/` | 用户交互、即时预览、当前页面编辑状态 | 版本化 API 类型、领域字段 | 模型加载、云凭据、服务器文件路径 |
| 流水线编排 | `vue-frontend/src/composables/translation/core/` | 步骤顺序、模式、页面上下文投影 | 原子步骤客户端、稳定领域类型 | 具体 OCR/GPU SDK |
| Flask 路由 | `src/app/api/` | HTTP 验证、错误映射、调用应用服务 | 端口/服务、序列化器 | 模型实现细节、长期任务状态 |
| 领域状态 | `src/core/config_models.py`、前端类型 | 气泡文字、几何、样式、OCR 元数据 | 纯数据类型 | Flask、Modal、MTU、数据库客户端 |
| 当前算法实现 | `src/core/detection.py`、`ocr.py`、`inpainting.py`、`rendering.py`、`translation.py` | Saber 现有本地行为 | 领域类型、模型接口 | UI/书架所有权 |
| 后端端口与注册 | `src/core/extraction_backends/` | 当前 detection/OCR 执行选择 | 纯 Python callable/协议 | Flask request、Pinia、磁盘会话 |
| 插件中间件 | `src/plugins/`、`plugins/` | 步骤前后 payload/result 扩展 | 公开插件上下文 | 模型生命周期、任务队列、核心状态替代 |
| 页面持久化 | `src/core/page_storage.py` | 会话路径、页面图片和元数据原子写入 | 版本化领域文档 | 模型推理和 UI 组件 |
| 书架 | `src/core/bookshelf_manager.py` 与相应 API/store | 书、章节、标签与章节会话关系 | 页面持久化接口 | GPU 调度细节 |
| MTU 适配器 | 尚未创建 | Saber 契约与固定 MTU 版本之间的转换 | MTU 公共/经验证入口 | 向 UI 泄漏 `TextBlock` 或 MTU 配置对象 |
| Modal 适配器 | 尚未创建 | 作业提交、状态、artifact 传输和错误转换 | 阶段端口、远程客户端 | 项目真相、书架真相 |

## 目标依赖方向

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

领域契约不能反向导入具体适配器。具体适配器可以导入供应商 SDK，但必须把返回值转换成
Saber 的稳定结果类型后再交给上层。

## 阶段端口

目标是为每一步提供窄接口，而不是一个万能 `process()`：

| 端口 | 最小职责 | 主要输出 |
| --- | --- | --- |
| `Detector` | 从页面找文字区域和文字蒙版 | 区域、角度、多边形、方向、文本行、mask |
| `OcrEngine` | 对给定区域识别原文 | 与区域一一对应的 OCR 结果 |
| `Translator` | 翻译一组有稳定 ID 的文本 | 与输入 ID 对应的译文和警告 |
| `Inpainter` | 用区域/mask 生成干净背景 | clean image、可选修复 mask |
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

## 插件与后端的区别

使用插件的场景：清洗 OCR 文本、追加提示词、过滤检测框、统一样式、审计某一步结果。

使用后端适配器的场景：更换检测/OCR/修复/渲染模型，把计算从本机迁往 Modal，或调用新的
模型 API。

插件可以包围适配器调用，但不应自己创建不可见的第二套任务系统。

## 改动落点

- 改步骤顺序：先改 `pipelineRegistry.ts` 及其测试，再核对顺序/并行两套执行器。
- 改气泡字段：同时核对 Python/TypeScript 模型、API 序列化、保存/加载、迁移和渲染。
- 新增模型：增加适配器和注册项，不在路由中增加供应商条件树。
- 新增执行位置：增加执行适配器和配置映射，不复制阶段业务逻辑。
- 改持久化：先定义 schema 版本与迁移，不用运行时对象直接覆盖旧文件。
