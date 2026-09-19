# 源码开发与启动

状态：`CURRENT`。本文只描述这个 fork 当前源码树的本地开发、离线验证和启动行为。
Modal 实际部署、真实 GPU 推理、Oracle 部署均不在本文的“已验证”范围内。

## 先知道你启动的是什么

本仓库同时包含三个不同层次，不能混在一起理解：

1. `vue-frontend/` 是浏览器编辑器和自动流水线客户端。
2. `app.py` 是 Flask 控制面、原子步骤 API、书架/会话存储和静态文件服务。
3. 检测、OCR、取色、翻译、修补、嵌字通过阶段端口选择本地或显式配置的插件。

源码检出后默认只有 `local_saber` 方案。没有设置 `SABER_REMOTE_CONFIG` 或
`SABER_PIPELINE_CONFIG` 时，不会注册远程方案，也不会因为导入插件系统而连接 Modal、
DeepSeek 或其他模型服务。

Git 不包含 `models/`。完整使用本地检测、OCR、修补前，需要按上游 Release 的说明准备模型
文件；文档检查、前端开发以及纯契约测试不应为了方便而下载模型。

## 环境基线

- Python 3.12：发布工作流当前使用的版本。
- Node.js `^20.19.0` 或 `>=22.12.0`：当前 Vite 锁文件声明的范围。
- npm：使用 `vue-frontend/package-lock.json` 执行可重复安装。
- Git，以及所选 Python 包需要的系统运行库。

macOS 或没有 NVIDIA/CUDA 13.0 的机器应使用 CPU 依赖或远程插件，不要安装 GPU requirements
后假设 CUDA 会自动可用。

## 1. 取得正确源码

不要把应用源码克隆进 Oracle 运维仓库。使用独立目录检出本 fork 的集成分支：

```sh
git clone --branch integration/mtu-backend https://github.com/Chtholly000/Saber-Translator.git
cd Saber-Translator
git status --short --branch
```

开始修改前先确认分支和工作树；已有未提交文件属于当前操作者，不能为了“干净”而直接覆盖。

## 2. Python 环境

在仓库根目录创建独立虚拟环境。CPU 开发环境是最稳妥的起点：

```sh
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-cpu.txt
```

Windows PowerShell 激活命令是：

```powershell
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-cpu.txt
```

GPU 环境必须遵守 `requirements-gpu.txt` 顶部的安装顺序：先安装非 PyTorch 依赖，再从
PyTorch CUDA 13.0 索引安装匹配的 `torch` 和 `torchvision`。先确认显卡驱动、平台和模型
许可；不要在 Oracle 控制面安装这一套依赖。

只有需要部署或直连 Modal Worker 的控制进程才额外安装：

```sh
python -m pip install -r requirements-remote.txt
```

这条命令只安装客户端 SDK，不会部署 Worker。`modal deploy` 会产生外部状态及潜在费用，
必须由运营者另外明确执行。

## 3. Vue 环境

```sh
cd vue-frontend
npm ci
npm run typecheck
npm run test
```

两种开发方式：

- `npm run dev`：启动 Vite 开发服务器，默认在 `5173`，并把 `/api` 代理到
  `http://127.0.0.1:5000`。
- `npm run build`：把生产前端写入 `src/app/static/vue/`，由 Flask 在 `5000` 端口提供。

生产构建目录在 Git 中受版本控制。执行 build 后必须检查完整 diff，不能把无关的哈希产物
混入文档或后端提交。需要同时检查类型与构建时使用 `npm run build:check`。

## 4. 启动 Flask

### Agent、CI 或无界面开发：建议入口

```sh
python -m flask --app app run --host 127.0.0.1 --port 5000
```

这个入口会导入真实 Flask 应用、加载显式配置、创建运行目录并执行数据迁移检查，但不会执行
`app.py` 的 `__main__` 区块。因此它不会自动打开浏览器，不会启动 Sakura 监控线程，也不会在
启动时预加载 MangaOCR。适合验证 API、前端代理和文档中的启动步骤；第一次真正调用本地模型时
仍可能加载权重。

