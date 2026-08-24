# V2.1a Creative Tagging

V2.1a 基于 0–30s 决策窗口的多模态信息，产出三类业务标签（Value Tags / Opening Type / User Expectation），写入 `output/<creative_id>/v2/creative_tags.json`。与 V1 完全隔离（不改 V1 任何文件/行为）。规格见 `docs/v2.1a-creative-tagging-spec-v1.0.md`。

## 运行

```bash
# 1) 配置 API（复用 V1 config.env 或用 V2_ 前缀覆盖）
cp config.env.example config.env   # 填入 API_BASE_URL / API_KEY / MODEL_NAME
# V2 专属覆盖（可选）：
#   V2_API_BASE_URL / V2_API_KEY / V2_MODEL_NAME
#   V2_FRAME_BUDGET=20  V2_FRAME_COMPRESS_KB=100  V2_TEMPERATURE=0
#   V2_AUDIO_UNDERSTANDING_ENABLED=false   (MVP 默认 false：source=audio 非法)
#   V2_FORCE_STAGED=1   (强制走分批请求路径，用于测试 correction #1)
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
