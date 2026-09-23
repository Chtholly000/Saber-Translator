# 开发文档索引

状态：`CURRENT`

本目录是该 fork 的开发权威入口。根目录 `README.md` 面向使用者；这里记录
代码当前怎样工作、计划怎样拆分，以及未来 Agent 修改代码时必须保持的契约。

## 状态标记

- `CURRENT`：已经存在并经源码核对的行为。
- `TARGET`：已经选定的目标架构，但可能尚未实现。
- `PROPOSED`：候选方案，实施前仍可调整。
- `HISTORICAL`：历史证据，不得当作当前指令。
- `SUPERSEDED`：已被另一份文档取代，必须附上新权威链接。

同一事实只能有一份 `CURRENT` 权威。文档和源码冲突时，先验证运行行为，再修正文档；
不要为了让文档“看起来正确”而凭猜测改代码。

## 当前权威

| 文档 | 负责回答 |
| --- | --- |
| [DEVELOPMENT_SETUP.md](./DEVELOPMENT_SETUP.md) | 从零准备源码环境、启动前后端、配置插件以及各验证层实际证明什么 |
| [BLANK_BUBBLE_PAGE.md](./BLANK_BUBBLE_PAGE.md) | 不跑 OCR/翻译，把指定文字写进空白漫画气泡；轻量安装、实测边界与更换检测器 |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | 系统现在怎样运行，未来浏览器、Oracle、Modal、模型 API 怎样分工 |
| [MODULE_BOUNDARIES.md](./MODULE_BOUNDARIES.md) | 每个模块拥有什么、允许依赖什么、禁止依赖什么 |
| [PIPELINE_CONTRACTS.md](./PIPELINE_CONTRACTS.md) | 页面、气泡、原子步骤、重试和人工编辑保护规则 |
| [UPSTREAM_MTU.md](./UPSTREAM_MTU.md) | MTU 固定版本、可复用能力、适配边界和升级检查 |
| [STAGE_PLUGINS.md](./STAGE_PLUGINS.md) | 六阶段独立插件、配置安装/替换、模板、输入输出、生命周期与验证 |
| [DEVELOPMENT_HISTORY.md](./DEVELOPMENT_HISTORY.md) | 历史：用户目标、实施经过与设计选择，不是当前运行指令 |
| [../workers/mtu_native/README.md](../workers/mtu_native/README.md) | Agent 默认整页入口、MTU 提取/完成包装、控制端 Translator 与 Modal 部署边界 |
| [../workers/mtu/README.md](../workers/mtu/README.md) | Worker 实现、远程配置、部署验证边界、只抽字/只嵌字客户端 |
| [../AGENTS.md](../AGENTS.md) | 编码 Agent 的阅读顺序、改动纪律和验证要求 |
| [../plugins/README.md](../plugins/README.md) | 原有 before/after 中间件插件用法；模型执行插件见 STAGE_PLUGINS |
| [../vue-frontend/README.md](../vue-frontend/README.md) | Vue 工程入口和现有前端目录说明 |

## 文档缺口基线

建立本目录前，Saber 根 README 指向多份并不存在的 `docs/*` 开发手册；代码中的
前端原子流水线、Python 原子 API、`BubbleState`、页面存储和插件系统没有一份共同的
架构权威。MTU v3.0.4 有大量用户、开发和历史文档，但没有供本项目使用的稳定集成契约，
其模型注册表与中间对象仍需要从源码核对。

因此本 fork 的文档策略是：不复制 MTU 的整套说明，只维护我们实际依赖的版本、字段映射
和升级验证项。

## 修改文档时

1. 先确认是在描述当前行为还是目标设计。
2. 引用真实源码路径和公开字段，不引用个人电脑绝对路径。
3. 不记录密钥、Token、私有 URL、用户图片或生产配置值。
4. 接口发生不兼容变化时，先增加版本和迁移策略，再修改调用方。
5. 完成实现后，将对应章节从 `TARGET` 更新为 `CURRENT`，但只更新已经验证的部分。
6. 运行 `python tools/validate_docs.py`；错误会阻止提交，不能用手工浏览代替。
