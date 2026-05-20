-- =====================================================
-- 用户活跃天表汇总 dws.topic_user_active_detail_day
-- =====================================================
--
-- 【知识库使用边界】
--   - 本表不是 C 端活跃主口径表。
--   - C 端活跃人数、月活、ARPU、活跃用户转化率分母，默认必须使用
--     `aws.business_active_user_last_14_day`。
--   - 本表仅允许在已经用 `aws.business_active_user_last_14_day` 确定活跃用户集合后，
--     通过 `LEFT JOIN` 补充学习行为、设备、下载渠道、端口等辅助字段。
--   - 禁止直接用本表作为 C 端活跃分母或默认用户分层来源。
--

-- =====================================================
-- 【表粒度】★必填
--   用户 + 日期 + 下载渠道 + 产品 + 活跃端口 + 设备 = 一条记录
--   常用聚合：按 u_user + day 去重即为日活
--   分区字段：day（int 类型，格式 yyyyMMdd），T+1 更新
--
--   一个用户一个下载渠道一个产品id一个活跃端口一个手机品牌一个手机型号一个sn_code一条记录(分区 day int，yyyyMMdd)
--   补充：一行 = 一个 user_sk 在一个统计 day 下、一个 product_id + download_channel + client_os
--         + d_model_brand + d_model_name + sn_code 切片上的活跃明细（来源 biMetadata）
--   - 同一用户同一天可因产品、渠道、端、设备不同出现多行
--   - 行集由 dw.fact_user_active_day 当日活跃切片决定，不是全量用户日快照
-- =====================================================

-- =====================================================
-- 【统计口径】
--   日活用户数 = COUNT(DISTINCT u_user)
--   学习活跃数 = COUNT(DISTINCT CASE WHEN is_learn_active_user = 1 THEN u_user END)
--
--   注意：业务指标的权威定义在 glossary.md，本段仅记录"用本表补字段时怎么算"
--   本表中的活跃 UV 说明仅适用于行为辅助分析，不得覆盖 C 端活跃主口径。
--
--   智课用户学校归属：school_sk1
--
--   活跃 UV = COUNT(DISTINCT u_user)；学习活跃等同理
--   字段选择指南：
-- >   默认/无特殊说明 → business_user_pay_status_business ⭐
-- >   需求明确"新用户=当日注册" → business_user_pay_status_statistics
-- >   不需要区分高净值用户 → user_pay_status_statistics 或 user_pay_status_business
--
--   补充（来源 biMetadata）：
--   - 活跃用户数：count(distinct user_sk)
--   - 学习活跃用户数：count(distinct if(is_learn_active_user = 1, user_sk, null))
--   - 课程视频活跃用户数：count(distinct if(is_watch_course_video_user = 1, user_sk, null))
--   - 做题用户数：count(distinct total_problem_user_sk)
--   - 练习用户数：count(distinct total_exercise_user_sk)
--   - enter_*_user_sk、pad_*_user_sk、*_valid_user_sk 是命中场景时回填的用户主键，不是次数
-- =====================================================

-- =====================================================
-- 【常用筛选条件】
--   ★必加条件（默认看 C 端活跃）：
--   - product_id = '01'                                     -- 洋葱学园主站
--   - client_os IN ('android', 'ios', 'harmony')            -- 移动端
--   - active_user_attribution IN ('中学用户', '小学用户', 'c') -- C 端用户
--   场景条件：
--   - is_learn_active_user = 1         -- 区分学习行为活跃 vs 普通活跃（打开APP即算）
--   - is_test_user = 0                 -- 排除测试用户
--
--   ★必加条件（来源 biMetadata）：
--   - day = yyyymmdd                   -- 禁止不带 day 扫全表
--
--   常见过滤（来源 biMetadata）：
--   - role = 'student'
--   - is_test_user = 0
--   - is_active_user = 1
--   - is_learn_active_user = 1
--   - is_watch_course_video_user = 1
--
-- =====================================================
-- 【常用关联】（来源 biMetadata）
--   | 场景 | Join Key | 说明 |
--   |------|----------|------|
--   | 与用户日快照联查 | user_sk + day | 优先和同日 dws.topic_user_info 对齐 |
--   | 与学校维表联查 | school_sk | school_sk1 / school_id1 为修正学校口径 |
--   | 与业务用户表联查 | u_user | 仅在必须对齐业务用户 id 时使用 |
--
-- =====================================================
-- 【业务定位】
--
--   - 活跃主表结果的辅助补字段：学习行为、端口、设备、下载渠道等
--   - 全量用户日活/学习行为：叠加 product_id、client_os、active_user_attribution（见 glossary「C 端活跃默认筛选」）
--   - 寒假/大盘流量：仅用 is_active_user、is_test_user（不加 C 端三件套）
--   - 付费分层、地域、线索在席等直接选列
--   - 按需区分C端和B端活跃用户
--   补充：日粒度活跃分析宽表。以 dw.fact_user_active_day 为主链，补齐用户属性、学校地域、
--         视频/练习/做题/App 使用、页面进入、付费分层、策略标签与线索状态（来源 biMetadata）
-- =====================================================

