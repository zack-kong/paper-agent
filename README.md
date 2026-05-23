# PaperAgent

学术文献检索与精读 CLI Agent。支持两个模式：

- **`/search`** — 从顶会顶刊检索论文，返回结构化元数据（标题、作者、出处、链接、中文简介）
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
| `KIMI_API_KEY` | Kimi API 密钥（web search） | `/search` 模式下必需 |
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥（文本分析） | `/read` 模式下必需 |
| `DEEPSEEK_BASE_URL` | DeepSeek API 地址 | 可选，默认 `https://api.deepseek.com` |
| `KIMI_BASE_URL` | Kimi API 地址 | 可选，默认 `https://api.moonshot.cn/v1` |

### 配置文件

- `config/venues.yaml` — 顶会顶刊白名单（robotics / AI安全 / 通用AI），可按需增删
- `config/user_profile.json` — 用户偏好学习数据，自动累积

## 快速开始

```bash
# 交互式检索
python -m paper_agent.main search

# 带关键词直接检索
python -m paper_agent.main search --query "adversarial attacks on reinforcement learning"

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
│   └── user_profile.json        # 用户偏好（自动学习）
├── core/
│   ├── paper.py                 # Pydantic 数据模型
│   ├── search_engine.py         # 搜索引擎 + Kimi API
│   ├── validator.py             # Anti-Hallucination 自检
│   └── reading_pipeline.py      # 三层阅读 + DeepSeek API
├── modes/
│   ├── search_mode.py           # /search 交互流程
│   └── reading_mode.py          # /read 交互流程
├── utils/
│   └── markdown_exporter.py     # Markdown 笔记导出
├── main.py                      # CLI 入口
└── requirements.txt
```

## 各模块可独立运行

```bash
python -m paper_agent.core.search_engine   # 测试搜索引擎
python -m paper_agent.core.validator       # 测试反幻觉检查
python -m paper_agent.modes.search_mode    # 直接启动检索
python -m paper_agent.modes.reading_mode   # 直接启动精读
```

## 模型分工

| 任务 | 模型 | 说明 |
|---|---|---|
| Web 搜索、查询最新论文 | Kimi (`kimi-latest`) | 通过 `web_search` tool |
| 文本分析、摘要、翻译、批判性思考 | DeepSeek (`deepseek-chat`) | 全部阅读分析走此模型 |
