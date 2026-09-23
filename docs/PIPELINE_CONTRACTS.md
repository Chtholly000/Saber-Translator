# 流水线与数据契约

状态：原生 MTU 整页契约与编辑器气泡身份/人工锁为 `CURRENT`；跨设备工程文档、revision 和
provenance 为 `TARGET`。

## CURRENT：Agent 整页契约与原生文档

`saber-native-mtu-page/v3` 是自动完整翻译的主边界，保留单页操作并增加有界批量操作：

- `extract_page` 输入 PNG 和非秘密 detector/OCR/render language 配置，输出同尺寸
  `working_image`、`raw_mask` 和 `mtu-extraction/v1` 文档；
- `render_page` 输入上述产物、按稳定区域 ID 提供的译文和非秘密 inpainter/render 配置，
  输出 `clean_image`、`final_image`、`repair_mask` 和 `mtu-rendered/v1` 文档。
- `extract_pages` / `render_pages` 在一次 Worker 调用中顺序处理 1～8 页；页面以批次内唯一
  `page id` 对应，每页仍独立调用上述 MTU controller 半程，不能跨页混用 Context/TextBlock。

提取文档的每个 `regions[]` 记录都包含 `id`、`text` 和完整 `native`
`TextBlock.to_dict()`。译文 ID 必须与区域 ID 精确相等；缺失、重复或额外 ID 在成图前失败。
完成 Worker 把 native 字段重建为 MTU `TextBlock` 后调用原 controller 的 mask refinement、
inpainting 和 rendering，不经过 `BubbleState`。

`src/core/page_engines/` 在两次 Worker 调用之间执行注入的 Translator adapter。批量入口先以
默认每组 4 页执行有界 GPU 提取，再把全部页面的文本展平成一次 Translator 调用，最后按相同
上限分组完成 GPU 成图。DeepSeek API Key
只来自控制进程环境；Modal 请求、响应、配置文件和 artifact 均不携带密钥，GPU 也不等待 API。
所有 Worker 请求拒绝 key/token/secret 字段并校验固定 MTU revision。当前直接文件客户端
`tools/translate_page_native.py` 接受重复的 `--image` 参数。单页保持原输出结构；多页整批原子发布
`batch.json` 和各 `page-NNNN/` 子目录。每页包含：

- `clean.png`：MTU 原生 inpainting 后的页面；
- `final.png`：MTU 原生 rendering 后的页面；
- `mask.png`：MTU refined repair mask；
- `page.json`：artifact 相对名、revision metadata、warning 和完整 native document。

Saber 编辑器将来需要接收该页面时，应由单独的外层 adapter 将 native document 投影为编辑器
文档；当前原生 CLI 尚未接入这项可选投影。该投影可以有显式降级 warning，但不是原生流水线的
阶段输入，也不是完整处理的真相源。

2026-09-21 已以两张公开页面真实验证 v3 批量边界：一个 `extract_pages` 调用返回 5+4 个区域，
一个 `render_pages` 调用完成两页原生写回，均无 runtime warning；提取和完成分别耗时 98.195 秒、
45.261 秒。测试把 OCR 原文作为译文回填且未调用 DeepSeek，因此它证明批量传输、同一 GPU 容器
复用和图片写回，不是可见翻译成图，也不证明目标语言翻译质量。纠正后的第二次验证复用同一
extraction，以 9 段明确简体中文执行一次 `render_pages`；200.111 秒完成、0 warning，肉眼确认
两页全部检测区域显示中文。由于控制环境没有 API Key，该次也未调用 DeepSeek，只证明译文写回。
具体批量调优与提高硬上限的步骤由 `workers/mtu_native/README.md` 维护。

## CURRENT：可选 Saber 编辑器运行时对象

前端 `TaskContext` 是单页流水线的聚合状态，当前包含：

- 页面身份和执行状态；
- 检测坐标、角度、多边形、自动方向、文本行和文字 mask；
- OCR 原文与结构化 OCR 结果；
- 自动颜色；
- 译文、文本框文字、警告和术语统计；
- clean image、final image、`bubbleStates` 与保存状态。

