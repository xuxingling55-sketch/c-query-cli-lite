WITH periods AS (
    SELECT '本期' AS period, {{CURRENT_START}} AS start_day, {{CURRENT_END}} AS end_day
    UNION ALL
    SELECT '去年同期', {{LAST_YEAR_START}}, {{LAST_YEAR_END}}
),
raw AS (
    SELECT
        p.period,
        CAST(a.u_user AS VARCHAR) AS user_id,
        CASE
            WHEN a.business_gmv_attribution = '商业化' THEN 'APP'
            WHEN a.business_gmv_attribution = '电销' THEN '销售'
        END AS channel,
        COALESCE(a.normal_price_amount, 0) AS pay_amount
    FROM periods p
    JOIN aws.business_active_user_last_14_day a
      ON a.day BETWEEN p.start_day AND p.end_day
    WHERE a.u_user IS NOT NULL
),
user_channel AS (
    SELECT period, channel, user_id, SUM(pay_amount) AS pay_amount
    FROM raw
    WHERE channel IS NOT NULL
    GROUP BY period, channel, user_id
    UNION ALL
    SELECT period, '私域整体', user_id, SUM(pay_amount)
    FROM raw
    WHERE channel IS NOT NULL
    GROUP BY period, user_id
),
summary AS (
    SELECT
        period,
        channel,
        COUNT(DISTINCT user_id) AS active_users,
        COUNT(DISTINCT CASE WHEN pay_amount > 0 THEN user_id END) AS pay_users,
        SUM(pay_amount) AS pay_amount
    FROM user_channel
    GROUP BY period, channel
),
metrics AS (
    SELECT period, channel, '活跃人数' AS metric, CAST(active_users AS DOUBLE) AS value FROM summary
    UNION ALL SELECT period, channel, '付费人数', CAST(pay_users AS DOUBLE) FROM summary
    UNION ALL SELECT period, channel, '付费金额', pay_amount FROM summary
    UNION ALL SELECT period, channel, '付费转化率', pay_users / NULLIF(active_users, 0) FROM summary
    UNION ALL SELECT period, channel, '客单价', pay_amount / NULLIF(pay_users, 0) FROM summary
    UNION ALL SELECT period, channel, 'ARPU', pay_amount / NULLIF(active_users, 0) FROM summary
    UNION ALL
    SELECT s.period, s.channel, '活跃人数占比', s.active_users / NULLIF(t.active_users, 0)
    FROM summary s JOIN summary t ON s.period = t.period AND t.channel = '私域整体'
    UNION ALL
    SELECT s.period, s.channel, '付费人数占比', s.pay_users / NULLIF(t.pay_users, 0)
    FROM summary s JOIN summary t ON s.period = t.period AND t.channel = '私域整体'
    UNION ALL
    SELECT s.period, s.channel, '营收占比', s.pay_amount / NULLIF(t.pay_amount, 0)
    FROM summary s JOIN summary t ON s.period = t.period AND t.channel = '私域整体'
)
SELECT
    period,
    channel,
    '渠道' AS dimension_type,
    channel AS dimension_value,
    metric,
    value,
    'v1' AS source_version,
    CURRENT_TIMESTAMP AS data_updated_at,
    'active_efficiency.business_active_user_last_14_day.v1' AS definition_id
FROM metrics
LIMIT 10000
