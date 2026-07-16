WITH periods AS (
    SELECT '本期' AS period, {{CURRENT_START}} AS start_day, {{CURRENT_END}} AS end_day
    UNION ALL SELECT '去年同期', {{LAST_YEAR_START}}, {{LAST_YEAR_END}}
),
channels AS (
    SELECT '私域整体' AS channel UNION ALL SELECT 'APP' UNION ALL SELECT '销售'
),
fixed_high_value_layers AS (
    SELECT '高净值汇总' AS user_layer
    UNION ALL SELECT '高净值－当年毕业'
    UNION ALL SELECT '高净值－历史大会员可续购'
    UNION ALL SELECT '高净值－历史大会员不可续购'
    UNION ALL SELECT '高净值－其他组合品'
),
unknown_high_value_layers AS (
    SELECT '高净值－未知标签' AS user_layer
),
high_value_layers AS (
    SELECT user_layer FROM fixed_high_value_layers
    UNION ALL SELECT user_layer FROM unknown_high_value_layers
),
stage_values AS (
    SELECT '1–3 年级' AS stage UNION ALL SELECT '4–6 年级'
    UNION ALL SELECT '初中' UNION ALL SELECT '高中' UNION ALL SELECT '未知学段'
),
products AS (
    SELECT '全部' AS product UNION ALL SELECT '组合品' UNION ALL SELECT '零售品'
    UNION ALL SELECT '家庭包' UNION ALL SELECT '从小学系列' UNION ALL SELECT '198'
    UNION ALL SELECT '498' UNION ALL SELECT '千元及以上'
),
source_pool_raw AS (
    SELECT
        p.period,
        CAST(m.u_user AS VARCHAR) AS user_id,
        CASE
            WHEN m.user_strategy_tag_month REGEXP CONCAT(
                '付费组合品用户-', SUBSTR(CAST(p.start_day AS VARCHAR), 1, 4), '年初中毕业'
            ) THEN '高净值－当年毕业'
            WHEN m.user_strategy_tag_month REGEXP '历史大会员用户_可续购'
                THEN '高净值－历史大会员可续购'
            WHEN m.user_strategy_tag_month REGEXP '历史大会员用户_不可续购'
                THEN '高净值－历史大会员不可续购'
            WHEN m.user_strategy_tag_month REGEXP '付费组合品用户|付费加购品用户|付费零售品用户'
                THEN '高净值－其他组合品'
            ELSE '高净值－未知标签'
        END AS detail_layer,
        m.user_strategy_tag_month
    FROM periods p
    JOIN dws.topic_user_active_detail_month m
      ON m.`month` = CAST(SUBSTR(CAST(p.start_day AS VARCHAR), 1, 6) AS INT)
    WHERE m.u_user IS NOT NULL
      AND (
           m.user_strategy_tag_month IN (
               '历史大会员用户_可续购',
               '历史大会员用户_不可续购'
           )
        OR m.user_strategy_tag_month REGEXP '^(付费组合品用户|付费加购品用户|付费零售品用户)(-|$)'
      )
),
source_pool_ranked AS (
    SELECT
        period, user_id, detail_layer,
        ROW_NUMBER() OVER(
            PARTITION BY period, user_id
            ORDER BY
                CASE WHEN detail_layer = '高净值－未知标签' THEN 2 ELSE 1 END,
                user_strategy_tag_month DESC
        ) AS fact_rank
    FROM source_pool_raw
),
source_pool AS (
    SELECT period, user_id, detail_layer
    FROM source_pool_ranked
    WHERE fact_rank = 1
),
attribution_order_lines AS (
    SELECT
        p.period,
        s.user_id,
        o.order_id,
        o.paid_time AS source_time,
        CASE
            WHEN o.business_gmv_attribution = '商业化' THEN 2
            WHEN o.business_gmv_attribution = '电销' THEN 1
        END AS channel_priority,
        CASE
            WHEN o.grade_name_month IN ('一年级','二年级','三年级') THEN 5
            WHEN o.grade_name_month IN ('四年级','五年级','六年级') THEN 4
            WHEN o.grade_name_month IN ('七年级','八年级','九年级','初一','初二','初三') THEN 3
            WHEN o.grade_name_month IN ('高一','高二','高三','十年级') THEN 2
            ELSE 1
        END AS stage_priority
    FROM source_pool s
    JOIN periods p ON s.period = p.period
    JOIN dws.topic_order_detail o
      ON CAST(o.u_user AS VARCHAR) = s.user_id
     AND o.paid_time_sk < p.start_day
    WHERE o.u_user IS NOT NULL
      AND o.is_test_user = 0
      AND o.original_amount >= 39
      AND o.business_gmv_attribution IN ('商业化', '电销')
),
attribution_order_rows AS (
    SELECT
        period,
        user_id,
        order_id,
        MAX(source_time) AS source_time,
        CASE MAX(channel_priority)
            WHEN 2 THEN 'APP'
            WHEN 1 THEN '销售'
        END AS channel,
        CASE MAX(stage_priority)
            WHEN 5 THEN '1–3 年级'
            WHEN 4 THEN '4–6 年级'
            WHEN 3 THEN '初中'
            WHEN 2 THEN '高中'
            ELSE '未知学段'
        END AS stage
    FROM attribution_order_lines
    GROUP BY period, user_id, order_id
),
attribution_ranked AS (
    SELECT
        period, user_id, order_id, source_time, channel, stage,
        ROW_NUMBER() OVER(
            PARTITION BY period, user_id
            ORDER BY source_time DESC, order_id DESC
        ) AS source_rank
    FROM attribution_order_rows
),
attributed_source_users AS (
    SELECT period, user_id, channel, stage
    FROM attribution_ranked
    WHERE source_rank = 1
),
source_users AS (
    SELECT
        s.period, '私域整体' AS channel, s.user_id,
        COALESCE(a.stage, '未知学段') AS stage, s.detail_layer
    FROM source_pool s
    LEFT JOIN attributed_source_users a
      ON s.period = a.period AND s.user_id = a.user_id
    UNION ALL
    SELECT
        s.period, a.channel, s.user_id, a.stage, s.detail_layer
    FROM source_pool s
    JOIN attributed_source_users a
      ON s.period = a.period AND s.user_id = a.user_id
),
active_users AS (
    SELECT DISTINCT s.period, s.channel, s.user_id
    FROM source_users s
    JOIN periods p ON s.period = p.period
    JOIN aws.business_active_user_last_14_day a
      ON CAST(a.u_user AS VARCHAR) = s.user_id
     AND a.day BETWEEN p.start_day AND p.end_day
    WHERE a.u_user IS NOT NULL
),
layer_audience AS (
    SELECT period, channel, user_id, stage, '高净值汇总' AS user_layer
    FROM source_users
    UNION ALL
    SELECT period, channel, user_id, stage, detail_layer
    FROM source_users
),
order_line_rows AS (
    SELECT
        p.period,
        CAST(o.u_user AS VARCHAR) AS user_id,
        o.order_id,
        o.sku_group_good_id,
        o.business_good_kind_name_level_1,
        o.business_good_kind_name_level_3,
        o.good_name,
        o.good_kind_name_level_3,
        o.good_stage_subject_cnt,
        o.good_stage_subject,
        o.original_amount,
        o.sub_amount AS revenue
    FROM periods p
    JOIN dws.topic_order_detail o
      ON o.paid_time_sk BETWEEN p.start_day AND p.end_day
    WHERE o.u_user IS NOT NULL
      AND o.is_test_user = 0
      AND o.original_amount >= 39
      AND o.business_gmv_attribution IN ('商业化', '电销')
),
product_order_lines AS (
    SELECT period, user_id, order_id, sku_group_good_id, revenue, '全部' AS product
    FROM order_line_rows
    UNION ALL
    SELECT period, user_id, order_id, sku_group_good_id, revenue, '组合品'
    FROM order_line_rows WHERE business_good_kind_name_level_1 = '组合品'
    UNION ALL
    SELECT period, user_id, order_id, sku_group_good_id, revenue, '零售品'
    FROM order_line_rows WHERE business_good_kind_name_level_1 = '零售商品'
    UNION ALL
    SELECT period, user_id, order_id, sku_group_good_id, revenue, '家庭包'
    FROM order_line_rows WHERE business_good_kind_name_level_3 = '小初高品'
    UNION ALL
    SELECT period, user_id, order_id, sku_group_good_id, revenue, '从小学系列'
    FROM order_line_rows
    WHERE business_good_kind_name_level_3 = '小学品加拓展'
       OR (good_name LIKE '从小学%' AND good_name NOT LIKE '%系列%')
       OR (
            good_kind_name_level_3 = '拓展课'
        AND good_stage_subject_cnt = 1
        AND (
               good_stage_subject REGEXP '1-2-specialCourse'
            OR good_stage_subject REGEXP '1-6-specialCourse'
            OR good_stage_subject REGEXP '1-7-specialCourse'
        )
       )
    UNION ALL
    SELECT period, user_id, order_id, sku_group_good_id, revenue, '198'
    FROM order_line_rows WHERE original_amount >= 198 AND original_amount < 199
    UNION ALL
    SELECT period, user_id, order_id, sku_group_good_id, revenue, '498'
    FROM order_line_rows WHERE original_amount >= 498 AND original_amount < 499
    UNION ALL
    SELECT period, user_id, order_id, sku_group_good_id, revenue, '千元及以上'
    FROM order_line_rows WHERE original_amount >= 1000
),
audience_order_lines AS (
    SELECT
        s.period, s.channel, s.user_id, s.stage, s.detail_layer,
        o.order_id, o.sku_group_good_id, o.product, o.revenue
    FROM source_users s
    JOIN product_order_lines o
      ON s.period = o.period AND s.user_id = o.user_id
),
layer_grid AS (
    SELECT p.period, c.channel, u.user_layer
    FROM periods p CROSS JOIN channels c CROSS JOIN high_value_layers u
),
stage_grid AS (
    SELECT p.period, c.channel, s.stage
    FROM periods p CROSS JOIN channels c CROSS JOIN stage_values s
),
product_grid AS (
    SELECT p.period, c.channel, x.product
    FROM periods p CROSS JOIN channels c CROSS JOIN products x
),
layer_actual AS (
    SELECT
        s.period, s.channel, s.user_layer,
        COUNT(DISTINCT s.user_id) AS source_users,
        COUNT(DISTINCT a.user_id) AS active_users,
        COUNT(DISTINCT o.user_id) AS pay_users,
        COUNT(DISTINCT o.order_id) AS orders,
        SUM(o.revenue) AS revenue
    FROM layer_audience s
    LEFT JOIN active_users a
      ON s.period = a.period AND s.channel = a.channel AND s.user_id = a.user_id
    LEFT JOIN audience_order_lines o
      ON s.period = o.period AND s.channel = o.channel AND s.user_id = o.user_id
     AND o.product = '全部'
    GROUP BY s.period, s.channel, s.user_layer
),
stage_actual AS (
    SELECT
        s.period, s.channel, s.stage,
        COUNT(DISTINCT s.user_id) AS source_users,
        COUNT(DISTINCT a.user_id) AS active_users,
        COUNT(DISTINCT o.user_id) AS pay_users,
        COUNT(DISTINCT o.order_id) AS orders,
        SUM(o.revenue) AS revenue
    FROM source_users s
    LEFT JOIN active_users a
      ON s.period = a.period AND s.channel = a.channel AND s.user_id = a.user_id
    LEFT JOIN audience_order_lines o
      ON s.period = o.period AND s.channel = o.channel AND s.user_id = o.user_id
     AND o.product = '全部'
    GROUP BY s.period, s.channel, s.stage
),
product_actual AS (
    SELECT
        s.period, s.channel, p.product,
        COUNT(DISTINCT s.user_id) AS source_users,
        COUNT(DISTINCT a.user_id) AS active_users,
        COUNT(DISTINCT o.user_id) AS pay_users,
        COUNT(DISTINCT o.order_id) AS orders,
        SUM(o.revenue) AS revenue
    FROM source_users s
    CROSS JOIN products p
    LEFT JOIN active_users a
      ON s.period = a.period AND s.channel = a.channel AND s.user_id = a.user_id
    LEFT JOIN audience_order_lines o
      ON s.period = o.period AND s.channel = o.channel AND s.user_id = o.user_id
     AND p.product = o.product
    GROUP BY s.period, s.channel, p.product
),
layer_combo_actual AS (
    SELECT
        s.period, s.channel, s.user_layer,
        COUNT(DISTINCT o.user_id) AS combo_pay_users,
        COUNT(DISTINCT o.order_id) AS combo_orders,
        SUM(o.revenue) AS combo_revenue
    FROM layer_audience s
    JOIN audience_order_lines o
      ON s.period = o.period AND s.channel = o.channel AND s.user_id = o.user_id
     AND o.product = '组合品'
    GROUP BY s.period, s.channel, s.user_layer
),
stage_combo_actual AS (
    SELECT
        s.period, s.channel, s.stage,
        COUNT(DISTINCT o.user_id) AS combo_pay_users,
        COUNT(DISTINCT o.order_id) AS combo_orders,
        SUM(o.revenue) AS combo_revenue
    FROM source_users s
    JOIN audience_order_lines o
      ON s.period = o.period AND s.channel = o.channel AND s.user_id = o.user_id
     AND o.product = '组合品'
    GROUP BY s.period, s.channel, s.stage
),
layer_summary AS (
    SELECT
        g.period, g.channel, g.user_layer,
        COALESCE(a.source_users, 0) AS source_users,
        COALESCE(a.active_users, 0) AS active_users,
        COALESCE(a.pay_users, 0) AS pay_users,
        COALESCE(a.orders, 0) AS orders,
        COALESCE(a.revenue, 0) AS revenue,
        COALESCE(c.combo_pay_users, 0) AS combo_pay_users,
        COALESCE(c.combo_orders, 0) AS combo_orders,
        COALESCE(c.combo_revenue, 0) AS combo_revenue
    FROM layer_grid g
    LEFT JOIN layer_actual a
      ON g.period = a.period AND g.channel = a.channel AND g.user_layer = a.user_layer
    LEFT JOIN layer_combo_actual c
      ON g.period = c.period AND g.channel = c.channel AND g.user_layer = c.user_layer
),
stage_summary AS (
    SELECT
        g.period, g.channel, g.stage,
        COALESCE(a.source_users, 0) AS source_users,
        COALESCE(a.active_users, 0) AS active_users,
        COALESCE(a.pay_users, 0) AS pay_users,
        COALESCE(a.orders, 0) AS orders,
        COALESCE(a.revenue, 0) AS revenue,
        COALESCE(c.combo_pay_users, 0) AS combo_pay_users,
        COALESCE(c.combo_orders, 0) AS combo_orders,
        COALESCE(c.combo_revenue, 0) AS combo_revenue
    FROM stage_grid g
    LEFT JOIN stage_actual a
      ON g.period = a.period AND g.channel = a.channel AND g.stage = a.stage
    LEFT JOIN stage_combo_actual c
      ON g.period = c.period AND g.channel = c.channel AND g.stage = c.stage
),
product_summary AS (
    SELECT
        g.period, g.channel, g.product,
        COALESCE(a.source_users, 0) AS source_users,
        COALESCE(a.active_users, 0) AS active_users,
        COALESCE(a.pay_users, 0) AS pay_users,
        COALESCE(a.orders, 0) AS orders,
        COALESCE(a.revenue, 0) AS revenue
    FROM product_grid g
    LEFT JOIN product_actual a
      ON g.period = a.period AND g.channel = a.channel AND g.product = a.product
),
private_revenue AS (
    SELECT p.period, SUM(o.sub_amount) AS revenue
    FROM periods p
    JOIN dws.topic_order_detail o
      ON o.paid_time_sk BETWEEN p.start_day AND p.end_day
    WHERE o.u_user IS NOT NULL
      AND o.is_test_user = 0
      AND o.original_amount >= 39
      AND o.business_gmv_attribution IN ('商业化', '电销')
    GROUP BY p.period
),
layer_metrics AS (
    SELECT s.period, s.channel, s.user_layer AS dimension_value, '来源用户数' AS metric, CAST(s.source_users AS DOUBLE) AS value FROM layer_summary s
    UNION ALL SELECT period, channel, user_layer, '活跃人数', CAST(active_users AS DOUBLE) FROM layer_summary
    UNION ALL SELECT period, channel, user_layer, '付费人数', CAST(pay_users AS DOUBLE) FROM layer_summary
    UNION ALL SELECT period, channel, user_layer, '订单量', CAST(orders AS DOUBLE) FROM layer_summary
    UNION ALL SELECT period, channel, user_layer, '营收', revenue FROM layer_summary
    UNION ALL SELECT period, channel, user_layer, '付费转化率', pay_users / NULLIF(active_users, 0) FROM layer_summary
    UNION ALL SELECT period, channel, user_layer, '客单价', revenue / NULLIF(pay_users, 0) FROM layer_summary
    UNION ALL SELECT period, channel, user_layer, 'ARPU', revenue / NULLIF(active_users, 0) FROM layer_summary
    UNION ALL SELECT period, channel, user_layer, '组合品付费人数', CAST(combo_pay_users AS DOUBLE) FROM layer_summary
    UNION ALL SELECT period, channel, user_layer, '组合品订单量', CAST(combo_orders AS DOUBLE) FROM layer_summary
    UNION ALL SELECT period, channel, user_layer, '组合品营收', combo_revenue FROM layer_summary
    UNION ALL SELECT period, channel, user_layer, '组合品转化率', combo_pay_users / NULLIF(active_users, 0) FROM layer_summary
    UNION ALL
    SELECT s.period, s.channel, s.user_layer, '高净值营收占私域营收比例', s.revenue / NULLIF(p.revenue, 0)
    FROM layer_summary s JOIN private_revenue p ON s.period = p.period
),
stage_metrics AS (
    SELECT s.period, s.channel, s.stage AS dimension_value, '来源用户数' AS metric, CAST(s.source_users AS DOUBLE) AS value FROM stage_summary s
    UNION ALL SELECT period, channel, stage, '活跃人数', CAST(active_users AS DOUBLE) FROM stage_summary
    UNION ALL SELECT period, channel, stage, '付费人数', CAST(pay_users AS DOUBLE) FROM stage_summary
    UNION ALL SELECT period, channel, stage, '订单量', CAST(orders AS DOUBLE) FROM stage_summary
    UNION ALL SELECT period, channel, stage, '营收', revenue FROM stage_summary
    UNION ALL SELECT period, channel, stage, '付费转化率', pay_users / NULLIF(active_users, 0) FROM stage_summary
    UNION ALL SELECT period, channel, stage, '客单价', revenue / NULLIF(pay_users, 0) FROM stage_summary
    UNION ALL SELECT period, channel, stage, 'ARPU', revenue / NULLIF(active_users, 0) FROM stage_summary
    UNION ALL SELECT period, channel, stage, '组合品付费人数', CAST(combo_pay_users AS DOUBLE) FROM stage_summary
    UNION ALL SELECT period, channel, stage, '组合品订单量', CAST(combo_orders AS DOUBLE) FROM stage_summary
    UNION ALL SELECT period, channel, stage, '组合品营收', combo_revenue FROM stage_summary
    UNION ALL SELECT period, channel, stage, '组合品转化率', combo_pay_users / NULLIF(active_users, 0) FROM stage_summary
    UNION ALL
    SELECT s.period, s.channel, s.stage, '高净值营收占私域营收比例', s.revenue / NULLIF(p.revenue, 0)
    FROM stage_summary s JOIN private_revenue p ON s.period = p.period
),
product_metrics AS (
    SELECT s.period, s.channel, s.product AS dimension_value, '来源用户数' AS metric, CAST(s.source_users AS DOUBLE) AS value FROM product_summary s
    UNION ALL SELECT period, channel, product, '活跃人数', CAST(active_users AS DOUBLE) FROM product_summary
    UNION ALL SELECT period, channel, product, '付费人数', CAST(pay_users AS DOUBLE) FROM product_summary
    UNION ALL SELECT period, channel, product, '订单量', CAST(orders AS DOUBLE) FROM product_summary
    UNION ALL SELECT period, channel, product, '营收', revenue FROM product_summary
    UNION ALL SELECT period, channel, product, '付费转化率', pay_users / NULLIF(active_users, 0) FROM product_summary
    UNION ALL SELECT period, channel, product, '客单价', revenue / NULLIF(pay_users, 0) FROM product_summary
    UNION ALL SELECT period, channel, product, 'ARPU', revenue / NULLIF(active_users, 0) FROM product_summary
    UNION ALL
    SELECT s.period, s.channel, s.product, '高净值营收占私域营收比例', s.revenue / NULLIF(p.revenue, 0)
    FROM product_summary s JOIN private_revenue p ON s.period = p.period
    UNION ALL SELECT period, channel, product, '组合品付费人数', CAST(pay_users AS DOUBLE) FROM product_summary WHERE product = '组合品'
    UNION ALL SELECT period, channel, product, '组合品订单量', CAST(orders AS DOUBLE) FROM product_summary WHERE product = '组合品'
    UNION ALL SELECT period, channel, product, '组合品营收', revenue FROM product_summary WHERE product = '组合品'
    UNION ALL SELECT period, channel, product, '组合品转化率', pay_users / NULLIF(active_users, 0) FROM product_summary WHERE product = '组合品'
),
independent_metrics AS (
    SELECT period, channel, '高净值层级' AS dimension_type, dimension_value, metric, value FROM layer_metrics
    UNION ALL
    SELECT period, channel, '学段' AS dimension_type, dimension_value, metric, value FROM stage_metrics
    UNION ALL
    SELECT period, channel, '商品' AS dimension_type, dimension_value, metric, value FROM product_metrics
),
output_rows AS (
    SELECT
        period, channel, dimension_type, dimension_value, metric, value,
        'v5;monthly_tag_pool;order_level_history_attribution' AS source_version,
        CURRENT_TIMESTAMP AS data_updated_at,
        'high_value.monthly_tag_pool_order_history.v5' AS definition_id
    FROM independent_metrics
)
SELECT
    period, channel, dimension_type, dimension_value, metric, value,
    source_version, data_updated_at, definition_id
FROM output_rows
LIMIT 10000
