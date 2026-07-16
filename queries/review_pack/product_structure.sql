WITH periods AS (
    SELECT '本期' AS period, {{CURRENT_START}} AS start_day, {{CURRENT_END}} AS end_day
    UNION ALL SELECT '去年同期', {{LAST_YEAR_START}}, {{LAST_YEAR_END}}
),
channels AS (
    SELECT '私域整体' AS channel UNION ALL SELECT 'APP' UNION ALL SELECT '销售'
),
products AS (
    SELECT '组合品' AS product UNION ALL SELECT '零售品' UNION ALL SELECT '家庭包'
    UNION ALL SELECT '从小学系列' UNION ALL SELECT '198' UNION ALL SELECT '498'
    UNION ALL SELECT '千元及以上'
),
user_layer_values AS (
    SELECT '新增' AS user_layer UNION ALL SELECT '老未' UNION ALL SELECT '续费'
    UNION ALL SELECT '高净值汇总' UNION ALL SELECT '高净值－当年毕业'
    UNION ALL SELECT '高净值－历史大会员可续购'
    UNION ALL SELECT '高净值－历史大会员不可续购'
    UNION ALL SELECT '高净值－其他组合品' UNION ALL SELECT '未映射'
),
stage_values AS (
    SELECT '1–3 年级' AS stage UNION ALL SELECT '4–6 年级'
    UNION ALL SELECT '初中' UNION ALL SELECT '高中' UNION ALL SELECT '未知学段'
),
active_raw AS (
    SELECT
        p.period,
        CAST(a.u_user AS VARCHAR) AS user_id,
        CASE WHEN a.business_gmv_attribution = '商业化' THEN 'APP'
             WHEN a.business_gmv_attribution = '电销' THEN '销售' END AS channel,
        CASE
            WHEN a.grade_name_month IN ('一年级','二年级','三年级') THEN '1–3 年级'
            WHEN a.grade_name_month IN ('四年级','五年级','六年级') THEN '4–6 年级'
            WHEN a.grade_name_month IN ('七年级','八年级','九年级','初一','初二','初三') THEN '初中'
            WHEN a.grade_name_month IN ('高一','高二','高三','十年级') THEN '高中'
            ELSE '未知学段'
        END AS stage,
        COALESCE(a.business_user_pay_status_statistics_month, '') AS raw_layer,
        a.user_strategy_tag_level2_month AS high_value_tag
    FROM periods p
    JOIN aws.business_active_user_last_14_day a ON a.day BETWEEN p.start_day AND p.end_day
    WHERE a.u_user IS NOT NULL
),
all_active_users AS (
    SELECT
        period,
        user_id,
        CASE
            WHEN MAX(CASE WHEN stage = '1–3 年级' THEN 1 ELSE 0 END) = 1 THEN '1–3 年级'
            WHEN MAX(CASE WHEN stage = '4–6 年级' THEN 1 ELSE 0 END) = 1 THEN '4–6 年级'
            WHEN MAX(CASE WHEN stage = '初中' THEN 1 ELSE 0 END) = 1 THEN '初中'
            WHEN MAX(CASE WHEN stage = '高中' THEN 1 ELSE 0 END) = 1 THEN '高中'
            ELSE '未知学段'
        END AS stage,
        CASE
            WHEN MAX(CASE WHEN raw_layer = '高净值用户' THEN 1 ELSE 0 END) = 1 THEN '高净值汇总'
            WHEN MAX(CASE WHEN raw_layer = '新增' THEN 1 ELSE 0 END) = 1 THEN '新增'
            WHEN MAX(CASE WHEN raw_layer = '老未' THEN 1 ELSE 0 END) = 1 THEN '老未'
            WHEN MAX(CASE WHEN raw_layer = '续费用户' THEN 1 ELSE 0 END) = 1 THEN '续费'
            ELSE '未映射'
        END AS user_layer,
        MAX(CASE WHEN raw_layer = '高净值用户' THEN high_value_tag END) AS high_value_tag
    FROM active_raw
    GROUP BY period, user_id
),
private_active_users AS (
    SELECT period, '私域整体' AS channel, user_id, stage, user_layer, high_value_tag
    FROM all_active_users
),
channel_active_users AS (
    SELECT
        period,
        channel,
        user_id,
        CASE
            WHEN MAX(CASE WHEN stage = '1–3 年级' THEN 1 ELSE 0 END) = 1 THEN '1–3 年级'
            WHEN MAX(CASE WHEN stage = '4–6 年级' THEN 1 ELSE 0 END) = 1 THEN '4–6 年级'
            WHEN MAX(CASE WHEN stage = '初中' THEN 1 ELSE 0 END) = 1 THEN '初中'
            WHEN MAX(CASE WHEN stage = '高中' THEN 1 ELSE 0 END) = 1 THEN '高中'
            ELSE '未知学段'
        END AS stage,
        CASE
            WHEN MAX(CASE WHEN raw_layer = '高净值用户' THEN 1 ELSE 0 END) = 1 THEN '高净值汇总'
            WHEN MAX(CASE WHEN raw_layer = '新增' THEN 1 ELSE 0 END) = 1 THEN '新增'
            WHEN MAX(CASE WHEN raw_layer = '老未' THEN 1 ELSE 0 END) = 1 THEN '老未'
            WHEN MAX(CASE WHEN raw_layer = '续费用户' THEN 1 ELSE 0 END) = 1 THEN '续费'
            ELSE '未映射'
        END AS user_layer,
        MAX(CASE WHEN raw_layer = '高净值用户' THEN high_value_tag END) AS high_value_tag
    FROM active_raw
    WHERE channel IS NOT NULL
    GROUP BY period, channel, user_id
),
active_user_channel AS (
    SELECT period, channel, user_id, stage, user_layer, high_value_tag FROM channel_active_users
    UNION ALL
    SELECT period, channel, user_id, stage, user_layer, high_value_tag FROM private_active_users
),
active_layer_expanded AS (
    SELECT period, channel, user_id, stage, user_layer FROM active_user_channel
    UNION ALL
    SELECT
        period, channel, user_id, stage,
        CASE
            WHEN high_value_tag = CONCAT('付费组合品用户-', SUBSTR(CAST(CASE WHEN period = '本期' THEN {{CURRENT_START}} ELSE {{LAST_YEAR_START}} END AS VARCHAR), 1, 4), '年初中毕业') THEN '高净值－当年毕业'
            WHEN high_value_tag = '历史大会员用户_可续购' THEN '高净值－历史大会员可续购'
            WHEN high_value_tag = '历史大会员用户_不可续购' THEN '高净值－历史大会员不可续购'
            ELSE '高净值－其他组合品'
        END
    FROM active_user_channel
    WHERE user_layer = '高净值汇总'
),
order_rows AS (
    SELECT
        p.period,
        CASE WHEN o.business_gmv_attribution = '商业化' THEN 'APP' ELSE '销售' END AS channel,
        o.order_id,
        CAST(o.u_user AS VARCHAR) AS user_id,
        o.business_good_kind_name_level_1,
        o.business_good_kind_name_level_3,
        o.good_name,
        o.good_kind_name_level_3,
        o.good_stage_subject_cnt,
        o.good_stage_subject,
        o.original_amount,
        o.sub_amount
    FROM periods p
    JOIN dws.topic_order_detail o ON o.paid_time_sk BETWEEN p.start_day AND p.end_day
    WHERE o.u_user IS NOT NULL
      AND o.is_test_user = 0
      AND o.original_amount >= 39
      AND o.business_gmv_attribution IN ('商业化', '电销')
),
channel_order_level AS (
    SELECT
        period, channel, order_id, MIN(user_id) AS user_id,
        MAX(CASE WHEN business_good_kind_name_level_1 = '组合品' THEN 1 ELSE 0 END) AS is_combo,
        MAX(CASE WHEN business_good_kind_name_level_1 = '零售商品' THEN 1 ELSE 0 END) AS is_retail,
        MAX(CASE WHEN business_good_kind_name_level_3 = '小初高品' THEN 1 ELSE 0 END) AS is_family,
        MAX(CASE
            WHEN business_good_kind_name_level_3 = '小学品加拓展' THEN 1
            WHEN good_name LIKE '从小学%' AND good_name NOT LIKE '%系列%' THEN 1
            WHEN good_kind_name_level_3 = '拓展课' AND good_stage_subject_cnt = 1
             AND (good_stage_subject REGEXP '1-2-specialCourse'
               OR good_stage_subject REGEXP '1-6-specialCourse'
               OR good_stage_subject REGEXP '1-7-specialCourse') THEN 1
            ELSE 0 END) AS is_from_primary,
        MAX(CASE WHEN original_amount >= 198 AND original_amount < 199 THEN 1 ELSE 0 END) AS is_198,
        MAX(CASE WHEN original_amount >= 498 AND original_amount < 499 THEN 1 ELSE 0 END) AS is_498,
        MAX(CASE WHEN original_amount >= 1000 THEN 1 ELSE 0 END) AS is_1000_plus,
        SUM(sub_amount) AS revenue
    FROM order_rows
    GROUP BY period, channel, order_id
),
private_order_level AS (
    SELECT
        period, '私域整体' AS channel, order_id, MIN(user_id) AS user_id,
        MAX(is_combo) AS is_combo, MAX(is_retail) AS is_retail, MAX(is_family) AS is_family,
        MAX(is_from_primary) AS is_from_primary, MAX(is_198) AS is_198,
        MAX(is_498) AS is_498, MAX(is_1000_plus) AS is_1000_plus, SUM(revenue) AS revenue
    FROM channel_order_level
    GROUP BY period, order_id
),
orders_by_channel AS (
    SELECT period, channel, order_id, user_id, is_combo, is_retail, is_family,
           is_from_primary, is_198, is_498, is_1000_plus, revenue
    FROM channel_order_level
    UNION ALL
    SELECT period, channel, order_id, user_id, is_combo, is_retail, is_family,
           is_from_primary, is_198, is_498, is_1000_plus, revenue
    FROM private_order_level
),
product_orders AS (
    SELECT period, channel, order_id, user_id, revenue, '组合品' AS product FROM orders_by_channel WHERE is_combo = 1
    UNION ALL SELECT period, channel, order_id, user_id, revenue, '零售品' FROM orders_by_channel WHERE is_retail = 1
    UNION ALL SELECT period, channel, order_id, user_id, revenue, '家庭包' FROM orders_by_channel WHERE is_family = 1
    UNION ALL SELECT period, channel, order_id, user_id, revenue, '从小学系列' FROM orders_by_channel WHERE is_from_primary = 1
    UNION ALL SELECT period, channel, order_id, user_id, revenue, '198' FROM orders_by_channel WHERE is_198 = 1
    UNION ALL SELECT period, channel, order_id, user_id, revenue, '498' FROM orders_by_channel WHERE is_498 = 1
    UNION ALL SELECT period, channel, order_id, user_id, revenue, '千元及以上' FROM orders_by_channel WHERE is_1000_plus = 1
),
product_order_audience AS (
    SELECT
        o.period, o.channel, o.order_id, o.user_id, o.revenue, o.product,
        CASE WHEN a.user_id IS NOT NULL THEN o.user_id END AS active_cohort_pay_user_id,
        COALESCE(a.user_layer, '未映射') AS user_layer,
        COALESCE(a.stage, '未知学段') AS stage
    FROM product_orders o
    LEFT JOIN active_user_channel a
      ON o.period = a.period AND o.channel = a.channel AND o.user_id = a.user_id
),
product_order_layer_audience AS (
    SELECT
        o.period, o.channel, o.order_id, o.user_id, o.revenue, o.product,
        CASE WHEN a.user_id IS NOT NULL THEN o.user_id END AS active_cohort_pay_user_id,
        COALESCE(a.user_layer, '未映射') AS user_layer
    FROM product_orders o
    LEFT JOIN active_layer_expanded a
      ON o.period = a.period AND o.channel = a.channel AND o.user_id = a.user_id
),
summary_rows AS (
    SELECT period, channel, order_id, user_id, active_cohort_pay_user_id, revenue,
           '商品' AS dimension_type, product AS dimension_value
    FROM product_order_audience
    UNION ALL
    SELECT period, channel, order_id, user_id, active_cohort_pay_user_id, revenue,
           '用户层级×商品', CONCAT(user_layer, '×', product)
    FROM product_order_layer_audience
    UNION ALL
    SELECT period, channel, order_id, user_id, active_cohort_pay_user_id, revenue,
           '学段×商品', CONCAT(stage, '×', product)
    FROM product_order_audience
),
summary_actual AS (
    SELECT period, channel, dimension_type, dimension_value,
           COUNT(DISTINCT order_id) AS orders,
           COUNT(DISTINCT user_id) AS pay_users,
           COUNT(DISTINCT active_cohort_pay_user_id) AS active_cohort_pay_users,
           SUM(revenue) AS revenue
    FROM summary_rows
    GROUP BY period, channel, dimension_type, dimension_value
),
dimension_values AS (
    SELECT '商品' AS dimension_type, product AS dimension_value FROM products
    UNION ALL
    SELECT '用户层级×商品', CONCAT(u.user_layer, '×', p.product)
    FROM user_layer_values u JOIN products p ON 1 = 1
    UNION ALL
    SELECT '学段×商品', CONCAT(s.stage, '×', p.product)
    FROM stage_values s JOIN products p ON 1 = 1
),
dimension_grid AS (
    SELECT p.period, c.channel, d.dimension_type, d.dimension_value
    FROM periods p JOIN channels c ON 1 = 1 JOIN dimension_values d ON 1 = 1
),
active_dimension_rows AS (
    SELECT a.period, a.channel, a.user_id, '商品' AS dimension_type, p.product AS dimension_value
    FROM active_user_channel a JOIN products p ON 1 = 1
    UNION ALL
    SELECT a.period, a.channel, a.user_id, '用户层级×商品', CONCAT(a.user_layer, '×', p.product)
    FROM active_layer_expanded a JOIN products p ON 1 = 1
    UNION ALL
    SELECT a.period, a.channel, a.user_id, '学段×商品', CONCAT(a.stage, '×', p.product)
    FROM active_user_channel a JOIN products p ON 1 = 1
),
active_denominators AS (
    SELECT period, channel, dimension_type, dimension_value,
           COUNT(DISTINCT user_id) AS active_users
    FROM active_dimension_rows
    GROUP BY period, channel, dimension_type, dimension_value
),
order_audience AS (
    SELECT o.period, o.channel, o.order_id, o.user_id, o.revenue,
           COALESCE(a.user_layer, '未映射') AS user_layer,
           COALESCE(a.stage, '未知学段') AS stage
    FROM orders_by_channel o
    LEFT JOIN active_user_channel a
      ON o.period = a.period AND o.channel = a.channel AND o.user_id = a.user_id
),
order_layer_audience AS (
    SELECT o.period, o.channel, o.order_id, o.user_id, o.revenue,
           COALESCE(a.user_layer, '未映射') AS user_layer
    FROM orders_by_channel o
    LEFT JOIN active_layer_expanded a
      ON o.period = a.period AND o.channel = a.channel AND o.user_id = a.user_id
),
order_denominator_rows AS (
    SELECT o.period, o.channel, o.order_id, o.user_id, o.revenue,
           '商品' AS dimension_type, p.product AS dimension_value
    FROM order_audience o JOIN products p ON 1 = 1
    UNION ALL
    SELECT o.period, o.channel, o.order_id, o.user_id, o.revenue,
           '用户层级×商品', CONCAT(o.user_layer, '×', p.product)
    FROM order_layer_audience o JOIN products p ON 1 = 1
    UNION ALL
    SELECT o.period, o.channel, o.order_id, o.user_id, o.revenue,
           '学段×商品', CONCAT(o.stage, '×', p.product)
    FROM order_audience o JOIN products p ON 1 = 1
),
order_denominators AS (
    SELECT period, channel, dimension_type, dimension_value,
           COUNT(DISTINCT order_id) AS total_orders,
           COUNT(DISTINCT user_id) AS total_pay_users,
           SUM(revenue) AS total_revenue
    FROM order_denominator_rows
    GROUP BY period, channel, dimension_type, dimension_value
),
summary AS (
    SELECT
        g.period, g.channel, g.dimension_type, g.dimension_value,
        COALESCE(s.orders, 0) AS orders,
        COALESCE(s.pay_users, 0) AS pay_users,
        COALESCE(s.active_cohort_pay_users, 0) AS active_cohort_pay_users,
        COALESCE(s.revenue, 0) AS revenue,
        COALESCE(a.active_users, 0) AS active_users,
        COALESCE(o.total_orders, 0) AS total_orders,
        COALESCE(o.total_pay_users, 0) AS total_pay_users,
        COALESCE(o.total_revenue, 0) AS total_revenue
    FROM dimension_grid g
    LEFT JOIN summary_actual s ON g.period=s.period AND g.channel=s.channel
      AND g.dimension_type=s.dimension_type AND g.dimension_value=s.dimension_value
    LEFT JOIN active_denominators a ON g.period=a.period AND g.channel=a.channel
      AND g.dimension_type=a.dimension_type AND g.dimension_value=a.dimension_value
    LEFT JOIN order_denominators o ON g.period=o.period AND g.channel=o.channel
      AND g.dimension_type=o.dimension_type AND g.dimension_value=o.dimension_value
),
metrics AS (
    SELECT period, channel, dimension_type, dimension_value, '订单量' AS metric, CAST(orders AS DOUBLE) AS value FROM summary
    UNION ALL SELECT period, channel, dimension_type, dimension_value, '付费人数', CAST(pay_users AS DOUBLE) FROM summary
    UNION ALL SELECT period, channel, dimension_type, dimension_value, '活跃付费人数', CAST(active_cohort_pay_users AS DOUBLE) FROM summary
    UNION ALL SELECT period, channel, dimension_type, dimension_value, '活跃人数', CAST(active_users AS DOUBLE) FROM summary
    UNION ALL SELECT period, channel, dimension_type, dimension_value, '营收', revenue FROM summary
    UNION ALL SELECT period, channel, dimension_type, dimension_value, '订单占比', orders / NULLIF(total_orders, 0) FROM summary
    UNION ALL SELECT period, channel, dimension_type, dimension_value, '付费人数占比', pay_users / NULLIF(total_pay_users, 0) FROM summary
    UNION ALL SELECT period, channel, dimension_type, dimension_value, '营收占比', revenue / NULLIF(total_revenue, 0) FROM summary
    UNION ALL SELECT period, channel, dimension_type, dimension_value, '转化率', active_cohort_pay_users / NULLIF(active_users, 0) FROM summary
    UNION ALL SELECT period, channel, dimension_type, dimension_value, '客单价', revenue / NULLIF(pay_users, 0) FROM summary
    UNION ALL SELECT period, channel, dimension_type, dimension_value, 'ARPU', revenue / NULLIF(active_users, 0) FROM summary
)
SELECT
    period,
    channel,
    dimension_type,
    dimension_value,
    metric,
    value,
    'v1' AS source_version,
    CURRENT_TIMESTAMP AS data_updated_at,
    'price_basis=original_amount' AS definition_id
FROM metrics
LIMIT 10000
