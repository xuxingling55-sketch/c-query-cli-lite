# C端取数业务知识字典

## 术语总览

### 核心对象


| 术语     | 含义                                           | 主要表                                    |
| ------ | -------------------------------------------- | -------------------------------------- |
| 注册用户   | 在指定日期范围内完成注册的 C 端用户                          | `aws.user_increase_new_add_day`        |
| 注册渠道   | 注册用户对应的一级、二级、三级渠道标签                          | `aws.user_increase_channel_label_day`  |
| C端活跃用户 | C 端/私域口径下的活跃用户                               | `aws.business_active_user_last_14_day` |
| 订单用户   | 在订单表中产生订单行为的用户                               | `dws.topic_order_detail`               |
| 子订单    | `dws.topic_order_detail` 的明细粒度，一笔主订单可对应多条子订单 | `dws.topic_order_detail`               |


### 核心指标


| 术语       | 标准口径                                                          | 注意事项                                                                                                         |
| -------- | ------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| 注册用户数    | `COUNT(DISTINCT u_user)`                                      | 必须限定 `day` 时间范围                                                                                              |
| 注册用户 LTV | `pay_amount / install_users`                                  | 默认按注册转化月维度口径计算，`pay_amount` 来自注册月内付费金额，`install_users` 为注册用户数                                                |
| 活跃用户数    | 基于 `aws.business_active_user_last_14_day`，按 `user_sk + 月份` 去重 | 该表就是 C 端活跃表；一用户一天可能多行，月趋势必须先做用户月去重                                                                           |
| 活跃用户转化率  | `pay_user_cnt / active_user_cnt`                              | 付费用户必须去重，不能直接累加标记字段                                                                                          |
| 客单价      | `pay_amount / pay_user_cnt`                                   | 按付费人数计算，不按订单数计算                                                                                              |
| 订单量      | `COUNT(DISTINCT order_id)`                                    | 不能使用 `COUNT(*)` 代表订单量                                                                                        |
| GMV / 营收 | `SUM(sub_amount)`                                             | 默认看正价营收：订单表 `dws.topic_order_detail`，必须筛选 `is_test_user = 0`、`original_amount >= 39`、`business_gmv_attribution IN ('电销','商业化')`；不默认筛 `status = '支付成功'` |
| 正价订单     | 满足场景 SQL 中正价条件的订单                                             | 常见条件为 `original_amount >= 39`                                                                                |


### 关键维度


| 术语        | 含义          | 常见字段                                              |
| --------- | ----------- | ------------------------------------------------- |
| 注册日期      | 用户完成注册的日期   | `day`、`regist_day`                                |
| 订单日期      | 订单支付日期      | `paid_time_sk`                                    |
| 端口        | 用户注册或活跃来源端  | `u_from`、`os`、`client_os`                         |
| 渠道一级标签    | 注册渠道一级分类    | `regist_channel_label1`                           |
| 渠道二级标签    | 注册渠道二级分类    | `regist_channel_label2`                           |
| 业务 GMV 归属 | 订单 GMV 业务归属 | `business_gmv_attribution`                        |
| 商品 2.0 类目 | 商品类目体系      | `good_kind_name_level_1`、`good_kind_name_level_2` |
| 策略组商品类目   | 策略组口径商品类目   | `business_good_kind_name_level_1`                 |


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

  | 字段              | 定义            | 推荐 SQL 表达式                                                                 |
  | --------------- | ------------- | -------------------------------------------------------------------------- |
  | `install_users` | 注册月内新增注册用户数   | 看板对齐按聚合维度 `COUNT(u_user)`；若只问去重用户数才用 `COUNT(DISTINCT u_user)` |
  | `pay_user_num`  | 注册月内有付费的注册用户数 | 看板对齐按宽表粒度 `SUM(is_pay)`，报表层再 `SUM(pay_user_num)`；只有明确要求全局去重用户数时才用 `COUNT(DISTINCT CASE WHEN pay_amount > 0 THEN u_user END)` |
  | `pay_amount`    | 注册月内到账金额      | `SUM(arrival_amount)`                                                      |
  | `ltv`           | 注册用户 LTV      | `pay_amount / NULLIF(install_users, 0)`                                    |

- **表来源**：`aws.user_increase_new_add_day`、`aws.user_increase_channel_label_day`、`dws.topic_order_detail`
- **筛选条件**：
  - 注册用户：`a.u_from IN ('android', 'ios', 'harmony')`，`a.user_sk > 0`
  - 订单：`status IN ('支付成功','退款成功')`；金额用 `arrival_amount`
  - 付费月：`DATE_TRUNC('month', paid_time_sk 日期) = 注册月`
