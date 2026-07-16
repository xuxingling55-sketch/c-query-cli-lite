WITH periods AS (
    SELECT '本期' period,{{CURRENT_START}} start_day,{{CURRENT_END}} end_day
    UNION ALL SELECT '去年同期',{{LAST_YEAR_START}},{{LAST_YEAR_END}}
),
active_raw AS (
    SELECT p.period,CAST(a.u_user AS VARCHAR) user_id,
           CASE WHEN a.business_gmv_attribution='商业化' THEN 'APP'
                WHEN a.business_gmv_attribution='电销' THEN '销售' END channel,
           CASE WHEN a.business_user_pay_status_statistics_month IN ('新增','新用户') THEN '新增'
                WHEN a.business_user_pay_status_statistics_month='老未' THEN '老未'
                WHEN a.business_user_pay_status_statistics_month IN ('续费用户','续费') THEN '续费'
                WHEN a.business_user_pay_status_statistics_month='高净值用户' THEN '高净值汇总'
                ELSE '未映射' END user_layer,
           CASE WHEN a.grade_name_month IN ('一年级','二年级','三年级') THEN '1–3 年级'
                WHEN a.grade_name_month IN ('四年级','五年级','六年级') THEN '4–6 年级'
                WHEN a.grade_name_month IN ('七年级','八年级','九年级','初一','初二','初三') THEN '初中'
                WHEN a.grade_name_month IN ('高一','高二','高三','十年级') THEN '高中'
                ELSE '未知学段' END stage
    FROM periods p JOIN aws.business_active_user_last_14_day a ON a.day BETWEEN p.start_day AND p.end_day
    WHERE a.u_user IS NOT NULL
),
channel_active_users AS (
    SELECT period,channel,user_id,MAX(user_layer) user_layer,MAX(stage) stage
    FROM active_raw WHERE channel IS NOT NULL GROUP BY period,channel,user_id
),
private_active_users AS (
    SELECT period,'私域整体' channel,user_id,MAX(user_layer) user_layer,MAX(stage) stage
    FROM active_raw GROUP BY period,user_id
),
active_users AS (
    SELECT period,channel,user_id,user_layer,stage FROM channel_active_users
    UNION ALL SELECT period,channel,user_id,user_layer,stage FROM private_active_users
),
pool_users AS (
    SELECT p.period,CAST(d.active_u_user AS VARCHAR) user_id,
           MAX(CASE WHEN d.recieve_u_user IS NOT NULL THEN 1 ELSE 0 END) is_received
    FROM periods p JOIN aws.crm_active_data_pool_day d ON d.day BETWEEN p.start_day AND p.end_day
    WHERE d.active_u_user IS NOT NULL GROUP BY p.period,CAST(d.active_u_user AS VARCHAR)
),
phone_users AS (
    SELECT p.period,CAST(c.user_id AS VARCHAR) user_id,
           SUM(COALESCE(c.call_phone_cnt,0)) call_phone_cnt,
           SUM(COALESCE(c.valid_call_cnt,0)) valid_call_cnt
    FROM periods p JOIN aws.clue_info c
      ON CAST(DATE_FORMAT(c.created_at,'%Y%m%d') AS INT) BETWEEN p.start_day AND p.end_day
    WHERE c.workplace_id IN (4,400,702) AND c.regiment_id NOT IN (0,303,546)
      AND c.user_sk>0 AND c.worker_id<>'0' AND c.user_id IS NOT NULL
    GROUP BY p.period,CAST(c.user_id AS VARCHAR)
),
conversion_users AS (
    SELECT p.period,CAST(o.u_user AS VARCHAR) user_id,
           COUNT(DISTINCT o.order_id) orders,SUM(o.sub_amount) revenue
    FROM periods p JOIN dws.topic_order_detail o ON o.paid_time_sk BETWEEN p.start_day AND p.end_day
    WHERE o.u_user IS NOT NULL AND o.is_test_user=0 AND o.original_amount>=39
      AND o.business_gmv_attribution IN ('商业化','电销')
    GROUP BY p.period,CAST(o.u_user AS VARCHAR)
),
dimension_users AS (
    SELECT period,channel,user_id,'整体' dimension_type,'全部' dimension_value FROM active_users
    UNION ALL SELECT period,channel,user_id,'用户层级',user_layer FROM active_users
    UNION ALL SELECT period,channel,user_id,'学段',stage FROM active_users
    UNION ALL SELECT period,channel,user_id,'用户层级×学段',CONCAT(user_layer,'×',stage) FROM active_users
),
summary AS (
    SELECT d.period,d.channel,d.dimension_type,d.dimension_value,
           COUNT(DISTINCT d.user_id) active_users,
           COUNT(DISTINCT CASE WHEN p.is_received=1 THEN d.user_id END) received_users,
           COUNT(DISTINCT CASE WHEN COALESCE(ph.call_phone_cnt,0)>0 THEN d.user_id END) called_users,
           COUNT(DISTINCT CASE WHEN COALESCE(ph.valid_call_cnt,0)>0 THEN d.user_id END) connected_users,
           COUNT(DISTINCT CASE WHEN COALESCE(ph.call_phone_cnt,0)>0 AND COALESCE(ph.valid_call_cnt,0)=0 THEN d.user_id END) unconnected_users,
           COUNT(DISTINCT CASE WHEN c.user_id IS NOT NULL THEN d.user_id END) converted_users,
           SUM(COALESCE(c.revenue,0)) revenue,
           COUNT(DISTINCT CASE WHEN COALESCE(ph.valid_call_cnt,0)>0 AND c.user_id IS NOT NULL THEN d.user_id END) connected_converted_users,
           SUM(CASE WHEN COALESCE(ph.valid_call_cnt,0)>0 THEN COALESCE(c.revenue,0) ELSE 0 END) connected_revenue,
           COUNT(DISTINCT CASE WHEN COALESCE(ph.call_phone_cnt,0)>0 AND COALESCE(ph.valid_call_cnt,0)=0 AND c.user_id IS NOT NULL THEN d.user_id END) unconnected_converted_users,
           SUM(CASE WHEN COALESCE(ph.call_phone_cnt,0)>0 AND COALESCE(ph.valid_call_cnt,0)=0 THEN COALESCE(c.revenue,0) ELSE 0 END) unconnected_revenue
    FROM dimension_users d
    LEFT JOIN pool_users p ON d.period=p.period AND d.user_id=p.user_id
    LEFT JOIN phone_users ph ON d.period=ph.period AND d.user_id=ph.user_id
    LEFT JOIN conversion_users c ON d.period=c.period AND d.user_id=c.user_id
    GROUP BY d.period,d.channel,d.dimension_type,d.dimension_value
),
numeric_metrics AS (
    SELECT period,channel,dimension_type,dimension_value,'线索领取人数' metric,CAST(received_users AS DOUBLE) value FROM summary
    UNION ALL SELECT period,channel,dimension_type,dimension_value,'线索领取率',received_users/NULLIF(active_users,0) FROM summary
    UNION ALL SELECT period,channel,dimension_type,dimension_value,'电话拨打人数',CAST(called_users AS DOUBLE) FROM summary
    UNION ALL SELECT period,channel,dimension_type,dimension_value,'有效接通人数',CAST(connected_users AS DOUBLE) FROM summary
    UNION ALL SELECT period,channel,dimension_type,dimension_value,'有效接通率',connected_users/NULLIF(called_users,0) FROM summary
    UNION ALL SELECT period,channel,dimension_type,dimension_value,'未有效接通人数',CAST(unconnected_users AS DOUBLE) FROM summary
    UNION ALL SELECT period,channel,dimension_type,dimension_value,'转化人数',CAST(converted_users AS DOUBLE) FROM summary
    UNION ALL SELECT period,channel,dimension_type,dimension_value,'转化率',converted_users/NULLIF(received_users,0) FROM summary
    UNION ALL SELECT period,channel,dimension_type,dimension_value,'转化营收',revenue FROM summary
    UNION ALL SELECT period,channel,dimension_type,dimension_value,'客单价',revenue/NULLIF(converted_users,0) FROM summary
    UNION ALL SELECT period,channel,dimension_type,dimension_value,'ARPU',revenue/NULLIF(received_users,0) FROM summary
    UNION ALL SELECT period,channel,dimension_type,dimension_value,'有效接通后转化人数',CAST(connected_converted_users AS DOUBLE) FROM summary
    UNION ALL SELECT period,channel,dimension_type,dimension_value,'有效接通后转化率',connected_converted_users/NULLIF(connected_users,0) FROM summary
    UNION ALL SELECT period,channel,dimension_type,dimension_value,'有效接通后营收',connected_revenue FROM summary
    UNION ALL SELECT period,channel,dimension_type,dimension_value,'有效接通后客单价',connected_revenue/NULLIF(connected_converted_users,0) FROM summary
    UNION ALL SELECT period,channel,dimension_type,dimension_value,'有效接通后ARPU',connected_revenue/NULLIF(connected_users,0) FROM summary
    UNION ALL SELECT period,channel,dimension_type,dimension_value,'未有效接通后转化人数',CAST(unconnected_converted_users AS DOUBLE) FROM summary
    UNION ALL SELECT period,channel,dimension_type,dimension_value,'未有效接通后转化率',unconnected_converted_users/NULLIF(unconnected_users,0) FROM summary
    UNION ALL SELECT period,channel,dimension_type,dimension_value,'未有效接通后营收',unconnected_revenue FROM summary
    UNION ALL SELECT period,channel,dimension_type,dimension_value,'未有效接通后客单价',unconnected_revenue/NULLIF(unconnected_converted_users,0) FROM summary
    UNION ALL SELECT period,channel,dimension_type,dimension_value,'未有效接通后ARPU',unconnected_revenue/NULLIF(unconnected_users,0) FROM summary
),
wechat_metrics AS (
    SELECT period,channel,dimension_type,dimension_value,'企微添加人数' metric,'数据源未接入' value,
           'data_source_missing' source_version FROM summary
    UNION ALL
    SELECT period,channel,dimension_type,dimension_value,'企微添加率','数据源未接入','data_source_missing' FROM summary
),
metrics AS (
    SELECT period,channel,dimension_type,dimension_value,metric,CAST(value AS VARCHAR) value,
           'v1;phone_source=aws.clue_info' source_version FROM numeric_metrics
    UNION ALL
    SELECT period,channel,dimension_type,dimension_value,metric,value,source_version FROM wechat_metrics
)
SELECT period,channel,dimension_type,dimension_value,metric,value,source_version,
       CURRENT_TIMESTAMP data_updated_at,
       CASE WHEN source_version='data_source_missing' THEN 'sales_funnel.wechat.data_source_missing.v1'
            ELSE 'sales_funnel.receive_phone_conversion.v1' END definition_id
FROM metrics
LIMIT 10000
