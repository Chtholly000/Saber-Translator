# 开发经过与设计选择

状态：`HISTORICAL`。这里记录为什么这样改；当前行为以 ARCHITECTURE、MODULE_BOUNDARIES、
PIPELINE_CONTRACTS、STAGE_PLUGINS 为准。

## 2026-09-19：源码启动文档收口

为避免新 Agent 继续依据旧的个人绝对路径、已删除手册和不存在的前端命令工作，新增
`DEVELOPMENT_SETUP.md` 作为从零开发与启动的唯一当前权威，重写 Vue README，并加入
`tools/validate_docs.py` 校验文档索引、相对链接、状态标记和个人路径。文档明确区分 Flask
无界面开发入口与原有桌面入口的副作用，也把离线契约测试、前端构建、真实 GPU/云验证拆开，
防止把 mock 或 profile 注册写成“已经部署”。

同日验证基线：文档门禁、Vue 类型检查和 43 个阶段/Worker Python 契约测试通过；完整
`npm run test` 退出非零，结果为 127 个测试文件通过、22 个失败（646 个测试通过、43 个失败，
另有 90 个未处理异步错误，输出中反复出现 Insight 笔记保存失败）。本次只修改文档和文档校验器，
没有改 Vue 运行源码；该红色基线必须单独复现、归因和修复，不能在后续提交中写成全套通过。

## 用户的产品目标

个人使用，默认自动处理漫画；同时能只抽字，或给 AI 生成的空白图自动嵌文字。
精细编辑能力要保留，但不要求使用者逐句修改才可完成任务。算法、模型和执行位置应能独立替换。
应用开发在隔离 fork 和临时工作区进行，Oracle 运维仓库保持独立。Oracle 未来作为控制/存储中转，
GPU 计算交给 Modal，文本翻译可用 DeepSeek 等 API。

## 已完成的演进

1. 建立开发文档和 Agent 规则，选择 Saber 的浏览器编辑器/项目状态作为产品外壳，
   MTU 仅提供固定版本计算模块，不合并其 Qt 界面或完整控制器。
2. 自动流水线 profile（`2c14dbd`）：让自动任务整体选择阶段后端，并保留 local_saber。
3. MTU Worker 契约（`21d084d`）：建立 Saber 与 MTU 之间的版本化输入输出边界。
4. 远程组合（`98d99ea`）：加入 MTU Worker 运行代码、Modal 传输、DeepSeek adapter、
   取色/修补以及独立抽字/嵌字 CLI；仅做离线验证，没有部署云服务。
5. 2026-09-19，独立阶段插件：用户要求新增 OCR 等实现时无需改主流水线。
   检测/OCR 从组合边界迁入与其他四阶段同样的独立注册表；加入显式配置的插件工厂、
   惰性实例生命周期、按阶段结果检查、profile 继承、模板与配置检查工具。
   同时修正浏览器按整个 profile 判断本地/远端的逻辑，使“只换 OCR”保留其他阶段设置。
   对应提交可用 Git 日志中的 `feat: make pipeline stages configurable plugins` 定位。
6. 2026-09-19，Modal 真实冒烟：构建并部署固定 MTU v3.0.4 revision 的 L4 Worker；通过逐次
   真实调用发现并补齐 `libEGL`、`libxkbcommon`、`libdbus` 运行库，并把系统库层移到大型
   CUDA/Python 层之后。上游公开竖排样图返回四个检测区、文字蒙版及四个非空 48px OCR
   结果，冷路径总计 80.612 秒。测试后本月 Modal 汇总为 USD 0.18 metered、USD 0 billed
   （额度抵扣）；46 个 Worker/插件/profile/CLI 相关测试在干净进程通过。额外的全后端
   discover 共运行 266 项，因本机 PyTorch 动态库损坏、缺 MangaOCR/ONNX Runtime 及套件间
   共享状态而有 5 个失败、16 个错误，不能记录为全套通过。DeepSeek、取色、修复、浏览器
   整链和 Oracle 未在本次验证。
7. 2026-09-20，DeepSeek 独立翻译实测：按当前官方 API 将已退役的 `deepseek-chat` 和 `/v1`
   示例更新为 `deepseek-flash` 与根 API 地址，并为严格 JSON 翻译显式关闭默认 thinking。
   使用上一项 Modal 冒烟得到的四条日文 OCR 文本真实调用，2.029 秒内返回四条 ID 对齐的
   非空简体中文译文。专用密钥仅经标准输入传给临时进程环境，未进入仓库、配置、浏览器或
   归档，调用后剪贴板已清空。46 个阶段/DeepSeek/远程流水线聚焦测试通过；本项仍不代表
   浏览器整链、取色/修复或 Oracle 部署已验证。
8. 2026-09-20，无界面整页编排：在已有只抽字与只嵌字 CLI 之间补上
   `src/core/page_pipeline.py` 和 `tools/translate_page.py`。完整流程直接解析 profile 并调用六阶段
   registry，输出 clean/final PNG 与 BubbleState JSON；Vue 仅保留为可选客户端，不再是执行完整
   流水线的必要条件。
