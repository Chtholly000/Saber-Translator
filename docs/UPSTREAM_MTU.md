# MTU 上游集成说明

状态：上游审计、staged Worker 和原生 controller wrapper 为 `CURRENT`；旧 staged 云镜像与
原生 controller 均以一张公开竖排样图完成过真实 GPU 调用，广泛品质验证仍为 `TARGET`。

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

MTU 的配置枚举和注册表是内部实现事实，不是 Saber 的持久项目 schema。`TextBlock` 在每个
native 半程中保持原对象；translation 接缝只允许把完整字段序列化为版本化 native document，
再由完成 Worker 重建，不能泄漏为跨进程 Python 对象或降级成 BubbleState。

### v3.0.4 架构审计结论

MTU 的 `detection/__init__.py`、`ocr/__init__.py`、`inpainting/__init__.py` 与
`translators/__init__.py` 都有“名称/枚举 → 实现类”的内部注册映射，并提供惰性 `prepare`、
`dispatch`、缓存和 `unload`。`rendering/__init__.py` 同样按 `Renderer` 配置选择渲染器。
这正是 wrapper 可以直接利用的**原生按阶段选择、惰性加载、worker 内缓存**模式。

但这些注册表是 MTU 代码内的固定枚举，不是可跨进程发现的插件协议；完整执行顺序、可变
`Context`、中间对象和错误处理仍集中在约五千行的 `manga_translator/manga_translator.py`。
其 Qt `desktop_qt_ui` 与 editor 模块属于 MTU 自己的客户端，不需要带入本项目。MTU controller
负责一页的原生计算语义；Saber/Oracle 仍负责外部任务、项目和持久化，浏览器仍只是可选客户端。

## CURRENT：默认接入方式（原生 controller wrapper）

完整自动翻译首选在 MTU 原有 translation 接缝两侧包装固定版本 controller：

```text
Agent page/batch request
  → Modal: pinned _translate_until_translation() once per page
  → stable IDs + complete TextBlock.to_dict() + raw mask
  → control-plane Translator adapter
  → Modal: rehydrate TextBlock + pinned _complete_translation_pipeline() once per page
  → final artifacts + TextBlock.to_dict() native document
```

`workers/mtu_native/runtime.py` 只配置 MTU `Config` 并调用原生 controller 的预翻译和完成方法。
它在接缝处完整序列化/重建 TextBlock，并在 MTU rendering 释放中间图前旁路复制 clean image 与
refined mask；不替换检测、OCR、合并、mask、修补或排字算法。
固定版本的 `TextBlock.to_dict()` 为工程文件将倾斜区域的 `lines` 绕其 `center` 反旋转，
同时保留 `angle`；这些坐标不能直接当作运行中的原生多边形。
完成 Worker 使用同一组 `angle`/`center` 将坐标转回后才构造 TextBlock。
`src/core/native_mtu_page_contract.py` 拒绝请求内凭据、固定 MTU revision，并要求译文 ID 与区域 ID
精确相等。DeepSeek 等翻译器在控制进程实现同一个 Translator 端口，密钥不进入 Modal。

不带入 MTU Web/Qt UI，也不让 MTU 保存 Saber/Oracle 的书架与项目。controller 的职责止于一页
计算；外部任务状态、重试、artifact 存储和项目 revision 仍由未来 Oracle 控制面负责。

图像模块替换通过 MTU 自己的 Config/registry 接缝完成。例如更换固定版本已支持的 OCR 只修改
`page.ocr.ocr`；其余原生阶段不变。完全新的 OCR 必须在 worker 内适配 MTU OCR 接口并保留
`Quadrilateral`/TextBlock 下游语义，不能在 OCR 后转换成 Saber boxes/strings 再拼回原生流程。
翻译模型不受 MTU Config 绑定，只替换控制端 Translator adapter。

