# Gold Cases

本文件保存经过业务确认、可作为后续取数对齐基准的 SQL 案例。规则性口径仍以 `knowledge/c_end/glossary.md` 为准；本文件优先保存最新看板对齐 SQL，也可保留必要的人工 SQL 方便排查差异。

## 月度宏观看板聚合

### 使用场景

- 对齐月度宏观看板中的活跃量、活跃付费转化率、活跃 ARPU、客单价、留存等指标。
- 关键原则：
  - 活跃相关指标只使用 `aws.business_active_user_last_14_day`。
  - 活跃付费转化率、活跃 ARPU、活跃口径客单价都必须先圈同月活跃池，再使用活跃表同月金额字段。
  - 月度口径下，“先活跃再付款”统一理解为“当月活跃池 + 当月付款”，不要求支付时间严格晚于某次活跃日期。
  - 转化人数用活跃表金额字段判断：用户同月 `normal_price_amount > 0`。
  - 转化金额用活跃表 `normal_price_amount`，按 `business_gmv_attribution IN ('电销','商业化')` 归因。
  - `mid_active_type` 只能从 `dws.topic_user_active_detail_day` 辅助补字段；金额必须先在活跃表按 `u_user + stat_month` 聚合，不能在 JOIN 辅助明细后再 SUM。
  - 单独看 GMV 营收流水、商品订单营收、订单明细时才使用订单表 `dws.topic_order_detail`。

### 最新看板对齐 SQL