-- =====================================================
-- 【注意事项】
--
--   ⚠️ is_learn_active_user 区分"学习活跃"与"普通活跃"：
--     · 普通活跃：打开 APP 即算（不加此过滤），日活统计默认用普通活跃
--     · 学习活跃：需有学习行为（加 is_learn_active_user = 1）
--
--   ⚠️ 知识库默认 C 端活跃口径不使用本表做分母；如需本表字段，应从
--     `aws.business_active_user_last_14_day` 的用户集合出发 `LEFT JOIN` 本表。
--
--   ⚠️ user_allocation 字段：用户全域服务期，包含"电销"则表示在电销服务期
--
--   ⚠️ is_clue_seat = 1：表示当天线索在坐席名下（当天快照）
--
--   补充常见误用（来源 biMetadata）：
--   - 本表不是"一用户一日一行"，同一用户同日可因设备、渠道、产品拆多行
--   - count(*) 只能得到活跃切片数，不是人数
--   - product_id='05'/'06' 时，部分注册属性会被 dw.dim_user_m2_his / dw.dim_user_primary 覆盖
--
-- =====================================================
-- 【数据来源】（来源 biMetadata）
--   - 调度入口：com.onion.etl.dws.TopicUserActiveDetailDay
--   - 主链：dw.fact_user_active_day
--   - 维度补充：dw.dim_user_his、dw.dim_region_his、dw.dim_user_primary、dw.dim_user_m2_his
--   - 行为补充：dw.fact_user_use_every_time_day、dw.fact_user_learn_active_detail_day、
--     dw.fact_user_behavior_day、dw.fact_user_watch_video_day、dw.fact_user_exercise_day、
--     dw.fact_user_exercise_problem_day、dw.fact_video_player_day、events.frontend_event_orc
--   - 分层补充：dw.fact_order_detail、dw.fact_clue_allocate_info、dws.topic_user_info
--
-- =====================================================

