# SRSZW

SRSZW 是一个面向 Python 3.12 及以上版本的轻量级库和命令行工具：它将中文转换为适用于 VOICEVOX Engine 的音高短语，再直接调用 Engine 合成 WAV 音频。

> 当前版本：`0.2.0`（开发中）
>
> 已验证 Engine：VOICEVOX Engine `0.25.2`
>
> 当前范围：离线中文韵律转换、直接 TTS、诊断查询、Engine 角色查询与可编辑 `.vvproj` 导出。反向代理将在后续版本提供。

## 不包含的功能

- 不提供 Web、Tk 或其他桌面 GUI。
- 不捆绑、下载或分发 VOICEVOX Engine、模型或角色音源。
- 不承诺将中文变为自然的日语语音；本项目通过日语音素与音高曲线近似表达中文声调。

## 前置条件

1. 安装 Python 3.12 或更高版本。
2. 安装 [uv](https://docs.astral.sh/uv/)。
3. 单独启动一个兼容的 VOICEVOX Engine。默认地址为 `http://127.0.0.1:50021`。

## 安装与开发环境

克隆仓库后，在 Windows `cmd.exe` 中执行：

```cmd
uv sync --all-groups
```

开发时运行质量检查：

```cmd
uv run ruff check . && uv run pyright && uv run pytest
```

安装为普通 Python 包：

```cmd
uv pip install .
```

## 命令行

所有命令都可在 Windows `cmd.exe` 中单行执行。未指定 `--engine-url` 时会连接默认的本地 Engine。

### 查看角色与 style ID

```cmd
uv run srszw speakers
```

每行按 `style ID`、风格名称、角色名称输出。直接合成时，`--speaker` 必须使用这里返回的整数 style ID。

### 直接合成 WAV

```cmd
uv run srszw synthesize --text "你好，世界。" --speaker 2 --output hello.wav
```

可以调节常用语音参数：

```cmd
uv run srszw synthesize --text "你好，世界。" --speaker 2 --output hello.wav --speed-scale 1.05 --pitch-scale 0.0 --seed 7
```

也可以从 UTF-8 文本文件读取内容：

```cmd
uv run srszw synthesize --text-file input.txt --speaker 2 --output hello.wav
```

为防止误覆盖，已有输出文件会使命令失败；明确覆盖时追加 `--force`。

### 导出可编辑的 VVProj 工程

导出器当前仅明确支持经 VOICEVOX UI `0.25.2` schema 核对的工程格式。它会从 Engine 查询实际的 Engine UUID 与 speaker UUID，复用直接合成的中文韵律转换，并为每个台词写入 voice 与 query。

```cmd
uv run srszw export-project --text "你好，世界。" --speaker 2 --output hello.vvproj
```

需要逐条指定声线或参数时，创建 UTF-8 JSON 数组：

```json
[
  {"text": "你好。"},
  {
    "text": "世界！",
    "speaker": 3,
    "options": {"speed_scale": 1.15, "output_sampling_rate": 48000}
  }
]
```

然后以 `--speaker` 提供默认 style ID；输入项中的 `speaker` 与 `options` 会覆盖全局值：

```cmd
uv run srszw export-project --input utterances.json --speaker 2 --output project.vvproj --seed 7
```

`--text`、`--text-file` 与 `--input` 互斥。和 WAV 合成一样，已有输出默认拒绝覆盖，显式追加 `--force` 才会覆盖。

### 查看生成的 AudioQuery

此命令不访问 Engine，只输出本地中文转换得到的 Engine 请求 JSON：

```cmd
uv run srszw query --text "你好，世界！" --seed 7 > query.json
```

## Python API

```python
from pathlib import Path

from srszw import ChineseSynthesizer, SynthesisOptions, VoicevoxClient

options = SynthesisOptions(speed_scale=1.05)
with VoicevoxClient("http://127.0.0.1:50021") as client:
    synthesizer = ChineseSynthesizer(client, seed=7)
    wav = synthesizer.synthesize("你好，世界。", speaker=2, options=options)

Path("hello.wav").write_bytes(wav)
```

导出工程时使用 [`ProjectUtterance`](src/srszw/project.py) 表示每段台词；全局 `speaker` / `options` 可以被单段覆盖：

```python
from srszw import ProjectUtterance

with VoicevoxClient("http://127.0.0.1:50021") as client:
    synthesizer = ChineseSynthesizer(client, seed=7)
    synthesizer.export_project(
        [
            ProjectUtterance("你好。"),
            ProjectUtterance("世界！", speaker=3),
        ],
        "project.vvproj",
        speaker=2,
        app_version="0.25.2",
    )
```

如果只需要检查离线转换结果，可调用 `build_audio_query()` 或 `generate_accent_phrases()`；二者都不需要运行 Engine。

```python
from srszw import build_audio_query

query = build_audio_query("你好，世界！", seed=7)
print(query["accent_phrases"])
```

## 数据与迁移

转换数据只随包发布，位于 [`src/srszw/data/`](src/srszw/data/)；项目根目录不再保留重复的 `data/` 副本。包内资源采用描述性英文名称，例如 [`pinyin_to_voicevox_phonemes.json`](src/srszw/data/pinyin_to_voicevox_phonemes.json) 和 [`mandarin_tone_contours.json`](src/srszw/data/mandarin_tone_contours.json)。

根目录的 [`config.json`](config.json) 已改为只保存旧工程导出所需的示例参数，默认使用包内转换数据。旧 `.hooay-srszw.json`、`charactor` 参数拼写和扁平命令行仍暂作为兼容层保留；新代码请使用本文档中的子命令和公开 Python API。

## 开发与测试

离线测试默认不会连接 Engine。要执行真实集成测试，在 `cmd.exe` 中设置地址后运行：

```cmd
set VVENGINE_URL=http://127.0.0.1:50021 && uv run pytest -m integration
```

测试覆盖离线转换、资源加载、HTTP MockTransport、CLI 文件输入、VVProj schema 结构、每段 voice/options 覆盖，以及本机 Engine 的 WAV 合成闭环。

## 许可证与 VOICEVOX

本项目采用 [WTFPL](LICENSE)。使用 VOICEVOX 或其他语音引擎、模型和角色时，仍须遵守它们各自的许可证、角色使用条款和相关规范。
