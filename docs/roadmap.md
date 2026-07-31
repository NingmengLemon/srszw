# SRSZW 改造路线图

> 状态：提案  
> 适用版本：0.2.0 起  
> 最后核对：2026-07-31

## 1. 愿景与边界

SRSZW 将从“生成旧版 VOICEVOX 工程文件的脚本”演进为一个面向 Python 3.12 及以上版本的轻量级库。它只提供两种产品入口：

1. Python API：可嵌入其他应用，构造中文适配后的 VOICEVOX `AudioQuery`、请求引擎并取得 WAV 字节，或导出可编辑的 `.vvproj` 工程。
2. 命令行：面向脚本、自动化任务及手工调用，功能与公共 Python API 一一对应。

长期目标是在可选的反向代理模式中，对 VOICEVOX Engine 的中文相关请求做兼容补丁，使既有客户端可将代理地址当作普通 Engine 地址使用；未受影响的接口必须按原方法、路径、查询参数、状态码、响应头和响应体透传。

### 明确不做

- 不恢复或维护 Web、Tk、桌面 GUI。
- 不打包或分发 VOICEVOX Engine、核心模型和角色音源。
- 不把网络服务或代理作为基础安装依赖。
- 不承诺将中文文本转成自然的日语语音；本库的职责是把汉语拼音和声调映射为当前引擎可合成的日语音素序列与音高曲线。

## 2. 当前基线与已验证事实

### 仓库基线

- 包已经采用 `src` 布局，Python 下限为 3.12，并由 `uv.lock` 锁定环境。
- 上一次 `restructure` 提交已移除 GUI、将旧脚本拆分为 CLI、配置、转换器和工具函数；README 则保留了旧使用方式，不能作为当前 API 契约。
- 当前转换器已能生成含 `accentPhrases` 的旧式 `.vvproj`，但数据文件依赖运行时工作目录，公开 API 仍暴露旧的 `charactor` 命名和全局 JSON 配置模型。
- 临时目录中的 OpenAPI 快照是本地探索材料，不能作为发布包内容或长期手写接口定义来源。

### 本机 Engine 基线

已连接到 `http://127.0.0.1:50021`：

- Engine 版本为 `0.25.2`。
- `/speakers` 返回 43 个角色；首个 style ID 为 2。
- 对中文文本调用原生 `/audio_query` 可成功响应，但返回的 `kana` 是日语读音，说明中文需要由 SRSZW 自行构造重音短语，而不能直接信任引擎的文本解析结果。
- 已确认存在直接合成和代理相关的关键接口：`/audio_query`、`/accent_phrases`、`/synthesis`、`/multi_synthesis`、`/cancellable_synthesis`、`/mora_data`、`/mora_length`、`/mora_pitch`、`/speakers`、`/speaker_info`、`/engine_manifest` 和 `/version`。

## 3. 目标架构

### 分层

```text
CLI ───────────────┐
                   ├── 公共 API（同步优先） ── 编排服务
Python 调用方 ──────┘                           ├── 中文韵律转换
                                               ├── VOICEVOX HTTP 客户端
                                               └── VVProj 导出器

可选代理 ───────────────────────────────────────┴── 透传/补丁策略
```

各层只依赖其下层，核心中文转换不得依赖 HTTP、CLI 参数或 Web 框架。

### 建议模块边界

| 模块 | 责任 |
| --- | --- |
| `srszw.models` | 冻结/校验公开输入输出模型：语音参数、说话人、转换结果和工程台词。 |
| `srszw.converter` | 汉字/拼音分词、音节映射、声调曲线与 `AudioQuery` 的 `accentPhrases` 生成。必须可离线运行。 |
| `srszw.engine` | 基于 `httpx` 的同步 Engine 客户端；负责超时、HTTP 错误、JSON、WAV 字节和 Engine 信息。 |
| `srszw.project` | 将转换结果和说话人元数据写成指定版本的 `.vvproj`；不负责联网合成。 |
| `srszw.api` | 稳定的高层函数和 `ChineseSynthesizer` 门面，组合转换器、客户端与导出器。 |
| `srszw.cli` | 仅做参数解析、stdin/stdout、退出码和调用公共 API；不能复制业务逻辑。 |
| `srszw.proxy`（可选 extra） | HTTP 反向代理、中文请求识别与定点补丁，不得进入基础依赖图。 |

