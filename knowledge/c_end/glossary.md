# C端取数业务知识字典

## 注册用户数

- **定义**：指定时间范围内完成注册的 C 端用户数。
- **计算方式**：`COUNT(DISTINCT u_user)`
- **表来源**：`aws.user_increase_new_add_day`
- **筛选条件**：`day BETWEEN ${start_day} AND ${end_day}`，`u_from IN ('android', 'ios', 'harmony')`，`user_sk > 0`

## 注册渠道标签

- **定义**：注册用户对应的一级、二级、三级渠道标签。
- **计算方式**：按 `u_user` 与 `day` 关联注册表和渠道标签表。
- **表来源**：`aws.user_increase_new_add_day`、`aws.user_increase_channel_label_day`
- **注意**：渠道标签取数必须保留注册日期条件，避免跨日标签错配。

## 注册用户 LTV

- **定义**：注册 cohort 在注册月内产生的付费金额相对注册用户数的人均价值。
- **标准计算方式**：`pay_amount / install_users`
- **字段口径**：
  | 字段 | 定义 | 推荐 SQL 表达式 |
  |---|---|---|
  | `install_users` | 注册月内新增注册用户数 | `COUNT(DISTINCT u_user)` |
  | `pay_user_num` | 注册月内有付费的注册用户数 | `SUM(is_pay)` 或 `COUNT(DISTINCT CASE WHEN pay_amount > 0 THEN u_user END)` |
  | `pay_amount` | 注册月内营收金额 | `SUM(sub_amount)` |
  | `ltv` | 注册用户 LTV | `pay_amount / NULLIF(install_users, 0)` |
- **表来源**：`aws.user_increase_new_add_day`、`aws.user_increase_channel_label_day`、`dws.topic_order_detail`
- **筛选条件**：
  - 注册用户：`a.u_from IN ('android', 'ios', 'harmony')`，`a.user_sk > 0`
  - 订单：`u_user IS NOT NULL`、`original_amount >= 39`、`business_gmv_attribution IN ('电销','商业化')`
  - 付费月：`DATE_TRUNC('month', paid_time_sk 日期) = 注册月`
- **默认输出结构**：注册月、端口、注册渠道一级、注册渠道二级、`install_users`、`pay_user_num`、`pay_amount`、`ltv`。
- **月度报表扩展**：如用户要求或使用月维度转化报表，应同时输出 `FULL_MONTH`、`MTD`、`MIX` 和去年同期 `ly_*` 字段。
- **注意**：用户问“新增注册用户的 LTV”时，默认使用本口径，不要简化为 `SUM(arrival_amount) / COUNT(DISTINCT regist_user)` 的单窗口明细口径。

## 注册转化月维度

- **定义**：按注册月、端口、注册渠道统计注册用户、注册月付费、注册月付费金额、次月留存，并支持去年同期对比。
- **核心指标**：
  | 指标 | 定义 |
  |---|---|
  | `install_users` | 注册月内新增注册用户数 |
  | `pay_user_num` | 注册月内有付费的注册用户数 |
  | `pay_amount` | 注册月内付费金额 |
  | `ltv` | `pay_amount / install_users` |
  | `retention_users` | 注册次月在 `aws.business_active_user_last_14_day` 出现的活跃用户数 |
  | `ly_*` | 去年同期同维度指标 |
- **表来源**：`aws.user_increase_new_add_day`、`aws.user_increase_channel_label_day`、`dws.topic_order_detail`、`aws.business_active_user_last_14_day`
- **输出类型**：
  - `FULL_MONTH`：整月口径。
  - `MTD`：按当前日期的前一日 day-of-month 截断。
  - `MIX`：当前月取 `MTD`，历史月取 `FULL_MONTH`。
- **SQL 骨架要点**：
  - 基础注册层从 `aws.user_increase_new_add_day` 取用户、端口和注册日期。
  - 订单层从 `dws.topic_order_detail` 按 `u_user + pay_month` 聚合 `SUM(sub_amount)`。
  - 订单层营收筛选固定包含：`u_user IS NOT NULL`、`original_amount >= 39`、`business_gmv_attribution IN ('电销','商业化')`。
  - 注册层与订单层按 `u_user` 和 `reg_month = pay_month` 关联。
  - 留存层按 `act.active_month = ADD_MONTHS(reg_month, 1)` 关联。
  - 月聚合层建议一次性聚合 full 与 mtd 指标，降低重复扫描。

## C端活跃用户数

- **定义**：C 端/私域口径下的活跃用户数。
- **标准表来源**：`aws.business_active_user_last_14_day`
- **计算方式**：
  - 总量：按 `user_sk + stat_month` 去重后统计人数。
  - SQL 推荐写法：先按 `user_sk, DATE_TRUNC('month', day日期)` 生成一人一月一行，再 `COUNT(*)`。
