# PaperAgent

学术文献检索与精读 CLI Agent。支持两个模式：

- **`/search`** — 从顶会顶刊检索论文，AI 自动翻译中文查询、提取学术概念、多批次搜索、AI 自评结果质量
- **`/read`** — 对单篇论文执行漏斗式三层精读（扫描→速读→精读），生成 Markdown 笔记

## 安装

```bash
cd paper_agent
pip install -r requirements.txt
```

依赖：Python 3.10+, `openai`, `pydantic`, `rich`, `typer`, `ruamel.yaml`

## 配置

### 环境变量

| 变量 | 用途 | 必需 |
|---|---|---|
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥（查询分析 + 论文评估 + 精读） | 必需 |
| `DEEPSEEK_BASE_URL` | DeepSeek API 地址 | 可选，默认 `https://api.deepseek.com` |

### 配置文件

- `config/venues.yaml` — 顶会顶刊白名单（robotics / AI安全 / 通用AI），可按需增删
- `config/user_profile.json` — 用户偏好学习数据，自动累积
- `config/eval_cache/` — AI 评估结果缓存（30 天有效期），自动管理

## 快速开始

```bash
# 交互式检索（支持中文查询）
python -m paper_agent.main search

# 带关键词直接检索
python -m paper_agent.main search --query "adversarial attacks on reinforcement learning"

# 中文查询自动翻译
python -m paper_agent.main search --query "机器人抓取中的对抗攻击"

# 指定年份范围
python -m paper_agent.main search --query "diffusion policy" --years 2023-2025

# 交互式精读（手动输入论文信息）
python -m paper_agent.main read

# 从命令行直接精读
python -m paper_agent.main read \
  --title "Adversarial Robustness in Deep RL" \
  --authors "Smith, Jones" \
  --venue "ICRA 2025" \
  --url "https://arxiv.org/abs/2501.00001" \
  --abstract "We investigate..."

# 查看版本
python -m paper_agent.main version
```

## 项目结构

```
paper_agent/
├── config/
│   ├── venues.yaml              # 顶会顶刊白名单
│   ├── user_profile.json        # 用户偏好（自动学习）
│   └── eval_cache/              # AI 评估缓存
├── core/
│   ├── paper.py                 # Pydantic 数据模型
│   ├── search_engine.py         # 搜索引擎（WebBridge + DeepSeek）
│   ├── validator.py             # Anti-Hallucination 自检（8 点）
│   └── reading_pipeline.py      # 三层阅读 + DeepSeek API
├── modes/
│   ├── search_mode.py           # /search 交互流程
│   └── reading_mode.py          # /read 交互流程
├── utils/
│   └── markdown_exporter.py     # Markdown 笔记导出
├── main.py                      # CLI 入口
└── requirements.txt
```

## /search 检索流程

```
用户输入查询（支持中文）
    │
    ▼
1. analyze_query()    ← DeepSeek 翻译 + 提取学术概念 + 同义词扩展
    │
    ▼
2. recommend_venues() ← AI 推荐最相关的顶会/顶刊
    │
    ▼
3. build_search_batches() ← 3 层搜索策略（精确 / 同义扩展 / 宽泛）
    │
    ▼
4. execute_search_batch() ← WebBridge 操控浏览器在 arXiv 检索
    │
    ▼
5. deduplicate + rank_results() ← 去重 + 多维度排序（关键词/声望/年份）
    │
    ▼
6. evaluate_search_results() ← DeepSeek 自评结果质量 + 多样性检查
    │
    ▼
7. 质量不足？← 自动用 AI 建议的更宽泛查询重试
    │
    ▼
8. boost_by_user_preferences() ← 根据历史采纳偏好加分
    │
    ▼
输出最终结果
```

### 关键特性

- **中文查询自动翻译**：输入"机器人抓取规划"，自动翻译为 "robot grasping manipulation planning" 并提取学术概念
- **学术术语扩展**：AI 为每个关键概念生成同义词和相关术语，提高召回率
- **AI 自评**：DeepSeek 评估每篇论文的相关度和结果集整体质量，质量不足时自动用更宽泛查询重试
- **多样性检查**：检测结果是否过度集中在同一 venue 或同一作者，自动扣分
- **评估缓存**：相同查询 30 天内复用评估结果，节省 API 调用
- **偏好学习**：自动学习用户采纳的 venue 和关键词，后续搜索自动加分

## 模型分工

| 任务 | 模型 | 说明 |
|---|---|---|
| 查询分析、翻译、概念提取 | DeepSeek (`deepseek-chat`) | `analyze_query()` |
| 浏览器操控 arXiv 搜索 | WebBridge（本地浏览器） | `execute_search_batch()` |
| 结果评估、多样性检查 | DeepSeek (`deepseek-chat`) | `evaluate_search_results()` |
| 三层阅读分析 | DeepSeek (`deepseek-chat`) | `reading_pipeline.py` |

## 各模块可独立运行

```bash
python -m paper_agent.core.search_engine   # 测试搜索引擎
python -m paper_agent.core.validator       # 测试反幻觉检查
python -m paper_agent.modes.search_mode    # 直接启动检索
python -m paper_agent.modes.reading_mode   # 直接启动精读
```
