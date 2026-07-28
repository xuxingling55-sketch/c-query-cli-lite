# 知识库域索引

每个子目录是一个业务域，包含 `glossary.md`（业务知识字典）、可选 `gold_cases.md`（已确认 SQL 案例）和 `ddl/`（表结构）。CLI 加载时始终加载 `公共` + `config.json` 中配置的业务域。

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
| `dws.topic_user_active_detail_day.sql` | `c_end` | 活跃行为辅助明细；仅用于 `LEFT JOIN` 补字段，不作为 C 端活跃主口径 |

## C 端 Gold Cases

| 文件 | 用途 |
|---|---|
| `knowledge/c_end/gold_cases.md` | 保存已确认的最新看板对齐 SQL 案例，用于排查月报、活跃 ARPU、转化率、客单价等指标差异 |
| `knowledge/c_end/product_knowledge_base.md` | 商品分析可迁移知识库，沉淀组合品、零售商品、续购、家庭包、从小学、蓄水、定金等商品口径和分析模板 |

## 已沉淀纠偏

| 主题 | 纠偏后口径 | 沉淀位置 |
|---|---|---|
| 注册用户 LTV | `LTV = pay_amount / install_users`，默认使用注册转化月维度口径 | `knowledge/c_end/glossary.md`、`knowledge/c_end/business-terms.md` |
| 单指标回复 | 只返回核心数值和极短口径，不默认展开 SQL 或结果目录 | `knowledge/AI提示词.md`、`knowledge/c_end/business-terms.md` |
| C 端活跃月趋势 | 使用 `aws.business_active_user_last_14_day`，按 `user_sk + 月份` 去重；用户标签只用 `business_` 前缀字段 | `knowledge/c_end/glossary.md`、`knowledge/c_end/business-terms.md`、`knowledge/AI提示词.md` |
| C 端活跃 ARPU | 先用 `aws.business_active_user_last_14_day` 圈定同月 C 端活跃用户池，分子默认使用该表 `normal_price_amount`；不要默认用订单表 JOIN 活跃池计算，也不要直接取其他活跃聚合表 | `knowledge/c_end/glossary.md`、`knowledge/AI提示词.md` |
| 月报看板对齐 | 单独看 GMV/营收流水/商品订单营收用订单表；跟活跃相关且以活跃用户为分母的转化率、客单价、ARPU 只用 `aws.business_active_user_last_14_day` | `knowledge/c_end/glossary.md`、`knowledge/AI提示词.md`、`knowledge/c_end/gold_cases.md` |
| 活跃行为辅助表 | `dws.topic_user_active_detail_day` 只能作为 `LEFT JOIN` 辅助补字段，不能作为活跃人数、ARPU、转化率分母主表 | `knowledge/c_end/glossary.md`、`knowledge/AI提示词.md` |
| 活跃金额防放大 | 补 `mid_active_type` 时，金额必须先在 `aws.business_active_user_last_14_day` 按 `u_user + 月` 聚合，再 JOIN 辅助维度；同比 JOIN 需包含业务分层、统计分层和 `mid_active_type` | `knowledge/c_end/glossary.md`、`knowledge/AI提示词.md` |
| 订单表默认选择 | 订单明细、订单聚合、注册付费金额默认使用 `dws.topic_order_detail`；看板 SQL 中的 `dw.fact_order_detail` 按项目口径等价替换为 `dws.topic_order_detail` | `knowledge/c_end/glossary.md`、`knowledge/c_end/business-terms.md`、`knowledge/c_end/gold_cases.md` |
| 营收金额 | 单独看 GMV/营收流水/商品订单营收使用 `dws.topic_order_detail.sub_amount`；活跃相关指标使用 `aws.business_active_user_last_14_day.normal_price_amount` | `knowledge/c_end/glossary.md`、`knowledge/AI提示词.md`、`knowledge/c_end/ddl/dws.topic_order_detail.sql` |
| 新增注册看板 | 只有新增注册、注册用户 LTV、注册转化月维度、月报新增流量模块使用 `dws.topic_order_detail.arrival_amount`，筛 `status IN ('支付成功','退款成功')`；非新增注册场景不得套用该例外 | `knowledge/c_end/glossary.md`、`knowledge/AI提示词.md`、`knowledge/c_end/gold_cases.md` |
| 客单价 | `pay_amount / pay_user_cnt`，不是金额 / 订单数 | `knowledge/c_end/glossary.md`、`knowledge/c_end/business-terms.md` |
| 月度宏观/转化月报 | 同时取目标月、上月、去年同期；以同比为主、环比为辅；核心结论按“总判断 + 关键数据支撑”，章节表格后补经营解释 | `knowledge/c_end/glossary.md`、`knowledge/AI提示词.md` |
| 商品体系2.0与中台策略 | 商品策略类问题优先使用 `business_good_kind_name_level_1/2/3`、`course_timing_kind`、`course_group_kind`、`strategy_type`、`strategy_detail`、`user_strategy_tag_*`、`user_strategy_eligibility_*`；资格转化需先圈资格分母 | `knowledge/c_end/glossary.md`、`knowledge/AI提示词.md`、`knowledge/c_end/ddl/dws.topic_order_detail.sql` |
