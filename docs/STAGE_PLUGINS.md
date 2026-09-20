# 处理阶段插件

状态：`CURRENT`。配置加载、六阶段替换和浏览器/CLI 接入已用离线测试验证；所附 MTU
Modal detector + 48px OCR 另以一张公开竖排样图通过真实 GPU 冒烟测试，该页的四条 OCR
文字也通过所附 DeepSeek 翻译插件完成独立实际调用。两项局部验证不自动证明其他插件、
其他 MTU 阶段或完整远程流水线可用。

## 设计与范围

检测、OCR、取色、翻译、修补、嵌字分别有自己的注册表和端口，全部通过
`src/core/stage_backends/` 选择实现。一个插件只实现一个阶段的 `execute`，
不需要实现其他阶段，更不需要修改 Flask 路由、Vue 编辑器或页面存储。
这沿用 MTU 的按阶段注册、惰性加载和实例复用方式。

配置中一项插件由 `stage + name + factory + options` 组成。`factory` 指向一个
Python 模块中的工厂函数或类。你可以将模块放在应用可导入的路径，或单独安装为
Python 包；主仓库不需要为每个新模型添加注册代码。模型本身的输入输出仍需由
该插件转换到下面的 Saber 契约，不能直接扔进任意权重文件就期望可用。

`pipeline_plugins/` 是示例/模板目录，不会自动扫描执行。原来的 `plugins/` 是
before/after 中间件，继续包围阶段调用；两种插件可以并存。
浏览器编辑器、存储、书架和异步任务系统不属于这六个模型阶段，尚未变成动态插件包。

## 只换 OCR

1. 创建可信的 `my_ocr.py`，实现 `build(**options)`，返回只有 OCR `execute` 的对象。
   可复制 `pipeline_plugins/templates.py` 中的 `Ocr` 类；其他五阶段也各有模板。
2. 创建非秘密 JSON 配置：

```json
{
  "schema_version": 1,
  "plugins": [{
    "stage": "ocr",
    "name": "my_ocr",
    "factory": "my_ocr:build",
    "options": {"model": "your-model-version"}
  }],
  "profiles": {
    "my_ocr_pipeline": {
      "extends": "local_saber",
      "stages": {"ocr": "my_ocr"}
    }
  }
}
```

3. 将 `SABER_PIPELINE_CONFIG` 指向该文件并重启 Saber。环境变量指向路径，文件不放密钥。
4. 浏览器“自动处理的计算方案”选择 `my_ocr_pipeline`。其余阶段继承原方案，
   仍为 `local` 的 OCR/翻译阶段继续使用浏览器已有设置；自定义插件使用服务器配置。

也可继承已配置的 `modal_mtu_deepseek`，只把 OCR 换走。启动先装配
`SABER_REMOTE_CONFIG`（旧远程组合），再装配 `SABER_PIPELINE_CONFIG`。
不需要旧远程组合时只配置后者即可。新方案也能继承同一 JSON 中的另一方案，
定义顺序任意；循环继承、未知阶段、重复名称或未注册实现都会阻止启动。

更改配置或插件代码后重启服务。已经注册的多个方案可在界面切换，下一次任务使用
新选择。运行中的一次任务保持自己的方案名称；目前不支持在进程内热重载配置/模型，
也没有跨重启的任务配置快照。请完成或停止任务后再重启。

## 可直接核对的例子

`pipeline_plugins/provided-text.example.json` 使用随仓库提供的 `provided_text` 插件，
只给已知区域注入配置中的文字。它是无模型的接口示例，不宣称识别图片。
配置中的文本数必须与区域数相同；可用 `/api/parallel/ocr` 单独调用验证。

`pipeline_plugins/mtu.example.json` 独立配置检测、两种 OCR、取色、翻译和修补。
其中 `modular_mtu` 使用 48px，`modular_mtu_mocr` 只覆盖 OCR 为 mocr，其他阶段相同。
它使用现有 Modal Worker 配方和 DeepSeek adapter，没有复制 MTU 源代码。当前示例选择
`deepseek-flash`，只记录环境变量名 `DEEPSEEK_API_KEY`，不在 JSON 中保存密钥。该 adapter
已通过一次四条文本的直接实际调用；真正执行完整方案仍需要已部署 Worker 和运营者自己的凭据。

配置检查不会导入插件模块、加载模型或调用服务：

```sh
python -m tools.check_pipeline_config --plugins-config pipeline_plugins/mtu.example.json
```

若继承旧远程方案，还需传 `--config remote-config.json`。检查只证明配置结构及注册引用
有效，不证明模块能导入、依赖已安装、工厂签名正确或模型可运行。

同一套插件也可用于无浏览器客户端：

```sh
python -m tools.extract_text --image page.png --output text.json --plugins-config pipeline.json --profile my_ocr_pipeline
python -m tools.typeset --image blank.png --layout captions.json --output lettered.png --plugins-config pipeline.json --profile my_renderer_pipeline
python -m tools.translate_page --image page.png --output-dir result --config remote.json --plugins-config pipeline.json --profile my_full_pipeline
```

