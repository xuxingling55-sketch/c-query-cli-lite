# C端轻量取数工具

本项目仿照 `bi-query-cli` 的轻量结构：用 AI + `knowledge/` 生成 SQL，再用 CLI 执行 SQL 并导出 Excel。

## 覆盖范围

当前覆盖 C 端注册、渠道、活跃、订单、LTV、GMV、转化等取数问题。

## 目录结构

```text
c-query-cli-lite/
├── README.md
├── config.example.json
├── config.json                 # 本地配置，不提交
├── requirements.txt
├── knowledge/
│   ├── AI提示词.md
│   ├── _index.md
│   ├── 公共/
│   │   ├── glossary.md
│   │   └── ddl/
│   └── c_end/
│       ├── business-terms.md
│       ├── glossary.md
│       └── ddl/
├── queries/                    # 查询产物目录
└── src/
    ├── cli.py
    ├── executor.py
    └── knowledge.py
```

## 第一步：安装依赖

```bash
cd /Users/hilda/Documents/GitHub/c-query-cli-lite
python3 -m pip install -r requirements.txt
```

## 第二步：配置数据库账号

```bash
cp config.example.json config.json
```

打开 `config.json`，填入自己的 StarRocks 账号密码。SparkSQL 是备用引擎，可按需要填写。

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
