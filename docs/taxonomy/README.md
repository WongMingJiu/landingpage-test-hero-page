# V2.1a Business Taxonomy

本目录保存 V2.1a Creative Tagging 的 canonical 业务标签定义。

原始来源：用户提供的 Excel `素材级标签文档（初稿）`。

## Canonical files

- `singing-value-taxonomy-v1.0.md`：7 个一级类 / 36 个 Value 二级标签，包含原表标签描述与识别示例。
- `opening-type-taxonomy-v1.0.md`：18 个 Opening Type，包含定义、脚本信号、分镜信号、用户期待、指标、优先级与完整识别规则。
- `user-expectation-taxonomy-v1.0.md`：15 个 User Expectation，包含定义、主要识别信号、示例与排除/边界规则。

## Source priority

实现 V2.1a 时：

1. 产品行为、Decision Window、Schema、Evidence、Matched/Active 规则：以 `docs/v2.1a-creative-tagging-spec-v1.0.md` 为准。
2. 标签本身的 canonical 名称、定义、信号、示例与边界：以本目录对应 taxonomy 文件为准。
3. Benchmark Ground Truth：以 `docs/benchmarks/singing-creative-tagging-benchmark-v1.0.md` 为准。
4. 如旧文档冲突，以上述三类当前 V1.0 文件为准。

`CONTEXT.md` 不作为任何实现依据。

## Change policy

- 不允许实现侧自行改写标签定义来“让模型更好理解”。
- 如需修改标签名称、定义、边界或优先级，应先更新业务 Taxonomy / Spec 版本，再修改实现。
- 运行时 JSON 可以由 Phase B 从这些 canonical 文档忠实转录生成/维护，但不得新增业务含义。