`my_renderer_pipeline` 是你在配置中声明、包含自定义 render 的方案。只嵌字不会初始化
检测、OCR 或翻译插件。完整 CLI 直接按 profile 调用六个独立端口并生成去字图、成品图和
BubbleState JSON；它不启动 Flask/Vue。以上输出必须是新文件或不存在的新目录。

## 插件 v1 的进程内契约

所有端口是同步 `execute`，按下面的参数调用；自定义函数不需要 `name` 属性，注册名由
加载器提供。类型化端口见 `src/core/stage_backends/base.py`。图片为 `PIL.Image`，
坐标始终是原图像素。此处是进程内插件格式，跨进程 Worker JSON 另见
[PIPELINE_CONTRACTS.md](PIPELINE_CONTRACTS.md)，不能混用。

| stage | execute 输入 | 返回值 |
| --- | --- | --- |
| detect | `(image, **options)` | `dict`：必有 `coords`；可有与框数相同的 `angles`、`polygons`、`auto_directions`、`textlines_per_bubble`；`raw_mask` 可为原图尺寸的二维 uint8 numpy 数组 |
| ocr | `(image, bubble_coords, source_language=..., textlines_per_bubble=...)` | 与区域等长且同序的 `list[OcrResult]`；识别失败保留空字符串，不缩短列表 |
| color | `(image, bubble_coords, textlines_per_bubble=None)` | 等长 `list[dict]`，每项有 `fg_color`、`bg_color`，值为 RGB 整数三元组/数组或 None |
| translate | `(texts, target_language=..., prompt_content=...)` | 同序等长 `list[str]`，保留术语保护占位符 |
| inpaint | `(image, bubble_coords, **options)` | `(PIL 结果图, PIL 干净背景或 None)`，图片尺寸不变；第二项不是 mask |
| render | `(image, bubble_states, auto_font_size=False)` | 同尺寸 PIL 图；可原地更新传入 BubbleState 的规范化样式以供响应序列化，不修改原文 |

detect 的兼容 options 包括检测器、扩框、辅助检测等原有字段；插件应明确消费或忽略，
由自己的服务器 options 选择模型，不在路由增加供应商分支。
inpaint 的 options 包含 `method`、`fill_color`、`bubble_polygons`、`precise_mask`、
`user_mask`、`mask_dilate_size`、`mask_box_expand_ratio`、旧 `lama_model`。
手动 mask 的保留区优先于自动修补。render 自行实现自动字号，不会偷偷调用本地字号算法。

加载器在返回前检查结果数量/基本类型、OCR 置信度、RGB 值、图片/mask 尺寸及检测框边界。
插件还应自己验证复杂多边形、模型语义和返回 ID；这不是完整模型质量验证器。
云端乱序结果必须在插件内部按 ID 排回请求顺序，不能让列表错位覆盖页面。

## 生命周期和错误

- 服务启动只注册声明，不导入工厂，不读取模型凭据，不加载模型。
- 第一次 `execute` 才导入工厂、调用 `factory(**options)`；每个注册项每个进程复用一个实例。
- 同一个插件实例的调用串行执行，以兼容有状态的模型；不同插件可以独立执行。
- 模型依赖可在工厂/构造函数中导入；远端调用由插件自己的客户端承担。GPU 权重留在 Worker。
- 可实现 `close()` 清理资源；正常退出或显式卸载时调用一次，未使用的插件不会为清理而初始化。
  强制杀进程不能保证运行清理。
- 导入失败、模型失败、输出不合约都明确失败，无自动重试或隐式切回本地模型。
  工厂/供应商异常只对客户端返回阶段/插件名，避免附带请求或密钥。

## 配置与安全边界

factory 是任意受信任 Python 代码，拥有应用进程权限；这里不是沙箱，也不是第三方插件市场。
只由服务器运营者安装/配置，浏览器不得上传或指定 factory、模块路径、Python 文件或 options。
不扫描用户工程目录、不从 URL 下载代码、不按请求安装依赖。
配置中的 secret 使用环境变量名称，由插件读取，禁止把真实 key/token 放进 JSON 或 Git。

`GET /api/parallel/backends` 只列各阶段已注册名称；`/profiles` 只列方案与阶段映射。
二者不会暴露 factory、options、密钥名称或触发模型加载。浏览器 OCR/翻译凭据不会传给
自定义阶段插件。`local` 名称保留给原有行为，配置不能覆盖它或任何已注册同阶段同名实现。

## 后续 Agent 怎么新增实现

新模型：只添加插件包、非秘密配置和该模型的结果契约测试。先用 CPU/offline fixture 验证
形状与映射，再单独做真实推理。新执行位置：在插件中使用对应传输客户端。
不要改原子路由的供应商条件树，不要把模型对象或 SDK 返回对象交给编辑器。
旧 `extraction_backends` 只保留兼容入口，自动桥接成 detect、ocr 两个端口，新插件不要继承
组合 `ExtractionBackend`。历史原因见 [DEVELOPMENT_HISTORY.md](DEVELOPMENT_HISTORY.md)。

验证入口：`python -m unittest tests_backend.test_pipeline_plugins`，再运行受影响的阶段/前端测试。
