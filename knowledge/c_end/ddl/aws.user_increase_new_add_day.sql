-- =====================================================
-- 新增用户日表 aws.user_increase_new_add_day
-- =====================================================
-- 【表粒度】
--   每天每个 app 新增用户一条；分区 day(yyyyMMdd)；T+1
--
-- 【使用场景】
--   - 新增用户：按 day、channel、u_from 统计
--   - 激活-注册漏斗：与 device_increase_new_add_day 同日关联
--
-- 【业务定位】
--   新增注册日明细
--
-- 【常用关联】
--   u_user
--
-- 【常用筛选条件】
--   ★必加：
--   - day BETWEEN ${start} AND ${end}
--   - u_from IN ('android', 'ios', 'harmony')
--   - user_sk > 0
-- =====================================================

CREATE TABLE aws.user_increase_new_add_day (
    user_sk INT COMMENT '用户sk',
    u_user STRING COMMENT '用户id',
    u_from STRING COMMENT '注册端口 android/ios/harmony',
    channel STRING COMMENT '注册渠道',
    type STRING COMMENT '注册方式（详见文件末尾枚举值）',
    role STRING COMMENT '注册时的身份（详见文件末尾枚举值）',
    is_parents SMALLINT COMMENT '注册时是否是家长',
    grade STRING COMMENT '注册时的年级',
    stage STRING COMMENT '注册时的学段（详见文件末尾枚举值）',
    regist_app_version STRING COMMENT '注册时版本',
    province STRING COMMENT '注册时所在省',
    city STRING COMMENT '注册时所在市',
    city_class STRING COMMENT '注册时所在城市分线',
    gender STRING COMMENT '注册时用户性别',
    is_admin_user SMALLINT COMMENT '是否是行政班用户',
    is_active_user SMALLINT COMMENT '是否是活跃用户',
    device_sk BIGINT COMMENT '新增激活设备_sk',
    regist_time_sk INT COMMENT '用户注册日期sk',
    regist_timestamp TIMESTAMP COMMENT '用户注册时间',
    regist_7day_time_sk INT COMMENT '7日内用户注册日期sk',
    regist_7day_timestamp TIMESTAMP COMMENT '7日内用户注册时间',
    device_os STRING COMMENT '设备端口',
    device_channel STRING COMMENT '设备激活渠道',
    device_app_version STRING COMMENT '设备激活时app版本',
    device_product_id STRING COMMENT '设备激活时首次product_id',
    device_province STRING COMMENT '设备的省',
    device_city STRING COMMENT '设备的市',
    device_area STRING COMMENT '设备的区',
    device_city_class STRING COMMENT '设备的城市分线',
    day_timestamp TIMESTAMP COMMENT '日时间戳',
    user_attribution STRING COMMENT '用户归属',
    dw_insert_time TIMESTAMP COMMENT 'etl处理时间戳',
    regist_user_allocation ARRAY<STRING> COMMENT '用户注册当天服务期归属',
    day INT COMMENT '分区日期 yyyyMMdd'
)
USING orc
PARTITIONED BY (day)
COMMENT '一个用户一条记录且对应一个设备，只有设备无用户时用户为空';

-- =====================================================
-- 枚举值
-- =====================================================
--
-- ## stage（注册时的学段）
--
-- > 字段为字符串存储时与数字含义对应如下；统计「中学」时取 stage IN ('2','3')（或等价数值口径）。
--
-- | 枚举值 | 含义 |
-- |--------|------|
-- | 1 | 小学 |
-- | 2 | 初中 |
-- | 3 | 高中 |
-- | 4 | 高职 |
-- | 5 | 学前 |
--
-- | 汇总口径 | 含义 |
-- |----------|------|
-- | 中学 | 初中(2) + 高中(3) |
--
-- ## role（注册时的身份）
--
-- | 枚举值 | 含义 |
-- |--------|------|
-- | student | 学生 |
-- | NULL | 未填/空 |
--
-- ## type（注册方式）
--
-- > 以手机号注册为主路径；落库代码以上游为准。下表为注册方式代码。
--
-- | 枚举值 | 含义 |
-- |--------|------|
-- | phone | 手机号注册（主路径） |
-- | youxuepai | 优学派账号注册 |
-- | bubugao | 步步高账号注册 |
-- | dushulang | 读书郎账号注册 |
-- | weixin | 微信 |
-- | ios | iOS |
-- | signup | signup |
-- | huawei | 华为账号注册   |
-- | qq | QQ |
-- | noPassword | 免密 
-- | quickRegister | 快速注册 |
-- | oppo | OPPO账号注册 |