```sql
drop table if exists tmp.xuxingling_step1_monthly_agg_v3 force;

CREATE TABLE tmp.xuxingling_step1_monthly_agg_v3 AS
WITH active_main AS (
    SELECT
        u_user,
        business_user_pay_status_business_month AS business_user_pay_status_business,
        business_user_pay_status_statistics_month AS business_user_pay_status_statistics,
        DATE_TRUNC('MONTH', STR_TO_DATE(CAST(day AS STRING), '%Y%m%d')) AS stat_month,
        day,
        CASE
            WHEN CAST(SUBSTR(CAST(day AS STRING), 7, 2) AS INT) <= DAY(CURRENT_DATE())
            THEN 1 ELSE 0
        END AS is_mtd_day,
        ROW_NUMBER() OVER (
            PARTITION BY u_user, DATE_TRUNC('MONTH', STR_TO_DATE(CAST(day AS STRING), '%Y%m%d'))
            ORDER BY day ASC
        ) AS rn
    FROM aws.business_active_user_last_14_day
    WHERE day >= 20230101
      AND u_user IS NOT NULL
),
mid_active_type_month AS (
    SELECT
        u_user,
        DATE_TRUNC('MONTH', STR_TO_DATE(CAST(day AS STRING), '%Y%m%d')) AS stat_month,
        mid_active_type,
        ROW_NUMBER() OVER (
            PARTITION BY u_user, DATE_TRUNC('MONTH', STR_TO_DATE(CAST(day AS STRING), '%Y%m%d'))
            ORDER BY day ASC
        ) AS rn
    FROM dws.topic_user_active_detail_day
    WHERE client_os IN ('ios', 'android','harmony')
      AND is_test_user = 0
      AND day >= 20230101
      AND product_id IN ('01')
      AND active_user_attribution IN ('中学用户', '小学用户', 'c')
      AND u_user IS NOT NULL
),
user_monthly_base AS (
    SELECT
        a.u_user,
        a.stat_month,
        MAX(CASE WHEN a.rn = 1 THEN a.business_user_pay_status_business END) AS business_user_pay_status_business,
        MAX(CASE WHEN a.rn = 1 THEN a.business_user_pay_status_statistics END) AS business_user_pay_status_statistics,
        MAX(CASE WHEN m.rn = 1 THEN m.mid_active_type END) AS mid_active_type,
        MAX(a.is_mtd_day) AS is_mtd
    FROM active_main a
    LEFT JOIN mid_active_type_month m
      ON a.u_user = m.u_user
     AND a.stat_month = m.stat_month
    GROUP BY a.u_user, a.stat_month
),
user_monthly_enhanced AS (
    SELECT
        *,
        LEAD(stat_month, 1) OVER(PARTITION BY u_user ORDER BY stat_month) AS next_active_month
    FROM user_monthly_base
),
monthly_active_amount AS (
    SELECT
        u_user,
        DATE_TRUNC('MONTH', STR_TO_DATE(CAST(day AS STRING), '%Y%m%d')) AS pay_month,
        SUM(IF(business_gmv_attribution IN ('电销','商业化'), normal_price_amount, 0)) AS amount
    FROM aws.business_active_user_last_14_day
    WHERE day >= 20230101
      AND u_user IS NOT NULL
    GROUP BY 1, 2
)
SELECT
    t1.stat_month,
    t1.business_user_pay_status_business,
    t1.business_user_pay_status_statistics,
    t1.mid_active_type,

    SUM(1) AS active_cnt,
    SUM(CASE WHEN IFNULL(o.amount, 0) > 0 THEN 1 ELSE 0 END) AS pay_user_cnt,
    SUM(IFNULL(o.amount, 0)) AS pay_amount,
    SUM(CASE WHEN t1.next_active_month = ADD_MONTHS(t1.stat_month, 1) THEN 1 ELSE 0 END) AS retain_cnt,

    SUM(CASE WHEN t1.is_mtd = 1 THEN 1 ELSE 0 END) AS mtd_active_cnt,
    SUM(CASE WHEN t1.is_mtd = 1 AND IFNULL(o.amount, 0) > 0 THEN 1 ELSE 0 END) AS mtd_pay_user_cnt,
    SUM(CASE WHEN t1.is_mtd = 1 THEN IFNULL(o.amount, 0) ELSE 0 END) AS mtd_pay_amount,
    SUM(CASE WHEN t1.is_mtd = 1 AND t1.next_active_month = ADD_MONTHS(t1.stat_month, 1) THEN 1 ELSE 0 END) AS mtd_retain_cnt

FROM user_monthly_enhanced t1
LEFT JOIN monthly_active_amount o
  ON t1.u_user = o.u_user
 AND t1.stat_month = o.pay_month
GROUP BY 1, 2, 3, 4;

drop table if exists tmp.xuxingling_active_cnt_month_yoy_v2 force;

CREATE TABLE tmp.xuxingling_active_cnt_month_yoy_v2 AS
WITH report_with_ly AS (
    SELECT
        curr.*,
        ly.active_cnt AS active_cnt_ly,
        ly.pay_user_cnt AS pay_user_cnt_ly,
        ly.pay_amount AS pay_amount_ly,
        ly.retain_cnt AS retain_cnt_ly,
        ly.mtd_active_cnt AS mtd_active_cnt_ly,
        ly.mtd_pay_user_cnt AS mtd_pay_user_cnt_ly,
        ly.mtd_pay_amount AS mtd_pay_amount_ly,
        ly.mtd_retain_cnt AS mtd_retain_cnt_ly
    FROM tmp.xuxingling_step1_monthly_agg_v3 curr
    LEFT JOIN tmp.xuxingling_step1_monthly_agg_v3 ly
        ON curr.business_user_pay_status_business = ly.business_user_pay_status_business
       AND curr.business_user_pay_status_statistics = ly.business_user_pay_status_statistics
       AND curr.mid_active_type = ly.mid_active_type
       AND curr.stat_month = ADD_MONTHS(ly.stat_month, 12)
),
unpivoted_data AS (
    SELECT
        stat_month,
        DATE_FORMAT(stat_month, '%Y-%m') AS report_month,
        business_user_pay_status_business,
        business_user_pay_status_statistics,
        mid_active_type,
        'FULL_MONTH' AS date_filter_type,
        active_cnt, pay_user_cnt, pay_amount, retain_cnt,
        active_cnt_ly, pay_user_cnt_ly, pay_amount_ly, retain_cnt_ly
    FROM report_with_ly

    UNION ALL

    SELECT
        stat_month,
        DATE_FORMAT(stat_month, '%Y-%m') AS report_month,
        business_user_pay_status_business,
        business_user_pay_status_statistics,
        mid_active_type,
        'MTD' AS date_filter_type,
        mtd_active_cnt, mtd_pay_user_cnt, mtd_pay_amount, mtd_retain_cnt,
        mtd_active_cnt_ly, mtd_pay_user_cnt_ly, mtd_pay_amount_ly, mtd_retain_cnt_ly
    FROM report_with_ly
)
SELECT
    report_month,
    business_user_pay_status_business,
    business_user_pay_status_statistics,
    mid_active_type,
    date_filter_type,
    active_cnt, pay_user_cnt, pay_amount, retain_cnt,
    active_cnt_ly, pay_user_cnt_ly, pay_amount_ly, retain_cnt_ly
FROM unpivoted_data

UNION ALL

SELECT
    report_month,
    business_user_pay_status_business,
    business_user_pay_status_statistics,
    mid_active_type,
    'MIX' AS date_filter_type,
    active_cnt, pay_user_cnt, pay_amount, retain_cnt,
    active_cnt_ly, pay_user_cnt_ly, pay_amount_ly, retain_cnt_ly
FROM unpivoted_data
WHERE
    (stat_month = DATE_TRUNC('month', CURRENT_DATE()) AND date_filter_type = 'MTD')
    OR
    (stat_month <> DATE_TRUNC('month', CURRENT_DATE()) AND date_filter_type = 'FULL_MONTH');
```

