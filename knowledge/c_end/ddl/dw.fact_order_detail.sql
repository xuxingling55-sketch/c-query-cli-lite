-- =====================================================
-- 订单明细事实表 dw.fact_order_detail
-- =====================================================
--
-- 【表粒度】
--   一笔订单的一个子商品一条记录（支付成功/退款成功等非测试，见表 COMMENT）
--   无分区（本导出；以线上为准）
--   补充：一行 = 一笔订单拆分到一个 `sub_good_sk` 后的**子订单事实**；同一 `order_id`
--         通常多行；主键口径为 `order_id + sub_good_sk`（来源 biMetadata）
--
-- 【业务定位】
--   - 数仓底层订单事实；dws.topic_order_detail 上游之一
--   - 与 dw.dim_date 等按 date_sk 关联
--   补充：订单**事件事实表**——把支付成功 / 退款成功的非测试订单按子商品维度拆成明细行，
--         并补齐商品、用户、渠道、营收归属、授权时长、退款汇总与业务归属字段；
--         是大部分营收 / 订单 / 首单 / 续费 / 退款分析的底层事实表（来源 biMetadata）
--
-- 【统计口径】
--   金额类见 COMMENT；正价与营收展示多在宽表 glossary 口径
--   补充（来源 biMetadata）：
--   - 本表是**订单事件事实**，不是快照表
--   - 仅保留 `dw.fact_order` 中 `status IN ('支付成功','退款成功')` 且非测试的订单
--   - 金额字段单位均为**元**；`sub_amount` 是整单金额按 SKU/子商品比例分摊后的子订单金额
--   - `paid_time_sk` 为支付发生日；`date_sk` 为订单创建日；分析付费通常看 `paid_time_sk`
--   - `refund_info_list` 记录该子订单的退款明细；逐次退款分析请用 dw.fact_order_detail_refund
--   - `add_time_day` / `add_time_ms`、`activate_time` / `activate_time_sk` 会按权限表、
--     商品类型、保险、课程包等逻辑校正，不是简单照搬源订单字段
--
-- 【常用筛选条件】
--   场景条件：
--   - status、is_test_user 等在本表或下游宽表按需求
--
--   补充（来源 biMetadata）：
--   - 非分区表，建议始终带 `paid_time_sk`、`status`、`payment_platform`、
--     `business_attribution` 等条件
--   - 若只统计实付订单，常见再加 `sub_amount > 0`
--
-- 【常用关联】（来源 biMetadata）
--   | 场景 | Join Key | 说明 |
--   |------|----------|------|
--   | 原子订单分析 | order_id + sub_good_sk | 子订单唯一口径 |
--   | 用户付费分析 | user_sk                | 常配合 paid_time_sk |
--   | 退款分析     | order_id + sub_good_sk | 与 dw.fact_order_detail_refund 对应 |
--
-- 【注意事项】
--   - 更新频率 T+1
--
--   补充常见误用（来源 biMetadata）：
--   - 把 order_id 当唯一行键：同一订单可能拆成多个子商品
--   - 用 date_sk 当支付日：支付分析通常应看 paid_time_sk
--   - 将 sub_amount 理解为源系统原始金额：它是按子商品比例分摊后的结果
--   - 把 refund_info_list 当最终退款事实：逐次退款请用退款事实表
--
-- 【数据来源】（来源 biMetadata）
--   - 调度实现类：com.onion.etl.dw.FactOrderDetail
--   - 主链步骤：
--     1. 从 go_order.order_list、go_order.good_info、dw.fact_order 等取订单与商品信息
--     2. 基于 dw.dim_sub_good 按 SKU 将整单拆成子商品，并计算 sub_amount
--     3. 结合 dw.fact_userauth、课程包、保险、设备授权等修正 activate_time、add_time_day
--     4. 将服务费、手续费、到账金额、退款汇总等按子订单比例分摊，并做舍入差异纠偏
--     5. 补充用户属性、学校、归属、销售来源、商品类目、团队归属后写入目标表
--
-- =====================================================

