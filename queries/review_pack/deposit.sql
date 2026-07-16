WITH strategy_periods AS (
    SELECT '本期' AS period,
           {{DEPOSIT_SOURCE_START}} AS source_start, {{DEPOSIT_SOURCE_END}} AS source_end
    UNION ALL
    SELECT '去年同期',
           CAST(DATE_FORMAT(DATE_SUB(STR_TO_DATE(CAST({{DEPOSIT_SOURCE_START}} AS VARCHAR), '%Y%m%d'), INTERVAL 1 YEAR), '%Y%m%d') AS INT),
           CAST(DATE_FORMAT(DATE_SUB(STR_TO_DATE(CAST({{DEPOSIT_SOURCE_END}} AS VARCHAR), '%Y%m%d'), INTERVAL 1 YEAR), '%Y%m%d') AS INT)
),
deposit_source_rows AS (
    SELECT
        p.period,
        CASE WHEN o.business_gmv_attribution = '商业化' THEN 'APP' ELSE '销售' END AS channel,
        CAST(o.u_user AS VARCHAR) AS user_id,
        o.order_id,
        MIN(o.paid_time) AS first_deposit_time,
        SUM(o.sub_amount) AS deposit_amount,
        CASE
            WHEN o.business_user_pay_status_statistics IN ('新增', '新用户') THEN '新增'
            WHEN o.business_user_pay_status_statistics = '老未' THEN '老未'
            WHEN o.business_user_pay_status_statistics IN ('续费用户', '续费') THEN '续费'
            WHEN o.business_user_pay_status_statistics = '高净值用户' THEN '高净值汇总'
            ELSE '未映射'
        END AS user_layer,
        CASE
            WHEN o.business_user_pay_status_statistics = '高净值用户'
             AND o.user_strategy_tag_day LIKE CONCAT('付费组合品用户-', SUBSTR(CAST(CASE WHEN p.period='本期' THEN {{CURRENT_START}} ELSE {{LAST_YEAR_START}} END AS VARCHAR), 1, 4), '年初中毕业')
                THEN '高净值－当年毕业'
            WHEN o.business_user_pay_status_statistics = '高净值用户'
             AND o.user_strategy_tag_day = '历史大会员用户_可续购'
                THEN '高净值－历史大会员可续购'
            WHEN o.business_user_pay_status_statistics = '高净值用户'
             AND o.user_strategy_tag_day = '历史大会员用户_不可续购'
                THEN '高净值－历史大会员不可续购'
            WHEN o.business_user_pay_status_statistics = '高净值用户'
                THEN '高净值－其他组合品'
            ELSE '非高净值'
        END AS high_value_layer
    FROM strategy_periods p
    JOIN dws.topic_order_detail o ON o.paid_time_sk BETWEEN p.source_start AND p.source_end
    WHERE o.u_user IS NOT NULL
      AND o.is_test_user = 0
      AND o.business_gmv_attribution IN ('商业化', '电销')
      AND (
          (p.period = '本期' AND o.sku_group_good_id = '74ec057c-4a49-45aa-a0ee-0fd2a410989a')
          OR (p.period = '去年同期' AND o.good_kind_id_level_2 IN (
              '9433f2e3-7908-44b6-ae84-d3ba257ad3ce',
              'ee74d649-8e32-452a-a461-65de25560440'
          ))
      )
    GROUP BY p.period,
        CASE WHEN o.business_gmv_attribution = '商业化' THEN 'APP' ELSE '销售' END,
        CAST(o.u_user AS VARCHAR), o.order_id,
        CASE
            WHEN o.business_user_pay_status_statistics IN ('新增', '新用户') THEN '新增'
            WHEN o.business_user_pay_status_statistics = '老未' THEN '老未'
            WHEN o.business_user_pay_status_statistics IN ('续费用户', '续费') THEN '续费'
            WHEN o.business_user_pay_status_statistics = '高净值用户' THEN '高净值汇总'
            ELSE '未映射' END,
        CASE
            WHEN o.business_user_pay_status_statistics = '高净值用户' AND o.user_strategy_tag_day LIKE CONCAT('付费组合品用户-', SUBSTR(CAST(CASE WHEN p.period='本期' THEN {{CURRENT_START}} ELSE {{LAST_YEAR_START}} END AS VARCHAR), 1, 4), '年初中毕业') THEN '高净值－当年毕业'
            WHEN o.business_user_pay_status_statistics = '高净值用户' AND o.user_strategy_tag_day = '历史大会员用户_可续购' THEN '高净值－历史大会员可续购'
            WHEN o.business_user_pay_status_statistics = '高净值用户' AND o.user_strategy_tag_day = '历史大会员用户_不可续购' THEN '高净值－历史大会员不可续购'
            WHEN o.business_user_pay_status_statistics = '高净值用户' THEN '高净值－其他组合品'
            ELSE '非高净值' END
),
deposit_users AS (
    SELECT period, channel, user_id, MIN(first_deposit_time) AS first_deposit_time,
           COUNT(DISTINCT order_id) AS deposit_orders, SUM(deposit_amount) AS deposit_amount,
           MAX(user_layer) AS user_layer, MAX(high_value_layer) AS high_value_layer
    FROM deposit_source_rows
    GROUP BY period, channel, user_id
),
activity_audience AS (
    SELECT p.period, CAST(a.u_user AS VARCHAR) AS user_id,
           CASE
               WHEN MAX(CASE WHEN a.grade_name_month IN ('一年级','二年级','三年级') THEN 1 ELSE 0 END) = 1 THEN '1–3 年级'
               WHEN MAX(CASE WHEN a.grade_name_month IN ('四年级','五年级','六年级') THEN 1 ELSE 0 END) = 1 THEN '4–6 年级'
               WHEN MAX(CASE WHEN a.grade_name_month IN ('七年级','八年级','九年级','初一','初二','初三') THEN 1 ELSE 0 END) = 1 THEN '初中'
               WHEN MAX(CASE WHEN a.grade_name_month IN ('高一','高二','高三','十年级') THEN 1 ELSE 0 END) = 1 THEN '高中'
               ELSE '未知学段'
           END AS stage
    FROM strategy_periods p
    JOIN aws.business_active_user_last_14_day a
      ON a.day BETWEEN CASE WHEN p.period='本期' THEN {{CURRENT_START}} ELSE {{LAST_YEAR_START}} END
                   AND CASE WHEN p.period='本期' THEN {{CURRENT_END}} ELSE {{LAST_YEAR_END}} END
    WHERE a.u_user IS NOT NULL
    GROUP BY p.period, CAST(a.u_user AS VARCHAR)
),
tail_order_rows AS (
    SELECT d.period, d.channel, d.user_id, o.order_id,
           CASE
               WHEN o.original_amount >= 498 AND o.original_amount < 499 THEN '498'
               WHEN o.business_good_kind_name_level_1 = '组合品' THEN '组合品'
               ELSE '其他商品'
           END AS flow_product,
           SUM(o.sub_amount) AS revenue
    FROM deposit_users d
    JOIN strategy_periods p ON d.period = p.period
    JOIN dws.topic_order_detail o
      ON CAST(o.u_user AS VARCHAR) = d.user_id
     AND o.paid_time >= d.first_deposit_time
     AND o.paid_time_sk BETWEEN CASE WHEN p.period='本期' THEN {{CURRENT_START}} ELSE {{LAST_YEAR_START}} END
                            AND CASE WHEN p.period='本期' THEN {{CURRENT_END}} ELSE {{LAST_YEAR_END}} END
    WHERE o.u_user IS NOT NULL AND o.is_test_user = 0 AND o.original_amount >= 39
      AND o.business_gmv_attribution IN ('商业化', '电销')
    GROUP BY d.period, d.channel, d.user_id, o.order_id,
        CASE WHEN o.original_amount >= 498 AND o.original_amount < 499 THEN '498'
             WHEN o.business_good_kind_name_level_1 = '组合品' THEN '组合品' ELSE '其他商品' END
),
tail_orders AS (
    SELECT period, channel, user_id, order_id, flow_product, revenue FROM tail_order_rows
),
channel_deposit_users AS (
    SELECT d.period, d.channel, d.user_id, d.deposit_orders, d.deposit_amount,
           d.user_layer, d.high_value_layer, COALESCE(a.stage, '未知学段') AS stage
    FROM deposit_users d LEFT JOIN activity_audience a ON d.period=a.period AND d.user_id=a.user_id
    UNION ALL
    SELECT d.period, '私域整体', d.user_id, SUM(d.deposit_orders), SUM(d.deposit_amount),
           MAX(d.user_layer), MAX(d.high_value_layer), COALESCE(MAX(a.stage), '未知学段')
    FROM deposit_users d LEFT JOIN activity_audience a ON d.period=a.period AND d.user_id=a.user_id
    GROUP BY d.period, d.user_id
),
channel_tail_orders AS (
    SELECT period, channel, user_id, order_id, flow_product, revenue FROM tail_orders
    UNION ALL
    SELECT period, '私域整体', user_id, order_id, flow_product, MAX(revenue)
    FROM tail_orders GROUP BY period, user_id, order_id, flow_product
),
dimension_users AS (
    SELECT period, channel, user_id, deposit_orders, deposit_amount, '整体' AS dimension_type, '全部' AS dimension_value FROM channel_deposit_users
    UNION ALL SELECT period, channel, user_id, deposit_orders, deposit_amount, '用户层级', user_layer FROM channel_deposit_users
    UNION ALL SELECT period, channel, user_id, deposit_orders, deposit_amount, '学段', stage FROM channel_deposit_users
    UNION ALL SELECT period, channel, user_id, deposit_orders, deposit_amount, '高净值细分', high_value_layer FROM channel_deposit_users WHERE high_value_layer <> '非高净值'
),
source_summary AS (
    SELECT period,channel,dimension_type,dimension_value,
           COUNT(DISTINCT user_id) source_users,SUM(deposit_orders) source_orders,SUM(deposit_amount) source_amount
    FROM dimension_users GROUP BY period,channel,dimension_type,dimension_value
),
tail_summary AS (
    SELECT d.period, d.channel, d.dimension_type, d.dimension_value,
           COUNT(DISTINCT t.user_id) AS tail_users, COUNT(DISTINCT t.order_id) AS tail_orders, SUM(COALESCE(t.revenue, 0)) AS tail_revenue,
           COUNT(DISTINCT CASE WHEN t.flow_product='组合品' THEN t.user_id END) AS combo_users,
           COUNT(DISTINCT CASE WHEN t.flow_product='组合品' THEN t.order_id END) AS combo_orders,
           SUM(CASE WHEN t.flow_product='组合品' THEN t.revenue ELSE 0 END) AS combo_revenue,
           COUNT(DISTINCT CASE WHEN t.flow_product='498' THEN t.user_id END) AS p498_users,
           COUNT(DISTINCT CASE WHEN t.flow_product='498' THEN t.order_id END) AS p498_orders,
           SUM(CASE WHEN t.flow_product='498' THEN t.revenue ELSE 0 END) AS p498_revenue,
           COUNT(DISTINCT CASE WHEN t.flow_product='其他商品' THEN t.user_id END) AS other_users,
           COUNT(DISTINCT CASE WHEN t.flow_product='其他商品' THEN t.order_id END) AS other_orders,
           SUM(CASE WHEN t.flow_product='其他商品' THEN t.revenue ELSE 0 END) AS other_revenue
    FROM dimension_users d LEFT JOIN channel_tail_orders t
      ON d.period=t.period AND d.channel=t.channel AND d.user_id=t.user_id
    GROUP BY d.period, d.channel, d.dimension_type, d.dimension_value
),
summary AS (
    SELECT s.period,s.channel,s.dimension_type,s.dimension_value,s.source_users,s.source_orders,s.source_amount,
           COALESCE(t.tail_users,0) tail_users,COALESCE(t.tail_orders,0) tail_orders,COALESCE(t.tail_revenue,0) tail_revenue,
           COALESCE(t.combo_users,0) combo_users,COALESCE(t.combo_orders,0) combo_orders,COALESCE(t.combo_revenue,0) combo_revenue,
           COALESCE(t.p498_users,0) p498_users,COALESCE(t.p498_orders,0) p498_orders,COALESCE(t.p498_revenue,0) p498_revenue,
           COALESCE(t.other_users,0) other_users,COALESCE(t.other_orders,0) other_orders,COALESCE(t.other_revenue,0) other_revenue
    FROM source_summary s LEFT JOIN tail_summary t
      ON s.period=t.period AND s.channel=t.channel AND s.dimension_type=t.dimension_type AND s.dimension_value=t.dimension_value
),
private_revenue AS (
    SELECT p.period, SUM(o.sub_amount) AS revenue
    FROM strategy_periods p JOIN dws.topic_order_detail o
      ON o.paid_time_sk BETWEEN CASE WHEN p.period='本期' THEN {{CURRENT_START}} ELSE {{LAST_YEAR_START}} END
                            AND CASE WHEN p.period='本期' THEN {{CURRENT_END}} ELSE {{LAST_YEAR_END}} END
    WHERE o.u_user IS NOT NULL AND o.is_test_user=0 AND o.original_amount>=39
      AND o.business_gmv_attribution IN ('商业化','电销')
    GROUP BY p.period
),
metrics AS (
    SELECT period,channel,dimension_type,dimension_value,'定金来源用户数' metric,CAST(source_users AS DOUBLE) value FROM summary
    UNION ALL SELECT period,channel,dimension_type,dimension_value,'定金订单量',CAST(source_orders AS DOUBLE) FROM summary
    UNION ALL SELECT period,channel,dimension_type,dimension_value,'定金金额',source_amount FROM summary
    UNION ALL SELECT period,channel,dimension_type,dimension_value,'尾款人数',CAST(tail_users AS DOUBLE) FROM summary
    UNION ALL SELECT period,channel,dimension_type,dimension_value,'尾款订单量',CAST(tail_orders AS DOUBLE) FROM summary
    UNION ALL SELECT period,channel,dimension_type,dimension_value,'尾款营收',tail_revenue FROM summary
    UNION ALL SELECT period,channel,dimension_type,dimension_value,'尾款率',tail_users/NULLIF(source_users,0) FROM summary
    UNION ALL SELECT s.period,s.channel,s.dimension_type,s.dimension_value,'尾款营收占整体营收比例',s.tail_revenue/NULLIF(p.revenue,0) FROM summary s JOIN private_revenue p ON s.period=p.period
    UNION ALL SELECT period,channel,dimension_type,dimension_value,'转组合品人数',CAST(combo_users AS DOUBLE) FROM summary
    UNION ALL SELECT period,channel,dimension_type,dimension_value,'转组合品订单量',CAST(combo_orders AS DOUBLE) FROM summary
    UNION ALL SELECT period,channel,dimension_type,dimension_value,'转组合品营收',combo_revenue FROM summary
    UNION ALL SELECT period,channel,dimension_type,dimension_value,'转498人数',CAST(p498_users AS DOUBLE) FROM summary
    UNION ALL SELECT period,channel,dimension_type,dimension_value,'转498订单量',CAST(p498_orders AS DOUBLE) FROM summary
    UNION ALL SELECT period,channel,dimension_type,dimension_value,'转498营收',p498_revenue FROM summary
    UNION ALL SELECT period,channel,dimension_type,dimension_value,'转其他商品人数',CAST(other_users AS DOUBLE) FROM summary
    UNION ALL SELECT period,channel,dimension_type,dimension_value,'转其他商品订单量',CAST(other_orders AS DOUBLE) FROM summary
    UNION ALL SELECT period,channel,dimension_type,dimension_value,'转其他商品营收',other_revenue FROM summary
    UNION ALL SELECT period,channel,dimension_type,dimension_value,'未转化人数',CAST(source_users-tail_users AS DOUBLE) FROM summary
)
SELECT period, channel, dimension_type, dimension_value, metric, value,
       'v1;source_rule=deposit_product_ids;activity_window=tail' AS source_version,
       CURRENT_TIMESTAMP AS data_updated_at,
       'deposit.source_tail_flow.v1' AS definition_id
FROM metrics
LIMIT 10000
