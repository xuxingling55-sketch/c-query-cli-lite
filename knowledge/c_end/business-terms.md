# C端 query_cli 业务术语

本文件是业务同事和 Agent 查询口径前的术语入口。详细计算方式与表来源见 `glossary/【C端取数】_query_cli.md`。

## 核心对象

| 术语 | 含义 | 主要表 |
|---|---|---|
| 注册用户 | 在指定日期范围内完成注册的 C 端用户 | `aws.user_increase_new_add_day` |
| 注册渠道 | 注册用户对应的一级、二级、三级渠道标签 | `aws.user_increase_channel_label_day` |
| C端活跃用户 | C 端/私域口径下的活跃用户 | `aws.business_active_user_last_14_day` |
| 订单用户 | 在订单表中产生订单行为的用户 | `dws.topic_order_detail` |
| 子订单 | `dws.topic_order_detail` 的明细粒度，一笔主订单可对应多条子订单 | `dws.topic_order_detail` |

## 核心指标

| 术语 | 标准口径 | 注意事项 |
|---|---|---|
| 注册用户数 | `COUNT(DISTINCT u_user)` | 必须限定 `day` 时间范围 |
| 注册用户 LTV | `pay_amount / install_users` | 默认按注册转化月维度口径计算，`pay_amount` 来自注册月内付费金额，`install_users` 为注册用户数 |
| 活跃用户数 | 基于 `aws.business_active_user_last_14_day`，按 `user_sk + 月份` 去重 | 该表就是 C 端活跃表；一用户一天可能多行，月趋势必须先做用户月去重 |
| 活跃用户转化率 | `pay_user_cnt / active_user_cnt` | 付费用户必须去重，不能直接累加标记字段 |
| 客单价 | `pay_amount / pay_user_cnt` | 按付费人数计算，不按订单数计算 |
| 订单量 | `COUNT(DISTINCT order_id)` | 不能使用 `COUNT(*)` 代表订单量 |
| GMV / 营收 | `SUM(sub_amount)` | 默认订单表 `dws.topic_order_detail`，需筛选 `original_amount >= 39`、`business_gmv_attribution IN ('电销','商业化')` |
| 正价订单 | 满足场景 SQL 中正价条件的订单 | 常见条件为 `original_amount >= 39` |

## 关键维度

| 术语 | 含义 | 常见字段 |
|---|---|---|
| 注册日期 | 用户完成注册的日期 | `day`、`regist_day` |
| 订单日期 | 订单支付日期 | `paid_time_sk` |
| 端口 | 用户注册或活跃来源端 | `u_from`、`os`、`client_os` |
| 渠道一级标签 | 注册渠道一级分类 | `regist_channel_label1` |
| 渠道二级标签 | 注册渠道二级分类 | `regist_channel_label2` |
| 业务 GMV 归属 | 订单 GMV 业务归属 | `business_gmv_attribution` |
| 商品 2.0 类目 | 商品类目体系 | `good_kind_name_level_1`、`good_kind_name_level_2` |
| 策略组商品类目 | 策略组口径商品类目 | `business_good_kind_name_level_1` |

## 易混淆术语

| 易混点 | 正确理解 |
|---|---|
| C端活跃 vs 全公司活跃 | `aws.business_active_user_last_14_day` 只代表 C 端/私域活跃，不代表全公司活跃 |
| C端活跃 ARPU | 使用 `aws.business_active_user_last_14_day.amount / 月活用户数`，不需要 JOIN 订单表 |
| 活跃主表 vs 活跃行为辅助表 | `aws.business_active_user_last_14_day` 是 C 端活跃主表；`dws.topic_user_active_detail_day` 只能 `LEFT JOIN` 补充行为/设备/渠道字段 |
| 用户标签字段 | 牵涉用户标签时只用带 `business_` 前缀字段；统计维度用 `business_user_pay_status_statistics_month`，业务维度用 `business_user_pay_status_business_month` |
| 订单量 vs 子订单行数 | 订单量必须按 `order_id` 去重，子订单行数不能直接当订单量 |
| 商品 2.0 类目 vs 策略组商品类目 | 两套类目字段不能混用，输出时必须明确字段名 |
| LTV 金额 vs GMV | LTV 通常看注册 cohort 的到账金额，GMV 按订单或商品归属汇总 |
| 注册用户 LTV vs 注册转化月维度 | 用户问“新增注册用户 LTV”时，默认走注册转化月维度口径，输出 `pay_amount / install_users`，而不是只输出订单金额汇总 |
| 支付成功 vs 退款成功 | 不同场景包含的订单状态不同，必须以场景 SQL 和口径说明为准 |

## 业务纠偏沉淀

- 如果业务方在取数过程中纠正口径，必须把纠正后的稳定规则沉淀到 `business-terms.md` 或 `glossary.md`。
- 本次纠偏：`注册用户 LTV = pay_amount / install_users`。
- 本次回复方式纠偏：用户只问单个核心指标时，只返回核心数值和极短口径，不默认展开 SQL、结果目录、文件清单或完整字段解释。
- 本次活跃口径纠偏：
  - `aws.business_active_user_last_14_day` 是 C 端活跃主表。
  - C 端活跃 ARPU 使用 `aws.business_active_user_last_14_day.amount`。
  - 统计月活时按 `user_sk + active_month` 去重。
  - 牵涉用户标签、统计分层、业务分层时，只用带 `business_` 前缀的字段。
  - `user_pay_status_statistics_month` 标记为知识库不引用，默认不得使用。
  - `dws.topic_user_active_detail_day` 只能作为辅助明细表，在主活跃口径结果上 `LEFT JOIN` 补字段；不得作为活跃人数、ARPU、转化率分母的主表。
- 本次订单表纠偏：涉及订单明细、订单聚合、注册用户付费金额时，默认使用 `dws.topic_order_detail`，不要默认使用 `dw.fact_order_detail`。
- 本次营收口径纠偏：
  - 营收金额使用 `dws.topic_order_detail.sub_amount`。
  - 必加筛选：`u_user IS NOT NULL`、`original_amount >= 39`、`business_gmv_attribution IN ('电销','商业化')`。
  - 订单数使用 `COUNT(DISTINCT order_id)`。
- 本次客单价口径纠偏：客单价 = 金额 / 付费人数，即 `pay_amount / pay_user_cnt`，不是金额 / 订单数。
- 用户问“4月份新增注册用户的 LTV”这类问题时，应先确认年份，再使用注册转化月维度口径：
  - `install_users`：注册月内新增注册用户数。
  - `pay_user_num`：注册月内有付费的注册用户数。
  - `pay_amount`：注册月内付费金额。
  - `ltv`：`pay_amount / install_users`。
  - 可同时输出 `FULL_MONTH`、`MTD`、`MIX` 以及去年同期 `ly_*` 字段。

## Agent 使用要求

当用户提到上述术语时，Agent 应先映射到对应场景，再用 `c-query-cli ask "<用户问题>" --dry-run` 生成 DSL 和 SQL。如果用户没有提供时间范围，必须先反问。