内部实现使用 Python 3.12+ 的类型语法、`dataclass`、`pathlib.Path`、`collections.abc` 和 `typing.Self`；公开模块避免暴露内部可变字典作为唯一 API。

### 公共 Python API 草案

第一版优先提供同步 API，避免为轻量脚本强制引入异步生命周期。后续若确有并发需求，再在不破坏同步 API 的前提下增加独立 async 客户端。

```python
from pathlib import Path

from srszw import ChineseSynthesizer, SynthesisOptions, VoicevoxClient

client = VoicevoxClient("http://127.0.0.1:50021")
synthesizer = ChineseSynthesizer(client)
options = SynthesisOptions(speed_scale=1.05, pitch_scale=0.0)

wav = synthesizer.synthesize("你好，世界。", speaker=3, options=options)
Path("hello.wav").write_bytes(wav)

synthesizer.export_project(
    [("你好，世界。", 3, options)],
    "hello.vvproj",
    app_version="0.25.2",
)
```

契约原则：

- `prepare_query(text, options)` 只做本地中文转换，返回可序列化、与 Engine `AudioQuery` 结构兼容的对象。
- `synthesize(...)` 先准备查询，再向 `/synthesis?speaker=<style-id>` 提交 JSON，返回原始 WAV 字节；调用方可完全控制保存位置。
- `export_project(...)` 从同一查询结果生成工程，保证“直接合成”和“导出工程”使用同一韵律算法。
- `VoicevoxClient` 提供低层 `version()`、`speakers()`、`speaker_info()`、`synthesis()` 等明确方法，不在高层 API 中硬编码角色昵称或历史 Engine UUID。
- 角色参数使用 Engine 真实的整数 style ID，历史 `charactor` / `style` 别名仅可在迁移期由显式兼容层解析。

## 4. 命令行设计

命令入口固定为 `srszw`，所有参数使用跨平台的短横线形式；文档和测试中的 Windows 示例必须可在 cmd 中一行执行。

| 命令 | 用途 | 核心参数 |
| --- | --- | --- |
| `srszw synthesize` | 直接从中文生成 WAV。 | `--text` / `--text-file`、`--speaker`、`--engine-url`、`--output`、语音参数。 |
| `srszw export-project` | 生成可编辑的 `.vvproj`。 | `--text` / `--input`、`--speaker`、`--output`、语音参数、`--app-version`。 |
| `srszw speakers` | 显示当前 Engine 的角色和 style ID。 | `--engine-url`、`--json`。 |
| `srszw query` | 输出本地生成的 `AudioQuery` JSON，用于诊断、调参和代理测试。 | `--text`、`--speaker`、语音参数。 |
| `srszw proxy`（后续 optional extra） | 启动中文适配反向代理。 | `--listen`、`--upstream`、`--mode`、`--log-level`。 |

输入互斥规则：`--text`、`--text-file` 和项目输入文件三者只允许一个。WAV 或工程输出目录不存在时自动创建；同名文件默认拒绝覆盖，使用 `--force` 才允许覆盖。错误写入 stderr，并使用稳定的非零退出码。

## 5. 依赖、打包与配置策略

### 依赖策略

- 基础运行依赖：保留 `pypinyin`，新增 `httpx` 用于 HTTP 客户端。
- 开发依赖组：`pytest`、`pytest-httpx` 或 `respx`、`ruff`、`pyright`；全部由 uv 管理。
- 可选代理 extra：选择轻量 ASGI 实现（建议 `starlette` + `uvicorn`），只在 `srszw[proxy]` 时安装。
- 不引入大型 CLI 框架、ORM 或通用配置框架；初期继续使用标准库 `argparse`。

### 打包修复

1. 将转换表移动到 `src/srszw/data/` 并通过 `importlib.resources` 读取，禁止默认配置依赖当前工作目录。
2. 以 `setuptools` 自动发现 `srszw` 及其子包，并正确声明 JSON 包数据；当前手写包列表和包数据目标不匹配，需要在迁移时修正。
3. 将库默认设置改为不可变或按调用复制的 `ConversionOptions`，不再隐式读取根目录 `config.json`。
4. 根目录 `config.json` 和旧 `.hooay-srszw.json` 作为迁移样例保留一个小版本周期，然后迁移到 `examples/legacy/` 或在下一个破坏性版本删除。
5. 使用 `uv sync --all-groups`、`uv run pytest`、`uv run ruff check .` 和 `uv run pyright` 作为本项目固定验证入口。

