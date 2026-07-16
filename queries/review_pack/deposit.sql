WITH strategy_periods AS (
    SELECT '本期' AS period,
           {{DEPOSIT_SOURCE_START}} AS source_start, {{DEPOSIT_SOURCE_END}} AS source_end
    UNION ALL
    SELECT '去年同期',
           CAST(DATE_FORMAT(DATE_SUB(STR_TO_DATE(CAST({{DEPOSIT_SOURCE_START}} AS VARCHAR), '%Y%m%d'), INTERVAL 1 YEAR), '%Y%m%d') AS INT),
           CAST(DATE_FORMAT(DATE_SUB(STR_TO_DATE(CAST({{DEPOSIT_SOURCE_END}} AS VARCHAR), '%Y%m%d'), INTERVAL 1 YEAR), '%Y%m%d') AS INT)
),
channels AS (SELECT '私域整体' channel UNION ALL SELECT 'APP' UNION ALL SELECT '销售'),
user_layer_values AS (SELECT '新增' user_layer UNION ALL SELECT '老未' UNION ALL SELECT '续费' UNION ALL SELECT '高净值汇总' UNION ALL SELECT '高净值－当年毕业' UNION ALL SELECT '高净值－历史大会员可续购' UNION ALL SELECT '高净值－历史大会员不可续购' UNION ALL SELECT '高净值－其他组合品' UNION ALL SELECT '未映射'),
stage_values AS (SELECT '1–3 年级' stage UNION ALL SELECT '4–6 年级' UNION ALL SELECT '初中' UNION ALL SELECT '高中' UNION ALL SELECT '未知学段'),
deposit_source_rows AS (
    SELECT
        p.period,
        CASE WHEN o.business_gmv_attribution = '商业化' THEN 'APP' ELSE '销售' END AS channel,
        CAST(o.u_user AS VARCHAR) AS user_id,
        o.order_id,
        MIN(o.paid_time) AS source_time,
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
deposit_source_ranked AS (
    SELECT period,channel,user_id,order_id,source_time,deposit_amount,user_layer,high_value_layer,COUNT(*) OVER(PARTITION BY period,user_id) source_orders,
           SUM(deposit_amount) OVER(PARTITION BY period,user_id) source_amount,
           MIN(source_time) OVER(PARTITION BY period,user_id) earliest_source_time,
           ROW_NUMBER() OVER(PARTITION BY period, user_id ORDER BY source_time DESC, order_id DESC) source_rank
    FROM deposit_source_rows s
),
deposit_users AS (
    SELECT period,channel,user_id,earliest_source_time first_deposit_time,source_orders deposit_orders,source_amount deposit_amount,user_layer,high_value_layer
    FROM deposit_source_ranked WHERE source_rank = 1
),
activity_audience AS (
    SELECT period,user_id,stage FROM (
      SELECT p.period,CAST(a.u_user AS VARCHAR) user_id,
       CASE WHEN a.grade_name_month IN ('一年级','二年级','三年级') THEN '1–3 年级' WHEN a.grade_name_month IN ('四年级','五年级','六年级') THEN '4–6 年级' WHEN a.grade_name_month IN ('七年级','八年级','九年级','初一','初二','初三') THEN '初中' WHEN a.grade_name_month IN ('高一','高二','高三','十年级') THEN '高中' ELSE '未知学段' END stage,
       ROW_NUMBER() OVER(
         PARTITION BY p.period,CAST(a.u_user AS VARCHAR)
         ORDER BY a.day DESC,
           CASE WHEN a.business_user_pay_status_statistics_month='高净值用户' THEN 1
                WHEN a.business_user_pay_status_statistics_month IN ('新增','新用户') THEN 2
                WHEN a.business_user_pay_status_statistics_month='老未' THEN 3
                WHEN a.business_user_pay_status_statistics_month IN ('续费用户','续费') THEN 4 ELSE 5 END,
           CASE WHEN a.grade_name_month IS NULL OR TRIM(a.grade_name_month)='' THEN 2 ELSE 1 END,
           CASE WHEN a.grade_name_month IN ('一年级','二年级','三年级') THEN 1
                WHEN a.grade_name_month IN ('四年级','五年级','六年级') THEN 2
                WHEN a.grade_name_month IN ('七年级','八年级','九年级','初一','初二','初三') THEN 3
                WHEN a.grade_name_month IN ('高一','高二','高三','十年级') THEN 4 ELSE 5 END,
           CASE WHEN a.user_strategy_tag_level2_month IS NULL OR TRIM(a.user_strategy_tag_level2_month)='' THEN 2 ELSE 1 END,
           a.user_strategy_tag_level2_month DESC,
           COALESCE(a.business_user_pay_status_statistics_month,'') DESC,
           COALESCE(a.grade_name_month,'') DESC
       ) fact_rank
      FROM strategy_periods p JOIN aws.business_active_user_last_14_day a ON a.day BETWEEN CASE WHEN p.period='本期' THEN {{CURRENT_START}} ELSE {{LAST_YEAR_START}} END AND CASE WHEN p.period='本期' THEN {{CURRENT_END}} ELSE {{LAST_YEAR_END}} END WHERE a.u_user IS NOT NULL
    ) x WHERE fact_rank = 1
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
     AND o.paid_time > d.first_deposit_time
     AND o.paid_time_sk BETWEEN CASE WHEN p.period='本期' THEN {{CURRENT_START}} ELSE {{LAST_YEAR_START}} END
                            AND CASE WHEN p.period='本期' THEN {{CURRENT_END}} ELSE {{LAST_YEAR_END}} END
    WHERE o.u_user IS NOT NULL AND o.is_test_user = 0 AND o.original_amount >= 39
      AND o.business_gmv_attribution IN ('商业化', '电销')
      AND NOT EXISTS (
          SELECT 1
          FROM deposit_source_rows source_order
          WHERE source_order.period = d.period
            AND source_order.user_id = d.user_id
            AND source_order.order_id = o.order_id
      )
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
    SELECT d.period, '私域整体', d.user_id, d.deposit_orders, d.deposit_amount,
           d.user_layer, d.high_value_layer, COALESCE(a.stage, '未知学段')
    FROM deposit_users d LEFT JOIN activity_audience a ON d.period=a.period AND d.user_id=a.user_id
),
channel_tail_orders AS (
    SELECT period, channel, user_id, order_id, flow_product, revenue FROM tail_orders
    UNION ALL
    SELECT period, '私域整体', user_id, order_id, flow_product, MAX(revenue)
    FROM tail_orders GROUP BY period, user_id, order_id, flow_product
),
layer_expanded AS (
    SELECT period,channel,user_id,deposit_orders,deposit_amount,stage,user_layer FROM channel_deposit_users
    UNION ALL SELECT period,channel,user_id,deposit_orders,deposit_amount,stage,high_value_layer FROM channel_deposit_users WHERE high_value_layer<>'非高净值'
),
dimension_grid AS (
    SELECT p.period,c.channel,u.user_layer,s.stage FROM strategy_periods p CROSS JOIN channels c CROSS JOIN user_layer_values u CROSS JOIN stage_values s
),
summary_actual AS (
    SELECT d.period, d.channel, d.user_layer,d.stage,
           COUNT(DISTINCT d.user_id) source_users,SUM(d.deposit_orders) source_orders,SUM(d.deposit_amount) source_amount,
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
    FROM layer_expanded d LEFT JOIN channel_tail_orders t
      ON d.period=t.period AND d.channel=t.channel AND d.user_id=t.user_id
    GROUP BY d.period, d.channel,d.user_layer,d.stage
),
summary AS (
    SELECT g.period,g.channel,'用户层级×学段' dimension_type,CONCAT(g.user_layer,'×',g.stage) dimension_value,
           COALESCE(a.source_users,0) source_users,COALESCE(a.source_orders,0) source_orders,COALESCE(a.source_amount,0) source_amount,
           COALESCE(a.tail_users,0) tail_users,COALESCE(a.tail_orders,0) tail_orders,COALESCE(a.tail_revenue,0) tail_revenue,
           COALESCE(a.combo_users,0) combo_users,COALESCE(a.combo_orders,0) combo_orders,COALESCE(a.combo_revenue,0) combo_revenue,
           COALESCE(a.p498_users,0) p498_users,COALESCE(a.p498_orders,0) p498_orders,COALESCE(a.p498_revenue,0) p498_revenue,
           COALESCE(a.other_users,0) other_users,COALESCE(a.other_orders,0) other_orders,COALESCE(a.other_revenue,0) other_revenue
    FROM dimension_grid g LEFT JOIN summary_actual a ON g.period=a.period AND g.channel=a.channel AND g.user_layer=a.user_layer AND g.stage=a.stage
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
