# C端取数业务知识字典

## 注册用户数

- **定义**：指定时间范围内完成注册的 C 端用户数。
- **计算方式**：`COUNT(DISTINCT u_user)`
- **表来源**：`aws.user_increase_new_add_day`
- **筛选条件**：`day BETWEEN ${start_day} AND ${end_day}`，`u_from IN ('android', 'ios', 'harmony')`，`user_sk > 0`

## 注册渠道标签

- **定义**：注册用户对应的一级、二级、三级渠道标签。
- **计算方式**：按 `u_user` 与 `day` 关联注册表和渠道标签表。
- **表来源**：`aws.user_increase_new_add_day`、`aws.user_increase_channel_label_day`
- **注意**：渠道标签取数必须保留注册日期条件，避免跨日标签错配。

## 注册用户 LTV

- **定义**：注册 cohort 在指定订单窗口内产生的到账金额。
- **计算方式**：`SUM(arrival_amount) / COUNT(DISTINCT regist_user)`
- **表来源**：`aws.user_increase_new_add_day`、`aws.user_increase_channel_label_day`、`dws.topic_order_detail`
- **筛选条件**：订单状态取 `支付成功`、`退款成功`，订单时间使用 `paid_time_sk`。
- **注意**：订单量必须使用 `COUNT(DISTINCT order_id)`。

## C端活跃用户数

- **定义**：C 端/私域口径下的活跃用户数。
- **计算方式**：`COUNT(DISTINCT user_sk)` 或场景模板中的用户去重字段。
- **表来源**：`aws.business_active_user_last_14_day`
- **注意**：该表只包含 C 端/私域活跃，不代表全公司活跃。

## 活跃用户转化

- **定义**：活跃用户中产生订单或支付行为的用户占比。
- **计算方式**：`pay_user_cnt / active_user_cnt`
- **表来源**：`aws.business_active_user_last_14_day`
- **注意**：付费人数用用户字段去重，不能直接对标记字段求和。

## GMV

- **定义**：指定订单窗口内的订单金额汇总。
- **计算方式**：按场景使用 `SUM(sub_amount)`、`SUM(order_amount)` 或 `SUM(arrival_amount)`。
- **表来源**：`dws.topic_order_detail`
- **筛选条件**：正价场景优先使用 `original_amount >= 39`；业务归属使用 `business_gmv_attribution`。
- **注意**：`dws.topic_order_detail` 是子订单粒度，汇总订单量时必须对 `order_id` 去重。
