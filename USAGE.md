# PaperAgent 使用指南

## 目录

1. [检索模式 /search](#检索模式-search)
2. [精读模式 /read](#精读模式-read)
3. [配置与调优](#配置与调优)
4. [常见问题](#常见问题)

---

## 检索模式 /search

### 基本流程（8 步）

```
用户输入查询（支持中文）
  → 1. 查询分析（翻译 + 概念提取 + 同义词扩展）
  → 2. AI 推荐会议/期刊
  → 3. 构建 3 层搜索策略
  → 4. 浏览器执行 arXiv 搜索
  → 5. 去重 + 多维度排序
  → 6. AI 自评结果质量 + 多样性检查
  → 7. 质量不足时自动重试
  → 8. 用户偏好加分 → 输出
```

### 交互示例

**Step 1: 输入查询（支持中文）**

```bash
$ python -m paper_agent.main search
```

```
╭────────────────────────── /search ──────────────────────────╮
│ 学术文献检索模式                                             │
│ 从顶会顶刊中检索论文，返回结构化元数据。                      │
│ 输入 'quit' 退出。                                           │
╰─────────────────────────────────────────────────────────────╯

请输入检索主题/关键词: 机器人抓取中的对抗攻击
```

**Step 2: 查询自动翻译与分析**

系统调用 DeepSeek 自动翻译中文查询并提取学术概念：

```
查询翻译: 机器人抓取中的对抗攻击 → adversarial attacks in robot grasping
提取概念: adversarial attack, robot grasping, manipulation security, policy manipulation
```

**Step 3: AI 推荐会议**

```
┌───┬──────────┬────────────────────────────────┬──────────────┬──────┬──────────────┐
│ # │ 名称     │ 全称                           │ 领域         │ 类型 │ 推荐理由     │
├───┼──────────┼────────────────────────────────┼──────────────┼──────┼──────────────┤
│ 1 │ ICRA     │ IEEE International Conf…       │ robotics     │ 会议 │ 机器人学核心 │
│ 2 │ IROS     │ IEEE/RSJ International Conf…   │ robotics     │ 会议 │ 机器人学核心 │
│ 3 │ IEEE S&P │ IEEE Symposium on Security…    │ ai_security  │ 会议 │ AI 安全顶会  │
│ 4 │ ACM CCS  │ ACM Conference on Computer…    │ ai_security  │ 会议 │ AI 安全顶会  │
│ 5 │ CoRL     │ Conference on Robot Learning   │ robotics     │ 会议 │ 机器人学习   │
└───┴──────────┴────────────────────────────────┴──────────────┴──────┴──────────────┘
```

**Step 4: 确认或调整**

```
你可以：✅ 确认 / 🔄 换推荐 / ➕ 添加会议 / 🔍 调整时间范围
选择操作 [确认]:
```

- **确认** — 使用推荐会议开始搜索
- **换推荐** — 重新生成推荐
- **添加会议** — 手动添加指定会议名称
- **调整时间** — 修改年份范围（默认近 3 年）

**Step 5: 3 层分批次搜索**

```
正在执行搜索...

  Query analysis...
  Query: 机器人抓取中的对抗攻击 → adversarial attacks in robot grasping

  DeepSeek 优化查询...

  批次 1: 精确匹配：(adversarial attack AND robot grasping) AND ("ICRA" OR "IROS")
    找到 5 篇候选
  批次 2: 同义词扩展：(adversarial perturbation OR attack) AND (grasping OR manipulation)
    找到 7 篇候选
  批次 3: 宽泛搜索：adversarial robot manipulation
    找到 4 篇候选
```

3 层策略：
- **Tier 1** — 精确 AND 匹配，并注入 venue 名称过滤
- **Tier 2** — 同义词 OR 扩展，提高召回
- **Tier 3** — 宽泛关键词，兜底

**Step 6: AI 自评结果**

```
  AI 自评中...

╭─────────────────────── AI 自评结果 ───────────────────────╮
│ AI 评估: ★★★★☆ (4/5)                                      │
│ 结果整体质量较好，多数论文与查询高度相关。                   │
│ 1 篇论文来自同一 venue (ICRA)，多样性尚可。                 │
╰──────────────────────────────────────────────────────────╯
```

AI 评估包括：
- 每篇论文 1-5 分相关性评分
- 结果集整体质量评分
- venue/作者多样性检查
- 质量不足时自动建议更宽泛查询并重试

**Step 7: 结果展示**

```
┌───┬──────────────────────────┬────────────────┬──────────┬──────┬────────┬──────────────┬──────┐
│ # │ 标题                     │ 作者           │ 出处     │ 年份 │ 相关度 │ 推荐理由     │ 验证 │
├───┼──────────────────────────┼────────────────┼──────────┼──────┼────────┼──────────────┼──────┤
│ 1 │ Adversarial Attacks on…  │ Smith et al.   │ ICRA     │ 2024 │ ★★★★★  │ 标题高度匹配 │  ✓   │
│ 2 │ Robust Grasping via…     │ Jones et al.   │ IROS     │ 2024 │ ★★★★☆  │ 顶会/ICRA    │  ✓   │
│ … │ …                        │ …              │ …        │ …    │ …      │ …            │ …    │
└───┴──────────────────────────┴────────────────┴──────────┴──────┴────────┴──────────────┴──────┘
```

相关度评分经过 AI 评估覆盖（keyword-based → AI-adjusted），推荐理由由 AI 生成中文说明。

**Step 8: 后续操作**

```
操作选项：✅ 确认结果 / 🔄 换一批 / ➕ 深入某篇 / 💾 保存 / 🚫 退出
```

- **深入某篇** — 查看完整摘要和验证详情，可选择切换到 `/read` 模式
- **保存** — 导出为 `search_results.json`
- **确认结果** — 自动学习偏好（记录采纳的 venue 和关键词）

### 中文查询支持

系统自动处理中文学术查询的完整流程：

```
输入: "大模型后门攻击防御"
  → 翻译: "backdoor attack defense in large language models"
  → 提取概念: ["backdoor attack", "LLM security", "model defense", "trojan detection"]
  → 同义词: backdoor→["trojan", "poisoning"], defense→["mitigation", "robustness"]
  → 推荐 venue: IEEE S&P, ACM CCS, NDSS, USENIX Security, NeurIPS
  → 生成 3 层 arXiv 搜索查询
```

### 命令行快捷方式

```bash
# 跳过交互，直接检索
python -m paper_agent.main search -q "diffusion policy for manipulation" -y 2023-2025 -a

# 中文查询
python -m paper_agent.main search -q "自动驾驶中的对抗样本" -y 2022-2025
```

### 搜索结果导出

```python
from paper_agent.utils.markdown_exporter import export_search_results
export_search_results(results, output_dir="./my_results")
```

### 偏好学习

每次确认搜索结果后，系统自动记录：
- 采纳的论文 venue 和关键词
- 下次搜索时自动给匹配的论文加分

查看已学习的偏好：
```bash
cat config/user_profile.json
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

保存路径：`./reading_notes/20260525_Adversarial_Attacks_on_Policy_Gradients.md`

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

下次检索时，系统会自动给匹配偏好 venue/keyword 的论文加分。

### 评估缓存

`config/eval_cache/` 目录存储 AI 评估结果（30 天有效期），相同查询直接复用缓存，节省 API 费用。可安全删除该目录清理缓存。

### API 配置

所有 API 调用使用 `openai` 库的 OpenAI 兼容接口，因此：

- DeepSeek API: 通过 `DEEPSEEK_API_KEY` + `DEEPSEEK_BASE_URL` 配置
- 可替换为任意 OpenAI 兼容的 API 端点（如本地 vLLM）

### WebBridge 配置

搜索功能依赖 WebBridge（本地浏览器自动化）：
- 默认地址：`http://127.0.0.1:10086/command`
- 确保 WebBridge daemon 在搜索前已启动

---

## 常见问题

**Q: 搜索返回空结果？**
A: 
1. 检查 `DEEPSEEK_API_KEY` 是否设置
2. 检查 WebBridge daemon 是否在运行
3. 系统会自动用 AI 生成更宽泛的查询重试

**Q: 中文查询搜不到相关论文？**
A: 系统已内置中文→英文学术翻译。如结果仍不理想，尝试在查询中加入英文关键词。

**Q: 精读分析失败？**
A: 检查 `DEEPSEEK_API_KEY` 是否设置。网络问题可能导致超时，可重试。

**Q: 如何添加自定义会议？**
A: 编辑 `config/venues.yaml`，在对应领域下添加条目即可。AI venue 推荐会自动匹配新条目。

**Q: 反幻觉检查过于严格？**
A: `validator.py` 中的检查是启发式的，标记 `[待验证]` 仅提醒人工确认，不影响使用。

**Q: 如何减少 API 调用费用？**
A: 
- 评估缓存自动生效（相同查询 30 天内复用）
- 偏好学习可减少重复搜索
- 使用 `--auto` 参数跳过交互环节