- **默认输出结构**：注册月、端口、注册渠道一级、注册渠道二级、`install_users`、`pay_user_num`、`pay_amount`、`ltv`。
- **月度报表扩展**：如用户要求或使用月维度转化报表，应同时输出 `FULL_MONTH`、`MTD`、`MIX` 和去年同期 `ly_`* 字段。
- **新增客单价**：看板对齐时使用 `SUM(pay_amount) / SUM(pay_user_num)`，其中 `pay_user_num` 来自宽表聚合后的 `SUM(is_pay)`；其中 `is_pay = IF(up.u_user IS NOT NULL, 1, 0)`（只要订单表有匹配记录即算付费，不要求 amount > 0）；不要改成全局 `COUNT(DISTINCT u_user)` 口径。
- **注意**：只有用户问“新增注册用户的 LTV”、注册转化月维度或月报“新增流量”模块时，才使用 `arrival_amount + status IN ('支付成功','退款成功')` 的新增注册看板口径；不要套用商业化营收的 `sub_amount`、正价、归属或订单层测试用户筛选。整体 GMV、整体营收、活跃 ARPU、活跃付费转化、商品结构等非新增注册场景仍按各自口径，不使用本例外。

## 注册转化月维度

- **定义**：按注册月、端口、注册渠道统计注册用户、注册月付费、注册月付费金额、次月留存，并支持去年同期对比。
- **核心指标**：

  | 指标                | 定义                                                    |
  | ----------------- | ----------------------------------------------------- |
  | `install_users`   | 注册月内新增注册用户数                                           |
  | `pay_user_num`    | 注册月内有付费的注册用户数                                         |
  | `pay_amount`      | 注册月内付费金额                                              |
  | `ltv`             | `pay_amount / install_users`                          |
  | `retention_users` | 注册次月在 `aws.business_active_user_last_14_day` 出现的活跃用户数 |
  | `ly_`*            | 去年同期同维度指标                                             |

- **表来源**：`aws.user_increase_new_add_day`、`aws.user_increase_channel_label_day`、`dws.topic_order_detail`、`aws.business_active_user_last_14_day`
- **输出类型**：
  - `FULL_MONTH`：整月口径。
  - `MTD`：按当前日期的前一日 day-of-month 截断。
  - `MIX`：当前月取 `MTD`，历史月取 `FULL_MONTH`。
- **SQL 骨架要点**：
  - 基础注册层从 `aws.user_increase_new_add_day` 取用户、端口和注册日期。
  - 订单层从 `dws.topic_order_detail` 按 `u_user + pay_month` 聚合 `SUM(arrival_amount)`。
  - 订单层筛选固定包含：`status IN ('支付成功','退款成功')`；不要默认加 `is_test_user = 0`、`original_amount >= 39` 或 `business_gmv_attribution IN ('电销','商业化')`。
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
- **辅助表规则**：
  - `dws.topic_user_active_detail_day` 不是 C 端活跃主表。
  - 只有当需要补充学习行为、设备、下载渠道、端口等字段时，才允许在 `aws.business_active_user_last_14_day` 已确定的活跃用户集合上 `LEFT JOIN dws.topic_user_active_detail_day`。
  - 不得使用 `dws.topic_user_active_detail_day` 直接作为活跃人数、ARPU、活跃转化率分母或默认用户分层口径。

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
- **计算方式**：`SUM(normal_price_amount) / C端活跃用户数`
- **表来源**：`aws.business_active_user_last_14_day`
- **口径说明**：
  - 分母：先用 `aws.business_active_user_last_14_day` 圈定同月 C 端活跃用户池，按 `u_user + active_month` 或 `user_sk + active_month` 去重。
  - 分子：只使用同月 `aws.business_active_user_last_14_day.normal_price_amount`；如需对齐商业化归因，按 `business_gmv_attribution IN ('电销','商业化')` 聚合。
  - 跟活跃相关、需要以活跃用户为分母的活跃 ARPU、活跃付费转化率、活跃口径客单价，都不得默认用订单表 `dws.topic_order_detail` JOIN 活跃池计算。
  - 单独看 GMV 营收流水、商品订单营收、订单明细时才使用订单表；不要把订单营收口径混入活跃 ARPU。
- **SQL 骨架**：
  ```sql
  WITH user_month_amount AS (
      SELECT
          DATE_TRUNC('month', STR_TO_DATE(CAST(day AS STRING), '%Y%m%d')) AS active_month,
          u_user,
          SUM(IF(business_gmv_attribution IN ('电销','商业化'), normal_price_amount, 0)) AS amount
      FROM aws.business_active_user_last_14_day
      WHERE u_user IS NOT NULL
        AND day BETWEEN ${start_day} AND ${end_day}
      GROUP BY 1, 2
  )
  SELECT
      active_month,
      SUM(amount) / NULLIF(COUNT(DISTINCT u_user), 0) AS active_arpu
  FROM user_month_amount
  GROUP BY active_month
  ```

## 订单明细默认表

