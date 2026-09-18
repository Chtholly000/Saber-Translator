# 流水线与数据契约

状态：现有字段说明为 `CURRENT`；版本化、来源和人工锁规则为 `TARGET`。

## CURRENT：现有运行时对象

前端 `TaskContext` 是单页流水线的聚合状态，当前包含：

- 页面身份和执行状态；
- 检测坐标、角度、多边形、自动方向、文本行和文字 mask；
- OCR 原文与结构化 OCR 结果；
- 自动颜色；
- 译文、文本框文字、警告和术语统计；
- clean image、final image、`bubbleStates` 与保存状态。

Python `BubbleState` 和 TypeScript `BubbleState` 表达可编辑气泡，核心字段包括：

- `coords`、`polygon`、`rotationAngle`、位置偏移；
- `originalText`、`translatedText`、`textboxText`；
- 字体、字号、文字方向、颜色、填充、描边、行距和对齐；
- inpaint 方法、自动颜色、文本行与 OCR 元数据。

当前六个主要原子 API 位于 `src/app/api/translation/parallel_routes.py`。请求和响应的
TypeScript 形状位于 `vue-frontend/src/api/parallelTranslate.ts`。

## TARGET：持久工程文档

运行时对象不应直接成为永远不变的磁盘格式。目标持久结构需要显式版本：

```json
{
  "schema_version": 1,
  "project_id": "...",
  "page_id": "...",
  "revision": 7,
  "artifacts": {
    "original": {"ref": "..."},
    "text_mask": {"ref": "..."},
    "clean": {"ref": "..."},
    "rendered": {"ref": "..."}
  },
  "bubbles": []
}
```

这里的 `ref` 是概念字段；当前本地保存仍可落到会话目录，远程模式再映射到受控 artifact。
不要在尚未迁移前宣称当前页面文件已经使用此 JSON。

每个气泡最终应有稳定 `bubble_id`，并记录：

- 几何与阅读顺序；
- 原文、译文和排版样式；
- 每个生成字段的 backend/model/version provenance；
- 哪些字段被人工修改或锁定；
- 创建和最近修改的页面 revision。

## 不变量

所有后端和流水线实现必须保持：

1. OCR 输出数量与输入气泡数量一致；无法识别时返回空结果和错误元数据，不静默缩短数组。
2. 翻译按稳定 ID 对应，不依赖远程服务返回顺序。
3. 坐标以原图像素空间表示；适配器内部缩放必须在返回前转换回来。
4. mask 尺寸必须与其声明的图像 artifact 一致。
5. `render` 不修改原文；对样式做规范化时必须把结果显式返回。
6. 没有气泡是合法结果，不等于任务失败。
7. 人工创建的气泡可以没有 OCR 结果。
8. 未运行的步骤不得伪造“成功的空结果”覆盖已有数据。

## 人工编辑保护

目标写回规则：

| 字段 | 默认重新运行行为 |
| --- | --- |
| 自动检测几何 | 可更新未人工调整的气泡；人工气泡/人工几何默认保留 |
| OCR 原文 | 可更新未锁定原文；人工修正原文默认保留 |
| 译文 | 重新翻译只更新未锁定译文，除非用户明确选择覆盖 |
| 字体和样式 | 模型步骤不得覆盖人工样式 |
| clean/final artifact | 可生成新版本，但旧版本在任务提交时不能被提前删除 |

在字段级来源/锁定尚未实现前，任何可能覆盖人工编辑的模块化改动都必须停下来，先补迁移和
用户确认路径。

## 阶段契约

### detect

输入：原图 artifact、检测配置、原图尺寸。

输出：稳定顺序的 region 列表、坐标、多边形、角度、方向、文本行、可选 text mask，及
backend/model provenance。

### ocr

输入：原图 artifact、带 ID 的 regions、OCR 配置。

输出：按 `bubble_id` 对应的文本、置信度、置信度是否受支持、实际引擎、fallback 信息。

### translate

输入：带 ID 的原文、源/目标语言、术语与不翻译规则、provider 配置引用。

输出：按 ID 对应的译文、警告和 provider/model provenance。适配器不得返回或记录 API Key。

### inpaint

输入：原图 artifact、regions、用户 mask/模型 mask、修复配置。

输出：clean image artifact 与可选实际使用的 mask。不得改变气泡文字或样式。

### render

输入：clean/original image artifact、完整气泡状态、字体资源引用和渲染配置。

输出：rendered artifact 与规范化气泡状态。手动嵌字路径允许没有 detect/OCR/translate 结果。

## 任务与重试

远程任务至少需要：`job_id`、`idempotency_key`、`project_id`、`page_id`、`page_revision`、
`stage`、输入 artifact 版本和 backend profile。

结果写回前比较 `page_revision`：如果用户在计算期间修改了页面，结果进入待合并状态，不能
无条件覆盖。相同幂等键的重试应返回同一结果或同一活动任务。

## 错误分类

- `invalid_input`：坐标、图片或配置不可用，不重试。
- `configuration_error`：缺少模型/API 配置，不重试并提示用户。
- `transient_remote_error`：超时、限流或临时服务错误，可退避重试。
- `resource_exhausted`：显存/内存不足，可换 profile、降分辨率或人工重试。
- `cancelled`：用户取消；不得继续写回。
- `internal_error`：未知错误，保留关联 ID 和脱敏日志。

HTTP 状态只负责传输层；任务状态和错误分类必须出现在版本化结果中。
