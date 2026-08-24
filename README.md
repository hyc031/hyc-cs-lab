# 📚 学习笔记 · 语音大模型方向

> 持续更新中 · 最后更新：2026-08-24

个人学习笔记仓库，主线为 **语音大模型（Audio/Speech LLM）工程方向**：从 LLM 推理与微调基础，到 Whisper 领域 ASR 微调，再到实时语音对话系统。

---

## 📖 简介

本仓库记录「大模型 + 语音」方向的学习与项目实践，内容以个人理解为主，仅供参考。

**记录原则：**

- 用自己的话复述，而非简单复制
- 重点记录易错点与个人思考
- 代码即笔记：每个阶段产出可运行的脚本，而非仅文档

**环境**：4 × RTX 3090（24G/卡）/ CUDA 12.8 / Python 3.11 / PyTorch 2.11

---

## 🗂 仓库结构

```
├── AudioLLmDemo/          # 语音 LLM 学习主目录
│   ├── Week1Basics/       # HuggingFace 生态：推理全流程 / tokenizer / chat template / KV cache
│   ├── Week2LoRA/         # SFT / LoRA 微调入门
│   ├── WAug01/            # 🔥 Whisper 实战：推理 / 特征提取 / 全量微调 / LoRA 微调 / WER 评测
│   ├── MiniBPE/           # 从零手写 BPE 分词器（练手项目）
│   └── minimind/          # 第三方参考项目：LLM 全链路训练代码（仅作阅读参考）
├── CodeTopic/             # LeetCode 按专题刷题（数组/前缀和/差分/二分/滑动窗口...）
└── demo.py
```

---

## 🚀 当前工作摘要

### 阶段一 · LLM 工程基础（6月底 – 7月初）✅

- 手写「加载 → tokenize → 推理 → 解码」全流程，不依赖 `pipeline()`
- 实操 chat template、生成参数（temperature / top_k / top_p）、KV cache 加速
- 用 `datasets` 将 alpaca 数据集处理为 SFT 格式，完成批量推理与评测（见 `Week1Basics/results/`）
- 参考阅读：minimind（pretrain / SFT / LoRA 训练链路）、MiniBPE（从零实现 BPE）

### 阶段二 · Whisper 领域 ASR（8月）🔄 进行中

在 AISHELL-1 上微调 `whisper-medium`，已完成训练与评测链路搭建：

| 内容 | 脚本 | 状态 |
|---|---|---|
| 推理与特征提取（mel 全链路解析） | `WhisperDemo.py` / `Whisper_extraction.py` | ✅ |
| 30s 切块处理（流式前置） | `WhisperCutBlock.py` | ✅ |
| 全量微调 | `train_whisper.py` | ✅ |
| LoRA 微调（峰值显存 4.23 GB，含 adapter 合并导出） | `train_whisper_lora.py` | ✅ |
| WER 评测（基线 / 微调 / LoRA 三配置） | `eval_baseline.py` / `eval_whisper.py` | ✅ 待加繁简归一化 |

**当前结果**（200 条小样本验证，评测归一化修正中，数字待更新）：

| 配置 | WER |
|---|---|
| whisper-medium 基线 | 80.00%* |
| 全量微调（mini） | 68.50% |
| LoRA 微调 | 74.50% |

\* 基线数字受繁简体字形差异污染，偏高；归一化后将重新测得，见 `nextstep.md`。

### 并行 · LeetCode 每日刷题 ✅ 持续中

按专题推进：数组/双指针 → 滑动窗口 → 二分 → 前缀和/差分 → 区间合并，见 `CodeTopic/`。

---

## 🎯 后续方向

- **项目二收尾**：评测归一化 + dev 全量重测 + 错误分析，形成完整项目文档

- **项目三（旗舰）**：实时语音对话系统 —— 级联链路（流式 ASR + vLLM LLM + 流式 TTS）与 Qwen3-Omni 端到端模型同条件对比压测

  