- **默认订单表**：`dws.topic_order_detail`
- **适用场景**：单独看 GMV / 营收流水、商品订单营收、订单用户、商品类目、订单明细、注册用户付费金额。
- **不适用场景**：凡是跟活跃相关、需要以活跃用户为分母或解释活跃商业化效率的指标，例如活跃付费转化率、活跃 ARPU、活跃口径客单价，默认不用订单表直接 JOIN 活跃池计算，只用 `aws.business_active_user_last_14_day` 的金额/转化字段。
- **营收标准口径**：
  ```sql
  SELECT
      STR_TO_DATE(CAST(paid_time_sk AS STRING), '%Y%m%d') AS stat_date,
      u_user,
      COUNT(DISTINCT order_id) AS user_order_cnt,
      SUM(sub_amount) AS user_amount
  FROM dws.topic_order_detail
  WHERE u_user IS NOT NULL
    AND is_test_user = 0
    AND original_amount >= 39
    AND business_gmv_attribution IN ('电销','商业化')
  ```
- **注意**：
  - `dws.topic_order_detail` 是子订单粒度，订单量必须 `COUNT(DISTINCT order_id)`。
  - 默认营收金额使用 `sub_amount`。
  - 对用户说明口径时，必须直接写“**正价营收**（订单侧常用 `original_amount >= 39`；活跃侧常用 `normal_price_amount > 0`）”，不要只抛条件不解释“正价”含义。
  - 默认所有营收类指标均看**正价营收**，必须包含 `original_amount >= 39`；除非用户明确要求“不筛正价”或“全量营收”。
  - 用户即使只说“总营收”，默认也按**正价营收**处理；只有用户明确要求“包含非正价/全量营收”时，才去掉正价筛选并在结果中提示口径变化。
  - 默认营收筛选必须包含 `is_test_user = 0`、`original_amount >= 39` 与 `business_gmv_attribution IN ('电销','商业化')`。
  - 看营收、GMV、ARPU 分子或付费金额时，默认不要筛选 `status = '支付成功'`；只有用户明确要求支付成功、退款、到账或指定订单状态时，才按需求筛选 `status`。
  - `dw.fact_order_detail` 是底层事实表，不作为知识库默认订单表。

## 活跃用户转化

- **定义**：活跃用户中产生订单或支付行为的用户占比。
- **计算方式**：`pay_user_cnt / active_user_cnt`
- **表来源**：`aws.business_active_user_last_14_day`
- **注意**：
  - 月度口径下，“先活跃再付款”统一理解为“当月活跃池 + 当月付款”，不要求支付时间严格晚于某次活跃日期。
  - 看板对齐时，转化人数来自活跃表金额字段：`normal_price_amount > 0` 的活跃用户去重。
  - 不要默认用订单表 `dws.topic_order_detail` JOIN 活跃池后按订单用户数计算活跃转化率；该口径会和 `aws.business_active_channel_month` 看板不齐。
  - 默认只使用 `aws.business_active_user_last_14_day` 取活跃与活跃相关转化；`aws.business_active_channel_month` 只作为看板来源说明或对照，不作为默认取数表。

## 客单价

- **定义**：付费用户人均营收金额。
- **计算方式**：`pay_amount / pay_user_cnt`
- **表来源**：
  - 活跃相关客单价：默认使用 `aws.business_active_user_last_14_day` 的活跃口径字段。
  - 单独看订单客单价或商品订单营收：使用 `dws.topic_order_detail`。
- **注意**：
  - 跟活跃相关、需要与活跃转化率/活跃 ARPU 同看时，客单价必须和活跃口径一致：`SUM(normal_price_amount) / COUNT(DISTINCT CASE WHEN normal_price_amount > 0 THEN u_user END)`。
  - 不要默认用订单表 JOIN 活跃池后的订单用户数和 `sub_amount` 计算活跃相关客单价。
  - 单独看订单流水时，订单表筛选仍按 GMV / 营收口径执行。

## GMV

- **定义**：指定订单窗口内、归属电销/商业化的正价营收金额汇总。
- **计算方式**：`SUM(sub_amount)`
- **表来源**：`dws.topic_order_detail`
- **筛选条件**：`is_test_user = 0`、`u_user IS NOT NULL`、`original_amount >= 39`、`business_gmv_attribution IN ('电销','商业化')`，默认不加 `status = '支付成功'`。
- **注意**：
  - 默认所有 GMV / 营收问题均按正价营收处理，即必须筛 `original_amount >= 39`。
  - 用户问“总营收”时，默认解释并执行为“正价营收”；如需“包含非正价”，必须由用户明确提出。
  - 默认不筛选 `status = '支付成功'`；只有用户明确要求支付成功、退款、到账或指定订单状态时，才按需求筛选 `status`。
  - `dws.topic_order_detail` 是子订单粒度，汇总订单量时必须对 `order_id` 去重。
  - 只有用户明确要求“全量营收”“不筛正价”“含低价/体验品”时，才允许去掉正价筛选，并必须在结果中说明。

## 月度宏观/转化月报规范

本节用于沉淀 C 端月度宏观/转化月报的取数、归因和输出规则。用户询问“月报”“宏观简报”“转化月报”“五月大盘”等场景时，优先使用本规范。

### 适用场景

- 目标是解释某个月的大盘经营表现，而不是只回答单个指标。
- 默认同时取三个月份：
  - 目标月：用户指定月份。
  - 上月：用于环比。
  - 去年同期：用于同比。