CREATE EXTERNAL TABLE `dw`.`fact_order_detail` (
  `order_id` string COMMENT '订单业务 ID |上游：来自订单系统 |加工：与 sub_good_sk 共同唯一',
  `good_sk` int COMMENT '商品代理键 |上游：商品维映射 |加工：无',
  `good_name` string COMMENT '商品名 |上游：原订单 / 商品维 |加工：无',
  `sub_good_cnt` int COMMENT '该订单对应子商品个数 |上游：dw.dim_sub_good 聚合 |加工：无',
  `sub_good_sk` int COMMENT '子商品代理键 |上游：dw.dim_sub_good |加工：子订单维度',
  `user_sk` int COMMENT '用户代理键 |上游：订单主表 / 用户维 |加工：无',
  `u_user` string COMMENT '用户 ID |上游：订单主表 |加工：无',
  `date_sk` int COMMENT '订单创建日 |上游：原订单字段 |加工：无',
  `update_time_sk` int COMMENT '订单修改日 |上游：原订单字段 |加工：无',
  `status` string COMMENT '当前订单状态 |上游：源订单 \'支付成功/退款成功\' |加工：仅保留这两种成功态',
  `kind` string COMMENT '子商品类型 |上游：子商品维 |加工：无',
  `stage_id` int COMMENT '学段 ID |上游：子商品维 |加工：无',
  `stage_name` string COMMENT '学段名 |上游：子商品维 |加工：无',
  `subject_id` int COMMENT '学科 ID |上游：子商品维 |加工：无',
  `subject_name` string COMMENT '学科名 |上游：子商品维 |加工：无',
  `semester_id` int COMMENT '学期 ID |上游：子商品维 |加工：无',
  `semester_name` string COMMENT '学期名 |上游：子商品维 |加工：无',
  `good_original_amount` double COMMENT '商品原价 |上游：源订单 / 商品信息 |加工：无',
  `original_amount` double COMMENT '整单原价 |上游：源订单 |加工：无',
  `amount` double COMMENT '整单实收金额 |上游：源订单 |加工：无',
  `discount_amount` double COMMENT '优惠金额 |上游：源订单 |加工：无',
  `sub_amount` double COMMENT '子订单实收金额 |上游：整单金额按 SKU/子商品比例分摊 |加工：保留 4 位小数并做差额纠偏',
  `add_time_ms` bigint COMMENT '服务时长毫秒 |上游：商品权限、课程包、保险等多源计算 |加工：会按商品类型修正',
  `add_time_day` int COMMENT '服务时长天数 |上游：同 add_time_ms |加工：会按商品类型修正',
  `client_os` string COMMENT '下单客户端 OS |上游：源订单 |加工：无',
  `payment_platform` string COMMENT '支付平台 |上游：源订单 |加工：开放集合',
  `platform_id` string COMMENT '平台 ID |上游：源订单 |加工：无',
  `business_id` string COMMENT '商户 ID |上游：源订单 |加工：无',
  `role` string COMMENT '用户角色 |上游：源订单 / 用户维 |加工：无',
  `business_group` string COMMENT '业务群 |上游：历史订单明细回补 |加工：无',
  `activate_time_sk` int COMMENT '激活日 |上游：权限表、课程包、绑定时间等多源计算 |加工：不是简单取支付日',
  `create_time` timestamp COMMENT '源创建时间 |上游：源订单 |加工：无',
  `update_time` timestamp COMMENT '源更新时间 |上游：源订单 |加工：无',
  `dw_insert_time` timestamp COMMENT 'ETL 写入时间 |上游：now() |加工：无',
  `dw_update_time` timestamp COMMENT 'ETL 更新时间 |上游：now() |加工：无',
  `publisher_id` int COMMENT '教材版本 ID |上游：子商品维 |加工：无',
  `publisher_name` string COMMENT '教材版本名 |上游：子商品维 |加工：无',
  `product_id` string COMMENT '产品 ID |上游：源订单 |加工：无',
  `is_group_buy` boolean COMMENT '是否线下团购订单 |上游：源订单 |加工：无',
  `app_version` string COMMENT '下单 App 版本 |上游：源订单 |加工：无',
  `service_amount` double COMMENT '服务费 |上游：整单服务费按子订单比例分摊 |加工：保留 4 位小数',
  `procedures_amount` double COMMENT '手续费 |上游：整单手续费按子订单比例分摊 |加工：保留 4 位小数',
  `arrival_amount` double COMMENT '到账金额 |上游：整单到账金额按子订单比例分摊 |加工：保留 4 位小数',
  `payment_channel` string COMMENT '支付渠道 |上游：源订单 |加工：无',
  `coupon` string COMMENT '代金券 ID |上游：源订单 |加工：无',
  `app_channel` string COMMENT '下载渠道 |上游：源订单 |加工：无',
  `transaction_no` string COMMENT '支付流水号 |上游：源订单 |加工：无',
  `is_by_manual` boolean COMMENT '是否手工订单 |上游：源订单 |加工：无',
  `account_id` string COMMENT '账户 ID |上游：源订单 |加工：无',
  `shop_id` string COMMENT '推广来源 ID |上游：源订单 |加工：无',
  `shop_name` string COMMENT '推广来源 |上游：源订单 |加工：无',
  `is_parent_telemarketing` smallint COMMENT '是否家长电销订单 |上游：CRM/训练营订单匹配 |加工：0/1',
  `seat_no` string COMMENT '坐席号 |上游：CRM/训练营订单匹配 |加工：无',
  `mid_revenue_amount` double COMMENT '中学营收 |上游：源营收带出 |加工：无',
  `mid_revenue_finance_amount` double COMMENT '中学财务营收 |上游：源营收带出 |加工：无',
  `teacher_school_revenue_amount` double COMMENT '教师线下营收 |上游：源营收带出 |加工：无',
  `teacher_school_revenue_finance_amount` double COMMENT '教师线下财务营收 |上游：源营收带出 |加工：无',
  `parent_revenue_amount` double COMMENT '家长营收 |上游：源营收带出 |加工：无',
  `parent_revenue_finance_amount` double COMMENT '家长财务营收 |上游：源营收带出 |加工：无',
  `primary_revenue_amount` double COMMENT '小学营收 |上游：源营收带出 |加工：无',
  `primary_revenue_finance_amount` double COMMENT '小学财务营收 |上游：源营收带出 |加工：无',
  `other_revenue_amount` double COMMENT '其他营收 |上游：源营收带出 |加工：无',
  `paid_time` timestamp COMMENT '支付时间 |上游：源订单 |加工：无',
  `paid_time_sk` int COMMENT '支付业务日 |上游：源订单 |加工：付费分析主日字段',
  `recalled` boolean COMMENT '权限是否收回 |上游：源订单退款信息 |加工：无',
  `total_refund_amt` double COMMENT '累计退款金额 |上游：整单退款汇总按子订单比例分摊 |加工：保留 4 位小数',
  `refund_info_list` array < string > COMMENT '退款明细数组 |上游：源退款信息按子订单比例分摊 |加工：元素格式为 退款时间,金额,是否收回权益[,退款id]',
  `remain_amt` double COMMENT '子订单剩余金额 |上游：sub_amount - total_refund_amt |加工：保留 4 位小数',
  `shop_detail_id` string COMMENT '推广来源明细 ID |上游：源订单 |加工：无',
  `shop_detail_name` string COMMENT '推广来源明细名 |上游：源订单 |加工：无',
  `os` string COMMENT '端口 |上游：源订单 |加工：无',
  `is_by_manual_opertion` boolean COMMENT '是否手工标记订单 |上游：源订单 |加工：无',
  `activate_time` timestamp COMMENT '激活时间 |上游：权限表、绑定时间等多源计算 |加工：会按商品类型修正',
  `good_id` string COMMENT '商品 ID |上游：源订单 |加工：无',
  `attribution` string COMMENT '源订单 B/C 归属 |上游：源订单 |加工：开放集合',
  `check_attribution` string COMMENT '中台计算 B/C 归属 |上游：ETL 规则计算 |加工：常见 b/c',
  `grade` string COMMENT '用户填写年级 |上游：用户维补充 |加工：无',
  `mid_grade` string COMMENT '中学修正年级 |上游：用户维补充 |加工：无',
  `mid_stage_name` string COMMENT '中学修正学段 |上游：用户维补充 |加工：无',
  `gender` string COMMENT '用户性别 |上游：用户维补充 |加工：无',
  `regist_time` timestamp COMMENT '注册时间 |上游：用户维补充 |加工：无',
  `regist_time_sk` int COMMENT '注册日 |上游：用户维补充 |加工：无',
  `regist_channel` string COMMENT '注册渠道 |上游：用户维补充 |加工：无',
  `u_from` string COMMENT '注册系统平台 |上游：用户维补充 |加工：无',
  `regist_type` string COMMENT '注册方式 |上游：用户维补充 |加工：无',
  `is_put_channel` smallint COMMENT '是否投放渠道 |上游：用户维补充 |加工：0/1',
  `province` string COMMENT '省 |上游：用户维补充 |加工：无',
  `province_code` string COMMENT '省编码 |上游：用户维补充 |加工：无',
  `city` string COMMENT '市 |上游：用户维补充 |加工：无',
  `city_code` string COMMENT '市编码 |上游：用户维补充 |加工：无',
  `area` string COMMENT '区县 |上游：用户维补充 |加工：无',
  `area_code` string COMMENT '区县编码 |上游：用户维补充 |加工：无',
  `is_test_user` smallint COMMENT '是否测试用户 |上游：用户维补充 |加工：0/1',
  `is_teach_user` smallint COMMENT '是否教学班用户 |上游：用户维补充 |加工：0/1',
  `is_admin_room` smallint COMMENT '是否行政班用户 |上游：用户维补充 |加工：0/1',
  `is_room_user` smallint COMMENT '是否有班用户 |上游：用户维补充 |加工：0/1',
  `is_new_user` smallint COMMENT '是否新用户 |上游：用户维补充 |加工：0/1',
  `school_sk` int COMMENT '学校代理键 |上游：用户维补充 |加工：无',
  `school_id` string COMMENT '学校 ID |上游：用户维补充 |加工：无',
  `school_sk1` int COMMENT '修正学校代理键 |上游：用户维补充 |加工：无',
  `school_id1` string COMMENT '修正学校 ID |上游：用户维补充 |加工：无',
  `user_attribution` string COMMENT '活跃时归属 |上游：用户维补充 |加工：无',
  `regist_user_attribution` string COMMENT '注册时归属 |上游：用户维补充 |加工：无',
  `missed_order` boolean COMMENT '是否掉单 |上游：源订单 |加工：无',
  `group` array < string > COMMENT '商品 / 订单标签数组 |上游：源订单与商品维 |加工：原样带出',
  `real_add_time_day` int COMMENT '真实服务时长 |上游：校正前时长 |加工：无',
  `real_activate_time` timestamp COMMENT '真实激活时间 |上游：校正前激活时间 |加工：无',
  `sell_from` string COMMENT '售卖来源 |上游：源订单 extra 字段 |加工：无',
  `new_media_revenue_finance_amount` double COMMENT '新媒体财务营收 |上游：营收补充字段 |加工：无',
  `institution_revenue_finance_amount` double COMMENT '机构财务营收 |上游：营收补充字段 |加工：无',
  `business_attribution` string COMMENT '业务营收归属 |上游：ETL CASE 计算 |加工：常见 B 端/轻课/小学网课等',
  `yc_from` string COMMENT '机构名称 |上游：源订单 extra 字段 |加工：无',
  `sku_amount` double COMMENT 'sku 价格 |上游：商品明细 |加工：无',
  `sku_name` string COMMENT 'sku 名称 |上游：商品维 |加工：无',
  `procedures_rate` double COMMENT '手续费率 |上游：源订单 |加工：四舍五入到 3 位',
  `sn` string COMMENT 'pad SN |上游：源订单 |加工：无',
  `good_sell_kind` string COMMENT '商品售卖类型 |上游：由商品组合、金额、kind 等规则判定 |加工：非源系统原值',
  `is_pad_price_difference_order` boolean COMMENT '是否体验机补差价订单 |上游：源订单 |加工：无',
  `new_media_type` string COMMENT '新媒体营收类型 |上游：历史订单回补 |加工：无',
  `model_type` string COMMENT '平板型号 |上游：sku 维 |加工：无',
  `insurance_category` string COMMENT '保险类别 |上游：sku 维 |加工：无',
  `dynamic_diff_price_type` string COMMENT '补差价类型 |上游：ETL CASE 计算 |加工：体验机补差 / 系统补差 / 非补差',
  `binding_time` timestamp COMMENT '绑定时间 |上游：源订单 / 校正逻辑 |加工：早期数据可能回退支付时间',
  `binding_time_sk` int COMMENT '绑定业务日 |上游：由 binding_time 转换 |加工：无',
  `good_year` string COMMENT '商品时长描述 |上游：商品维 |加工：无',
  `good_content` string COMMENT '内容标识 |上游：商品维 |加工：无',
  `business_gmv_attribution` string COMMENT '业务 GMV 归属 |上游：ETL 规则计算 |加工：开放集合',
  `xugou_order_kind` string COMMENT '续购订单类型 |上游：源订单 |加工：无',
  `xugou_pre_order_id` string COMMENT '续购前序订单 ID |上游：源订单 |加工：无',
  `discount_id` string COMMENT '优惠券 ID |上游：源订单 |加工：无',
  `discount_note` string COMMENT '优惠券说明 |上游：源订单 |加工：无',
  `discount_price` double COMMENT '优惠券金额 |上游：源订单 |加工：无',
  `special_course_type` string COMMENT '课程包类型 |上游：sku / 子商品维 |加工：无',
  `discount_order_id` string COMMENT '尾款优惠券订单 ID |上游：源订单 |加工：无',
  `team_ids` array < string > COMMENT '全域业绩归属 ID |上游：源订单 |加工：原样带出',
  `team_names` array < string > COMMENT '全域业绩归属名称 |上游：源订单 |加工：原样带出',
  `good_category` string COMMENT '商品类别 |上游：源订单 |加工：无',
  `sku_group_good_id` string COMMENT 'sku 商品组 ID |上游：源订单 |加工：无',
  `good_type` string COMMENT '商品类型 |上游：ETL 规则计算 |加工：推荐优先使用类目字段',
  `correct_team_names` array < string > COMMENT '修正后业绩归属 |上游：多级优先级规则计算 |加工：非源系统直接字段',
  `first_order_type` string COMMENT '前序订单类型 |上游：基于前序/赠课逻辑计算 |加工：无',
  `last_order_type` string COMMENT '尾单类型 |上游：基于赠课 / 尾单逻辑计算 |加工：无',
  `coupon_order_id` string COMMENT '前序优惠券订单 ID |上游：go_order.promotions |加工：无',
  `pad_type` string COMMENT '平板类型 |上游：sku 与商品组规则计算 |加工：常见 S30/Q20/其他/不带平板',
  `pre_order_id` string COMMENT '前序订单 ID |上游：源订单 / 派生字段 |加工：无',
  `live_platform_tag` string COMMENT '直播平台标签 |上游：三方直播订单匹配 |加工：无',
  `good_kind_name_level_1` string COMMENT '商品类目一级 |上游：sku 类目维 |加工：无',
  `good_kind_name_level_2` string COMMENT '商品类目二级 |上游：sku 类目维 |加工：无',
  `good_kind_name_level_3` string COMMENT '商品类目三级 |上游：sku 类目维 |加工：无',
  `good_kind_id_level_1` string COMMENT '商品类目一级 ID |上游：sku 类目维 |加工：无',
  `good_kind_id_level_2` string COMMENT '商品类目二级 ID |上游：sku 类目维 |加工：无',
  `good_kind_id_level_3` string COMMENT '商品类目三级 ID |上游：sku 类目维 |加工：无',
  `auth_time_sk` int COMMENT '授权赋予时间 |上游：权限表与商品规则计算 |加工：无',
  `good_type_src` string COMMENT '业务系统售后方式 |上游：源订单字段 |加工：常见 Duration/Timing',
  `strategy_type` string COMMENT '策略类型 |上游：源订单策略字段 |加工：20260101 以后按业务系统值',
  `strategy_detail` string COMMENT '策略明细 |上游：源订单策略字段 |加工：未命中回填 {无策略:0}'
)
COMMENT '一笔订单一个子商品一条记录 根据子商品拆分的子订单，只包含支付成功和退款成功的非测试订单'