## 新增注册看板聚合

### 使用场景

- 对齐月度看板中的新增注册、注册月付费人数、注册月付费金额、新增付费率、新增 LTV、新增客单价、次月留存等指标。
- 项目内统一使用 `dws.topic_order_detail` 作为订单表；看板里的 `dw.fact_order_detail` 与 `dws.topic_order_detail` 业务等价，但知识库默认生成 `dws.topic_order_detail`。
- 只有看新增注册、注册用户 LTV、注册转化月维度或月报新增流量模块时，才使用本案例的付费字段和状态筛选。
- 新增注册付费金额按看板字段：`SUM(arrival_amount)`。
- 新增注册付费订单状态按看板筛选：`status IN ('支付成功', '退款成功')`。
- 新增注册看板口径不要默认加 `original_amount >= 39`、`business_gmv_attribution IN ('电销','商业化')` 或订单层 `is_test_user = 0`。
- 整体 GMV、整体营收、活跃 ARPU、活跃付费转化、商品结构等非新增注册场景不得套用本案例的 `arrival_amount + status` 例外。
- 看板先按 `reg_month + os + regist_channel_label1 + regist_channel_label2` 生成宽表，再由报表层汇总；新增客单价必须用 `SUM(pay_amount) / SUM(pay_user_num)`，不要改成全局 `COUNT(DISTINCT u_user)` 口径。

### 看板代码（项目适配版）