- 分析主线以同比为主，环比用于补充短期趋势。
- 表格列顺序统一为：目标月、去年同期、上月、同比变化、环比变化。
- 看板对齐月报默认使用看板 MTD 逻辑，而不是简单把三个月都截成同一个 `start_day/end_day` 订单窗口。不同模块的 MTD 截断规则不同，必须按下方核心指标口径分别处理。

### 核心指标口径

- MAU：从 `aws.business_active_user_last_14_day` 按 `user_sk + 月` 去重。
- 看板对齐时，必须先区分指标类型：
  - 单独看 GMV 营收流水、商品订单营收、订单明细时，使用订单表 `dws.topic_order_detail`。
  - 跟活跃相关、需要以活跃用户为分母或解释活跃商业化效率时，例如活跃付费转化率、活跃 ARPU、活跃口径客单价，只使用 `aws.business_active_user_last_14_day` 的金额/转化字段，默认不要用订单表 JOIN 活跃池计算，也不要直接取其他活跃聚合表。
- 整体商业化看板 MTD 的关键规则：
  - 活跃池按月取 `aws.business_active_user_last_14_day`，并用 `CAST(SUBSTR(CAST(day AS STRING), 7, 2) AS INT) <= DAY(CURRENT_DATE())` 标记/筛选 MTD 活跃用户；历史月、上月、目标月都按同一个 day-of-month 规则截活跃池。
  - 活跃相关转化人数使用活跃表金额字段判断：`normal_price_amount > 0` 的用户数。
  - 活跃相关转化金额使用活跃表 `normal_price_amount`。
  - 因此，整体商业化 MTD = “MTD 活跃池用户 + 活跃表同月金额/转化字段”，不是“MTD 活跃池 + 订单表 MTD 订单”，也不是“活跃池 JOIN 订单表”。
  - 这条规则适用于整体营收看板中的活跃付费转化率、活跃 ARPU、活跃口径客单价。
- 活跃付费转化率：`COUNT(DISTINCT CASE WHEN normal_price_amount > 0 THEN u_user END) / COUNT(DISTINCT u_user)`。
- 活跃 ARPU：`SUM(normal_price_amount) / COUNT(DISTINCT u_user)`。
- 活跃口径客单价：`SUM(normal_price_amount) / COUNT(DISTINCT CASE WHEN normal_price_amount > 0 THEN u_user END)`。
- 商品订单营收、GMV、订单量、商品订单结构仍用 `dws.topic_order_detail`；如果要输出商品活跃 ARPU 或商品活跃转化率，必须说明该指标是否有对应活跃表字段，否则不要用订单表口径冒充看板活跃口径。
- 订单层默认必须包含：
  ```sql
  u_user IS NOT NULL
  AND original_amount >= 39
  AND business_gmv_attribution IN ('电销', '商业化')
  ```
- 看板对齐口径下，订单层不筛 `is_test_user = 0`；这条规则覆盖通用订单默认筛选。
- 默认不筛选 `status = '支付成功'`；只有用户明确要求支付成功、退款、到账或指定订单状态时，才按需求筛选 `status`。
- `business_gmv_attribution IN ('电销', '商业化')` 为精确匹配，默认不包含 `商业化-电商`；如业务明确要纳入平台电商，必须显式增加并同步说明口径变化。
- 看板原始实现见 `knowledge/c_end/gold_cases.md` 的“月度宏观看板聚合”案例；默认不要直接取 `aws.business_active_channel_month`，如需与该看板对齐，也用 `aws.business_active_user_last_14_day` 的 `normal_price_amount`、`normal_price_scheme_amount`、`normal_price_non_scheme_amount` 等字段复算。

### 看板对齐 SQL 骨架

```sql
WITH active_pool AS (
    SELECT
        DATE_TRUNC('month', STR_TO_DATE(CAST(day AS STRING), '%Y%m%d')) AS stat_month,
        u_user
    FROM aws.business_active_user_last_14_day
    WHERE day BETWEEN ${month_start_day} AND ${month_end_day}
      AND CAST(SUBSTR(CAST(day AS STRING), 7, 2) AS INT) <= DAY(CURRENT_DATE())
      AND u_user IS NOT NULL
    GROUP BY 1, 2
),
active_amount AS (
    SELECT
        u_user,
        DATE_TRUNC('month', STR_TO_DATE(CAST(day AS STRING), '%Y%m%d')) AS stat_month,
        SUM(IF(business_gmv_attribution IN ('电销','商业化'), normal_price_amount, 0)) AS amount
    FROM aws.business_active_user_last_14_day
    WHERE day BETWEEN ${month_start_day} AND ${month_end_day}
      AND CAST(SUBSTR(CAST(day AS STRING), 7, 2) AS INT) <= DAY(CURRENT_DATE())
      AND u_user IS NOT NULL
    GROUP BY 1, 2
)
SELECT
    a.stat_month,
    COUNT(DISTINCT a.u_user) AS active_cnt,
    COUNT(DISTINCT CASE WHEN m.amount > 0 THEN a.u_user END) AS pay_user_cnt,
    SUM(COALESCE(m.amount, 0)) AS pay_amount,
    COUNT(DISTINCT CASE WHEN m.amount > 0 THEN a.u_user END) / NULLIF(COUNT(DISTINCT a.u_user), 0) AS active_pay_rate,
    SUM(COALESCE(m.amount, 0)) / NULLIF(COUNT(DISTINCT a.u_user), 0) AS active_arpu,
    SUM(COALESCE(m.amount, 0)) / NULLIF(COUNT(DISTINCT CASE WHEN m.amount > 0 THEN a.u_user END), 0) AS avg_order_value
FROM active_pool a
LEFT JOIN active_amount m
  ON a.u_user = m.u_user
 AND a.stat_month = m.stat_month
GROUP BY a.stat_month
```