CREATE EXTERNAL TABLE `dws`.`topic_user_active_detail_day` (
  `user_sk` int COMMENT '用户代理键 |上游：主链来自 dw.fact_user_active_day |加工：主分析优先 user_sk',
  `u_user` string COMMENT '用户id |上游：主链来自 dw.fact_user_active_day |加工：主分析优先 user_sk',
  `role` string COMMENT '用户角色 |上游：默认来自 dw.dim_user_his；product_id=\'05\'/\'06\' 时部分字段优先取专门维表 |加工：is_new_user 用 regist_time_sk = day 判定',
  `grade` string COMMENT '年级 |上游：默认来自 dw.dim_user_his；product_id=\'05\'/\'06\' 时部分字段优先取专门维表 |加工：is_new_user 用 regist_time_sk = day 判定',
  `gender` string COMMENT '性别 |上游：默认来自 dw.dim_user_his；product_id=\'05\'/\'06\' 时部分字段优先取专门维表 |加工：is_new_user 用 regist_time_sk = day 判定',
  `regist_time` timestamp COMMENT '注册时间 |上游：默认来自 dw.dim_user_his；product_id=\'05\'/\'06\' 时部分字段优先取专门维表 |加工：is_new_user 用 regist_time_sk = day 判定',
  `regist_time_sk` int COMMENT '注册时间sk |上游：默认来自 dw.dim_user_his；product_id=\'05\'/\'06\' 时部分字段优先取专门维表 |加工：is_new_user 用 regist_time_sk = day 判定',
  `activate_date` timestamp COMMENT '激活时间 |上游：默认来自 dw.dim_user_his；product_id=\'05\'/\'06\' 时部分字段优先取专门维表 |加工：is_new_user 用 regist_time_sk = day 判定',
  `activate_date_sk` int COMMENT '激活时间sk |上游：默认来自 dw.dim_user_his；product_id=\'05\'/\'06\' 时部分字段优先取专门维表 |加工：is_new_user 用 regist_time_sk = day 判定',
  `user_attribution` string COMMENT '用户注册当天归属 |上游：主链与用户维共同提供 |加工：三者口径不同，不可混用',
  `active_user_attribution` string COMMENT '用户活跃时归属（★必加条件：中学用户/小学用户/c 为C端） |上游：主链与用户维共同提供 |加工：三者口径不同，不可混用',
  `attribution` string COMMENT '用户归属 |上游：主链与用户维共同提供 |加工：三者口径不同，不可混用',
  `channel` string COMMENT '注册渠道 |上游：来自 dw.dim_user_his，并按产品口径覆写 |加工：regist_os 不等于本行活跃端',
  `u_from` string COMMENT '系统平台 |上游：来自 dw.dim_user_his，并按产品口径覆写 |加工：regist_os 不等于本行活跃端',
  `regist_app_version` string COMMENT '注册时的app版本号 |上游：来自 dw.dim_user_his，并按产品口径覆写 |加工：regist_os 不等于本行活跃端',
  `school_tag` smallint COMMENT '学校标签：0:非维护学校，1普通维护学校，2、重点维护学校 |上游：主链、地域维、用户维 |加工：修正学校口径与原学校口径需分开用',
  `regist_entrance_id` string COMMENT '注册入口 |上游：来自 dw.dim_user_his，并按产品口径覆写 |加工：regist_os 不等于本行活跃端',
  `regist_os` string COMMENT '操作系统 |上游：来自 dw.dim_user_his，并按产品口径覆写 |加工：regist_os 不等于本行活跃端',
  `regist_type` string COMMENT '注册方式 |上游：来自 dw.dim_user_his，并按产品口径覆写 |加工：regist_os 不等于本行活跃端',
  `city_class` string COMMENT '用户城市分线 |上游：主链、地域维、用户维 |加工：修正学校口径与原学校口径需分开用',
  `province` string COMMENT '省名称 |上游：主链、地域维、用户维 |加工：修正学校口径与原学校口径需分开用',
  `province_code` string COMMENT '省code |上游：主链、地域维、用户维 |加工：修正学校口径与原学校口径需分开用',
  `city` string COMMENT '市名称 |上游：主链、地域维、用户维 |加工：修正学校口径与原学校口径需分开用',
  `city_code` string COMMENT '市code |上游：主链、地域维、用户维 |加工：修正学校口径与原学校口径需分开用',
  `area` string COMMENT '区名称 |上游：主链、地域维、用户维 |加工：修正学校口径与原学校口径需分开用',
  `area_code` string COMMENT '区code |上游：主链、地域维、用户维 |加工：修正学校口径与原学校口径需分开用',
  `school_id` string COMMENT '学校id |上游：主链、地域维、用户维 |加工：修正学校口径与原学校口径需分开用',
  `school_sk` int COMMENT '学校sk |上游：主链、地域维、用户维 |加工：修正学校口径与原学校口径需分开用',
  `school_id1` string COMMENT '学校id1 |上游：主链、地域维、用户维 |加工：修正学校口径与原学校口径需分开用',
  `school_sk1` int COMMENT '学校sk1 |上游：主链、地域维、用户维 |加工：修正学校口径与原学校口径需分开用',
  `admin_room_id` string COMMENT '用户行政班id |上游：主链、地域维、用户维 |加工：修正学校口径与原学校口径需分开用',
  `school_agent_id` string COMMENT '用户所在学校的代理商id |上游：主链、地域维、用户维 |加工：修正学校口径与原学校口径需分开用',
  `is_bind_parent` smallint COMMENT '是否绑定家长用户 |上游：用户维与活跃主链 |加工：全部落 0/1',
  `is_test_user` smallint COMMENT '是否测试用户 |上游：用户维与活跃主链 |加工：全部落 0/1',
  `is_teach_user` smallint COMMENT '是否教学班用户 |上游：用户维与活跃主链 |加工：全部落 0/1',
  `is_admin_user` smallint COMMENT '是否在行政班 |上游：用户维与活跃主链 |加工：全部落 0/1',
  `is_room_user` smallint COMMENT '是否有班 |上游：用户维与活跃主链 |加工：全部落 0/1',
  `is_put_channel` smallint COMMENT '是否投放渠道 |上游：用户维与活跃主链 |加工：全部落 0/1',
  `is_new_user` smallint COMMENT '是否新注册用户 |上游：用户维与活跃主链 |加工：全部落 0/1',
  `is_vip_user` smallint COMMENT '是否是vip用户 |上游：用户维与活跃主链 |加工：全部落 0/1',
  `ss_arr` array < string > COMMENT 'vip的学段学科数组 |上游：主链 + dw.fact_user_mid_active_type_day |加工：mid_active_type 落中文值',
  `mid_grade` string COMMENT '中学修正年级 |上游：主链 + dw.fact_user_mid_active_type_day |加工：mid_active_type 落中文值',
  `mid_stage_name` string COMMENT '中学修正学段 |上游：主链 + dw.fact_user_mid_active_type_day |加工：mid_active_type 落中文值',
  `mid_active_type` string COMMENT '(中学)活跃类型：1新增 2 持续 3回流 |上游：主链 + dw.fact_user_mid_active_type_day |加工：mid_active_type 落中文值',
  `category` array < string > COMMENT '用户活跃功能 |上游：埋点与用户维 |加工：category 为多值数组',
  `stage_id` int COMMENT '学段id |上游：埋点与用户维 |加工：category 为多值数组',
  `subject_id` int COMMENT '学科id |上游：埋点与用户维 |加工：category 为多值数组',
  `client_os` string COMMENT '用户活跃的os（★必加条件：android/ios/harmony 为移动端） |上游：主链 dw.fact_user_active_day |加工：共同决定是否拆多行',
  `product_id` string COMMENT '产品ID（★必加条件：= 01 为主站） |上游：主链 dw.fact_user_active_day |加工：共同决定是否拆多行',
  `download_channel` string COMMENT '下载渠道 |上游：主链 dw.fact_user_active_day |加工：共同决定是否拆多行',
  `is_learn_active_user` smallint COMMENT '是否学习活跃用户 |上游：dw.fact_user_active_day、dw.fact_user_learn_active_detail_day、dw.fact_user_behavior_day |加工：本行粒度已聚合',
  `is_active_user` smallint COMMENT '是否活跃用户 |上游：dw.fact_user_active_day、dw.fact_user_learn_active_detail_day、dw.fact_user_behavior_day |加工：本行粒度已聚合',
  `learn_active_cnt` int COMMENT '学习活跃次数 |上游：dw.fact_user_active_day、dw.fact_user_learn_active_detail_day、dw.fact_user_behavior_day |加工：本行粒度已聚合',
  `active_cnt` int COMMENT '活跃次数 |上游：dw.fact_user_active_day、dw.fact_user_learn_active_detail_day、dw.fact_user_behavior_day |加工：本行粒度已聚合',
  `topic_finish_cnt` int COMMENT '完成知识点数 |上游：dw.fact_user_active_day、dw.fact_user_learn_active_detail_day、dw.fact_user_behavior_day |加工：本行粒度已聚合',
  `app_use_duration` int COMMENT 'app使用时长(秒) |上游：dw.fact_user_use_every_time_day 聚合 |加工：app_user_cnt 是使用记录数',
  `app_user_cnt` int COMMENT 'app使用次数 |上游：dw.fact_user_use_every_time_day 聚合 |加工：app_user_cnt 是使用记录数',
  `is_watch_course_video_user` smallint COMMENT '是否课程视频活跃用户 |上游：dw.fact_user_watch_video_day，过滤 video_type_level1=\'course\' |加工：serious_* 用 finish_type_level > 6；finish_* 用 is_finish=true',
  `watch_course_video_cnt` int COMMENT '课程视频开始次数 |上游：dw.fact_user_watch_video_day，过滤 video_type_level1=\'course\' |加工：serious_* 用 finish_type_level > 6；finish_* 用 is_finish=true',
  `watch_course_video_duration` int COMMENT '课程视频活跃时长（秒） |上游：dw.fact_user_watch_video_day，过滤 video_type_level1=\'course\' |加工：serious_* 用 finish_type_level > 6；finish_* 用 is_finish=true',
  `serious_watch_course_video_cnt` int COMMENT '课程视频认真观看次数 |上游：dw.fact_user_watch_video_day，过滤 video_type_level1=\'course\' |加工：serious_* 用 finish_type_level > 6；finish_* 用 is_finish=true',
  `finish_watch_course_video_cnt` int COMMENT '课程视频完播次数 |上游：dw.fact_user_watch_video_day，过滤 video_type_level1=\'course\' |加工：serious_* 用 finish_type_level > 6；finish_* 用 is_finish=true',
  `is_valid_watch_course_video_user` smallint COMMENT '是否课程视频活跃用户（观看时长>0） |上游：dw.fact_user_watch_video_day 增加 learn_duration > 0 |加工：与普通视频口径并存',
  `valid_watch_course_video_cnt` int COMMENT '课程视频开始次数（观看时长>0） |上游：dw.fact_user_watch_video_day 增加 learn_duration > 0 |加工：与普通视频口径并存',
  `valid_watch_course_video_duration` int COMMENT '课程视频活跃时长（观看时长>0） |上游：dw.fact_user_watch_video_day 增加 learn_duration > 0 |加工：与普通视频口径并存',
  `valid_serious_watch_course_video_cnt` int COMMENT '课程视频认真观看次数（观看时长>0） |上游：dw.fact_user_watch_video_day 增加 learn_duration > 0 |加工：与普通视频口径并存',
  `valid_finish_watch_course_video_cnt` int COMMENT '课程视频完播次数（观看时长>0） |上游：dw.fact_user_watch_video_day 增加 learn_duration > 0 |加工：与普通视频口径并存',
  `total_exercise_cnt` int COMMENT '所有模块练习次数 |上游：dw.fact_user_exercise_day、dw.fact_user_exercise_problem_day、dw.fact_video_player_day |加工：total_*_user_sk 为人数辅助列；做题时长取较稳妥口径',
  `total_exercise_user_sk` int COMMENT '所有模块练习学生sk |上游：dw.fact_user_exercise_day、dw.fact_user_exercise_problem_day、dw.fact_video_player_day |加工：total_*_user_sk 为人数辅助列；做题时长取较稳妥口径',
  `total_exercise_finish_cnt` int COMMENT '所有模块练习完成次数 |上游：dw.fact_user_exercise_day、dw.fact_user_exercise_problem_day、dw.fact_video_player_day |加工：total_*_user_sk 为人数辅助列；做题时长取较稳妥口径',
  `total_exercise_finish_user_sk` int COMMENT '所有模块练习完成学生sk |上游：dw.fact_user_exercise_day、dw.fact_user_exercise_problem_day、dw.fact_video_player_day |加工：total_*_user_sk 为人数辅助列；做题时长取较稳妥口径',
  `total_problem_cnt` int COMMENT '所有模块练习做题次数 |上游：dw.fact_user_exercise_day、dw.fact_user_exercise_problem_day、dw.fact_video_player_day |加工：total_*_user_sk 为人数辅助列；做题时长取较稳妥口径',
  `total_problem_user_sk` int COMMENT '所有模块练习做题学生sk |上游：dw.fact_user_exercise_day、dw.fact_user_exercise_problem_day、dw.fact_video_player_day |加工：total_*_user_sk 为人数辅助列；做题时长取较稳妥口径',
  `total_exercise_duration` double COMMENT '练习时长 |上游：dw.fact_user_exercise_day、dw.fact_user_exercise_problem_day、dw.fact_video_player_day |加工：total_*_user_sk 为人数辅助列；做题时长取较稳妥口径',
  `total_problem_duration` double COMMENT '做题目的时长 |上游：dw.fact_user_exercise_day、dw.fact_user_exercise_problem_day、dw.fact_video_player_day |加工：total_*_user_sk 为人数辅助列；做题时长取较稳妥口径',
  `total_problem_correct_rate` double COMMENT '做题目的正确率 |上游：dw.fact_user_exercise_day、dw.fact_user_exercise_problem_day、dw.fact_video_player_day |加工：total_*_user_sk 为人数辅助列；做题时长取较稳妥口径',
  `total_problem_explain_duration` double COMMENT '解析总时长 |上游：dw.fact_user_exercise_day、dw.fact_user_exercise_problem_day、dw.fact_video_player_day |加工：total_*_user_sk 为人数辅助列；做题时长取较稳妥口径',
  `total_video_explain_duration` int COMMENT '视频解析总时长 |上游：dw.fact_user_exercise_day、dw.fact_user_exercise_problem_day、dw.fact_video_player_day |加工：total_*_user_sk 为人数辅助列；做题时长取较稳妥口径',
  `user_pay_status_statistics` string COMMENT '新增(统计日期当天注册的)、付费(统计日期之前买过正价课)、老未(统计日期之前注册的) |上游：依据历史正价订单与注册天数计算 |加工：常见取值 新增 / 付费 / 老未',
  `user_pay_status_business` string COMMENT '付费用户(统计日期之前买过正价课)、新用户(统计日期30天内注册的)、老用户(统计日期30以前注册的) |上游：依据历史正价订单与注册天数计算 |加工：常见取值 付费用户 / 新用户 / 老用户',
  `click_pad_app_tab_cnt` int COMMENT '点击pad第三发app次数 |上游：events.frontend_event_orc 中 get_Pad_AppTab_AppQuitTime |加工：过滤异常超长时长',
  `click_pad_app_tab_duration` int COMMENT 'pad第三方app使用时长 |上游：events.frontend_event_orc 中 get_Pad_AppTab_AppQuitTime |加工：过滤异常超长时长',
  `enter_scene_chapter_user_sk` int COMMENT '教材同步进入用户user_sk |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `enter_scene_problem_user_sk` int COMMENT '题库进入用户user_sk |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `enter_scene_homework_user_sk` int COMMENT '进入作业场景user_sk |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `enter_scene_homework_valid_user_sk` int COMMENT '作业场景里，进入过作业题型详情页的user_sk |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `enter_scene_before_test_user_sk` int COMMENT '进入备考场景user_sk |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `enter_scene_before_test_valid_user_sk` int COMMENT '备考场景里，完成过至少一个专题的user_sk |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `enter_total_review_user_sk` int COMMENT '进入总复习场景user_sk |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `enter_scene_lt_user_sk` int COMMENT '进入试炼场user_sk |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `enter_wrong_book_user_sk` int COMMENT '进入错题本user_sk |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `enter_wrong_book_valid_user_sk` int COMMENT '至少作答一次错题用户user_sk |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `pad_enter_test_paper_user_sk` int COMMENT '(pad入口)进入试卷用户user_sk |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `pad_enter_report_tab_learn_report_user_sk` int COMMENT '(pad入口)进入学情报告user_sk |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `pad_enter_report_tab_puch_user_sk` int COMMENT '(pad入口)进入学习打卡user_sk |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `pad_enter_report_tab_daily_task_user_sk` int COMMENT '(pad入口)进入每日任务user_sk |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `pad_enter_learn_style_page_user_sk` int COMMENT '(pad入口)进入学习风格user_sk |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `pad_finish_learn_style_test_user_sk` int COMMENT '(pad入口)当日完成学习风格测评user_sk |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `pad_enter_learn_goal_page_user_sk` int COMMENT '(pad入口)进入学习目标user_sk |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `pad_finish_learn_goal_page_user_sk` int COMMENT '(pad入口)当日完成学习目标设定user_sk |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `pad_enter_learn_method_page_user_sk` int COMMENT '(pad入口)进入学习方法user_sk |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `pad_click_learn_method_page_user_sk` int COMMENT '(pad入口)点击任意学习方法user_sk |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `pad_enter_learn_feature_exercise_explain_user_sk` int COMMENT '(pad入口)进入题型精讲user_sk |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `pad_enter_learn_feature_student_note_user_sk` int COMMENT '(pad入口)进入学霸笔记user_sk |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `pad_enter_learn_feature_review_book_user_sk` int COMMENT '(pad入口)进入复习宝典user_sk |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `pad_enter_learn_feature_synthetical_note_user_sk` int COMMENT '(pad入口)进入综合提示user_sk |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `enter_variant_questions_show_page_user_sk` int COMMENT '变式题进入user_sk |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `enter_variant_questions_results_page_user_sk` int COMMENT '变式题有效学习user_sk |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `d_model_brand` string COMMENT '手机品牌 |上游：主链 dw.fact_user_active_day |加工：共同决定是否拆多行',
  `d_model_name` string COMMENT '手机型号 |上游：主链 dw.fact_user_active_day |加工：共同决定是否拆多行',
  `enter_pad_scene_task_user_sk` int COMMENT 'pad任务进入用户user_sk |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `finish_pad_task_claim_user_sk` int COMMENT '场景进入、有效学习、Pad 学习行为用户回填 |上游：全部来自 events.frontend_event_orc 按事件条件判定 |加工：命中则回填本行 user_sk',
  `enter_pad_scene_finaltreat_user_sk` int COMMENT 'pad体检表进入用户user_sk |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `finsh_pad_scene_finaltreat_user_sk` int COMMENT 'pad体检表有效学习用户user_sk |上游：当前表字段，详细来源与计算见对应 ETL/调度 |加工：无',
  `sn_code` string COMMENT 'sn_code |上游：主链 dw.fact_user_active_day |加工：共同决定是否拆多行',
  `user_allocation` array < string > COMMENT '用户全域服务期 |上游：用户维与 dws.topic_user_info |加工：user_identity 常见值见枚举段',
  `business_user_pay_status_statistics` string COMMENT '新增(统计日期当天注册的)、大会员付费用户(统计日期之前买过大会员商品)、续费用户(统计日期之前买过正价课)、老未(统计日期之前注册的) |上游：在统计口径基础上优先判断高净值商品历史 |加工：常见取值 高净值用户 / 续费用户 / 新用户 / 老用户',
  `regist_user_allocation` array < string > COMMENT '用户注册当天服务期归属 |上游：用户维与 dws.topic_user_info |加工：user_identity 常见值见枚举段',
  `user_vip_tag` string COMMENT '会员身份标签 |上游：用户维与 dws.topic_user_info |加工：user_identity 常见值见枚举段',
  `business_user_pay_status_business` string COMMENT '大会员付费用户(统计日期之前买过大会员商品)、续费用户(统计日期之前买过正价课)、新用户(统计日期30天内注册的)、老用户(统计日期30以前注册的) |上游：在统计口径基础上优先判断高净值商品历史 |加工：常见取值 高净值用户 / 续费用户 / 新用户 / 老用户',
  `enter_chapter_list_cnt` int COMMENT '进入章节列表也次数 |上游：埋点与资源位补充逻辑 |加工：全是次数口径',
  `enter_payment_page_cnt` int COMMENT '进入付费落地页次数 |上游：埋点与资源位补充逻辑 |加工：全是次数口径',
  `click_discovery_cnt` int COMMENT '点击切换宝藏tab次数 |上游：埋点与资源位补充逻辑 |加工：全是次数口径',
  `click_learn_cnt` int COMMENT '点击切换学习tab次数 |上游：埋点与资源位补充逻辑 |加工：全是次数口径',
  `click_learn_together_cnt` int COMMENT '点击切换共学tab次数 |上游：埋点与资源位补充逻辑 |加工：全是次数口径',
  `click_growup_cnt` int COMMENT '点击切换成长tab次数 |上游：埋点与资源位补充逻辑 |加工：全是次数口径',
  `click_myzone_cnt` int COMMENT '点击切换我的tab次数 |上游：埋点与资源位补充逻辑 |加工：全是次数口径',
  `click_operate_cnt` int COMMENT '触发资源位弹窗次数 |上游：埋点与资源位补充逻辑 |加工：全是次数口径',
  `is_clue_seat` smallint COMMENT '线索是否在坐席名下 |上游：dw.fact_clue_allocate_info 与业务筛选规则 |加工：都落 0/1',
  `user_identity` string COMMENT '用户身份：研究员：common，高级研究员：advanced，首席研究员：lead，体验版首席研究员：expLead |上游：用户维与 dws.topic_user_info |加工：user_identity 常见值见枚举段',
  `is_c_student_active` int COMMENT '是否C端学生活跃 |上游：dw.fact_clue_allocate_info 与业务筛选规则 |加工：都落 0/1',
  `user_strategy_tag_day` string COMMENT '用户策略标签 |上游：来自同日 dws.topic_user_info 与 Hive 分区 |加工：eligibility 为 ; 分隔字符串',
  `user_strategy_eligibility_day` string COMMENT '用户策略资格 |上游：来自同日 dws.topic_user_info 与 Hive 分区 |加工：eligibility 为 ; 分隔字符串'
) COMMENT '一个用户一个下载渠道一个产品id一个活跃端口一个手机品牌一个手机型号一个sn_code一条记录' PARTITIONED BY (`day` int COMMENT '日期分区 |上游：来自同日 dws.topic_user_info 与 Hive 分区 |加工：格式 yyyymmdd') ROW FORMAT SERDE 'org.apache.hadoop.hive.ql.io.orc.OrcSerde' STORED AS INPUTFORMAT 'org.apache.hadoop.hive.ql.io.orc.OrcInputFormat' OUTPUTFORMAT 'org.apache.hadoop.hive.ql.io.orc.OrcOutputFormat' LOCATION 'tos://yc-data-platform/user/hive/warehouse/dws.db/topic_user_active_detail_day' TBLPROPERTIES (
  'alias' = '用户活跃天表汇总',
  'bucketing_version' = '2',
  'is_core' = 'true',
  'last_modified_by' = 'finebi',
  'last_modified_time' = '1755162822',
  'spark.sql.create.version' = '2.3.0.2.6.5.0-292',
  'spark.sql.sources.schema.numPartCols' = '1',
  'spark.sql.sources.schema.numParts' = '4',
  'spark.sql.sources.schema.partCol.0' = 'day',
  'transient_lastDdlTime' = '1768534929'
)

