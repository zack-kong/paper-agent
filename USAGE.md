# PaperAgent 使用指南

## 目录

1. [检索模式 /search](#检索模式-search)
2. [精读模式 /read](#精读模式-read)
3. [配置与调优](#配置与调优)
4. [常见问题](#常见问题)

---

## 检索模式 /search

### 基本流程（7 步）

```
用户输入查询 → 需求澄清 → 推荐会议 → 制定搜索策略 → 执行搜索 → 去重排序 → 自检输出
```

### 交互示例

**Step 1: 输入查询**

```bash
$ python -m paper_agent.main search
```

```
╭────────────────────────── /search ──────────────────────────╮
│ 学术文献检索模式                                             │
│ 从顶会顶刊中检索论文，返回结构化元数据。                      │
│ 输入 'quit' 退出。                                           │
╰─────────────────────────────────────────────────────────────╯

请输入检索主题/关键词: adversarial robustness in robot RL
```

**Step 2: 自动推荐会议**

系统根据关键词自动匹配领域并推荐 5 个会议：

```
┌───┬────────────────┬──────────────────────────────┬──────────────┬──────┬──────────┐
│ # │ 名称           │ 全称                         │ 领域         │ 类型 │ 推荐理由 │
├───┼────────────────┼──────────────────────────────┼──────────────┼──────┼──────────┤
│ 1 │ IEEE S&P       │ IEEE Symposium on Security…  │ ai_security  │ 会议 │ AI 安全  │
│ 2 │ ACM CCS        │ ACM Conference on Computer…  │ ai_security  │ 会议 │ AI 安全  │
│ 3 │ NDSS           │ Network and Distributed…     │ ai_security  │ 会议 │ AI 安全  │
│ 4 │ USENIX Security│ USENIX Security Symposium    │ ai_security  │ 会议 │ AI 安全  │
│ 5 │ ICRA           │ IEEE International Conf…     │ robotics     │ 会议 │ 机器人学 │
└───┴────────────────┴──────────────────────────────┴──────────────┴──────┴──────────┘
```

**Step 3: 确认或调整**

```
你可以：✅ 确认 / 🔄 换推荐 / ➕ 添加会议 / 🔍 调整时间范围
选择操作 [确认]:
```

- **确认** — 使用推荐会议开始搜索
- **换推荐** — 重新生成推荐
- **添加会议** — 手动添加指定会议名称
- **调整时间** — 修改年份范围（默认近 3 年）

**Step 4: 分批次执行搜索**

```
正在执行搜索...
  批次 1/3: 精确匹配：adversarial robustness in robot RL
    找到 6 篇候选
  批次 2/3: 同义词扩展：adversarial attack, robustness, adversarial example
    找到 5 篇候选
  批次 3/3: 宽泛搜索：IEEE S&P, ACM CCS, NDSS
    找到 4 篇候选
```

每批针对不同关键词组合，提高召回率。

**Step 5: Anti-Hallucination 自检**

```
执行 Anti-Hallucination 检查...
  ⚠ Some Paper Title... [待验证]
```

对每篇论文执行 8 点检查，未通过的标记 `[待验证]`。

**Step 6: 结果展示**

```
┌───┬──────────────────────────┬────────────────┬──────────┬──────┬────────┬──────────┬──────┐
│ # │ 标题                     │ 作者           │ 出处     │ 年份 │ 相关度 │ 推荐理由 │ 验证 │
├───┼──────────────────────────┼────────────────┼──────────┼──────┼────────┼──────────┼──────┤
│ 1 │ Adversarial Attacks on…  │ Smith et al.   │ ICRA     │ 2024 │ ★★★★☆  │ 标题匹配 │  ✓   │
│ 2 │ Robust RL via Domain…    │ Jones et al.   │ CoRL     │ 2023 │ ★★★☆☆  │ 领域相关 │  ✓   │
│ … │ …                        │ …              │ …        │ …    │ …      │ …        │ …    │
└───┴──────────────────────────┴────────────────┴──────────┴──────┴────────┴──────────┴──────┘
```

**Step 7: 后续操作**

```
操作选项：✅ 确认结果 / 🔄 换一批 / ➕ 深入某篇 / 💾 保存 / 🚫 退出
```

- **深入某篇** — 查看完整摘要和验证详情，可选择切换到 `/read` 模式
- **保存** — 导出为 `search_results.json`
- **换一批** — 调整关键词或会议重新搜索

### 命令行快捷方式

```bash
# 跳过交互，直接检索
python -m paper_agent.main search -q "diffusion policy for manipulation" -y 2023-2025 -a
```

### 搜索结果自动导出

确认结果后，可通过 `💾 保存` 导出 JSON。也可在代码中调用：

```python
from paper_agent.utils.markdown_exporter import export_search_results
export_search_results(results, output_dir="./my_results")
```

---

## 精读模式 /read

### 漏斗式三层阅读

```
Level 1 (30s)  扫描  →  标题 + Abstract + 一句总结
    ↓ 相关性够？继续
Level 2 (3-5min) 速读  →  贡献 + 方法亮点 + 实验结果
    ↓ 值得深入？
Level 3 (15-30min) 精读  →  完整方法 + 公式 + 批判性分析 → 导出 .md
```

### 交互示例

```bash
$ python -m paper_agent.main read
```

**输入论文信息：**

```
论文标题: Adversarial Attacks on Policy Gradients
作者（逗号分隔）: Smith A, Jones B, Lee C
出处（会议/期刊）: ICRA 2025
年份: 2025
链接（URL）: https://arxiv.org/abs/2501.00001
Abstract（可粘贴，回车结束）: We investigate the vulnerability of...
关键词（逗号分隔）: adversarial, RL, policy gradient
```

**你的研究方向（可选）**: adversarial robustness in robot learning

---

**Level 1 — 扫描 (~30s)**

```
╭────────────────── Level 1 — 扫描结果 ──────────────────╮
│ 一句话总结: 该论文研究了策略梯度方法对对抗攻击的脆弱性，    │
│            提出了一种基于梯度掩码的防御机制                │
│ 相关性评分: ★★★★☆ (4/5)                                  │
│ 建议: 继续阅读 →                                          │
│ 标题和摘要与用户研究方向高度匹配，建议深入                  │
╰──────────────────────────────────────────────────────────╯

进入 Level 2 速读？ [是/否/stop]:
```

输入 `stop` 可随时停止。若相关度低于 3 分，系统会自动建议停止。

---

**Level 2 — 速读 (~3-5min)**

```
╭─────────────────── Level 2 — 速读结果 ───────────────────╮
│ 核心贡献:                                                  │
│   • 首次系统分析 PPO/SAC 在连续控制任务中的对抗脆弱面       │
│   • 提出 Gradient Masking Defense (GMD) 方法               │
│   • 在 5 个 MuJoCo 环境和 2 个真实机器人任务上验证          │
│                                                           │
│ 方法亮点: 与传统对抗训练不同，GMD 不修改奖励函数，           │
│          而是直接在梯度回传时对敏感维度进行掩码              │
│                                                           │
│ Threat Model: 白盒攻击，攻击者可观测完整状态和动作；         │
│               扰动预算 ε=0.1（L∞范数）                      │
│                                                           │
│ 关键实验结果: 在 Ant-v4 上 GMD 将攻击成功率从 87% 降至 12%； │
│             比对抗训练高 15% 的干净性能保持率                │
│                                                           │
│ 匹配点: 你关注对抗鲁棒性，该方法的干净性能保持与你的          │
│        研究方向高度相关                                     │
╰──────────────────────────────────────────────────────────╯

进入 Level 3 精读？ [是/否/stop]:
```

---

**Level 3 — 精读 (~15-30min)**

```
═══ Level 3: 精读 (Deep Reading, ~15-30min) ═══

如有全文可粘贴（可选，回车跳过）:
[可在此粘贴论文全文，或回车使用已有摘要进行深度分析]

深度分析中...
```

精读完成后展示批判性分析摘要：

```
╭─────────────────── Level 3 — 精读完成 ───────────────────╮
│ 问题定义: 在连续控制任务中，现有对抗防御方法面临...         │
│                                                           │
│ 优点:                                                      │
│   ✓ 首次在真实机器人上验证对抗防御                          │
│   ✓ 理论分析完备，给出了鲁棒性下界                          │
│                                                           │
│ 局限:                                                      │
│   ✗ 仅验证 L∞ 攻击，对 L2/L1 攻击的泛化未知                │
│   ✗ 假设全观测环境，部分可观测场景未涉及                     │
│                                                           │
│ 可改进方向:                                                 │
│   → 扩展到多智能体场景                                      │
│   → 结合不确定性量化，提升 OOD 检测能力                      │
╰──────────────────────────────────────────────────────────╯

导出 Markdown 精读笔记？ [Y/n]:
```

### 导出的 Markdown 笔记

保存路径：`./reading_notes/20260524_Adversarial_Attacks_on_Policy_Gradients.md`

包含完整模板：
- 元信息、一句话总结、核心贡献、方法精要（含公式表格）、实验与结果、批判性思考、待跟进清单

### 命令行快捷方式

```bash
# 一次传入所有信息
python -m paper_agent.main read \
  -t "Paper Title" \
  -a "Author1, Author2" \
  -v "ICRA 2025" \
  -y 2025 \
  -u "https://arxiv.org/abs/..." \
  --abstract "This paper proposes..." \
  -k "keyword1, keyword2"
```

### 从检索直接跳转精读

在 `/search` 结果中选择「深入某篇」→ 确认「切换到 /read 模式」即可无缝跳转。

---

## 配置与调优

### 修改会议白名单

编辑 `config/venues.yaml`，按格式增删会议/期刊。字段说明：

```yaml
- name: ICRA                           # 缩写（用于搜索过滤）
  full_name: IEEE International Conf…  # 全称（用于推荐展示）
  domain: robotics                     # 领域分类
```

### 偏好学习

`config/user_profile.json` 自动记录：
- 每次查询的关键词和采纳/拒绝的论文
- 偏好会议和关键词
- 交互次数

下次检索时，系统会显示已学习的偏好会议。

### API 配置

所有 API 调用使用 `openai` 库的 OpenAI 兼容接口，因此：

- Kimi API: 通过 `KIMI_API_KEY` + `KIMI_BASE_URL` 配置
- DeepSeek API: 通过 `DEEPSEEK_API_KEY` + `DEEPSEEK_BASE_URL` 配置
- 可替换为任意 OpenAI 兼容的 API 端点（如本地 vLLM）

---

## 常见问题

**Q: 搜索返回空结果？**
A: 检查 `KIMI_API_KEY` 是否设置。尝试放宽关键词或年份范围。

**Q: 精读分析失败？**
A: 检查 `DEEPSEEK_API_KEY` 是否设置。网络问题可能导致超时，可重试。

**Q: 如何添加自定义会议？**
A: 编辑 `config/venues.yaml`，在对应领域下添加条目即可。重启后生效。

**Q: 反幻觉检查过于严格？**
A: `validator.py` 中的检查是启发式的，标记 `[待验证]` 仅提醒人工确认，不影响使用。

**Q: 能否离线使用？**
A: 搜索需要 Kimi API（需联网），精读需要 DeepSeek API。可替换为本地模型。