### 归因分析规则

- 月报解释整体大盘时，优先按以下链路组织：
  1. MAU 变化：活跃规模是大盘水位。
  2. 付费转化率变化：活跃用户中有多少变成付费用户。
  3. 客单价变化：付费用户人均贡献。
  4. 活跃 ARPU 变化：营收效率综合结果。
  5. 订单营收变化：最终经营结果。
- 优先判断收入下降是由 MAU 下降、转化率下降还是客单价变化驱动。
- 如果 ARPU 上升但收入下降，应明确说明“客单价/ARPU 托底不足以抵消 MAU 或转化率下滑”。
- 如果客单价提升而转化率下滑，应说明“高客单价托底，但转化效率承压”。

### 活跃结构

- 活跃下滑需要拆分老未与非老未。
- 老未判断基于活跃表中的统计分层和业务分层字段，通常使用包含 `老未|老用户` 的规则。
- 判断“活跃下滑是否由老未用户流失导致”必须基于实际数据统计，不得只按经验或文档推断。
- `mid_active_type` 不在 `aws.business_active_user_last_14_day` 中，如需输出中学活跃类型，可从 `dws.topic_user_active_detail_day` 通过 `u_user + day` 辅助补字段。
- `dws.topic_user_active_detail_day` 只能补 `mid_active_type` 等辅助维度，不得作为活跃人数、转化人数、ARPU、客单价或金额的主计算表。
- 使用 `mid_active_type` 等辅助维度时，必须先在 `aws.business_active_user_last_14_day` 中按 `u_user + stat_month` 单独聚合 `normal_price_amount`，再 JOIN 到一人一月的活跃底表；不要在 JOIN 了 `dws.topic_user_active_detail_day` 后再 `SUM(normal_price_amount)`，否则会因辅助表多行粒度放大金额。
- 做去年同期关联时，如果输出同时包含业务分层和统计分层，JOIN 条件必须同时包含 `business_user_pay_status_business`、`business_user_pay_status_statistics`、`mid_active_type` 和月份偏移，避免统计分层缺失导致行重复放大。

### 新增流量

- 新增注册必须补充免费/付费流量拆分。
- 免费/付费流量使用注册渠道一级标签：
  - `免费` → 免费流量。
  - `付费` 或 `投放` → 付费流量。
  - 其他枚举保留为其他/未打标。
- 新增流量质量至少看：新增付费率、新增 LTV、新增客单价。
- 新增注册看板对齐时，基础用户来自 `aws.user_increase_new_add_day`，关联 `aws.user_increase_channel_label_day` 获取 `regist_channel_label1`、`regist_channel_label2`。
- 新增注册看板 MTD 的截断规则与整体商业化不同：基础注册层使用 `DAY(STR_TO_DATE(CAST(a.day AS STRING), '%Y%m%d')) <= DAY(DATE_SUB(CURRENT_DATE(), 1))`；历史月和上月也按这个 day-of-month 截注册用户。
- 新增注册的付费金额仍按注册月同月订单聚合，不按注册日 MTD 再截支付日；也就是先按 `u_user + pay_month` 汇总注册月订单，再关联注册 cohort。
- 只有看新增注册、注册用户 LTV、注册转化月维度或月报新增流量模块时，付费订单才使用新增注册看板口径；订单表仍使用 `dws.topic_order_detail`，但字段和筛选必须按看板：
  ```sql
  SUM(arrival_amount) AS pay_amount
  WHERE status IN ('支付成功', '退款成功')
  ```
- 新增注册看板对齐时，不要默认套用 `sub_amount`、`original_amount >= 39`、`business_gmv_attribution IN ('电销','商业化')` 或订单层 `is_test_user = 0`；这些是商业化营收默认口径，不是新增注册看板 LTV 口径。
- 非新增注册场景不得套用本条 `arrival_amount + status` 例外；整体商业化、活跃池订单、商品结构仍按对应章节的营收口径。
- 新增注册看板对齐时，必须先按看板宽表粒度 `reg_month + os + regist_channel_label1 + regist_channel_label2` 聚合，再由报表/看板层汇总指标；不要在报表查询里直接改成全局 `COUNT(DISTINCT u_user)`。
- 新增客单价按看板聚合字段计算：`SUM(pay_amount) / SUM(pay_user_num)`，其中 `pay_user_num` 来自宽表内 `SUM(is_pay)`；其中 `is_pay = IF(up.u_user IS NOT NULL, 1, 0)`，只要订单表有匹配记录即算付费，不要求 amount > 0 ；不要改成 `SUM(pay_amount) / COUNT(DISTINCT 付费 u_user)`。
- 新增注册看板的 `FULL_MONTH`、`MTD`、`MIX` 输出逻辑参考 `knowledge/c_end/gold_cases.md` 的“新增注册看板聚合”案例。
- 新增 LTV 变化要区分结构影响和质量影响：
  - 结构影响：免费/付费注册占比变化带来的 LTV 变化。
  - 质量影响：免费/付费各自 LTV 变化带来的 LTV 变化。