```sql
drop table if exists tmp.xuxingling_regist_channel_retention_cnt_month_v2 force;
create table tmp.xuxingling_regist_channel_retention_cnt_month_v2 as

WITH base_data AS (
    SELECT
        a.u_user,
        a.u_from AS os,
        c.regist_channel_label1,
        c.regist_channel_label2,
        STR_TO_DATE(CAST(a.day AS STRING), '%Y%m%d') AS reg_date,
        DATE_TRUNC('month', STR_TO_DATE(CAST(a.day AS STRING), '%Y%m%d')) AS reg_month,
        DAY(STR_TO_DATE(CAST(a.day AS STRING), '%Y%m%d')) AS day_of_month,
        DAY(DATE_SUB(CURRENT_DATE(), 1)) AS mtd_limit_day
    FROM aws.user_increase_new_add_day a
    LEFT JOIN aws.user_increase_channel_label_day c
        ON a.u_user = c.u_user
        AND a.day = c.day
    WHERE a.u_from IN ('android', 'ios', 'harmony')
      AND a.user_sk > 0
      AND a.day >= '20230101'
),
user_metrics AS (
    SELECT
        b.u_user,
        b.os,
        b.regist_channel_label1,
        b.regist_channel_label2,
        b.reg_date,
        b.reg_month,
        b.day_of_month,
        b.mtd_limit_day,
        IF(up.u_user IS NOT NULL, 1, 0) AS is_pay,
        IFNULL(up.amount, 0) AS pay_amount,
        IF(act.u_user IS NOT NULL, 1, 0) AS is_retention
    FROM base_data b
    LEFT JOIN (
        SELECT
            u_user,
            DATE_TRUNC('month', STR_TO_DATE(CAST(paid_time_sk AS STRING), '%Y%m%d')) AS pay_month,
            SUM(arrival_amount) AS amount
        FROM dws.topic_order_detail
        WHERE status IN ('支付成功', '退款成功')
          AND paid_time_sk >= '20230101'
        GROUP BY 1, 2
    ) up
      ON b.u_user = up.u_user
     AND b.reg_month = up.pay_month
    LEFT JOIN (
        SELECT DISTINCT
            u_user,
            DATE_TRUNC('month', CAST(day AS DATE)) AS active_month
        FROM aws.business_active_user_last_14_day
        WHERE day >= '20230101'
    ) act
      ON b.u_user = act.u_user
     AND act.active_month = ADD_MONTHS(b.reg_month, 1)
),
monthly_agg_wide AS (
    SELECT
        reg_month,
        os,
        regist_channel_label1,
        regist_channel_label2,
        COUNT(u_user) AS full_install_users,
        SUM(is_pay) AS full_pay_user_num,
        SUM(pay_amount) AS full_pay_amount,
        SUM(is_retention) AS full_retention_users,
        COUNT(CASE WHEN day_of_month <= mtd_limit_day THEN u_user END) AS mtd_install_users,
        SUM(CASE WHEN day_of_month <= mtd_limit_day THEN is_pay ELSE 0 END) AS mtd_pay_user_num,
        SUM(CASE WHEN day_of_month <= mtd_limit_day THEN pay_amount ELSE 0 END) AS mtd_pay_amount,
        SUM(CASE WHEN day_of_month <= mtd_limit_day THEN is_retention ELSE 0 END) AS mtd_retention_users
    FROM user_metrics
    GROUP BY 1, 2, 3, 4
),
joined_with_ly AS (
    SELECT
        curr.*,
        ly.full_install_users AS ly_full_install_users,
        ly.full_pay_user_num AS ly_full_pay_user_num,
        ly.full_pay_amount AS ly_full_pay_amount,
        ly.full_retention_users AS ly_full_retention_users,
        ly.mtd_install_users AS ly_mtd_install_users,
        ly.mtd_pay_user_num AS ly_mtd_pay_user_num,
        ly.mtd_pay_amount AS ly_mtd_pay_amount,
        ly.mtd_retention_users AS ly_mtd_retention_users
    FROM monthly_agg_wide curr
    LEFT JOIN monthly_agg_wide ly
        ON ADD_MONTHS(curr.reg_month, -12) = ly.reg_month
       AND curr.os = ly.os
       AND IFNULL(curr.regist_channel_label1,'') = IFNULL(ly.regist_channel_label1,'')
       AND IFNULL(curr.regist_channel_label2,'') = IFNULL(ly.regist_channel_label2,'')
),
final_unpivot AS (
    SELECT
        reg_month,
        DATE_FORMAT(reg_month, '%Y-%m') AS report_month,
        os,
        regist_channel_label1,
        regist_channel_label2,
        'FULL_MONTH' AS report_type,
        full_install_users AS install_users,
        ly_full_install_users AS ly_install_users,
        full_pay_user_num AS pay_user_num,
        ly_full_pay_user_num AS ly_pay_user_num,
        full_pay_amount AS pay_amount,
        ly_full_pay_amount AS ly_pay_amount,
        full_retention_users AS retention_users,
        ly_full_retention_users AS ly_retention_users
    FROM joined_with_ly

    UNION ALL

    SELECT
        reg_month,
        DATE_FORMAT(reg_month, '%Y-%m') AS report_month,
        os,
        regist_channel_label1,
        regist_channel_label2,
        'MTD' AS report_type,
        mtd_install_users AS install_users,
        ly_mtd_install_users AS ly_install_users,
        mtd_pay_user_num AS pay_user_num,
        ly_mtd_pay_user_num AS ly_pay_user_num,
        mtd_pay_amount AS pay_amount,
        ly_mtd_pay_amount AS ly_pay_amount,
        mtd_retention_users AS retention_users,
        ly_mtd_retention_users AS ly_retention_users
    FROM joined_with_ly
)
SELECT
    report_type,
    report_month,
    os,
    regist_channel_label1,
    regist_channel_label2,
    install_users,
    ly_install_users,
    pay_user_num,
    ly_pay_user_num,
    pay_amount,
    ly_pay_amount,
    retention_users,
    ly_retention_users
FROM final_unpivot

UNION ALL

SELECT
    'MIX' AS report_type,
    report_month,
    os,
    regist_channel_label1,
    regist_channel_label2,
    install_users,
    ly_install_users,
    pay_user_num,
    ly_pay_user_num,
    pay_amount,
    ly_pay_amount,
    retention_users,
    ly_retention_users
FROM final_unpivot
WHERE
    (reg_month = DATE_TRUNC('month', CURRENT_DATE()) AND report_type = 'MTD')
    OR
    (reg_month <> DATE_TRUNC('month', CURRENT_DATE()) AND report_type = 'FULL_MONTH')
```

