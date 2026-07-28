# 活动复盘 Skill 包（内含 C 端轻量取数工具）

这个包有两层能力：

1. **活动复盘 skill**（给 AI 用）：从"活动结束"到"一份能对外同步的飞书复盘文档"的完整工作流，含取数、目标达成评估、归因、定性证据闭环、成文。
2. **C 端轻量取数工具**（skill 的底层引擎）：用 AI + `knowledge/` 口径库生成 SQL，再用 CLI 执行并导出 Excel。也可以脱离复盘场景单独当取数工具用。

## 复盘 skill 是什么

skill 位于 `.agents/skills/` 目录（**隐藏目录**，访达按 `Cmd+Shift+.` 或终端 `ls -a` 可见），支持 Agent Skills 的 AI 工具（Cursor、Claude Code 等）打开本文件夹后会自动发现，无需手动安装。三个 skill 配合工作：

| Skill | 作用 |
|---|---|
| `campaign-review` | 复盘总流程：反问目标与材料 → 取数 → 目标评估 → 归因 → 定性闭环 → 产出本地工作稿和飞书正式文档（含口径文档、汇总表加工规则） |
| `review-data-pack` | 一次取齐 8 个复盘数据模块（总盘/活跃转化/用户分层/商品结构/定金/蓄水/高净值/销售漏斗），写入飞书表格 |
| `report-polish` | 报告可读性打磨；直接编辑飞书文档的方法和已知坑 |

## 复盘快速开始

一次性准备（约 10 分钟）：

```bash
python3 -m pip install -r requirements.txt
cp config.example.json config.json   # 填入自己的 StarRocks 账号密码
```

配置里只有数仓账号是必填的；`llm` 字段**不用填**（那是网页共享版专用的，见文末说明——走 skill 复盘时写 SQL 的就是你的 AI 本身），删掉或保留占位都行。

如需产出飞书正式文档，还要安装 `lark-cli` 并完成飞书授权（能建文档、写电子表格）。

然后用支持 Agent Skills 的 AI 工具打开本文件夹，对 AI 说：

```text
用 campaign-review skill 复盘「XX活动」
```

AI 会把缺失信息整理成一份清单一次问齐：活动期、GMV/服务期/分渠道目标、报告读者、复盘会议纪要或专项复盘链接、飞书文档建在工作号还是个人号。照清单回答即可。

产出物：

- 本地工作稿：`reports/YYYYMMDD_<活动名>_复盘.md`
- 飞书正式复盘文档（按团队复盘模板：营收完成卡、关键信息 callout、闭环表、加工后的汇总数据表）+ 配套口径文档
- 复盘数据包：飞书表格 + `outputs/review_pack/` 本地快照

---

# 底层：C 端轻量取数工具

用 AI + `knowledge/` 生成 SQL，再用 CLI 执行 SQL 并导出 Excel。当前覆盖 C 端注册、渠道、活跃、订单、LTV、GMV、转化等取数问题。

## 目录结构

```text
c-query-cli-lite/
├── README.md
├── config.example.json
├── config.json                 # 本地配置，不提交
├── requirements.txt
├── .agents/skills/             # 复盘相关 skill（隐藏目录）
│   ├── campaign-review/
│   ├── review-data-pack/
│   └── report-polish/
├── knowledge/                  # 口径知识库（AI 生成 SQL 的依据）
│   ├── AI提示词.md
│   ├── _index.md
│   ├── 公共/
│   └── c_end/
├── queries/
│   └── review_pack/            # 复盘数据包 8 个模块的 SQL
├── scripts/
│   └── review_data_pack.py     # 复盘数据包入口脚本
├── src/
│   ├── cli.py
│   ├── executor.py
│   ├── knowledge.py
│   └── review_pack/            # 数据包运行时
└── reports/                    # 复盘工作稿产出目录
```

## 第一步：安装依赖

```bash
python3 -m pip install -r requirements.txt
```

## 第二步：配置数据库账号

```bash
cp config.example.json config.json
```

打开 `config.json`，填入自己的 StarRocks 账号密码。SparkSQL 是备用引擎，可按需要填写。`llm` 字段仅网页共享版需要，用 AI 工具（Cursor 等）时不用填。

## 第三步：让 AI 生成 SQL

每次新对话都建议加载：

| 文件 | 作用 |
|---|---|
| `knowledge/AI提示词.md` | AI 工作规则 |
| `knowledge/公共/glossary.md` | 通用 SQL 规则 |
| `knowledge/c_end/business-terms.md` | C 端业务术语 |
| `knowledge/c_end/glossary.md` | C 端业务知识字典 |

如果 AI 需要字段定义，再加载 `knowledge/c_end/ddl/` 下对应 DDL。

示例问题：

```text
帮我查 2024年1月 注册用户的 LTV
看一下 2024年1月 C端活跃用户转化
查 2024年1月 各渠道订单转化
```

AI 需要先确认需求，再生成 SQL。把 SQL 保存成 `.sql` 文件。

## 第四步：执行 SQL 导出 Excel

```bash
python src/cli.py run query.sql
```

指定输出名称：

```bash
python src/cli.py run query.sql -o 注册用户LTV
```

强制使用 SparkSQL：

```bash
python src/cli.py run query.sql --engine spark
```

查看历史记录：

```bash
python src/cli.py history
```

查看知识库信息：

```bash
python src/cli.py knowledge
```

执行完成后，产物保存在：

```text
queries/
└── YYYY-MM-DD_HH-MM_输出名称/
    ├── query.sql
    ├── result.xlsx
    └── query.json
```

## 安全规则

- `config.json` 不提交到 Git。
- SQL 只允许 `SELECT` 或 `WITH ... SELECT`。
- SQL 必须包含时间或分区过滤。
- SQL 必须带 `LIMIT`，默认和上限都是 `10000`。
- 订单量必须使用 `COUNT(DISTINCT order_id)`。
- `aws.business_active_user_last_14_day` 只代表 C 端/私域活跃。

## 一键生成活动复盘数据包

不走完整复盘流程、只要数据时，可以直接对 AI 说：生成复盘数据包：暑促，2026/7/1–7/15，目标 1.2 亿。

系统会一次取齐固定指标、检查冲突并返回一份新的飞书表格。详细使用与故障恢复见 [复盘数据包操作说明](docs/review-data-pack-operations.md)。

## 网页共享版

如果想让团队成员通过浏览器一起使用，可以启动共享取数台：

```bash
python src/web_app.py
```

启动后打开：

```text
http://127.0.0.1:5001
```

如果要分享给同一办公网络或 VPN 内的同事，把 `127.0.0.1` 换成启动机器的局域网 IP。分享前需要保持这台机器和网页服务一直开着。同事如果打不开，通常是电脑防火墙、网络隔离或不在同一个办公网络导致的。

网页支持：

- 输入自然语言问题后自动生成查询、执行并导出 Excel。
- 选择自动、StarRocks 或 SparkSQL 执行。
- 查看最近执行记录，并下载历史结果。
- 复用原有安全规则，仍然只允许带时间过滤和 LIMIT 的查询语句。
- 展开查看系统生成的查询语句，方便核对口径。

部署给团队共享时，把服务运行在一台能访问数据源的机器上，并只在服务器本地保存 `config.json`。网页不会展示数据库账号密码。

自然语言取数需要在 `config.json` 里配置 `llm`，用于把问题转换成 SQL。模型服务需要兼容 `/chat/completions` 调用格式。