## 6. 里程碑

### M0：冻结基线与测试护栏

目标是让重构可回归验证，而不是立刻改变语音算法。

- 为拼音、标点、声调、整体认读和随机偏移可复现性补充单元测试。
- 对当前示例工程建立 JSON 结构快照或语义断言，避免 UUID 等随机字段造成脆弱快照。
- 给配置加载、未知角色、未知韵母、无效声调和输出路径错误定义明确异常。
- 在文档中标识旧 API 为弃用，不再更新旧 GUI/脚本教程。

验收：离线测试不依赖 50021 端口，且现有样例转换可稳定通过。

### M1：核心转换器与数据资源化

目标是把中文转换结果从旧 `.vvproj` 组装逻辑中剥离出来。

- 定义 `ConversionOptions`、`SynthesisOptions` 和可 JSON 序列化的 AudioQuery/AccentPhrase/Mora 模型。
- 将 `SRSZWConverter` 拆成无副作用的“文本到重音短语”转换器与独立的工程导出器。
- 为随机细节提供显式 `seed` 或禁用随机偏移的确定性模式；默认行为需在版本说明中声明。
- 修复拼音切分和标点处理边界：空白、连续标点、非汉字、英文数字、无声调拼音、儿化及多音字须有测试与可预期降级策略。
- 完成数据文件打包并在非仓库工作目录下进行安装后 smoke test。

验收：在空临时目录执行已安装的包，仍可从中文文本得到结构有效的 `accentPhrases`。

### M2：直接 TTS Engine 客户端

目标是产出 WAV，而不要求用户打开 GUI 或手工导入工程。

- 实现 `VoicevoxClient`：基地址标准化、可配置 connect/read/write timeout、合理的 HTTP 错误上下文和 JSON 解码错误。
- 实现 `ChineseSynthesizer.prepare_query()`、`synthesize()`、`synthesize_to_file()`；将本地构造的查询 POST 到 `/synthesis`。
- 以 `/speakers` 查询实际 style ID；CLI 增加 `speakers`，废除把过期静态角色表当作 Engine 真相的做法。
- 支持常用查询参数：速度、音高、抑扬、音量、前后无声、停顿、采样率和立体声。
- 加入真实 Engine 集成测试标记，默认跳过；当 `SRSZW_ENGINE_URL` 存在时，对本机 0.25.2 执行“中文 -> 查询 -> synthesis -> RIFF/WAVE 文件头”的端到端测试。

验收：`srszw synthesize --text "你好，世界。" --speaker 3 --output hello.wav` 在当前 50021 引擎可生成非空 WAV。

### M3：工程导出与 CLI 收敛

目标是给调参用户提供可编辑工程，同时保证与直接合成同源。

- 实现版本化 `VVProjExporter`，由显式 `app_version` 决定输出 schema，初始目标为已验证 Engine/UI 版本；未知版本拒绝猜测或要求显式 opt-in。
- 多段文本用列表模型表示，每段可覆盖全局 `SynthesisOptions` 和 speaker。
- CLI 实现 `synthesize`、`export-project`、`query`、`speakers` 子命令；旧扁平参数解析为兼容提示或在 0.3 移除。
- 全面更新 README：安装、uv、cmd 一行示例、Python API、Engine 前置条件、许可证边界和版本兼容性。

验收：同一输入以 API 和 CLI 调用产生等价 AudioQuery；导出的项目可被目标 VOICEVOX UI 打开，并保留每段的 voice 与 query 参数。

### M4：反向代理（可选安装包）

目标是让支持标准 VOICEVOX HTTP API 的现有客户端可选择性地获得中文输入能力。

#### 工作方式

- 代理监听本地地址并配置单一 upstream Engine URL；自身不重写 `/speakers`、`/speaker_info`、`/version` 等能力发现接口。
- 所有请求先保留原始 method、path、query、body 及与语义相关的 headers，然后按规则决定透传或补丁；二进制响应使用流式转发，避免整体读入内存。
- 默认 `auto` 模式只在 `text` 含汉字时拦截；纯日文、纯拉丁文本及未知路径原样转发。提供 `off` 和 `force` 明确控制模式。

