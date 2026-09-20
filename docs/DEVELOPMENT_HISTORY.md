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

## 保留的决定与待办

采用 MTU 的按阶段注册/惰性加载思路，但模型内部对象不成为 Saber 项目文件格式。
模型插件和 before/after 中间件插件分别负责执行与加工；前端属于客户端，不能承担模型所有权。
插件模块由运营者显式选择；配置或代码变更通过重启生效，避免任务中途更换实现。

模型权重许可核查、持久缓存、取色/修复参数调优与更广 GPU 品质样本、DeepSeek 浏览器整链、异步队列、
跨设备页面版本保护、轻量 Oracle 运行包和部署恢复仍待完成。一次 Modal 冒烟不能改写成
生产上线记录。