2026-09-20 的 v2 单页契约实际验证在 Modal L4 上运行上述精确 runtime：公开 3065×4096 页面提取出四个
稳定 ID 区域，完整 TextBlock 字段跨过序列化边界后重建，并以已保存译文完成 mask、lama_mpe
inpaint 和原生 render。最终 PNG 与不跨进程的原生 translation-seam 基准逐像素相同
（12,554,240 个像素中差异为 0）。该验证没有调用 DeepSeek，也不代表其他模型或样图已经验收。
2026-09-23 的三页复杂漫画对照发现这个旧样本没有覆盖的倾斜区域接缝错误：
原版与旧包装在两张含倾斜文字的页面上 mask/final 不同，无倾斜区域的一页则逐像素相同。
同次 OCR 的诊断分支只保留原始 `TextBlock.lines`，两张受影响页面的 clean/mask/final
均恢复为逐像素相同。修复因此只针对上述坐标映射，不改 MTU 算法、译文或对外 v3 协议。
2026-09-21 的 v3 契约在不改变上述单页半程的前提下增加 `extract_pages` / `render_pages`：
一次 Worker 调用顺序处理 1～8 页，控制端只调用一次 Translator。除离线 fixture 外，同日已把
v3 Worker 部署到 Modal L4，并以两张公开 3066×4096、3065×4096 页面完成一次真实
`extract_pages` 和一次真实 `render_pages`：分别识别 5、4 个区域，全部无 runtime warning，
提取 98.195 秒、完成 45.261 秒。测试把 OCR 原文作为译文回填，因此没有调用 DeepSeek，也不把
这次结果当作肉眼可见的翻译成图或翻译语言质量证明。随后纠正测试：复用同一批真实 extraction，
把 9 段明确的简体中文通过一次真实 `render_pages` 写回；200.111 秒完成、0 warning，肉眼确认两页
所有已检测区域均显示中文。该次仍未调用 DeepSeek，因为控制环境没有 API Key；它证明中文译文
可以通过原生 MTU 排版写回，但不证明模型翻译质量。

## CURRENT（高级/部分处理）：Worker v2 接缝

`src/core/mtu_worker_contract.py`、`src/core/extraction_backends/mtu_modal.py` 和
`src/core/stage_backends/mtu_*.py` 定义 detect/OCR/color/inpaint 的受测接缝。
`workers/mtu/runtime.py` 只调用该 revision 的 `detection.dispatch`、`ocr.dispatch`、
`textline_merge.dispatch` 和 `inpainting.dispatch`；`workers/mtu/modal_app.py` 是固定 revision 与
CUDA 依赖组的部署配方。控制进程的 `modal_worker_client.py` 只在真正执行时才导入 Modal SDK，
`remote_bootstrap.py` 只在显式非秘密配置存在时注册 profile。

检测/OCR 现有独立 `ModalMtuDetectorBackend`、`ModalMtuOcrBackend`，旧组合类仅保留兼容。
`src/core/pipeline_plugins/factories.py` 将 MTU 各阶段暴露为可配置的独立工厂，示例
`pipeline_plugins/mtu.example.json` 用两个 profile 演示 staged 路径只切换 48px/mocr。它适合
只抽字、只修补、只嵌字或明确的混合实验；因为它在阶段间规范化并重建状态，不再作为完整页面
原生质量的默认路径。

Worker 请求/响应使用 `saber-mtu-worker/v2`；严禁把 API Key、签名 artifact URL、HTTP response、
Modal object、Pydantic Config 或 `TextBlock` 放进 payload。OCR/color 必须按 `region-N` ID 对齐并完整
返回；detect 的可选 mask 和 inpaint 返回图必须与输入同尺寸且为 base64 PNG。离线 fixture 覆盖横排、
竖排、旋转框、空页、mask 尺寸不符、顺序反转与凭据隔离；真实 Worker 接入仍须执行相同类型的 GPU
fixture，不能把离线结果当成模型质量证明。

2026-09-19 的真实 Modal L4 测试使用该固定 revision、默认 detector（检测尺寸 1536）和 48px OCR
处理上游公开的 3065×4096 `pic/before2.png` 样图，返回四个竖排区域、同尺寸文字蒙版和四个
ID 对齐的非空 OCR 结果。冷路径总耗时 80.612 秒。它证明这两个阶段与 Worker 契约在该样图上
兼容。2026-09-20 同页又实际执行 color 与 lama_mpe inpaint，分别耗时 17.105 秒和 43.040 秒，
返回四个对齐颜色结果与同尺寸修补图。修补图仍有明显日文字影；这些调用不替代横排、旋转、
空页、复杂背景或参数调优的真实 fixture。

## 禁止做法

- 把 `manga_translator/` 整目录复制进本仓库。
- 从 MTU `main` 动态安装而不固定 commit/tag。
- 让运行中的 MTU Python 对象、Pydantic Config 或磁盘工程文件泄漏到 Saber UI/持久层；版本化
  native document 是服务契约，不属于此禁令。
- 让 MTU 自己保存 Saber 书架或覆盖页面 revision。
- 把 `BubbleState` 或只有框/字符串的响应插入 MTU 原生 OCR 与 mask/inpaint/render 之间。
- 为了“模块化”重写 MTU 已有 controller、mask refinement、inpainting 或 renderer。
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