### 留存与回流

- 不用“目标月用户向后留存”解释目标月大盘。
- 解释目标月活跃时，使用历史 cohort 的次月、次 2 月留存趋势判断其对目标月活跃的前置影响。
- 对目标月 `M`：
  - `M-2` 月 cohort 的次 2 月留存直接进入目标月活跃。
  - `M-1` 月 cohort 的次月留存直接进入目标月活跃。
- 例如解释 2026 年 4 月：
  - 2026 年 2 月 cohort 的次 2 月留存进入 2026 年 4 月活跃。
  - 2026 年 3 月 cohort 的次月留存进入 2026 年 4 月活跃。
- “目标月用户向后留存”只用于预测后续月份，不用于解释目标月已经发生的 MAU。
- 留存率除相对变化外，需要补充绝对变化，单位为 pp。

### 商品结构

- 商品结构重点关注组合品变化。
- 组合品常规规则：`business_good_kind_name_level_1 = '组合品'`。
- 2025 年特殊规则：`good_kind_name_level_2 in ('一年积木块'、'到期型积木块')`定义为组合品。
- 2025 年积木块为 998 模式商品，但不要单独用价格 `998` 识别积木块，优先使用商品类目或修正类目。
- 从小学产品取数口径（默认按 `dws.topic_order_detail`）：
  - 从小学单科/联售/小学全科规划提分课统一按以下 `CASE WHEN` 分类：
    ```sql
    SELECT DISTINCT
      CASE
        WHEN good_kind_name_level_3 = '拓展课'
         AND good_stage_subject_cnt = 1
         AND good_stage_subject regexp '1-2-specialCourse'
          THEN '从小学物理'
        WHEN good_kind_name_level_3 = '拓展课'
         AND good_stage_subject_cnt = 1
         AND good_stage_subject regexp '1-6-specialCourse'
          THEN '从小学生物'
        WHEN good_kind_name_level_3 = '拓展课'
         AND good_stage_subject_cnt = 1
         AND good_stage_subject regexp '1-7-specialCourse'
          THEN '从小学地理'
        WHEN good_kind_name_level_3 = '拓展课'
         AND good_stage_subject_cnt = 3
         AND good_stage_subject regexp '1-2-specialCourse'
         AND good_stage_subject regexp '1-6-specialCourse'
         AND good_stage_subject regexp '1-7-specialCourse'
          THEN '从小学物生地（3科联售）'
        WHEN business_good_kind_name_level_3 IN ('小学品加拓展')
          THEN '小学全科规划提分课'
      END AS good_kind,
      order_id
    FROM dws.topic_order_detail;
    ```
  - `regexp` 规则按“包含即可”理解，不要求字段等值。
  - 分类顺序保持“单科条件在前、3科联售在后”，不要调整 `CASE WHEN` 顺序。
  - 涉及营收时仍按默认正价营收口径执行（除非用户明确要求全量营收/包含非正价）。
- 商品核心指标优先级：
  1. 商品活跃 ARPU 及同比变化。
  2. 商品客单价。
  3. 商品活跃转化率。
- 非组合品仅保留收入占比和订单占比，不展开转化率、客单价、ARPU 解释。
- 如果组合品 ARPU 提升来自客单价而非转化率，要明确说明“收入托底来自客单价抬升，不是转化效率提升；若转化率继续下滑，单靠高客单价托底的持续性有限”。

### 输出结构

- 核心结论按“总-分”组织：
  1. 第一段只给一句总判断，不堆具体数据。
  2. 第二段用 3 条以内支撑说明：整体大盘、活跃/留存、商品结构。
  3. 核心结论不增加环比信息；环比放在分章节表格或正文中。
  4. 不单独增加“归因小结”，避免首尾重复。
- 月报默认章节：
  1. 整体收入与商业化。
  2. 新增流量。
  3. 活跃规模与结构。
  4. 留存与回流。
  5. 商品结构与转化。
  6. 数据文件或 SQL 附录（按需）。
- 每个章节表格后必须补一句高密度解释，说明“这个表说明了什么”，避免只罗列数据。
- 章节解释模板：
  - 整体收入章节：说明收入变化主要由 MAU、付费转化率、客单价中的哪一项驱动。
  - 新增流量章节：区分新增规模和新增质量，重点解释新增付费率、LTV 和客单价变化。
  - 活跃结构章节：说明老未/非老未对 MAU 变化的贡献。
  - 留存章节：先解释为什么看历史 cohort，再说明关键 cohort 的留存变化。
  - 商品章节：说明组合品收入/ARPU 变化来自客单价还是转化率，非组合品只看结构占比。

