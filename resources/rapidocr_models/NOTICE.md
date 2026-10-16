# 随包 OCR 模型：出处、许可与改动说明

本目录的三个 `.onnx` 是「截图提取文字」用的本地 OCR 模型，**随安装包分发**；
同目录的 `LICENSE.txt` 与 `MODEL_LICENSES.md` 是随包所需的许可与出处声明。

## 1. 文件清单与摘要

| 文件 | 字节 | sha256 |
| --- | --- | --- |
| `PP-OCRv6_det_small.onnx`（文本检测） | 9,929,594 | `090f04abcd9d9a7498bc4ebf677e4cb9bdce1fe4197ddb7e529f1ef44e1ff94f` |
| `PP-OCRv6_rec_small.onnx`（文本识别） | 21,234,383 | `6f327246b50388f3c176ae304bd95767ea6dc0c9ae92153ef8cbe210b3c14884` |
| `ch_ppocr_mobile_v2.0_cls_mobile.onnx`（方向分类） | 585,532 | `e47acedf663230f8863ff1ab0e64dd2d82b838fceb5957146dab185a89d6215c` |

三个模型都**逐字节取自 `rapidocr` wheel 自带的 `rapidocr/models/`**（同一版本），
没有做任何转换、量化或重命名；摘要与上游 `MODEL_LICENSES.md` 第 6 节登记的
SHA-256 逐项一致，也与 `pet/screen_capture/ocr.py::MODEL_SHA256` 一致。
构建期由 `scripts/verify_rapidocr_models.py` 按「文件名 + sha256」校验，任一项
不符即中止打包。

## 2. 许可与版权

- **模型权重**：`PP-OCRv6_det_small` / `PP-OCRv6_rec_small` 来自 PaddleOCR
  官方模型；`ch_ppocr_mobile_v2.0_cls` 来自 PaddleOCR 的旧版模型列表。上游
  模型权重的版权归 **Baidu 和/或相应的 PaddleOCR 权利人**所有，以
  **Apache License 2.0** 发布。
- **分发方**：RapidOCR 项目（RapidAI）把上游模型转换为 ONNX 并按同一许可
  （Apache-2.0）分发，转换不转移上游权重版权。
- `LICENSE.txt` = `rapidocr` wheel 的 `LICENSE`（Apache-2.0 全文，
  sha256 `3e0af25fdd06aa9586ae97adb00ea927ebe5a3805ac77d2d3a81ce5f55693333`）；
  `MODEL_LICENSES.md` = 同一 wheel 的 `MODEL_LICENSES`
  （sha256 `c5fd0e8603d3df743355b546121e6fe0f4ef8ff455c5a85c1681fd3ae520e153`）。
  两份都是**上游原文逐字，未改动**。

## 3. 改动说明（Apache-2.0 §4(b)）

我们**没有修改**任何模型文件：它们是上游产物的原样拷贝（文件名与字节都未变）。
因此不存在"被修改的文件需要加显著改动声明"的情形。上游对**转换后**产物建议的
声明（`MODEL_LICENSES.md` §7）随原文一并附在本目录：

> Converted from an official PaddleOCR model to the indicated inference format
> and packaged for use with RapidOCR. The upstream model weights are copyright
> Baidu and/or the applicable PaddleOCR rights holders and are licensed under
> the Apache License, Version 2.0.

## 4. 商标

Apache-2.0 不授予使用 Baidu / PaddlePaddle / PaddleOCR / RapidOCR 商标或产品名
的权利（仅限合理描述来源）。本项目的使用不暗示任何背书、赞助或关联关系。
