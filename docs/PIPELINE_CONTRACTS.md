# 流水线与数据契约

状态：气泡身份与人工锁为 `CURRENT (v1)`；跨设备工程文档、revision 和
provenance 为 `TARGET`。

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

### CURRENT (v1)：气泡身份与人工锁

每个经前端工厂创建或会话加载的气泡都具有不透明的 `bubbleId`。旧会话可能没有该字段；
`bubbleFactory` 会在加载时补发 ID，并在下次保存时将其写回。Python `BubbleState` 和
render API 会无损往返 `bubbleId`，不会在后端猜测或重写 ID。

`manualFields` 是去重后的下列字段组：

- `geometry`：矩形、多边形、旋转和位置偏移；
- `originalText`、`translatedText`、`textboxText`；
- `style`：字体、字号、方向、颜色、描边、行距、对齐和修复方式。

编辑器通过 `bubbleStore` 的直接用户更新自动添加对应锁。自动 OCR、翻译、强制检测和渲染
响应都要经过同一合并规则：锁定组保留本地值，未锁定组可以由生成结果更新。强制重新检测以
IoU 匹配既有气泡；检测不到的人工锁定气泡仍保留，用户必须在编辑器中显式删除它。

“重新 OCR”与“重新翻译单个气泡”是用户明确要求替换的操作，结果会直接写入该字段而不会
新增人工锁；它们不会绕过已经存在的流水线合并规则。当前没有单独的锁管理界面，后续 UI
必须提供查看、解锁和“用本次模型结果覆盖”的明确操作，不能静默清除锁。

页面元数据保存 `bubbleStateContractVersion: 1`，仅标识上述兼容契约，不等同于下面尚未实施
的远程项目文档 schema。当前本地流水线仍在若干调用中使用同下标数组；远程适配器不得沿用
这一做法，必须按 `bubbleId` 回传。

当前六个主要原子 API 位于 `src/app/api/translation/parallel_routes.py`。请求和响应的
TypeScript 形状位于 `vue-frontend/src/api/parallelTranslate.ts`。

五个主步骤请求现在都可携带 `pipeline_profile`；省略时固定为 `local_saber`。成功响应会带回
实际 `pipeline_profile` 与 `execution_backend`，作为轻量 provenance，不影响既有结果字段。
单阶段覆盖名分别是 `detector_backend`、`ocr_backend`、`translator_backend`、`inpainter_backend`
与 `renderer_backend`。过渡期内 detect/OCR 仍接受旧 `extraction_backend`；它与阶段专用名同时
出现且不一致时必须是请求错误，不能猜测或回退。当前只有 `local_saber` 注册，尚不能声明
`modal_mtu` 或 `deepseek` 已可运行。

浏览器设置的 `automaticPipelineProfile` 在 `PipelineRuntime` 创建时被固定为 `pipelineProfile`；同一
自动运行中的 detect、OCR、translate、inpaint、render 只能使用这一值。保存页面时该值写入
`pipelineProfile` provenance。逐气泡翻译尚未迁移到阶段后端，因此非 `local_saber` profile 必须
在前端明确失败，不能无提示改走旧单气泡 API。

`automaticPipelineProfile` 随设置 schema v4 一同持久化；旧设置在加载时由默认值补齐并升级到 v4。

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

每个气泡已经有稳定的 `bubbleId` 和 `manualFields`；未来完整项目文档仍需记录：

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

`CURRENT (v1)` 写回规则：

| 字段 | 默认重新运行行为 |
| --- | --- |
| 自动检测几何 | 可更新未人工调整的气泡；人工气泡/人工几何默认保留 |
| OCR 原文 | 可更新未锁定原文；人工修正原文默认保留 |
| 译文 | 重新翻译只更新未锁定译文，除非用户明确选择覆盖 |
| 字体和样式 | 模型步骤不得覆盖人工样式 |
| clean/final artifact | 可生成新版本，但旧版本在任务提交时不能被提前删除 |

字段级 provenance、页面 revision 比较和可见的锁管理 UI 仍未实现。任何远程写回或新的
模型适配器都必须先接入现有合并函数，再补齐这些更强的并发保护；不得绕开 `manualFields`。

## 阶段契约

### detect

输入：原图 artifact、检测配置、原图尺寸。

输出：稳定顺序的 region 列表、坐标、多边形、角度、方向、文本行、可选 text mask，及
backend/model provenance。

### ocr

输入：原图 artifact、带 ID 的 regions、OCR 配置。

输出：按 `bubble_id` 对应的文本、置信度、置信度是否受支持、实际引擎、fallback 信息。

### CURRENT：MTU Worker v1（detect / ocr）

`src/core/mtu_worker_contract.py` 定义跨进程 JSON 契约 `saber-mtu-worker/v1`。detect 请求包含 PNG
图片和非敏感检测选项；响应为稳定顺序的 regions、可选 PNG `text_mask`。OCR 请求把每个区域表示
为请求生成的稳定 `region-N` ID、坐标和文本行；响应必须逐一回传相同 ID。适配器将结果转换为
Saber detection dict 和 `OcrResult`，不返回 MTU `TextBlock`。

Mask 与输入图片的宽高必须完全一致。缺失/重复/未知 OCR ID、错误 stage、错误契约版本、越界坐标
或敏感调用方凭据都会导致契约错误；这些不是可静默 fallback 的情形。

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

profile 是任务输入的一部分；远程模式保存其名称和每阶段实际 adapter/model provenance。
客户端（Vue、CLI 或其他界面）不是 profile 字段，不能因为换了界面而改变计算结果。

## 错误分类

- `invalid_input`：坐标、图片或配置不可用，不重试。
- `configuration_error`：缺少模型/API 配置，不重试并提示用户。
- `transient_remote_error`：超时、限流或临时服务错误，可退避重试。
- `resource_exhausted`：显存/内存不足，可换 profile、降分辨率或人工重试。
- `cancelled`：用户取消；不得继续写回。
- `internal_error`：未知错误，保留关联 ID 和脱敏日志。

HTTP 状态只负责传输层；任务状态和错误分类必须出现在版本化结果中。
