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

## 已沉淀纠偏

| 主题 | 纠偏后口径 | 沉淀位置 |
|---|---|---|
| 注册用户 LTV | `LTV = pay_amount / install_users`，默认使用注册转化月维度口径 | `knowledge/c_end/glossary.md`、`knowledge/c_end/business-terms.md` |
| 单指标回复 | 只返回核心数值和极短口径，不默认展开 SQL 或结果目录 | `knowledge/AI提示词.md`、`knowledge/c_end/business-terms.md` |
| C 端活跃月趋势 | 使用 `aws.business_active_user_last_14_day`，按 `user_sk + 月份` 去重；用户标签只用 `business_` 前缀字段 | `knowledge/c_end/glossary.md`、`knowledge/c_end/business-terms.md`、`knowledge/AI提示词.md` |
| C 端活跃 ARPU | 使用 `aws.business_active_user_last_14_day.amount / 月活用户数` | `knowledge/c_end/glossary.md`、`knowledge/AI提示词.md` |
| 订单表默认选择 | 订单明细、订单聚合、注册付费金额默认使用 `dws.topic_order_detail` | `knowledge/c_end/glossary.md`、`knowledge/c_end/business-terms.md` |
| 营收金额 | 使用 `dws.topic_order_detail.sub_amount`，筛选 `original_amount >= 39`、`business_gmv_attribution IN ('电销','商业化')` | `knowledge/c_end/glossary.md`、`knowledge/AI提示词.md` |
| 客单价 | `pay_amount / pay_user_cnt`，不是金额 / 订单数 | `knowledge/c_end/glossary.md`、`knowledge/c_end/business-terms.md` |
