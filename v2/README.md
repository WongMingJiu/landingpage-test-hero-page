# V2.1a Creative Tagging — Frozen

V2.1a 基于 0–30s 决策窗口的多模态信息，产出三类业务标签（Value Tags / Opening Type / User Expectation），写入 `output/<creative_id>/v2/creative_tags.json`。与 V1 完全隔离（不改 V1 任何文件/行为）。规格见 `docs/v2.1a-creative-tagging-spec-v1.0.md`，最终裁决见 `docs/benchmarks/v2.1a-final-verdict.md`。

## 正式接口与生产链路

```text
广告视频 → 0–30s 多模态理解 → 直接完成 Creative Tagging → creative_tags.json → V2.1b Intent Decision
```

- **正式输入**：广告视频。
- **正式输出**：`creative_tags.json`（schema `creative_tagging_v1`：decision_window /
  matched_value_tags / active_value_tags / opening_type / user_expectation / review，
  每个标签带 evidence + confidence）。
- **V2.1b 的必需输入只有 `creative_tags.json`**；其他中间产物不构成正式业务依赖。

### Production Path（默认行为）

**Direct Multimodal Creative Tagging**：单次多模态调用 Fast Path（帧 + 带时间戳转写
→ 直接裁决 → creative_tags.json）。`V2_FORCE_STAGED` 默认关闭，该路径不产生
structured_evidence.json。

### Debug / Benchmark Path（非业务主链路）

以下能力全部保留，但统一为 **Benchmark / Debug / 稳定性分析 / 异常排查工具**：

- `V2_FORCE_STAGED=1`：staged 分批提取 + 受限裁决路径（单请求过载/超时时也会自动降级到该路径，属容错而非主链路）；
- `structured_evidence.json`：staged 路径的中间工件，仅用于冻结证据复现与排查，不是正式输出；
- `python -m v2.replay_adjudication`：adjudication-only replay（零提取成本重跑裁决）；
- `v2/benchmarks/adjudication_stability.py` / `extraction_stability.py`：稳定性验证工具。

## 运行

```bash
# 1) 配置 API（复用 V1 config.env 或用 V2_ 前缀覆盖）
cp config.env.example config.env   # 填入 API_BASE_URL / API_KEY / MODEL_NAME
# V2 专属覆盖（可选）：
#   V2_API_BASE_URL / V2_API_KEY / V2_MODEL_NAME
#   V2_FRAME_BUDGET=20  V2_FRAME_COMPRESS_KB=100  V2_TEMPERATURE=0
#   V2_AUDIO_UNDERSTANDING_ENABLED=false   (MVP 默认 false：source=audio 非法)
#   V2_FORCE_STAGED=1   (Debug/Benchmark 工具：强制走分批 + structured evidence 路径，生产默认关闭)
#   WHISPER_MODEL=small

# 2) 单视频打标
python -m v2.run_creative_tagging ./sample.mp4 --creative-id my_video

# 输出：output/my_video/v2/creative_tags.json
```

## 关键设计

- **Decision Window**：默认 0–30s；仅当多模态语义本身不足（`transcript_sparse != semantic_sparse`，ASR 稀疏不触发扩窗）才扩到 0–60s。
- **帧采样（correction #1）**：0–10s 1fps 硬保证（11 帧，永不降采样）；10–30s 每 2s 一帧（9 帧），默认 20 帧。单请求容不下时分批/分阶段请求，Opening 覆盖不牺牲。
- **Evidence source（correction #2）**：MVP 无音频理解组件，`source="audio"` 一律非法（schema 闸 `V2_AUDIO_UNDERSTANDING_ENABLED` 默认 false）；视觉推断记 `visual`，Whisper 转写记 `transcript`，画面字幕记 `subtitle`。
- **Schema**：`creative_tagging_v1` 逐字冻结（spec §11）；`schema.py` 手写校验，无新依赖。
- **Taxonomy**：从 `docs/taxonomy/*-v1.0.md` 忠实转录为 `v2/taxonomy/singing/*.json`；loader 缺字段即 fail-fast，绝不把裸枚举塞给模型。Opening 运行时冲突解决用 `决策优先级` 表（非 `默认优先级` 列）。

## 测试

```bash
python -m unittest discover tests -v   # 全部单测（无 API/无视频）
```

## Benchmark

```bash
# 本地视频放入：benchmarks-local/singing-creative-tagging-v1.0/videos/v01.mp4 ... v10.mp4
python -m v2.benchmarks.run_benchmark --videos-dir benchmarks-local/singing-creative-tagging-v1.0/videos
# 报告：output/benchmark-runs/<run_id>/report.{json,md}
```
