# 知识库域索引

每个子目录是一个业务域，包含 `glossary.md`（业务知识字典）和 `ddl/`（表结构）。CLI 加载时始终加载 `公共` + `config.json` 中配置的业务域。

| 域目录 | 内容 | 说明 |
|---|---|---|
| `公共` | 通用 SQL 规则和查询约束 | 始终加载 |
| `c_end` | C 端取数知识 | 注册、渠道、活跃、订单、LTV、GMV、转化 |

## C 端 DDL

| DDL 文件 | 所属域 | 用途 |
|---|---|---|
| `aws.user_increase_new_add_day.sql` | `c_end` | 新增注册用户 |
| `aws.user_increase_channel_label_day.sql` | `c_end` | 注册渠道标签 |
| `aws.business_active_user_last_14_day.sql` | `c_end` | C 端/私域活跃与付费分层 |
| `dws.topic_order_detail.sql` | `c_end` | 订单、GMV、商品类目 |
| `dws.topic_user_active_detail_day.sql` | `c_end` | C 端活跃日维度 |
| `dw.fact_order_detail.sql` | `c_end` | 订单事实明细 |