-- =====================================================
-- 枚举值
-- =====================================================
--
-- ## product_id（产品ID）
--
-- > 名称与备注来自 `product_id映射关系.xlsx`（表内首行含维护入口说明）；与 `knowledge/glossary.md`「C 端活跃默认筛选」中 `product_id = '01'` 口径可对照使用。
--
-- | 枚举值 | 含义 |
-- |--------|------|
-- | (空字符串) | 数仓可能出现的空产品编码 |
-- | 01 | 原app；支付；包含教师容器 |
-- | 02 | 教师独立app |
-- | 03 | 小学容器 |
-- | 04 | 学生校园版app 1.0；支持教育局报备 |
-- | 05 | M2(课程4.0) |
-- | 06 | 小学独立APP |
-- | 07 | 洋葱星球app |
-- | 08 | 洋葱学园PICO版 |
-- | 09 | 预习神器 |
-- | 10 | 个性化学习系统 |
-- | 11 | 小学小程序 |
-- | 12 | 家长小程序；家长业务群 |
-- | 13 | 小程序成长版 |
-- | 14 | 洋葱应用市场 |
-- | 21 | 电销小程序-洋葱学园 |
-- | 22 | 2023武汉电销春节福利卡 |
-- | 31 | 原教师pc（洋葱学院PC端） |
-- | 32 | 小学pc |
-- | 33 | PC校园版（解决方案2.0） |
-- | 34 | 运营后台；运营后台创建"校园版"订单 |
-- | 36 | B端运营后台 |
-- | 37 | 个性化学习系统 |
-- | 38 | 电销CRM系统 |
-- | 41 | 站外h5；弃用，站外h5用更小的分类替代，编码101开始 |
-- | 42 | 线下渠道；渠道系统订单 |
-- | 101 | 阿里云OS |
-- | 102 | QQ浏览器 |
-- | 103 | 有赞商城；家长业务群 |
-- | 110 | 小学数学营销小程序 |
-- | 111 | 小学数学学习体验小程序 |
-- | 112 | 洋葱星球小程序授权 |
-- | 120 | 家长洋葱商城；家长业务群（H5 商城）支付 |
-- | 121 | 京东商城；暂未接入订单系统；付缺 |
-- | 122 | 华为教育中心 |
-- | 123 | 百度小程序 |
-- | 124 | 洋葱星球家长课堂小程序授权 |
-- | 201 | 麦莉妈妈（分销商）；小学渠道分销 |
-- | 202 | 妈妈心选 |
-- | 203 | 花生日记 |
-- | 204 | ahaschool |
-- | 205 | 妈觅精选 |
-- | 206 | 枣妈与恺摩 |
-- | 207 | 萌状元 |
-- | 208 | 爸妈严选 |
-- | 209 | 向日葵妈妈分销 |
-- | 210 | 分销合作平台-习惯熊 |
-- | 211 | 分销合作平台公众号订单导入运营后台 |
-- | 300 | H5投放订单；打开H5投放支付的订单，复制链接支付 |
-- | 410 | 寒假课程礼包H5 |
-- | 411 | 企业微信h5 |
-- | 414 | 微店 |
-- | 415 | 抖音app h5页面 |
-- | 416 | 微信app 小程序 |
-- | 417 | 抖店商城 h5页面 |
-- | 418 | 洋葱教辅书二维码 |
-- | 419 | 智能客服系统 |
-- | 421 | 京东商城导入订单or未来接订单使用的h5页面 |
-- | 422 | 社区站外分享 |
-- | 423 | 奥德赛_直播 |
-- | 424 | 企微站外引流-H5登录 |
-- | 425 | 天猫商城h5页面注册 |
-- | 500 | 入校项目的希沃合作 |
-- | 501 | 洋葱学院APP-mac版 |
-- | 700 | 视频号小店导入订单 |
--
-- ## active_user_attribution（用户活跃时归属）
--
-- | 枚举值 | 含义 |
-- |--------|------|
-- | 中学用户 | C 端中学 |
-- | 小学用户 | C 端小学 |
-- | c | C 端其他 |
-- 来源：谭晨、惠慧
--
-- ## attribution（用户归属）
--
-- | 枚举值 | 含义 |
-- |--------|------|
-- | b | b端用户，智课团队的用户 |
-- | c | c端用户，非智课团队的用户 |
-- 来源：诗华
--
-- ## business_user_pay_status_business（见 `dws.topic_user_info` 同名字段 COMMENT；取值对齐线上）
--
-- | 枚举值 | 含义 |
-- |--------|------|
-- | 新用户 | 统计日期30天内注册的（见 `dws.topic_user_info` 字段 COMMENT） |
-- | 续费用户 | 统计日期之前买过正价课（见 `dws.topic_user_info` 字段 COMMENT） |
-- | 老用户 | 统计日期30以前注册的（见 `dws.topic_user_info` 字段 COMMENT） |
-- | 高净值用户 | 统计日期之前方案型商品（不包括商品二级分类 id 为一年积木块、体验机、到期型培优课积木块等）（见 `dws.topic_user_info` 字段 COMMENT） |
--
-- ## user_strategy_tag_day（用户策略标签）
--
-- | 枚举值 | 含义 |
-- |--------|------|
-- | 付费加购品用户 | 付费加购品用户（见 `dws.topic_user_info` / `aws.business_active_user_last_14_day` 枚举段） |
-- | 付费组合品用户 | 付费组合品用户（见 `dws.topic_user_info` / `aws.business_active_user_last_14_day` 枚举段） |
-- | 付费零售品用户 | 付费零售品用户（见 `dws.topic_user_info` / `aws.business_active_user_last_14_day` 枚举段） |
-- | 历史大会员用户_不可续购 | 历史大会员用户_不可续购（见 `dws.topic_user_info` / `aws.business_active_user_last_14_day` 枚举段） |
-- | 历史大会员用户_可续购 | 历史大会员用户_可续购（见 `dws.topic_user_info` / `aws.business_active_user_last_14_day` 枚举段） |
-- | 新用户 | 新用户（见 `dws.topic_user_info` / `aws.business_active_user_last_14_day` 枚举段） |
-- | 老用户 | 老用户（见 `dws.topic_user_info` / `aws.business_active_user_last_14_day` 枚举段） |
--
-- ## user_strategy_eligibility_day（用户策略资格）
--
-- | 枚举值 | 含义 |
-- |--------|------|
-- | (空字符串) | 无策略资格（见 `dws.topic_user_info` 枚举段） |
-- | 历史大会员续购策略资格;学习机加购策略资格 | 历史大会员续购策略资格;学习机加购策略资格（见 `dws.topic_user_info` 枚举段） |
-- | 历史大会员续购策略资格;学习机加购策略资格;小学品升级补差至小初品资格 | 历史大会员续购策略资格;学习机加购策略资格;小学品升级补差至小初品资格（见 `dws.topic_user_info` 枚举段） |
-- | 学习机加购策略资格;高中囤课策略资格 | 学习机加购策略资格;高中囤课策略资格（见 `dws.topic_user_info` 枚举段） |
-- | 学习机加购策略资格;高中囤课策略资格;多孩策略资格;多孩策略资格_寒促特别版 | 学习机加购策略资格;高中囤课策略资格;多孩策略资格;多孩策略资格_寒促特别版（见 `dws.topic_user_info` 枚举段） |
--
-- ## mid_grade（中学修正年级）
--
-- | 枚举值 | 含义 |
-- |--------|------|
-- | NULL | 未归类（与 `dw.dim_user`「grade」枚举段口径一致） |
-- | 一年级 | 一年级 |
-- | 二年级 | 二年级 |
-- | 三年级 | 三年级 |
-- | 四年级 | 四年级 |
-- | 五年级 | 五年级 |
-- | 六年级 | 六年级 |
-- | 七年级 | 七年级 |
-- | 八年级 | 八年级 |
-- | 九年级 | 九年级 |
-- | 高一 | 高一 |
-- | 高二 | 高二 |
-- | 高三 | 高三 |
-- | 学龄前 | 学龄前 |
-- | 职一 | 职一 |
-- | 职二 | 职二 |
-- | 职三 | 职三 |
--
-- ## mid_stage_name（中学修正学段）
--
-- | 枚举值 | 含义 |
-- |--------|------|
-- | NULL | 未归类（与 `dws.topic_user_info`「stage_name」枚举段一致） |
-- | 启蒙 | 启蒙 |
-- | 小学 | 小学 |
-- | 初中 | 初中 |
-- | 高中 | 高中 |
-- | 中职 | 中职 |