9. 2026-09-20，无界面真实出图：以公开 3065×4096 样图直接运行上述 CLI，实际调用 Modal
   detect（14.699 秒）、48px OCR（24.549 秒）、color（17.105 秒）、lama_mpe inpaint
   （43.040 秒）和 Saber 本地 render（0.056 秒）。翻译阶段回放同日独立真实 DeepSeek 调用的四条
   结果，并未再次请求 API。原图到 clean 图变化 708,420 个像素，clean 到 final 图变化 274,778
   个像素，证明擦字与嵌字实际写回图片；肉眼检查仍有明显残字和一处译文越出气泡，因此记录为
   接口/产物验证而非质量验收。该归档运行使用原型默认的 5px mask 膨胀与 0% 框扩展；检查后已将
   CLI 默认值对齐浏览器的 10px/20%，但尚未把调参后的结果写成已验证质量。
10. 2026-09-20，原生 MTU A/B 与边界纠正：同一公开样图改为保留 MTU `Context`/`TextBlock`，
    按原 controller 顺序执行 detection、OCR、merge、mask refinement、inpainting 和 rendering，
    只在原 translation 接缝回放同一组既有译文。原生结果明显改善擦除和气泡排版，并保留了
    staged 路径误并入对白的紫色拟声词。这证明之前的质量下降来自把原流程拆成 Saber 六阶段、
    过早降级成 BubbleState 后丢失语义，而不是 MTU 原算法。随后新增 `mtu_native` PageEngine、
    原生 controller Worker 和 Agent CLI：完整页面默认包装原控制器，六阶段路径降为高级/部分处理
    用途，编辑器降为可选消费端。
11. 2026-09-20，translation 接缝正式拆分：原生包装由“一次 Worker 调到底”改为
    `extract_page → control-plane Translator → render_page`。提取响应保留完整
    `TextBlock.to_dict()`、raw mask 和稳定区域 ID；完成 Worker 按 ID 写回译文并调用原
    controller 的 mask/inpaint/render。DeepSeek 凭据因此退出 Modal，GPU 不再等待语言模型 API。
    同一公开样图再次实际运行精确 v2 runtime，得到 4 个区域和完整成图；与同进程原生基准的
    12,554,240 个像素逐像素相同。该次使用已保存译文，未调用 DeepSeek。
12. 2026-09-21，原生多页批量：`saber-native-mtu-page/v3` 保留单页操作，并增加最多 8 页的
    `extract_pages` / `render_pages`。控制端默认每 4 页一次 GPU 调用，把全部已提取区域交给同一
    Translator 请求，再按批成图；每页仍分别调用 MTU 原 controller 半程。重复 `--image` 的 CLI
    原子发布批次目录。随后把 v3 部署到 Modal L4，以两张公开页面执行一次批量提取和一次批量
    成图；识别 5+4 个区域且无 runtime warning，耗时分别为 98.195 秒和 45.261 秒。该验证用 OCR
    原文回填，没有调用 DeepSeek，只证明批量契约、同容器模型复用和 MTU 原生写回确实可运行，
    不能作为可见翻译结果。随后以 9 段明确简体中文纠正验证：复用同一 extraction，只调用一次
    `render_pages`，200.111 秒完成且 0 warning；肉眼确认两页检测区域均已写成中文。该次仍未调用
    翻译 API，因此只验证中文嵌字，不评价模型译文质量。

## SUPERSEDED：早期“窄阶段优先”选择

上面第 1、8、9 项描述的“完整页面也应拆成 Saber 六阶段、不要使用 MTU controller”已经被
第 10 项的真实 A/B 证据取代。它们保留为失败路径的历史证据，不是当前实现指令。

- Superseded by：`ARCHITECTURE.md` 的“主路径是 Agent 调用的原生 MTU 后端”。
- Reason：阶段边界只保留框、字符串和简化气泡状态，丢失 MTU mask refinement、区域语义和
  原生 renderer 所需上下文，实际成图显著退化。
- Current authority：`ARCHITECTURE.md`、`MODULE_BOUNDARIES.md`、`UPSTREAM_MTU.md` 和
  `workers/mtu_native/README.md`。

## 保留的决定与待办

完整页面采用 MTU 原生 controller wrapper，并直接利用其按阶段注册/惰性加载。只在原生
translation 接缝将完整 TextBlock 数据版本化后交给控制端 Translator，再重建为 MTU 对象完成渲染；
不能在中间转换成 BubbleState。
模型插件和 before/after 中间件插件分别负责执行与加工；前端属于客户端，不能承担模型所有权。
插件模块由运营者显式选择；配置或代码变更通过重启生效，避免任务中途更换实现。

模型权重许可核查、持久缓存、取色/修复参数调优与更广 GPU 品质样本、DeepSeek 浏览器整链、异步队列、
跨设备页面版本保护、轻量 Oracle 运行包和部署恢复仍待完成。一次 Modal 冒烟不能改写成
生产上线记录。