导入应用会创建或更新运行数据/日志目录。不要对一份唯一的用户数据目录做破坏性开发测试。

启动后可在另一终端做最小探针：

```sh
curl --fail http://127.0.0.1:5000/api/parallel/profiles
```

未配置插件时，返回结果应包含 `local_saber`，不应凭空出现远程方案。

### 原有桌面式入口

```sh
python app.py
```

这个入口会自动打开浏览器、启动服务监控、尝试预加载 MangaOCR，并监听
`0.0.0.0:5000`。它更接近打包程序行为，但会把服务暴露给当前网络可达的主机；只应在受信任
网络使用。服务器、CI 和 Agent 验证不要把它当成默认入口。

### 前后端联调

终端一运行上面的 Flask 建议入口；终端二运行：

```sh
cd vue-frontend
npm run dev
```

浏览器访问 `http://127.0.0.1:5173`。若已执行 `npm run build`，也可以只启动 Flask 并访问
`http://127.0.0.1:5000`。

## 5. 配置一个阶段插件

先进行纯配置检查。它不会导入插件、加载模型或发出网络请求：

```sh
python -m tools.check_pipeline_config --plugins-config pipeline_plugins/provided-text.example.json
```

POSIX 系统可这样把配置用于下一次进程启动：

```sh
SABER_PIPELINE_CONFIG="$PWD/pipeline_plugins/provided-text.example.json" \
  python -m flask --app app run --host 127.0.0.1 --port 5000
```

PowerShell 等价写法：

```powershell
$env:SABER_PIPELINE_CONFIG = (Resolve-Path pipeline_plugins/provided-text.example.json).Path
python -m flask --app app run --host 127.0.0.1 --port 5000
```

更换 OCR 或其他阶段时，只改服务器信任的工厂配置与插件包；完整格式、六个端口和生命周期以
[STAGE_PLUGINS.md](./STAGE_PLUGINS.md) 为准。配置改变后重启进程，目前没有热重载。

旧的整套 MTU/DeepSeek 组合使用 `SABER_REMOTE_CONFIG`，可再由 `SABER_PIPELINE_CONFIG`
继承或覆盖单个阶段。配置文件只能记录非秘密选项和密钥环境变量名，不能提交真实密钥。

## 6. 从零验证顺序

以下顺序把“文档正确”“组合逻辑正确”“界面能构建”“本地/云模型真实可用”分开证明：

```sh
python tools/validate_docs.py
python -m unittest tests_backend.test_pipeline_plugins
python -m unittest tests_backend.test_pipeline_profiles tests_backend.test_stage_backend_registry
python -m unittest tests_backend.test_remote_pipeline tests_backend.test_mtu_worker_adapter
cd vue-frontend
npm run typecheck
npm run test
npm run build:check
```

- 文档校验只证明受维护 Markdown 的索引、相对链接和路径规则。
- Python fixture/contract 测试不会证明真实权重质量、Modal 镜像可构建或 DeepSeek 可达。
- 前端测试/构建不会证明后端模型已安装。
- 真实模型验证必须单独记录模型版本、输入样本、运行位置和结果；不能用 mock 测试冒充。

最后执行 `git diff --check` 并检查完整 diff。若依赖或硬件不足，应明确写“未运行”及原因，
不要把语法检查描述成行为测试。

## 7. 常见问题定位

- `src/app/static/vue/index.html` 不存在或界面是旧版：在 `vue-frontend/` 重新 build 并检查产物。
- profile 列表只有 `local_saber`：这是无显式配置时的正常行为。
- 配置检查通过但第一次调用失败：检查插件模块是否可导入、依赖是否安装、工厂签名和真实模型。
- 本地模型找不到：确认 `models/` 已按对应上游版本准备；不要把权重提交进 Git。
- 云 profile 能列出但执行失败：列表只证明配置已注册，不是服务健康检查。按
  [MTU Worker 文档](../workers/mtu/README.md) 核对部署与验证边界。
