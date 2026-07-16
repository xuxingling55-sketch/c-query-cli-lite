WITH periods AS (
    SELECT '本期' AS period, {{CURRENT_START}} AS start_day, {{CURRENT_END}} AS end_day
    UNION ALL
    SELECT '去年同期', {{LAST_YEAR_START}}, {{LAST_YEAR_END}}
),
active_raw AS (
    SELECT
        p.period,
        CAST(a.u_user AS VARCHAR) AS user_id,
        CASE
            WHEN a.business_gmv_attribution = '商业化' THEN 'APP'
            WHEN a.business_gmv_attribution = '电销' THEN '销售'
        END AS channel,
        CASE
            WHEN a.grade_name_month IN ('一年级','二年级','三年级') THEN '1–3 年级'
            WHEN a.grade_name_month IN ('四年级','五年级','六年级') THEN '4–6 年级'
            WHEN a.grade_name_month IN ('七年级','八年级','九年级','初一','初二','初三') THEN '初中'
            WHEN a.grade_name_month IN ('高一','高二','高三','十年级') THEN '高中'
            ELSE '未知学段'
        END AS stage,
        COALESCE(a.business_user_pay_status_statistics_month, '') AS raw_layer,
        a.user_strategy_tag_level2_month AS high_value_tag,
        COALESCE(a.normal_price_amount, 0) AS pay_amount
    FROM periods p
    JOIN aws.business_active_user_last_14_day a
      ON a.day BETWEEN p.start_day AND p.end_day
    WHERE a.u_user IS NOT NULL
),
active_user_channel AS (
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
        MAX(CASE WHEN raw_layer = '高净值用户' THEN high_value_tag END) AS high_value_tag,
        SUM(pay_amount) AS pay_amount
    FROM active_raw
    WHERE channel IS NOT NULL
    GROUP BY period, channel, user_id
    UNION ALL
    SELECT
        period,
        '私域整体',
        user_id,
        CASE
            WHEN MAX(CASE WHEN stage = '1–3 年级' THEN 1 ELSE 0 END) = 1 THEN '1–3 年级'
            WHEN MAX(CASE WHEN stage = '4–6 年级' THEN 1 ELSE 0 END) = 1 THEN '4–6 年级'
            WHEN MAX(CASE WHEN stage = '初中' THEN 1 ELSE 0 END) = 1 THEN '初中'
            WHEN MAX(CASE WHEN stage = '高中' THEN 1 ELSE 0 END) = 1 THEN '高中'
            ELSE '未知学段'
        END,
        CASE
            WHEN MAX(CASE WHEN raw_layer = '高净值用户' THEN 1 ELSE 0 END) = 1 THEN '高净值汇总'
            WHEN MAX(CASE WHEN raw_layer = '新增' THEN 1 ELSE 0 END) = 1 THEN '新增'
            WHEN MAX(CASE WHEN raw_layer = '老未' THEN 1 ELSE 0 END) = 1 THEN '老未'
            WHEN MAX(CASE WHEN raw_layer = '续费用户' THEN 1 ELSE 0 END) = 1 THEN '续费'
            ELSE '未映射'
        END,
        MAX(CASE WHEN raw_layer = '高净值用户' THEN high_value_tag END),
        SUM(pay_amount)
    FROM active_raw
    WHERE channel IS NOT NULL
    GROUP BY period, user_id
),
layer_expanded AS (
    SELECT period, channel, user_id, stage, user_layer, pay_amount
    FROM active_user_channel
    UNION ALL
    SELECT
        period,
        channel,
        user_id,
        stage,
        CASE
            WHEN high_value_tag = CONCAT('付费组合品用户-', SUBSTR(CAST(CASE WHEN period = '本期' THEN {{CURRENT_START}} ELSE {{LAST_YEAR_START}} END AS VARCHAR), 1, 4), '年初中毕业')
                THEN '高净值－当年毕业'
            WHEN high_value_tag = '历史大会员用户_可续购' THEN '高净值－历史大会员可续购'
            WHEN high_value_tag = '历史大会员用户_不可续购' THEN '高净值－历史大会员不可续购'
            ELSE '高净值－其他组合品'
        END,
        pay_amount
    FROM active_user_channel
    WHERE user_layer = '高净值汇总'
),
combo_order_rows AS (
    SELECT
        p.period,
        CASE
            WHEN o.business_gmv_attribution = '商业化' THEN 'APP'
            WHEN o.business_gmv_attribution = '电销' THEN '销售'
        END AS channel,
        CAST(o.u_user AS VARCHAR) AS user_id,
        o.order_id,
        o.sub_amount
    FROM periods p
    JOIN dws.topic_order_detail o
      ON o.paid_time_sk BETWEEN p.start_day AND p.end_day
    WHERE o.u_user IS NOT NULL
      AND o.is_test_user = 0
      AND o.original_amount >= 39
      AND o.business_gmv_attribution IN ('商业化', '电销')
      AND o.business_good_kind_name_level_1 = '组合品'
),
combo_users AS (
    SELECT period, channel, user_id,
           COUNT(DISTINCT order_id) AS combo_orders,
           SUM(sub_amount) AS combo_revenue
    FROM combo_order_rows
    GROUP BY period, channel, user_id
    UNION ALL
    SELECT period, '私域整体', user_id,
           COUNT(DISTINCT order_id), SUM(sub_amount)
    FROM combo_order_rows
    GROUP BY period, user_id
),
dimension_rows AS (
    SELECT period, channel, user_id, '用户层级' AS dimension_type,
           user_layer AS dimension_value, pay_amount
    FROM layer_expanded
    WHERE user_layer <> '未映射'
    UNION ALL
    SELECT period, channel, user_id, '学段', stage, pay_amount
    FROM active_user_channel
    WHERE stage <> '未知学段'
    UNION ALL
    SELECT period, channel, user_id, '用户层级×学段', CONCAT(user_layer, '×', stage), pay_amount
    FROM layer_expanded
    WHERE user_layer <> '未映射' AND stage <> '未知学段'
),
summary AS (
    SELECT
        d.period,
        d.channel,
        d.dimension_type,
        d.dimension_value,
        COUNT(DISTINCT d.user_id) AS active_users,
        COUNT(DISTINCT CASE WHEN d.pay_amount > 0 THEN d.user_id END) AS pay_users,
        SUM(d.pay_amount) AS pay_amount,
        COUNT(DISTINCT CASE WHEN c.combo_orders > 0 THEN d.user_id END) AS combo_pay_users,
        SUM(COALESCE(c.combo_orders, 0)) AS combo_orders,
        SUM(COALESCE(c.combo_revenue, 0)) AS combo_revenue
    FROM dimension_rows d
    LEFT JOIN combo_users c
      ON d.period = c.period AND d.channel = c.channel AND d.user_id = c.user_id
    GROUP BY d.period, d.channel, d.dimension_type, d.dimension_value
),
channel_totals AS (
    SELECT period, channel,
           COUNT(DISTINCT user_id) AS active_users,
           COUNT(DISTINCT CASE WHEN pay_amount > 0 THEN user_id END) AS pay_users,
           SUM(pay_amount) AS pay_amount
    FROM active_user_channel
    GROUP BY period, channel
),
metrics AS (
    SELECT period, channel, dimension_type, dimension_value, '活跃人数' AS metric, CAST(active_users AS DOUBLE) AS value FROM summary
    UNION ALL SELECT period, channel, dimension_type, dimension_value, '付费人数', CAST(pay_users AS DOUBLE) FROM summary
    UNION ALL SELECT period, channel, dimension_type, dimension_value, '付费金额', pay_amount FROM summary
    UNION ALL SELECT period, channel, dimension_type, dimension_value, '付费转化率', pay_users / NULLIF(active_users, 0) FROM summary
    UNION ALL SELECT period, channel, dimension_type, dimension_value, '客单价', pay_amount / NULLIF(pay_users, 0) FROM summary
    UNION ALL SELECT period, channel, dimension_type, dimension_value, 'ARPU', pay_amount / NULLIF(active_users, 0) FROM summary
    UNION ALL SELECT s.period, s.channel, s.dimension_type, s.dimension_value, '活跃人数占比', s.active_users / NULLIF(t.active_users, 0) FROM summary s JOIN channel_totals t ON s.period=t.period AND s.channel=t.channel
    UNION ALL SELECT s.period, s.channel, s.dimension_type, s.dimension_value, '付费人数占比', s.pay_users / NULLIF(t.pay_users, 0) FROM summary s JOIN channel_totals t ON s.period=t.period AND s.channel=t.channel
    UNION ALL SELECT s.period, s.channel, s.dimension_type, s.dimension_value, '营收占比', s.pay_amount / NULLIF(t.pay_amount, 0) FROM summary s JOIN channel_totals t ON s.period=t.period AND s.channel=t.channel
    UNION ALL SELECT period, channel, dimension_type, dimension_value, '组合品付费人数', CAST(combo_pay_users AS DOUBLE) FROM summary
    UNION ALL SELECT period, channel, dimension_type, dimension_value, '组合品订单量', CAST(combo_orders AS DOUBLE) FROM summary
    UNION ALL SELECT period, channel, dimension_type, dimension_value, '组合品营收', combo_revenue FROM summary
    UNION ALL SELECT period, channel, dimension_type, dimension_value, '组合品转化率', combo_pay_users / NULLIF(active_users, 0) FROM summary
    UNION ALL SELECT period, channel, dimension_type, dimension_value, '组合品客单价', combo_revenue / NULLIF(combo_pay_users, 0) FROM summary
    UNION ALL SELECT period, channel, dimension_type, dimension_value, '组合品ARPU', combo_revenue / NULLIF(active_users, 0) FROM summary
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
    'user_stage.active_and_combo.v1' AS definition_id
FROM metrics
LIMIT 10000