Python `BubbleState` 和 TypeScript `BubbleState` 只表达可选编辑器中的可编辑气泡，核心字段包括：

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
的远程项目文档 schema。当前本地流水线仍在若干调用中使用同下标数组；现有 MTU Worker 已用
请求内 `region-N` ID 对齐 OCR/color，页面级 `bubbleId`、revision 与异步写回仍是下面的 TARGET，
不能假装已经实现。

当前五个核心原子 API（detect/OCR/translate/inpaint/render）和可选 color API 位于
`src/app/api/translation/parallel_routes.py`。请求和响应的 TypeScript 形状位于
`vue-frontend/src/api/parallelTranslate.ts`。

五个核心步骤和 color 请求都可携带 `pipeline_profile`；省略时固定为 `local_saber`。成功响应会
带回实际 `pipeline_profile` 与 `execution_backend`，作为轻量 provenance，不影响既有结果字段。
单阶段覆盖名分别是 `detector_backend`、`ocr_backend`、`color_backend`、`translator_backend`、
`inpainter_backend` 与 `renderer_backend`。过渡期内 detect/OCR 仍接受旧 `extraction_backend`；它与
阶段专用名同时出现且不一致时必须是请求错误，不能猜测或回退。`local_saber` 永远内置；仅当
`SABER_REMOTE_CONFIG` 装配成功时才会注册 `modal_mtu_deepseek`。该 profile 的存在表示代码和
非秘密配置可用，本身并不构成云健康检查；实际 Modal/DeepSeek 冒烟边界另行记录在
`workers/mtu/README.md`。

`SABER_PIPELINE_CONFIG`（schema_version 1）也可声明六阶段插件及新 profile，并继承现有方案
只覆盖某一步。配置在进程启动时验证，工厂在第一次执行时才导入；接口和输出类型以
`STAGE_PLUGINS.md` 为准。旧 extraction 注册通过兼容桥接入同一组独立阶段端口。
`GET /api/parallel/backends` 返回六阶段已注册名称，不暴露工厂/配置，也不是运行健康检查。

浏览器设置的 `automaticPipelineProfile` 在 `PipelineRuntime` 创建时被固定为 `pipelineProfile`；同一
自动运行中的 detect、OCR、color、translate、inpaint、render 只能使用这一值。保存页面时该值写入
`pipelineProfile` provenance。逐气泡翻译尚未迁移到阶段后端，因此非 `local_saber` profile 必须
在前端明确失败，不能无提示改走旧单气泡 API。

`automaticPipelineProfile` 随设置 schema v4 一同持久化；旧设置在加载时由默认值补齐并升级到 v4。

浏览器根据所选方案中 OCR/translate 的实际阶段名决定是否发送旧本地模型设置，不能以
profile 是否叫 local_saber 判断所有步骤的位置。自定义 OCR/翻译插件仅接收业务输入，
路由不会转发浏览器保存的供应商凭据/地址。自定义 render 自行实现自动字号，避免绑定本地排版算法。

### CURRENT：六阶段实验性无界面整页运行

`src/core/page_pipeline.py` 使用同一 profile 和六阶段 registry 在 Python 进程内执行页面，
不经过 Flask 或 Vue。它仍保持本文件的不变量：检测数组必须等长、OCR/翻译必须与区域一一对应、
mask/clean/final 必须保持原图尺寸，任何不对齐都会在 inpaint/render 前失败。

`tools/translate_page.py` 是其文件适配器。目标输出目录必须不存在；全部阶段成功后才原子发布：

- `clean.png`：去字后的同尺寸背景图；
- `final.png`：嵌入译文后的同尺寸成品图；
- `page.json`：`bubbleStateContractVersion: 1`、profile、各阶段 backend/耗时、相对 artifact 名称和
  `bubble_states`。

这个 staged `page.json` 是可继续交给 `tools/typeset.py` 或浏览器导入的本地运行结果，不等同于原生
MTU 整页文档，也不等同于尚未实施的
跨设备 project/page revision schema。核心编排器不写页面存储，也不会绕过人工锁去覆盖既有页面。

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

## staged 六阶段不变量

所有 staged 后端和流水线实现必须保持：

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

输出：按请求区域 ID 对应的文本、置信度、置信度是否受支持、实际引擎、fallback 信息。

### color

输入：原图 artifact、已有 regions 与文本行。

