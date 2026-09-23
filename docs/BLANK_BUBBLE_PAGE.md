# 空白气泡页：检框后嵌入已有文字

状态：`CURRENT`，独立无界面流程。它不是完整漫画翻译，也不改动原生 MTU 翻译主路径。
输入是一张已经留出空白对白框的图片，以及调用者提供的每框文字。此路径不执行 OCR、
翻译或去字；已有文字和背景不会自动擦除。

## 从零启动

在仓库根目录用 Python 3.11 或 3.12 建独立环境；本路径无需本地 GPU、torch、Flask 或 Vue：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-blank-page.txt
.venv/bin/python -m unittest tests_backend.test_blank_bubble_page tests_backend.test_typeset_client
```

仅用本机明暗轮廓先找候选框，不会发远程请求：

```sh
.venv/bin/python -m tools.letter_blank_page \
  --image blank-page.png --detector contour --output-dir page-slots
```

若要使用固定 MTU v3.0.4 的 MangaLens 气泡检测器，先部署当前源码的
`workers/mtu_native/modal_app.py`，给控制端传一个**只含非秘密字段**的 JSON 配置：

```json
{"worker":{"app_name":"你的 Modal app 名称","class_name":"MtuNativeWorker"}}
```

```sh
.venv/bin/modal deploy -m workers.mtu_native.modal_app
.venv/bin/python -m tools.letter_blank_page \
  --image blank-page.png --config worker.json --detector mangalens \
  --output-dir page-slots
```

部署和调用可能产生 Modal 费用。需要隔离试验时，部署前设置
`SABER_MTU_NATIVE_APP_NAME`，并让 JSON 的 `app_name` 与它一致；不设置时使用现有原生
Worker 的默认应用名。`--detector hybrid` 会合并 MangaLens 和本机轮廓候选，**不是**质量更高
的保证。固定样页实测：MangaLens 找到 2 个框，轮廓找到 12 个候选，混合得到 13 个候选，
其中存在明显误报和漏报；模型分数与轮廓启发式分数不可当作同一概率。不要按这些分数无检查地
批量写入。推荐让 Agent 查看 `slots-preview.png` 后按 ID 选择，或替换检测器。

`page-slots/slots.json` 保存原图 SHA-256、尺寸、候选框、文字框、ID 和检测来源。
只有原图字节完全相同才可重用；检测只需跑一次。`slots-preview.png` 用红色标候选框、
蓝色标文字安全框。Agent 可直接修订该 JSON 的 `coords`、`text_coords`，但必须保持边界有效。
若自动找框失败，也可以为同一图片生成符合此 schema 的框文件；不必动渲染器。

`texts.json` 可以是按阅读顺序排列的字符串数组，或更安全的 ID→文字对象：

```json
{"slot-0001":"你好！","slot-0003":"这是第二个要嵌字的框。"}
```

当只选择这两个框时运行：

```sh
.venv/bin/python -m tools.letter_blank_page \
  --image blank-page.png --slots page-slots/slots.json \
  --select-slot slot-0001 --select-slot slot-0003 \
  --texts texts.json --output-dir page-lettered
```

输出 `final.png`、`layout.json`、`slots.json` 和预览；目标目录必须不存在，失败不会发布半成品。
可选 `--direction horizontal|vertical`、`--font-size`、`--font-family`、`--inset-ratio`；横排文字
由此客户端计算居中偏移后仍调用原 Saber renderer，竖排保留原 renderer 的列内居中行为。
手动指定字号过大、检测框偏离实际空白区、原图残留旧字时，成品仍可能溢出或重叠，必须看图。

## 模块与更换边界

```text
原图 → BubbleSlotDetector → slots.json → supplied text(ID 精确匹配)
                                          → BubbleState → Saber renderer → final.png
```

- `src/core/blank_bubble_page.py` 的 `BubbleSlotDetector.detect(PIL.Image)` 是可替换接口；
  返回原图坐标中的 `[{"coords":[x1,y1,x2,y2],"confidence":0..1}]`。可在这里注入新视觉模型、
  本地算法或远程执行适配器，而不改文字映射与 renderer。
- `workers/mtu_native/bubble_slots.py` 仅调用固定 MTU 已有 MangaLens 模型；
  `src/core/blank_bubble_contract.py` 是独立 `saber-blank-bubbles/v1` Worker 协议。
  它只传图片和检测选项，不传 DeepSeek Key。旧 `saber-native-mtu-page/v3` 翻译操作不变。
- `prepare_text_layout` 严格检查文字 ID/数量，转换成原 Saber `BubbleState`；
  `tools/typeset.py` 调原有可替换 render stage。换嵌字算法时替换该 render backend 或适配器，
  无须重新训练/部署气泡检测器。
- 阅读顺序目前只是上到下、同高度右到左/左到右的几何排序；复杂分镜应使用 ID 对应文字。

验证分层：离线测试覆盖 Worker 协议、假模型调用、两框轮廓样图、文字映射和真实 CPU PNG 写回；
实页已在隔离 Modal L4 app 跑过检测并在本地完成 7 个选定框的中文写回。这证明编排可用，
**不证明**自动候选可不经校验地处理任意漫画页。以后若更换检框模型，先对相同页面记录候选、
误报、漏报及最终 PNG，再决定是否改默认值。
