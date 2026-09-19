# Saber-Translator 前端开发说明

状态：`CURRENT`。这是 Vue 3 + TypeScript + Vite 前端的源码入口；完整环境和后端启动见
[源码开发与启动](../docs/DEVELOPMENT_SETUP.md)。

## 技术栈与命令

在 `vue-frontend/` 目录执行：

```sh
npm ci
npm run dev
npm run typecheck
npm run test
npm run build:check
```

命令真相源是 [`package.json`](./package.json)：

| 命令 | 用途 |
| --- | --- |
| `npm run dev` | Vite 开发服务器，默认 `5173`；`/api` 代理到 Flask `5000` |
| `npm run typecheck` | TypeScript/Vue 类型检查 |
| `npm run test` | Vitest 一次性测试 |
| `npm run test:watch` | Vitest 监听模式 |
| `npm run build` | 构建到 `../src/app/static/vue/` |
| `npm run build:check` | 先执行项目类型构建检查，再生成生产包 |
| `npm run lint` / `npm run lint:css` | TypeScript/Vue 与样式检查 |

仓库没有 `test:unit` 脚本。文档和 CI 不得引用一个不存在的命令。

## 目录所有权

- `src/views/`：翻译、书架、阅读、Insight 等页面入口。
- `src/components/`：页面组件和通用组件。
- `src/stores/`：图片、气泡、会话、设置和书架状态。
- `src/composables/translation/core/`：步骤图、运行时、原子步骤、结果投影和保存编排。
- `src/composables/translation/parallel/`：并行池和并行调度。
- `src/composables/useTextStyleSync.ts`：图片与侧栏文字样式同步。
- `src/composables/useEditRender.ts`：编辑模式重渲染辅助。

## 翻译执行主链

```text
useTranslationPipeline
  -> usePipeline
  -> SequentialPipeline / ParallelPipeline
  -> atomic steps
  -> taskProjector / persistenceService
```

修改主链前至少核对：

- [`pipelineRegistry.ts`](./src/composables/translation/core/pipelineRegistry.ts)：模式对应的步骤链。
- [`runtime.ts`](./src/composables/translation/core/runtime.ts)：`TaskContext` 与运行期 profile 冻结。
- [`atomicSteps.ts`](./src/composables/translation/core/atomicSteps.ts)：API 结果怎样进入任务上下文。
- [`persistenceService.ts`](./src/composables/translation/core/persistenceService.ts)：保存编排。
- [`saveStep.ts`](./src/composables/translation/core/saveStep.ts)：单页保存步骤。

前端只选择服务器已经注册的 pipeline profile，不拥有模型实现、工厂路径或云凭据。新增 OCR
等模型不能在 Vue 组件里增加供应商条件分支；按
[阶段插件文档](../docs/STAGE_PLUGINS.md) 接入后端端口。

## 编辑与持久化规则

- 文字样式同步集中在 [`useTextStyleSync.ts`](./src/composables/useTextStyleSync.ts)，不要塞回
  `TranslateView.vue`。
- 编辑模式重渲染通过 [`useEditRender.ts`](./src/composables/useEditRender.ts)。
- 书架模式保存沿用 `saveStep.ts`、`persistenceService.ts` 和 `sessionStore.ts`，不要重新引入
  旧的整批保存 helper。
- `BubbleState`、人工字段保护、步骤响应和页面写回语义以
  [流水线契约](../docs/PIPELINE_CONTRACTS.md) 为准，不能仅凭组件局部类型猜测。

## 构建产物

Vite 的 `outDir` 是 `../src/app/static/vue/`，Flask 会直接提供其中的 `index.html`、`js/`
和 `assets/`。该目录已由 Git 跟踪，build 会清空并重建它；提交前检查是否真的需要提交新的
哈希产物。只做 HMR 开发时无需先 build。

## 开发文档入口

- [开发权威索引](../docs/README.md)
- [源码开发与启动](../docs/DEVELOPMENT_SETUP.md)
- [系统架构](../docs/ARCHITECTURE.md)
- [模块边界](../docs/MODULE_BOUNDARIES.md)
- [流水线契约](../docs/PIPELINE_CONTRACTS.md)
- [代码风格](./CODING_STYLE.md)

不存在的旧手册或个人电脑绝对路径不是权威。若新增一份当前文档，先在
`docs/README.md` 指定它负责的唯一问题域。