ROW FORMAT SERDE 'org.apache.hadoop.hive.ql.io.orc.OrcSerde'
STORED AS INPUTFORMAT 'org.apache.hadoop.hive.ql.io.orc.OrcInputFormat'
OUTPUTFORMAT 'org.apache.hadoop.hive.ql.io.orc.OrcOutputFormat'
LOCATION 'tos://yc-data-platform/user/hive/warehouse/dw.db/fact_order_detail'

-- =====================================================
-- 关键枚举补充（来源 biMetadata）
-- =====================================================
--
-- ## status
--
-- | 取值 | 含义 |
-- |------|------|
-- | 支付成功 | 支付完成且未在源订单状态层面被排除 |
-- | 退款成功 | 源订单当前状态已退款成功，但仍保留订单事实 |
--
-- ## 是否类
--
-- - is_group_buy、is_by_manual、recalled、missed_order、is_pad_price_difference_order 为 true/false
-- - 用户补维类 is_* 多为 0/1
--
-- ## 开放集合
--
-- - payment_platform、payment_channel、kind、business_attribution、business_gmv_attribution、
--   good_sell_kind、team_names、strategy_type：开放集合，以订单系统和 ETL 规则为准

-- =====================================================
-- 数据库校验（来源 biMetadata）
-- =====================================================
--
-- - ./scripts/hive-inspect.sh -d dw -t fact_order_detail -m
-- - ./scripts/hive-inspect.sh -q "SELECT order_id, sub_good_sk, status, amount, sub_amount, paid_time_sk, total_refund_amt, refund_info_list, kind, payment_platform FROM dw.fact_order_detail LIMIT 5" -y
-- - 本表为非分区大表；为避免全表扫描，本次未执行全表 count(*)