输出：与输入 region 顺序一一对应的前景/背景 RGB；没有文字时允许空颜色。该步骤不修改 OCR 文本。

### CURRENT（staged）：MTU Worker v2（detect / ocr / color / inpaint）

`src/core/mtu_worker_contract.py` 定义跨进程 JSON 契约 `saber-mtu-worker/v2`。detect 请求包含 PNG
图片和服务器拥有的非敏感检测选项；响应为稳定顺序的 regions、可选 PNG `text_mask`。OCR/color
请求把每个区域表示为请求生成的稳定 `region-N` ID、坐标和文本行；响应必须逐一回传相同 ID。
inpaint 请求包含原图、单通道 repair mask 和服务器拥有的 inpaint 选项。适配器将结果转换为 Saber
detection dict、`OcrResult`、颜色数组或 PNG，绝不返回 MTU `TextBlock` 或 Config。

Mask 与输入图片的宽高必须完全一致。缺失/重复/未知 OCR ID、错误 stage、错误契约版本、越界坐标、
错误图片格式或敏感调用方凭据都会导致契约错误；这些不是可静默 fallback 的情形。该契约已由离线
Worker dispatcher fixture 覆盖，并以一张公开 3065×4096 竖排样图完成真实 Modal detector +
48px OCR 调用，返回四个区域、同尺寸文字蒙版与四个 ID 对齐结果。随后同页通过相同契约实际调用
color 和 lama_mpe inpaint；取色返回四个 ID 对齐结果，修补返回同尺寸 PNG。该单页冒烟不是横排、
旋转、空页和复杂背景的品质证明，且修补图仍有明显残字。

### translate

输入：带 ID 的原文、源/目标语言、术语与不翻译规则、provider 配置引用。

输出：按 ID 对应的译文、警告和 provider/model provenance。适配器不得返回或记录 API Key。

2026-09-20 的独立实际调用将上述 Modal 冒烟产生的四条日文 OCR 文本交给
`deepseek-flash`，2.029 秒内得到四条非空简体中文结果，ID 与输入保持一一对应。调用使用显式
关闭 thinking 的 JSON 模式，密钥只从进程环境读取。该结果不覆盖批量页面、自动重试、限流、
浏览器写回或整条 Modal + DeepSeek 链路。

### inpaint

输入：原图 artifact、regions、用户 mask/模型 mask、修复配置。

输出：clean image artifact 与可选实际使用的 mask。不得改变气泡文字或样式。

### render

输入：clean/original image artifact、完整气泡状态、字体资源引用和渲染配置。

输出：rendered artifact 与规范化气泡状态。手动嵌字路径允许没有 detect/OCR/translate 结果。

2026-09-20 的无界面整页验证在上述公开样图上实际执行 Modal detect、48px OCR、color、
lama_mpe inpaint 与 Saber 本地 render。为避免再次索取已不在进程中的专用密钥，translate 阶段
回放同日独立真实 DeepSeek 调用的四条结果；因此这次运行不能描述成新的端到端 DeepSeek 请求。
输出的 `clean.png` 相对原图变化 708,420 个像素，`final.png` 相对 clean 图变化 274,778 个像素，
证明真实图片擦除和嵌字写回已经发生。肉眼检查同时发现明显残字与一处译文越出气泡，故该结果只
证明六阶段组合、文件发布和像素写回，不是质量验收。

### CURRENT：原生 MTU 对照结论

同一公开页面随后通过固定 revision 的 MTU controller 原生顺序执行 detection、OCR、textline
merge、mask refinement、inpainting 和 rendering，并只在 MTU 自己的 translation 接缝回放同一组
既有译文。原生结果的擦除和气泡排版明显优于上面的 staged 组合，并正确保留了 staged 路径错误
合并进对白的紫色拟声词。该 A/B 证明问题来自中间契约丢失与重新编排，而不是 MTU 原算法。

因此完整自动翻译的默认边界现为 `saber-native-mtu-page/v3`：只在上述已验证的 translation
接缝拆成提取/完成两个 native 调用。staged Worker v2 仍用于只抽字、只修补、只嵌字和明确的
混合实验，但不能作为“原生 MTU 效果”的替代证明。

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
