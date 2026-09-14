# 📚 学习笔记 · 语音大模型方向

> 持续更新中 · 最后更新：2026-09-10

个人学习笔记仓库，主线为 **语音大模型（Audio/Speech LLM）工程方向**：从 LLM 推理与微调基础，到 Whisper 领域 ASR 微调，再到实时语音对话系统；并行推进 LeetCode 刷题与强化学习基础。

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
│   │   ├── m01~m04*.py    #   加载→tokenize→生成→解码 手写全流程 / datasets 数据处理
│   │   ├── kvCache.py     #   KV cache 原理与加速实验
│   │   ├── *.ipynb        #   chat template / tokenization / 数据处理笔记
│   │   ├── SumW1.md       #   第一周小结（BatchEncoding / chat template 要点）
│   │   └── results/       #   批量推理评测产物（metrics.log / predictions.jsonl）
│   ├── Week2LoRA/         # SFT / LoRA 微调入门（TRL SFTTrainer + minimind 数据）
│   ├── WAug01/            # 🔥 Whisper 实战：推理 / 特征提取 / 全量微调 / LoRA 微调 / WER 评测
│   │   ├── WhisperDemo.py / Whisper_extraction.py   # 推理与 mel 特征提取源码精读
│   │   ├── WhisperCutBlock.py / ConcatAudio.py      # 30s 切块 / 短音频拼接（流式前置）
│   │   ├── train_whisper.py / train_whisper2.py     # 全量微调（v2 为对照实验用）
│   │   ├── train_whisper_lora.py                    # LoRA 微调 + adapter 合并导出
│   │   ├── eval_baseline.py / eval_whisper.py       # 基线 / 微调模型 WER 评测
│   │   ├── eval文件.md                              # 评测结果记录（WER + 逐条对比）
│   │   ├── FuncFile/                                # 音频处理与工具函数
│   │   └── outputs/                                 # 训练产物（模型权重已 gitignore）
│   ├── MiniBPE/           # 从零手写 BPE 分词器（练手项目，参考 karpathy/minbpe）
│   ├── minimind/          # 第三方参考项目：LLM 全链路训练代码（仅作阅读参考）
│   └── requirements.txt   # 环境版本备注（python 3.11 / pytorch 2.11 / cuda 12.8）
├── CodeTopic/             # LeetCode 按专题刷题（数组/双指针/滑动窗口/链表...）
│   ├── Array&Pointer.md   #   数组 + 双指针题单（按组分类，标注考点）
│   ├── array_class.py / linked_list.py / DataStructure.ipynb   # 数据结构实现
│   └── FunctionMethod/    #   语言基础（函数与方法）
├── RLwork/                # 强化学习基础（DQN 等经典算法实现）🚧 刚起步
├── SelfProjectDemo/       # 个人工程实践（skills 编写等）
└── demo.py                # 本地临时脚本（已 gitignore，不上传）
```

> 注：模型权重（`.pth` / `.safetensors` / `.bin`）与数据集目录已在 `.gitignore` 中排除。

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
| 长音频 30s 切块 + 短音频拼接（流式前置） | `WhisperCutBlock.py` / `ConcatAudio.py` | ✅ |
| 全量微调 | `train_whisper.py` / `train_whisper2.py` | ✅ |
| LoRA 微调（峰值显存 4.23 GB，含 adapter 合并导出） | `train_whisper_lora.py` | ✅ |
| WER 评测（基线 / 微调 / LoRA 三配置） | `eval_baseline.py` / `eval_whisper.py` | ✅ 待加繁简归一化 |

**当前结果**（200 条 AISHELL-1 dev 小样本，详见 `WAug01/eval文件.md`；评测归一化修正中，数字待更新）：

| 配置 | WER |
|---|---|
| whisper-medium 基线 | 80.00%* |
| 全量微调（mini） | 68.50% |
| LoRA 微调 | 74.50% |

\* 基线数字受繁简体字形差异污染，偏高（LoRA 版逐条对比可见「广州→廣州」类字形差异）；繁简归一化后将重新测得。

### 并行 · LeetCode 每日刷题 ✅ 持续中

按专题推进：数组/双指针 → 滑动窗口 → 二分 → 前缀和/差分 → 区间合并 → 链表/数据结构，见 `CodeTopic/`。

### 并行 · 强化学习基础（9月 –）🔄 刚起步

从经典值函数方法入手，当前在 `RLwork/` 编写 DQN 算法实现，后续计划衔接 RLHF / GRPO 相关内容（可对照 `minimind/trainer/` 中的 PPO / DPO / GRPO 训练代码阅读）。

---

## 🛠 快速上手

```bash
# 环境
conda create -n audiollm python=3.11 -y
conda activate audiollm
pip install torch --index-url https://download.pytorch.org/whl/cu128
pip install transformers datasets evaluate peft trl librosa soundfile scipy tqdm

# Whisper WER 评测（在 AudioLLmDemo/WAug01/ 下）
python eval_baseline.py                                        # 原版 whisper-medium 基线
python eval_whisper.py                                         # 默认评估全量微调模型
python eval_whisper.py outputs/whisper-medium-aishell-lora/final_merged   # 评估 LoRA 合并模型
```

> AISHELL-1 数据需自行下载并按脚本内的本地路径放置；模型权重不随仓库分发。

---

## 🎯 后续方向

- **项目二收尾**：繁简体归一化 + dev 全量重测 + 错误分析，形成完整项目文档
- **项目三（旗舰）**：实时语音对话系统 —— 级联链路（流式 ASR + vLLM LLM + 流式 TTS）与 Qwen3-Omni 端到端模型同条件对比压测
- **强化学习**：DQN → 策略梯度 → RLHF 对齐链路，与 minimind 的 PPO/DPO/GRPO 实现互相印证