#### 需要补丁的接口

1. `POST /audio_query`：对中文文本生成本地 `accent_phrases`，并从 Engine 的种子查询或稳定默认值中保留全部标准语音参数，返回兼容的完整 AudioQuery。
2. `POST /accent_phrases`：对中文文本直接返回本地重音短语。
3. `POST /mora_data`、`/mora_length`、`/mora_pitch`：第一版先透传，并为“客户端编辑查询后是否覆盖中文自定义时值”建立集成测试；若事实证明会破坏结果，再仅对可安全保留的字段实施补丁，禁止盲目重算。
4. `POST /synthesis`、`/multi_synthesis`、`/cancellable_synthesis`：不解析中文、不修改 AudioQuery，直接将用户已有的查询转给 upstream，保留原始音频响应。
5. `/validate_kana` 和未枚举接口：默认透传；仅在实际客户端流程证明中文校验阻断时新增最小化兼容规则并记录。

代理必须为 upstream 不可达、超时、无效 JSON、body 过大和客户端取消请求定义行为。日志默认不记录完整文本；诊断模式可记录长度、命中规则和关联 ID。

验收：普通日语 `audio_query` 的代理响应与直接访问 upstream 在语义上相同；中文 `audio_query` 后接 `synthesis` 能产生 WAV；未登记接口的状态码和响应体不被代理篡改。

### M5：兼容性、发布与维护

- 发布 0.2.0：标记为 Alpha/Beta，明示 Python、Engine 和 UI 已验证版本矩阵。
- 建立语义化版本策略；公开 Python API 的破坏性变更只在主/次版本边界进行，并在迁移指南中给出替代方案。
- 为 Engine OpenAPI 文档建立“下载快照 + diff 审查”脚本或 CI 任务；不将抓取到的临时 JSON 当作人工修改的源码。
- GitHub Actions 仅保留 lint、type check、unit test、build 和发布需要的工作流；GUI 构建工作流不恢复。

## 7. 数据和算法改进清单

以下项不会阻塞 M2，但需要可观测、可复现地逐项推进：

1. 增加可配置的多音字词典和自定义拼音覆盖，优先级高于 `pypinyin` 默认结果。
2. 将标点分类为短停顿、长停顿、句末停顿和无声字符，避免当前“任意匹配字符都给上一短语塞相同 pauseMora”的粗粒度行为。
3. 按文本语义切段，避免超长句导致音高曲线跨不相关片段。
4. 将音素映射表的格式和版本纳入测试；缺失映射应报告具体拼音、声母/韵母和数据表来源。
5. 定义面向人工听感的中文回归语料：四声、轻声、变调、多音字、数字、英文、标点、长句和混合日文。
6. 区分“Engine 可以合成”与“听感达标”：端到端 WAV 测试证明接口正确，人工试听集用于算法质量评估。

## 8. 风险与决策原则

| 风险 | 应对原则 |
| --- | --- |
| VOICEVOX 的内部 query/vvproj schema 随版本变化 | 客户端只依赖已验证 OpenAPI；导出器显式版本化；CI 对 OpenAPI diff 报警。 |
| 静态角色数据过期 | 直接合成始终以 `/speakers` 为准；静态表只作为兼容别名或示例。 |
| `.vvproj` UI schema 不等于 Engine HTTP schema | 共享转换结果，不共享最终 JSON 包装；分别进行集成验证。 |
| 代理补丁范围膨胀 | 默认未知接口透传；每增加一个拦截接口都需有真实客户端用例和代理/直连对比测试。 |
| 声调随机量影响测试及用户复现 | 提供 seed 和确定性模式，并使测试固定 seed。 |
| 轻量库被可选服务依赖拖重 | HTTP 客户端是基础层；反向代理严格放在 optional extra。 |

## 9. 推荐执行顺序

1. 先完成 M0 和 M1，冻结纯转换输入输出和资源加载方式。
2. 紧接着实施 M2，在本机 50021 引擎上验证真正的 WAV 合成闭环。
3. 完成 M3，并以新 API/CLI 重写 README，之后再考虑旧接口移除时间点。
4. 仅在有明确的第三方客户端接入需求后实施 M4；代理层不得反向驱动核心库 API 设计。
5. 每个里程碑单独提交、可独立回滚，并在提交说明写清已验证的 Python 与 Engine 版本。