- **表来源**：`aws.business_active_user_last_14_day`
- **注意**：该表只包含 C 端/私域活跃，不代表全公司活跃。
- **去重原因**：该表一用户一天可能因 `team_ids`、`team_names`、`business_gmv_attribution` 等订单/归属标签出现多行；按月统计时必须先做用户月去重。
- **用户标签字段规则**：
  - 牵涉到用户标签、付费分层、统计分层时，只使用带 `business_` 前缀的字段。
  - 统计维度使用 `business_user_pay_status_statistics_month`，不要使用 `user_pay_status_statistics_month`。
  - 业务维度使用 `business_user_pay_status_business_month`。
  - `user_pay_status_statistics_month` 在 DDL 中标为“知识库不引用”，不要用于取数。

## C端活跃用户月报

- **定义**：按月份统计 C 端活跃用户规模，并可拆业务分层、统计分层、GMV 归属等标签。
- **标准表来源**：`aws.business_active_user_last_14_day`
- **月活总量口径**：
  ```sql
  WITH user_monthly_base AS (
      SELECT
          user_sk,
          DATE_TRUNC('month', STR_TO_DATE(CAST(day AS STRING), '%Y%m%d')) AS active_month,
          ROW_NUMBER() OVER (
              PARTITION BY user_sk, DATE_TRUNC('month', STR_TO_DATE(CAST(day AS STRING), '%Y%m%d'))
              ORDER BY day ASC
          ) AS rn
      FROM aws.business_active_user_last_14_day
      WHERE day BETWEEN ${start_day} AND ${end_day}
        AND user_sk IS NOT NULL
  )
  SELECT active_month, COUNT(*) AS active_cnt
  FROM user_monthly_base
  WHERE rn = 1
  GROUP BY active_month
  ```
- **分层口径**：
  - 如果要拆分用户标签，应在 `rn = 1` 的用户月记录上取标签。
  - 业务分层：`business_user_pay_status_business_month`
  - 统计分层：`business_user_pay_status_statistics_month`
  - 禁止使用无 `business_` 前缀的用户标签字段做知识库默认口径。

## C端活跃 ARPU

- **定义**：C 端活跃用户人均营收。
- **计算方式**：`SUM(amount) / active_cnt`
- **表来源**：`aws.business_active_user_last_14_day`
- **口径说明**：
  - 分子：`aws.business_active_user_last_14_day.amount`。
  - 分母：同月 C 端活跃用户数，按 `user_sk + active_month` 去重。
  - 不需要再 JOIN 订单表；活跃 ARPU 直接使用活跃主表中的 `amount` 字段。

## 订单明细默认表

- **默认订单表**：`dws.topic_order_detail`
- **适用场景**：注册用户付费金额、订单用户、GMV、商品类目、订单明细、付费转化。
- **营收标准口径**：
  ```sql
  SELECT
      STR_TO_DATE(CAST(paid_time_sk AS STRING), '%Y%m%d') AS stat_date,
      u_user,
      COUNT(DISTINCT order_id) AS user_order_cnt,
      SUM(sub_amount) AS user_amount
  FROM dws.topic_order_detail
  WHERE u_user IS NOT NULL
    AND original_amount >= 39
    AND business_gmv_attribution IN ('电销','商业化')
  ```
- **注意**：
  - `dws.topic_order_detail` 是子订单粒度，订单量必须 `COUNT(DISTINCT order_id)`。
  - 默认营收金额使用 `sub_amount`。
  - 默认营收筛选必须包含 `original_amount >= 39` 与 `business_gmv_attribution IN ('电销','商业化')`。
  - `dw.fact_order_detail` 是底层事实表，不作为知识库默认订单表。

## 活跃用户转化

- **定义**：活跃用户中产生订单或支付行为的用户占比。
- **计算方式**：`pay_user_cnt / active_user_cnt`
- **表来源**：`aws.business_active_user_last_14_day`
- **注意**：付费人数用用户字段去重，不能直接对标记字段求和。

## 客单价

- **定义**：付费用户人均营收金额。
- **计算方式**：`pay_amount / pay_user_cnt`
- **表来源**：`dws.topic_order_detail`
- **筛选条件**：`u_user IS NOT NULL`、`original_amount >= 39`、`business_gmv_attribution IN ('电销','商业化')`
- **注意**：这里的客单价按付费人数计算，不按订单数计算；订单数仍可作为辅助指标输出。

## GMV

- **定义**：指定订单窗口内、归属电销/商业化的正价营收金额汇总。
- **计算方式**：`SUM(sub_amount)`
- **表来源**：`dws.topic_order_detail`
- **筛选条件**：`u_user IS NOT NULL`、`original_amount >= 39`、`business_gmv_attribution IN ('电销','商业化')`。
- **注意**：`dws.topic_order_detail` 是子订单粒度，汇总订单量时必须对 `order_id` 去重。