### 月报汇总取数 SQL

用于在月报中汇总新增整体指标，保留看板“先宽表、后聚合”的口径。

```sql
WITH base_data AS (
    SELECT
        a.u_user,
        a.u_from AS os,
        c.regist_channel_label1,
        c.regist_channel_label2,
        DATE_TRUNC('month', STR_TO_DATE(CAST(a.day AS STRING), '%Y%m%d')) AS reg_month,
        DAY(STR_TO_DATE(CAST(a.day AS STRING), '%Y%m%d')) AS day_of_month,
        DAY(DATE_SUB(CURRENT_DATE(), 1)) AS mtd_limit_day
    FROM aws.user_increase_new_add_day a
    LEFT JOIN aws.user_increase_channel_label_day c
      ON a.u_user = c.u_user
     AND a.day = c.day
    WHERE a.day >= 20230101
      AND a.u_from IN ('android', 'ios', 'harmony')
      AND a.user_sk > 0
),
user_metrics AS (
    SELECT
        b.u_user,
        b.os,
        b.regist_channel_label1,
        b.regist_channel_label2,
        b.reg_month,
        b.day_of_month,
        b.mtd_limit_day,
        IF(up.u_user IS NOT NULL, 1, 0) AS is_pay,
        IFNULL(up.amount, 0) AS pay_amount
    FROM base_data b
    LEFT JOIN (
        SELECT
            u_user,
            DATE_TRUNC('month', STR_TO_DATE(CAST(paid_time_sk AS STRING), '%Y%m%d')) AS pay_month,
            SUM(arrival_amount) AS amount
        FROM dws.topic_order_detail
        WHERE paid_time_sk >= 20230101
          AND status IN ('支付成功', '退款成功')
        GROUP BY 1, 2
    ) up
      ON b.u_user = up.u_user
     AND b.reg_month = up.pay_month
),
monthly_agg_wide AS (
    SELECT
        reg_month,
        os,
        regist_channel_label1,
        regist_channel_label2,
        COUNT(u_user) AS full_install_users,
        SUM(is_pay) AS full_pay_user_num,
        SUM(pay_amount) AS full_pay_amount,
        COUNT(CASE WHEN day_of_month <= mtd_limit_day THEN u_user END) AS mtd_install_users,
        SUM(CASE WHEN day_of_month <= mtd_limit_day THEN is_pay ELSE 0 END) AS mtd_pay_user_num,
        SUM(CASE WHEN day_of_month <= mtd_limit_day THEN pay_amount ELSE 0 END) AS mtd_pay_amount
    FROM user_metrics
    GROUP BY 1, 2, 3, 4
),
final_unpivot AS (
    SELECT
        reg_month,
        DATE_FORMAT(reg_month, '%Y-%m') AS report_month,
        'FULL_MONTH' AS report_type,
        full_install_users AS install_users,
        full_pay_user_num AS pay_user_num,
        full_pay_amount AS pay_amount
    FROM monthly_agg_wide

    UNION ALL

    SELECT
        reg_month,
        DATE_FORMAT(reg_month, '%Y-%m') AS report_month,
        'MTD' AS report_type,
        mtd_install_users AS install_users,
        mtd_pay_user_num AS pay_user_num,
        mtd_pay_amount AS pay_amount
    FROM monthly_agg_wide
),
mix_data AS (
    SELECT
        reg_month,
        report_month,
        install_users,
        pay_user_num,
        pay_amount
    FROM final_unpivot
    WHERE report_month IN (${target_month}, ${last_year_month}, ${last_month})
      AND (
          (reg_month = DATE_TRUNC('month', CURRENT_DATE()) AND report_type = 'MTD')
          OR (reg_month <> DATE_TRUNC('month', CURRENT_DATE()) AND report_type = 'FULL_MONTH')
      )
)
SELECT
    report_month,
    SUM(install_users) AS new_user_cnt,
    SUM(pay_user_num) AS new_pay_user_cnt,
    SUM(pay_amount) AS new_pay_amount,
    SUM(pay_user_num) / NULLIF(SUM(install_users), 0) AS new_pay_rate,
    SUM(pay_amount) / NULLIF(SUM(install_users), 0) AS new_ltv,
    SUM(pay_amount) / NULLIF(SUM(pay_user_num), 0) AS new_avg_order_value
FROM mix_data
GROUP BY report_month
ORDER BY report_month
LIMIT 10000
```