### 表达与数字格式

- 同比相对变化、环比相对变化：保留一位小数。
- 留存率绝对变化：保留两位小数，单位 pp。
- ARPU：保留两位小数。
- 转化率、留存率：保留两位小数。
- 客单价：保留整数。
- 营收：保留整数。
- 活跃用户数：保留整数。
- 表格中涉及同比和环比时，列顺序统一为同比在前、环比在后。
- 涉及转化率、留存率下滑时，必须明确实际下降幅度。
- 内容要从“数据罗列”推进到“经营判断”，但每个判断都必须有对应数据支撑。

## 商品体系2.0与中台策略口径

本节来自《[规则]中台策略通用数据口径2.0》，用于统一商品体系 2.0、策略、补差、多孩、续购、加购等取数口径。该规则自 **2026-01-01** 起作为商品策略类问题的优先口径。

### 适用场景

- 用户询问商品结构、组合品/非组合品、单学段/多学段、到期型/时长型、公域品/私域品等商品体系 2.0 分类。
- 用户询问策略转化、策略资格、策略用户分层、多孩策略、补差、平板加购、续购、升级率等中台策略指标。
- 用户给出 `business_good_kind_name_level_1/2/3`、`strategy_type`、`strategy_detail`、`course_timing_kind`、`course_group_kind` 等条件时，优先按本节处理。

### 核心字段

- 商品业务分类：`dws.topic_order_detail.business_good_kind_name_level_1/2/3`。
  - 这是前端业务口径商品分类，适合策略组和商品体系 2.0 口径。
  - 与 `good_kind_name_level_1/2/3` 不能混用；输出时必须说明使用哪套类目。
- 商品类型：`course_timing_kind`，用于区分到期型/时长型等商品类型。
- 商品分组：`course_group_kind`，用于区分公域品/私域品或主推品等商品分组。
- 策略类型：`strategy_type`，2026-01-01 后为业务数据，之前可能按规则清洗。
- 策略明细：`strategy_detail`，记录策略及对应优惠金额明细。
- 策略用户分层：`user_strategy_tag_day/month/year`。
  - 历史大会员拆分为可续购和不可续购，如看整体历史大会员需合并。
- 用户策略资格：`user_strategy_eligibility_day/month/year`。
- 多孩策略退差价时间：`multi_child_refund_time`。

### 金额字段

- `original_amount`：超值价/订单原价。
- `sub_amount`：到手价/实收金额；商品订单营收、GMV、商品营收流水默认使用该字段。
- `discount_amount`：实际优惠总金额，通常为“超值价 - 到手价”。
- `discount_id`：优惠券 ID。
- `discount_price`：优惠券金额。
- 金额字段不可混用；如果用户问优惠、补差或策略让利，必须明确使用 `discount_amount`、`strategy_detail`、`fix_deductible_price` 等字段，而不是直接用营收字段替代。

### 策略转化与加购指标

- 付费零售品用户续购率：
  - 组合品续购率分母：购买过零售品的用户。
  - 组合品续购率分子：后续购买组合品的用户。
  - 非组合品续购率分子：后续再次购买非组合品的用户。
- 付费组合品或大会员用户续购率：
  - 分母：购买过组合品的用户，需区分历史大会员用户和付费组合品用户。
  - 组合品续购率分子：购买过组合品、续购品的用户，可按商品分类拆分。
  - 非组合品续购率分子：后续再次购买非组合品的用户。
- 平板加购率：
  - 单后加购：购买后再次购买三级类目为“学习机加购-平板加购”的用户。
  - 随单加购：购买当下商品中包含平板的用户。
  - 分母：购买了积木块、组合品的用户。
  - 分子：单后加购或随单加购用户。
- 多孩加购率：
  - 分母：有多孩策略资格的用户。
  - 分子：以多孩策略购买组合品的用户。
- 小学品/小初同步品升级率：
  - 分母：有小学同步 6 年时长品补差资格的用户，或小初同步 4 年时长品补差资格的用户。
  - 分子：升级购买组合品的用户。

### 使用注意

- 单独看商品订单营收、GMV、订单量时仍遵守订单表大标准：使用 `dws.topic_order_detail`。
- 跟活跃相关、需要以活跃用户为分母的转化率、客单价、ARPU，仍使用 `aws.business_active_user_last_14_day` 作为分母主表；策略字段只作为用户分层或资格条件使用。
- 策略资格类指标优先使用 `user_strategy_eligibility_*`；策略用户身份类指标优先使用 `user_strategy_tag_*`。
- 如果需求涉及“有资格但未购买”“资格用户转化”“升级率”，必须先圈资格用户分母，再关联订单购买分子，不得直接用订单购买用户当分母。

## 易混淆术语