-- =====================================================
-- 关键枚举补充（来源 biMetadata）
-- =====================================================
--
-- ## 是否类（本表实际值域）
--
-- | 字段 | 值域 | 含义 |
-- |------|------|------|
-- | `is_bind_parent` / `is_test_user` / `is_teach_user` / `is_admin_user` / `is_room_user` / `is_put_channel` / `is_new_user` / `is_vip_user` / `is_learn_active_user` / `is_active_user` / `is_watch_course_video_user` / `is_valid_watch_course_video_user` / `is_clue_seat` / `is_c_student_active` | 1 / 0 | 1=是，0=否 |
--
-- ## role
--
-- | 取值 | 含义 |
-- |------|------|
-- | student | 学生 |
-- | teacher | 教师 |
--
-- ## client_os
--
-- | 取值 | 含义 |
-- |------|------|
-- | android | Android 端 |
-- | ios | iOS 端 |
-- | pc | PC 端 |
-- | harmony | Harmony 端 |
--
-- ## mid_active_type
--
-- | 取值 | 含义 |
-- |------|------|
-- | 新增 | 新增活跃 |
-- | 持续 | 持续活跃 |
-- | 回流 | 回流活跃 |
-- | NULL | 未命中该口径 |
--
-- ## user_identity
--
-- | 取值 | 含义 |
-- |------|------|
-- | common | 研究员 |
-- | advanced | 高级研究员 |
-- | lead | 首席研究员 |
-- | expLead | 体验版首席研究员 |

-- =====================================================
-- 数据库校验（来源 biMetadata）
-- =====================================================
--
-- - 校验脚本：./scripts/hive-inspect.sh -d dws -t topic_user_active_detail_day -a
-- - 一次查库快照：表类型 EXTERNAL；存储格式 ORC；最新分区 day=20260419；该分区行数 687,790
