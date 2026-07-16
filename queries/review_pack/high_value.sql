WITH periods AS (
    SELECT '本期' period,{{CURRENT_START}} start_day,{{CURRENT_END}} end_day
    UNION ALL SELECT '去年同期',{{LAST_YEAR_START}},{{LAST_YEAR_END}}
),
high_value_raw AS (
    SELECT p.period,CAST(a.u_user AS VARCHAR) user_id,
           CASE WHEN a.business_gmv_attribution='商业化' THEN 'APP'
                WHEN a.business_gmv_attribution='电销' THEN '销售' END channel,
           CASE WHEN a.grade_name_month IN ('一年级','二年级','三年级') THEN '1–3 年级'
                WHEN a.grade_name_month IN ('四年级','五年级','六年级') THEN '4–6 年级'
                WHEN a.grade_name_month IN ('七年级','八年级','九年级','初一','初二','初三') THEN '初中'
                WHEN a.grade_name_month IN ('高一','高二','高三','十年级') THEN '高中'
                ELSE '未知学段' END stage,
           a.user_strategy_tag_level2_month tag2,
           SUBSTR(CAST(p.start_day AS VARCHAR),1,4) period_year
    FROM periods p JOIN aws.business_active_user_last_14_day a ON a.day BETWEEN p.start_day AND p.end_day
    WHERE a.u_user IS NOT NULL AND a.business_user_pay_status_statistics_month='高净值用户'
),
all_high_value_users AS (
    SELECT period,user_id,MAX(stage) stage,MAX(tag2) tag2,MAX(period_year) period_year
    FROM high_value_raw GROUP BY period,user_id
),
private_high_value_users AS (
    SELECT period,'私域整体' channel,user_id,stage,tag2,period_year FROM all_high_value_users
),
channel_high_value_users AS (
    SELECT period,channel,user_id,MAX(stage) stage,MAX(tag2) tag2,MAX(period_year) period_year
    FROM high_value_raw WHERE channel IS NOT NULL GROUP BY period,channel,user_id
),
high_value_users AS (
    SELECT period,channel,user_id,stage,'高净值汇总' user_layer FROM private_high_value_users
    UNION ALL SELECT period,channel,user_id,stage,
        CASE WHEN tag2=CONCAT('付费组合品用户-',period_year,'年初中毕业') THEN '高净值－当年毕业'
             WHEN tag2='历史大会员用户_可续购' THEN '高净值－历史大会员可续购'
             WHEN tag2='历史大会员用户_不可续购' THEN '高净值－历史大会员不可续购'
             ELSE '高净值－其他组合品' END
      FROM private_high_value_users
    UNION ALL SELECT period,channel,user_id,stage,'高净值汇总' FROM channel_high_value_users
    UNION ALL SELECT period,channel,user_id,stage,
        CASE WHEN tag2=CONCAT('付费组合品用户-',period_year,'年初中毕业') THEN '高净值－当年毕业'
             WHEN tag2='历史大会员用户_可续购' THEN '高净值－历史大会员可续购'
             WHEN tag2='历史大会员用户_不可续购' THEN '高净值－历史大会员不可续购'
             ELSE '高净值－其他组合品' END
      FROM channel_high_value_users
),
order_rows AS (
    SELECT p.period,CASE WHEN o.business_gmv_attribution='商业化' THEN 'APP' ELSE '销售' END channel,
           CAST(o.u_user AS VARCHAR) user_id,o.order_id,o.business_good_kind_name_level_1,
           o.business_good_kind_name_level_3,o.good_name,o.good_kind_name_level_3,
           o.good_stage_subject_cnt,o.good_stage_subject,o.original_amount,SUM(o.sub_amount) revenue
    FROM periods p JOIN dws.topic_order_detail o ON o.paid_time_sk BETWEEN p.start_day AND p.end_day
    WHERE o.u_user IS NOT NULL AND o.is_test_user=0 AND o.original_amount>=39
      AND o.business_gmv_attribution IN ('商业化','电销')
    GROUP BY p.period,CASE WHEN o.business_gmv_attribution='商业化' THEN 'APP' ELSE '销售' END,
             CAST(o.u_user AS VARCHAR),o.order_id,o.business_good_kind_name_level_1,
             o.business_good_kind_name_level_3,o.good_name,o.good_kind_name_level_3,
             o.good_stage_subject_cnt,o.good_stage_subject,o.original_amount
),
channel_orders AS (
    SELECT period,channel,user_id,order_id,revenue,business_good_kind_name_level_1,business_good_kind_name_level_3,
           good_name,good_kind_name_level_3,good_stage_subject_cnt,good_stage_subject,original_amount FROM order_rows
    UNION ALL
    SELECT period,'私域整体',user_id,order_id,SUM(revenue),MAX(business_good_kind_name_level_1),MAX(business_good_kind_name_level_3),
           MAX(good_name),MAX(good_kind_name_level_3),MAX(good_stage_subject_cnt),MAX(good_stage_subject),MAX(original_amount)
    FROM order_rows GROUP BY period,user_id,order_id
),
product_orders AS (
    SELECT period,channel,user_id,order_id,revenue,'全部' product FROM channel_orders
    UNION ALL SELECT period,channel,user_id,order_id,revenue,'组合品' FROM channel_orders WHERE business_good_kind_name_level_1='组合品'
    UNION ALL SELECT period,channel,user_id,order_id,revenue,'零售品' FROM channel_orders WHERE business_good_kind_name_level_1='零售商品'
    UNION ALL SELECT period,channel,user_id,order_id,revenue,'家庭包' FROM channel_orders WHERE business_good_kind_name_level_3='小初高品'
    UNION ALL SELECT period,channel,user_id,order_id,revenue,'从小学系列' FROM channel_orders
      WHERE business_good_kind_name_level_3='小学品加拓展' OR (good_name LIKE '从小学%' AND good_name NOT LIKE '%系列%')
         OR (good_kind_name_level_3='拓展课' AND good_stage_subject_cnt=1 AND (good_stage_subject REGEXP '1-2-specialCourse' OR good_stage_subject REGEXP '1-6-specialCourse' OR good_stage_subject REGEXP '1-7-specialCourse'))
    UNION ALL SELECT period,channel,user_id,order_id,revenue,'198' FROM channel_orders WHERE original_amount>=198 AND original_amount<199
    UNION ALL SELECT period,channel,user_id,order_id,revenue,'498' FROM channel_orders WHERE original_amount>=498 AND original_amount<499
    UNION ALL SELECT period,channel,user_id,order_id,revenue,'千元及以上' FROM channel_orders WHERE original_amount>=1000
),
products AS (
    SELECT '全部' product UNION ALL SELECT '组合品' UNION ALL SELECT '零售品' UNION ALL SELECT '家庭包'
    UNION ALL SELECT '从小学系列' UNION ALL SELECT '198' UNION ALL SELECT '498' UNION ALL SELECT '千元及以上'
),
dimension_grid AS (
    SELECT h.period,h.channel,h.user_layer,h.stage,p.product
    FROM (SELECT DISTINCT period,channel,user_layer,stage FROM high_value_users) h JOIN products p ON 1=1
),
active_summary AS (
    SELECT g.period,g.channel,g.user_layer,g.stage,g.product,
           COUNT(DISTINCT h.user_id) source_users,COUNT(DISTINCT h.user_id) active_users
    FROM dimension_grid g JOIN high_value_users h
      ON g.period=h.period AND g.channel=h.channel AND g.user_layer=h.user_layer AND g.stage=h.stage
    GROUP BY g.period,g.channel,g.user_layer,g.stage,g.product
),
product_summary AS (
    SELECT g.period,g.channel,g.user_layer,g.stage,g.product,
           COUNT(DISTINCT o.user_id) pay_users,COUNT(DISTINCT o.order_id) orders,SUM(COALESCE(o.revenue,0)) revenue
    FROM dimension_grid g JOIN high_value_users h
      ON g.period=h.period AND g.channel=h.channel AND g.user_layer=h.user_layer AND g.stage=h.stage
    LEFT JOIN product_orders o
      ON g.period=o.period AND g.channel=o.channel AND g.product=o.product AND h.user_id=o.user_id
    GROUP BY g.period,g.channel,g.user_layer,g.stage,g.product
),
combo_summary AS (
    SELECT h.period,h.channel,h.user_layer,h.stage,
           COUNT(DISTINCT c.user_id) combo_pay_users,COUNT(DISTINCT c.order_id) combo_orders,SUM(COALESCE(c.revenue,0)) combo_revenue
    FROM high_value_users h LEFT JOIN product_orders c
      ON h.period=c.period AND h.channel=c.channel AND c.product='组合品' AND h.user_id=c.user_id
    GROUP BY h.period,h.channel,h.user_layer,h.stage
),
summary AS (
    SELECT a.period,a.channel,a.user_layer,a.stage,a.product,a.source_users,a.active_users,
           COALESCE(p.pay_users,0) pay_users,COALESCE(p.orders,0) orders,COALESCE(p.revenue,0) revenue,
           COALESCE(c.combo_pay_users,0) combo_pay_users,COALESCE(c.combo_orders,0) combo_orders,COALESCE(c.combo_revenue,0) combo_revenue
    FROM active_summary a LEFT JOIN product_summary p
      ON a.period=p.period AND a.channel=p.channel AND a.user_layer=p.user_layer AND a.stage=p.stage AND a.product=p.product
    LEFT JOIN combo_summary c
      ON a.period=c.period AND a.channel=c.channel AND a.user_layer=c.user_layer AND a.stage=c.stage
),
private_revenue AS (
    SELECT p.period,SUM(o.sub_amount) revenue FROM periods p
    JOIN dws.topic_order_detail o ON o.paid_time_sk BETWEEN p.start_day AND p.end_day
    WHERE o.u_user IS NOT NULL AND o.is_test_user=0 AND o.original_amount>=39
      AND o.business_gmv_attribution IN ('商业化','电销') GROUP BY p.period
),
metrics AS (
    SELECT period,channel,'高净值细分×学段×商品' dimension_type,CONCAT(user_layer,'×',stage,'×',product) dimension_value,'来源用户数' metric,CAST(source_users AS DOUBLE) value FROM summary
    UNION ALL SELECT period,channel,'高净值细分×学段×商品',CONCAT(user_layer,'×',stage,'×',product),'活跃人数',CAST(active_users AS DOUBLE) FROM summary
    UNION ALL SELECT period,channel,'高净值细分×学段×商品',CONCAT(user_layer,'×',stage,'×',product),'付费人数',CAST(pay_users AS DOUBLE) FROM summary
    UNION ALL SELECT period,channel,'高净值细分×学段×商品',CONCAT(user_layer,'×',stage,'×',product),'订单量',CAST(orders AS DOUBLE) FROM summary
    UNION ALL SELECT period,channel,'高净值细分×学段×商品',CONCAT(user_layer,'×',stage,'×',product),'营收',revenue FROM summary
    UNION ALL SELECT period,channel,'高净值细分×学段×商品',CONCAT(user_layer,'×',stage,'×',product),'付费转化率',pay_users/NULLIF(active_users,0) FROM summary
    UNION ALL SELECT period,channel,'高净值细分×学段×商品',CONCAT(user_layer,'×',stage,'×',product),'客单价',revenue/NULLIF(pay_users,0) FROM summary
    UNION ALL SELECT period,channel,'高净值细分×学段×商品',CONCAT(user_layer,'×',stage,'×',product),'ARPU',revenue/NULLIF(active_users,0) FROM summary
    UNION ALL SELECT period,channel,'高净值细分×学段×商品',CONCAT(user_layer,'×',stage,'×',product),'组合品付费人数',CAST(combo_pay_users AS DOUBLE) FROM summary
    UNION ALL SELECT period,channel,'高净值细分×学段×商品',CONCAT(user_layer,'×',stage,'×',product),'组合品订单量',CAST(combo_orders AS DOUBLE) FROM summary
    UNION ALL SELECT period,channel,'高净值细分×学段×商品',CONCAT(user_layer,'×',stage,'×',product),'组合品营收',combo_revenue FROM summary
    UNION ALL SELECT period,channel,'高净值细分×学段×商品',CONCAT(user_layer,'×',stage,'×',product),'组合品转化率',combo_pay_users/NULLIF(active_users,0) FROM summary
    UNION ALL SELECT s.period,s.channel,'高净值细分×学段×商品',CONCAT(s.user_layer,'×',s.stage,'×',s.product),'高净值营收占私域营收比例',s.revenue/NULLIF(p.revenue,0) FROM summary s JOIN private_revenue p ON s.period=p.period
)
SELECT period,channel,dimension_type,dimension_value,metric,value,
       'v1;price_basis=original_amount' source_version,CURRENT_TIMESTAMP data_updated_at,
       'high_value.layer_stage_product.v1' definition_id
FROM metrics
LIMIT 10000