| 易混点                  | 正确理解                                                                                                                          |
| -------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| C端活跃 vs 全公司活跃        | `aws.business_active_user_last_14_day` 只代表 C 端/私域活跃，不代表全公司活跃                                                                  |
| C端活跃 ARPU            | 必须先圈 `aws.business_active_user_last_14_day` 的 C 端活跃用户池，分子只统计该用户池内同月营收；不能用全量订单营收直接除以月活                                         |
| 活跃主表 vs 活跃行为辅助表      | `aws.business_active_user_last_14_day` 是 C 端活跃主表；`dws.topic_user_active_detail_day` 只能 `LEFT JOIN` 补充行为/设备/渠道字段               |
| 用户标签字段               | 牵涉用户标签时只用带 `business_` 前缀字段；统计维度用 `business_user_pay_status_statistics_month`，业务维度用 `business_user_pay_status_business_month` |
| 订单量 vs 子订单行数         | 订单量必须按 `order_id` 去重，子订单行数不能直接当订单量                                                                                            |
| 商品 2.0 类目 vs 策略组商品类目 | 两套类目字段不能混用，输出时必须明确字段名                                                                                                         |
| LTV 金额 vs GMV        | LTV 通常看注册 cohort 的到账金额，GMV 按订单或商品归属汇总                                                                                         |
| 注册用户 LTV vs 注册转化月维度  | 用户问“新增注册用户 LTV”时，默认走注册转化月维度口径，输出 `pay_amount / install_users`，而不是只输出订单金额汇总                                                    |
| 支付成功 vs 退款成功         | 看营收、GMV、ARPU 分子或付费金额时默认不筛 `status = '支付成功'`；只有用户明确要求支付成功、退款、到账或指定订单状态时才筛选订单状态                                                         |
| 测试用户 vs 正常用户         | 订单、营收、GMV、ARPU 分子、付费金额默认必须筛 `is_test_user = 0`，排除测试用户                                                                                 |
| 正价营收 vs 全量营收         | 默认营收、GMV、ARPU 分子均使用正价营收，必须筛 `original_amount >= 39`；全量营收只有在用户明确要求时使用                                                          |
| 总营收表达                 | 对外默认把“总营收”解释为“正价营收”；若用户要包含非正价部分，需明确提出“全量营收/包含非正价”并同步说明口径变化                                                         |


## 业务纠偏沉淀

- 如果业务方在取数过程中纠正口径，必须把纠正后的稳定规则沉淀到本文件。
- 本次纠偏：`注册用户 LTV = pay_amount / install_users`。
- 本次回复方式纠偏：用户只问单个核心指标时，只返回核心数值和极短口径，不默认展开 SQL、结果目录、文件清单或完整字段解释。
- 本次活跃口径纠偏：
  - `aws.business_active_user_last_14_day` 是 C 端活跃主表。
  - C 端活跃 ARPU 的分母使用 `aws.business_active_user_last_14_day` 圈定的 C 端活跃用户池。
  - C 端活跃 ARPU 的分子必须限定在该活跃用户池内；使用 `dws.topic_order_detail` 时，需要先 `JOIN` 活跃用户池后再汇总订单金额。
  - 不得用全量订单营收直接除以 C 端活跃人数。
  - 统计月活时按 `user_sk + active_month` 去重。
  - 牵涉用户标签、统计分层、业务分层时，只用带 `business_` 前缀的字段。
  - `user_pay_status_statistics_month` 标记为知识库不引用，默认不得使用。
  - `dws.topic_user_active_detail_day` 只能作为辅助明细表，在主活跃口径结果上 `LEFT JOIN` 补字段；不得作为活跃人数、ARPU、转化率分母的主表。
- 本次订单表纠偏：涉及订单明细、订单聚合、注册用户付费金额时，默认使用 `dws.topic_order_detail`，不要默认使用 `dw.fact_order_detail`。
- 本次营收口径纠偏：
  - 营收金额使用 `dws.topic_order_detail.sub_amount`。
  - 默认所有营收类指标均为正价营收，必须筛 `original_amount >= 39`。
  - 必加筛选：`is_test_user = 0`、`u_user IS NOT NULL`、`original_amount >= 39`、`business_gmv_attribution IN ('电销','商业化')`。
  - 看营收、GMV、ARPU 分子或付费金额时，默认不加 `status = '支付成功'`；只有用户明确要求支付成功、退款、到账或指定订单状态时才加状态筛选。
  - 订单数使用 `COUNT(DISTINCT order_id)`。
- 本次客单价口径纠偏：客单价 = 金额 / 付费人数，即 `pay_amount / pay_user_cnt`，不是金额 / 订单数。
- 用户问“4月份新增注册用户的 LTV”这类问题时，应先确认年份，再使用注册转化月维度口径：
  - `install_users`：注册月内新增注册用户数。
  - `pay_user_num`：注册月内有付费的注册用户数。
  - `pay_amount`：注册月内付费金额。
  - `ltv`：`pay_amount / install_users`。
  - 可同时输出 `FULL_MONTH`、`MTD`、`MIX` 以及去年同期 `ly_`* 字段。
