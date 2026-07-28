# C端取数业务知识字典

## 术语总览

### 核心对象

| 术语 | 含义 | 主要表 |
| --- | --- | --- |
| 注册用户 | 在指定日期范围内完成注册的 C 端用户 | `aws.user_increase_new_add_day` |
| 注册渠道 | 注册用户对应的一级、二级、三级渠道标签 | `aws.user_increase_channel_label_day` |
| C端活跃用户 | C 端/私域口径下的活跃用户 | `aws.business_active_user_last_14_day` |
| 订单用户 | 在订单表中产生订单行为的用户 | `dws.topic_order_detail` |
| 子订单 | `dws.topic_order_detail` 的明细粒度，一笔主订单可对应多条子订单 | `dws.topic_order_detail` |
| 企微添加用户 | 通过企微渠道添加销售、并按用户和添加关系去重的 C 端用户 | `crm.contact_log` |
| 拉取入库用户 | 企微添加后于次日零点前被拉取进入销售线索库的用户 | `aws.clue_info` |
| 电销订单用户 | 满足电销组织、在职及非测试等条件的支付用户 | `aws.crm_order_info` |

### 核心指标

| 术语 | 标准口径 | 注意事项 |
| --- | --- | --- |
| 注册用户数 | `COUNT(DISTINCT u_user)` | 必须限定 `day` 时间范围 |
| 注册用户 LTV | `pay_amount / install_users` | 默认按注册转化月维度口径计算，`pay_amount` 来自注册月内付费金额，`install_users` 为注册用户数 |
| 活跃用户数 | 基于 `aws.business_active_user_last_14_day`，按 `user_sk + 月份` 去重 | 该表就是 C 端活跃表；一用户一天可能多行，月趋势必须先做用户月去重 |
| 活跃用户转化率 | `pay_user_cnt / active_user_cnt` | 付费用户必须去重，不能直接累加标记字段 |
| 客单价 | `pay_amount / pay_user_cnt` | 按付费人数计算，不按订单数计算 |
| 订单量 | `COUNT(DISTINCT order_id)` | 不能使用 `COUNT(*)` 代表订单量 |
| GMV / 营收 | `SUM(sub_amount)` | 默认看正价营收：订单表 `dws.topic_order_detail`，必须筛选 `is_test_user = 0`、`original_amount >= 39`、`business_gmv_attribution IN ('电销','商业化')`；不默认筛 `status = '支付成功'` |
| 正价订单 | 满足场景 SQL 中正价条件的订单 | 常见条件为 `original_amount >= 39` |
| 企微添加量 | `COUNT(DISTINCT external_user_id)` | 日活漏斗要求活跃日与企微添加日相同 |
| 拉取入库量 | `COUNT(DISTINCT userid)` | 企微添加后、次日零点前首次入库 |
| 销售侧转化量 | `COUNT(DISTINCT paid_userid)` | 日活企微漏斗默认累计转化；月活企微宽表目前仅统计当月转化 |
| 销售侧转化金额 | `SUM(amount)` | 转化周期必须与转化量保持一致 |

### 关键维度

| 术语 | 含义 | 常见字段 |
| --- | --- | --- |
| 注册日期 | 用户完成注册的日期 | `day`、`regist_day` |
| 订单日期 | 订单支付日期 | `paid_time_sk` |
| 端口 | 用户注册或活跃来源端 | `u_from`、`os`、`client_os` |
| 渠道一级标签 | 注册渠道一级分类 | `regist_channel_label1` |
| 渠道二级标签 | 注册渠道二级分类 | `regist_channel_label2` |
| 业务 GMV 归属 | 订单 GMV 业务归属；`商业化` 表示 APP 渠道，`电销` 表示电销渠道 | `business_gmv_attribution` |
| 商品 2.0 类目 | 商品类目体系 | `good_kind_name_level_1`、`good_kind_name_level_2` |
| 策略组商品类目 | 策略组口径商品类目 | `business_good_kind_name_level_1` |

### 渠道与营收归属

`business_gmv_attribution` 常见取值及对外业务名称如下：

| 字段取值 | 对外业务名称 |
| --- | --- |
| `商业化` | APP 渠道 |
| `电销` | 电销渠道 |
| `商业化-电商` | 电商渠道 |
| `新媒体视频` | 新媒体 |
| `新媒体变现` | 研学 |
| `体验营` | 体验营 |
| `入校` | 智课 |

- 默认商业化/私域营收只统计 `电销` 和 `商业化`。
- 如需统计电商、新媒体、研学、体验营或智课，必须显式增加对应取值，并在输出中说明口径变化。

### 年级与学段划分

| 学段 | 包含年级 |
| --- | --- |
| 小低 | 一年级、二年级、三年级 |
| 小高 | 四年级、五年级、六年级 |
| 初中 | 七年级、八年级、九年级 |
| 高中 | 高一、高二、高三 |

- 活跃分析优先使用 `grade_name_month` 进行年级归类。
- 订单分析可使用订单年级字段辅助；如需与活跃用户口径对齐，以活跃用户当月年级为准。

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

- **定义**：注册 cohort 在注册月内产生的付费金额相对注册用户数的人均价值。
- **标准计算方式**：`pay_amount / install_users`
- **字段口径**：

| 字段 | 定义 | 推荐 SQL 表达式 |
| --- | --- | --- |
| `install_users` | 注册月内新增注册用户数 | 看板对齐按聚合维度 `COUNT(u_user)`；若只问去重用户数才用 `COUNT(DISTINCT u_user)` |
| `pay_user_num` | 注册月内有付费的注册用户数 | 看板对齐按宽表粒度 `SUM(is_pay)`，报表层再 `SUM(pay_user_num)`；只有明确要求全局去重用户数时才用 `COUNT(DISTINCT CASE WHEN pay_amount > 0 THEN u_user END)` |
| `pay_amount` | 注册月内到账金额 | `SUM(arrival_amount)` |
| `ltv` | 注册用户 LTV | `pay_amount / NULLIF(install_users, 0)` |

- **表来源**：`aws.user_increase_new_add_day`、`aws.user_increase_channel_label_day`、`dws.topic_order_detail`
- **筛选条件**：

    - 注册用户：`a.u_from IN ('android', 'ios', 'harmony')`，`a.user_sk > 0`
    - 订单：`status IN ('支付成功','退款成功')`；金额用 `arrival_amount`
    - 付费月：`DATE_TRUNC('month', paid_time_sk 日期) = 注册月`

- **默认输出结构**：注册月、端口、注册渠道一级、注册渠道二级、`install_users`、`pay_user_num`、`pay_amount`、`ltv`。
- **月度报表扩展**：如用户要求或使用月维度转化报表，应同时输出 `FULL_MONTH`、`MTD`、`MIX` 和去年同期 `ly_`\* 字段。
- **新增客单价**：看板对齐时使用 `SUM(pay_amount) / SUM(pay_user_num)`，其中 `pay_user_num` 来自宽表聚合后的 `SUM(is_pay)`；其中 `is_pay = IF(up.u_user IS NOT NULL, 1, 0)`（只要订单表有匹配记录即算付费，不要求 amount > 0）；不要改成全局 `COUNT(DISTINCT u_user)` 口径。
- **注意**：只有用户问“新增注册用户的 LTV”、注册转化月维度或月报“新增流量”模块时，才使用 `arrival_amount + status IN ('支付成功','退款成功')` 的新增注册看板口径；不要套用商业化营收的 `sub_amount`、正价、归属或订单层测试用户筛选。整体 GMV、整体营收、活跃 ARPU、活跃付费转化、商品结构等非新增注册场景仍按各自口径，不使用本例外。

## 注册转化月维度

- **定义**：在“注册用户 LTV”口径上，按注册月、端口和注册渠道扩展次月留存、MTD 与同期对比。
- **新增指标**：`retention_users` 为注册次月在 `aws.business_active_user_last_14_day` 出现的活跃用户数；`ly_`* 为去年同期指标。
- **新增表来源**：次月留存使用 `aws.business_active_user_last_14_day`；其余表和指标沿用“注册用户 LTV”章节。
- **输出类型**：

    - `FULL_MONTH`：整月口径。
    - `MTD`：按当前日期的前一日 day-of-month 截断。
    - `MIX`：当前月取 `MTD`，历史月取 `FULL_MONTH`。

- **关联要点**：订单按 `u_user + pay_month` 聚合并按 `reg_month = pay_month` 关联；留存按 `active_month = ADD_MONTHS(reg_month, 1)` 关联。
- **完整 SQL**：见 `gold_cases.md` 的“新增注册看板聚合”。

## C端活跃用户数

- **定义**：C 端/私域口径下的活跃用户数。
- **标准表来源**：`aws.business_active_user_last_14_day`
- **计算方式**：

    - 总量：按 `user_sk + stat_month` 去重后统计人数。
    - SQL 推荐写法：先按 `user_sk, DATE_TRUNC('month', day日期)` 生成一人一月一行，再 `COUNT(*)`。

- **表来源**：`aws.business_active_user_last_14_day`
- **注意**：该表只包含 C 端/私域活跃，不代表全公司活跃。
- **去重原因**：该表一用户一天可能因 `team_ids`、`team_names`、`business_gmv_attribution` 等订单/归属标签出现多行；按月统计时必须先做用户月去重。
- **用户标签字段规则**：

    - 牵涉到用户标签、付费分层、统计分层时，只使用带 `business_` 前缀的字段。
    - 统计维度使用 `business_user_pay_status_statistics_month`，不要使用 `user_pay_status_statistics_month`。
    - 业务维度使用 `business_user_pay_status_business_month`。
    - `user_pay_status_statistics_month` 在 DDL 中标为“知识库不引用”，不要用于取数。

- **辅助表规则**：

    - `dws.topic_user_active_detail_day` 不是 C 端活跃主表。
    - 只有当需要补充学习行为、设备、下载渠道、端口等字段时，才允许在 `aws.business_active_user_last_14_day` 已确定的活跃用户集合上 `LEFT JOIN dws.topic_user_active_detail_day`。
    - 不得使用 `dws.topic_user_active_detail_day` 直接作为活跃人数、ARPU、活跃转化率分母或默认用户分层口径。

## 学习活跃指标

### 核心原则

- **最重要规则**：学习活跃率、视频活跃率、练习渗透率、做题渗透率等指标的活跃分母，统一使用 `aws.business_active_user_last_14_day`。
- `dws.topic_user_active_detail_day` 只提供学习行为分子、次数、时长及辅助维度，不能直接作为活跃分母。
- 先从活跃主表按 `user_sk + day` 圈定并去重活跃用户，再关联学习行为表。
- 学习行为表粒度为“用户 + 日期 + 下载渠道 + 产品 + 活跃端口 + 设备”；同一用户同一天可能多行，关联前必须先聚合到目标粒度。
- 日粒度优先按 `user_sk + day` 关联；月度先聚合为用户日，再按 `user_sk + 月份` 去重用户、累加次数和时长。

### 学习行为表默认筛选

默认看 C 端主站移动端学习行为时，`dws.topic_user_active_detail_day` 使用：

```sql
product_id = '01'
AND client_os IN ('android', 'ios', 'harmony')
AND active_user_attribution IN ('中学用户', '小学用户', 'c')
AND role = 'student'
AND is_test_user = 0
```

- 查询必须包含 `day` 分区过滤。
- 如需全端、Pad、其他产品或全公司学习行为，必须明确调整产品、端口和归属条件。

### 学习活跃

| 指标 | 标准口径 |
| --- | --- |
| 活跃用户数 | 活跃主表中按统计周期去重的 `user_sk` |
| 学习活跃用户数 | 活跃池内 `is_learn_active_user = 1` 的去重用户数 |
| 学习活跃率 | 学习活跃用户数 / 活跃用户数 |
| 学习活跃次数 | `SUM(learn_active_cnt)` |
| 完成知识点数 | `SUM(topic_finish_cnt)` |
| App 使用时长 | `SUM(app_use_duration)`，单位为秒 |
| App 使用次数 | `SUM(app_user_cnt)` |

普通活跃表示打开 App；学习活跃要求存在学习行为，两者不能混用。

### 视频活跃

- **默认口径**：视频活跃统一使用有效课程视频口径，即观看时长大于 0。
- 视频活跃用户使用 `is_valid_watch_course_video_user = 1`。
- 不再默认使用 `is_watch_course_video_user`；该字段只用于对齐明确指定的历史普通视频口径。

| 指标 | 标准口径 |
| --- | --- |
| 有效视频活跃用户数 | 活跃池内 `is_valid_watch_course_video_user = 1` 的去重用户数 |
| 视频活跃率 | 有效视频活跃用户数 / 活跃用户数 |
| 视频开始次数 | `SUM(valid_watch_course_video_cnt)` |
| 视频观看时长 | `SUM(valid_watch_course_video_duration)`，单位为秒 |
| 认真观看次数 | `SUM(valid_serious_watch_course_video_cnt)` |
| 完播次数 | `SUM(valid_finish_watch_course_video_cnt)` |
| 人均观看时长 | 视频观看时长 / 有效视频活跃用户数 |
| 人均开始次数 | 视频开始次数 / 有效视频活跃用户数 |
| 次数完播率 | 完播次数 / 视频开始次数 |
| 完播用户率 | 有完播行为的去重用户数 / 有效视频活跃用户数 |

- “认真观看”对应 `finish_type_level > 6`。
- “完播”对应 `is_finish = true`。

### 练习与做题

- **练习**是练习任务或练习过程层，一次练习通常包含多道题。
- **做题**是题目作答层，不能把做题次数当作练习次数。

| 指标 | 标准口径 |
| --- | --- |
| 练习用户数 | 活跃池内 `total_exercise_user_sk` 非空的去重用户数 |
| 练习渗透率 | 练习用户数 / 活跃用户数 |
| 练习次数 | `SUM(total_exercise_cnt)` |
| 完成练习用户数 | `total_exercise_finish_user_sk` 非空的去重用户数 |
| 完成练习次数 | `SUM(total_exercise_finish_cnt)` |
| 练习完成率 | 完成练习次数 / 练习次数 |
| 做题用户数 | 活跃池内 `total_problem_user_sk` 非空的去重用户数 |
| 做题渗透率 | 做题用户数 / 活跃用户数 |
| 做题次数 | `SUM(total_problem_cnt)` |
| 练习时长 | `SUM(total_exercise_duration)` |
| 做题时长 | `SUM(total_problem_duration)` |
| 解析时长 | `SUM(total_problem_explain_duration)` |
| 视频解析时长 | `SUM(total_video_explain_duration)` |

做题正确率不能直接平均，应按做题次数加权：

```sql
SUM(total_problem_correct_rate * total_problem_cnt)
    / NULLIF(SUM(total_problem_cnt), 0)
```

练习、做题和解析时长的单位在当前字段说明中未明确，对外展示前需要核对上游单位。

### 聚合与关联注意

- 用户标记字段按用户日聚合时使用 `MAX`，次数和时长字段使用 `SUM`。
- 场景用户字段如 `total_exercise_user_sk`、`total_problem_user_sk` 用于去重人数，不是次数。
- 不得只按 `user_sk` 跨日期关联，必须同时包含日期或月份。
- 拆端口、产品、下载渠道或设备时，活跃分母需要单独去重，避免同一用户跨维度重复。
- 补充学习行为后再计算活跃表金额时，必须先单独聚合活跃表金额，禁止在一对多关联后直接求和。

## 电话线索漏斗指标

- **定义**：电话线索（系统线索）从活跃用户到推送、入库、坐席领取，并观察领取后转化用户与转化金额的月度漏斗。
- **标准表来源**：`aws.crm_active_data_pool_paid_month`
- **表粒度**：按 `month` 分区，一个用户一条记录；`month` 为 int 类型，格式 `yyyyMM`。
- **常用指标**：

| 指标 | 推荐计算方式 | 字段说明 |
| --- | --- | --- |
| 活跃量 | `COUNT(DISTINCT active_u_user)` | 当月活跃用户 |
| 推送量 | `COUNT(DISTINCT push_u_user)` | 当月被数仓推送到电销的用户 |
| 入库量 | `COUNT(DISTINCT enter_datapool_u_user)` | 当月进入公海池的用户 |
| 入库电话线索领取量 | `COUNT(DISTINCT recieve_u_user)` | 限制入库 + 电话线索来源的领取用户 |
| 入库领取量 | `COUNT(DISTINCT recieve_u_user_all)` | 限制入库 + 所有来源的领取用户 |
| 活跃领取量 | `COUNT(DISTINCT CASE WHEN active_recieve_u_user_all IS NOT NULL THEN active_u_user END)` | 活跃 + 所有来源领取用户，无公海池前置条件；别名建议 `all_recieve_user` |
| 销售线索领取率 | `活跃领取量 / NULLIF(活跃量, 0)` | 即 `all_recieve_user / active_user` |

- **属性取值时点**：

    - 全部取当月首次活跃日的值（按 `day ASC` 排序取第一条），无月末值。
    - 常用字段包括：`grade_name_month`、`stage_name_month`、`user_pay_status_*_month`、`business_user_pay_status_*_month`、`is_tele_belong_first_month`、`user_allocation_month`。

- **注意**：

    - 该表用于电话线索漏斗，不作为 C 端活跃主表；C 端活跃规模、活跃 ARPU、活跃转化率仍按 `aws.business_active_user_last_14_day` 对应章节处理。
    - 查询必须按 `month` 分区过滤。
    - `recieve_u_user_all` 在本表中表示“进入公海池 + 所有来源领取”；`active_recieve_u_user_all` 才是不限制公海池前置的活跃领取口径。
    - 计算销售线索领取率时，分子用活跃领取量 `COUNT(DISTINCT CASE WHEN active_recieve_u_user_all IS NOT NULL THEN active_u_user END)`，分母用活跃量 `COUNT(DISTINCT active_u_user)`。
    - `first_deny_reason`、`first_deny_index` 用于分析公海池过滤/拒绝原因。

### 活跃—线索覆盖—外呼—营收窗口指标

- **回答要求**：用户询问本专项的任何指标、口径或结果时，回答开头必须先强调：本专项使用销售线索活跃底池，与 C 端活跃主表口径不同，只用于销售线索分析。
- **适用场景**：在指定日期窗口内，观察活跃用户的线索覆盖和外呼表现，并单独统计同期电销营收。用户分层可作为结果维度，但不改变以下指标定义。
- **活跃底池**：使用 `aws.crm_active_data_pool_day`，在统计窗口内按 `active_u_user` 去重。该专项底池与 C 端活跃主表口径不同，只用于销售线索分析。
- **线索覆盖范围**：使用 `aws.clue_info`。领取记录的创建日期不晚于统计结束日，且线索到期日期不早于统计开始日，即该领取记录的有效期与统计窗口有交集。
- **线索组织范围**：`workplace_id IN (4, 400, 702)`、`regiment_id NOT IN (0, 303, 546)`、`user_sk > 0`、`worker_id <> 0`。
- **外呼来源**：`tmp.niyiqiao_crm_clue_call_record`，按 `user_id` 汇总统计窗口内的外呼记录。
- **营收来源**：`aws.crm_order_info`。营收按订单用户单独汇总，不限定为活跃底池用户，避免把同期电销营收误写成“活跃用户营收”。

| 指标 | 计算方式 | 含义 |
| --- | --- | --- |
| 活跃用户数 | `COUNT(DISTINCT active_u_user)` | 统计窗口内销售线索活跃底池的去重用户数 |
| 线索覆盖用户数 | `COUNT(DISTINCT clue_info.user_id)` | 活跃底池中，统计窗口内处于坐席名下的去重用户数 |
| 线索覆盖次数 | `COUNT(DISTINCT info_uuid)` | 活跃底池用户在统计窗口内有效的领取关系数；同一用户可有多次 |
| 外呼用户数 | `COUNT(DISTINCT call.user_id)` | 活跃底池中，统计窗口内至少有一次外呼的用户数 |
| 接通用户数 | `COUNT(DISTINCT CASE WHEN is_connect = 1 THEN user_id END)` | 至少有一次接通的外呼用户数 |
| 外呼次数 | `COUNT(DISTINCT action_id)` | 去重后的拨打次数 |
| 接通次数 | `COUNT(DISTINCT CASE WHEN is_connect = 1 THEN action_id END)` | 去重后的接通电话次数 |
| 接通外呼总时长 | `SUM(CASE WHEN is_connect = 1 THEN COALESCE(call_time_length, 0) ELSE 0 END)` | 所有接通电话的通话时长之和，原始单位为秒；不包含未接通电话和振铃时长 |
| 未接通外呼用户数 | `COUNT(DISTINCT CASE WHEN 有外呼且从未接通 THEN user_id END)` | 有拨打记录、但整个统计窗口内一次都未接通的用户数 |
| 未接通外呼次数 | 未接通外呼用户的全部 `外呼次数` 之和 | 只统计“整个窗口从未接通的用户”的拨打次数，不等于所有未接通电话次数 |
| 有效接通用户数 | `COUNT(DISTINCT CASE WHEN is_valid_connect = 1 THEN user_id END)` | 至少有一次有效接通的外呼用户数 |
| 有效接通次数 | `COUNT(DISTINCT CASE WHEN is_valid_connect = 1 THEN action_id END)` | 去重后的有效接通电话次数 |
| 同期电销营收 | `SUM(crm_order_info.amount)` | 统计窗口内满足电销订单条件的支付成功营收；按订单用户单独统计，不受活跃底池限制 |

- **常用派生指标**：

    - 线索覆盖率：`线索覆盖用户数 / 活跃用户数`。
    - 人均线索覆盖次数：`线索覆盖次数 / 线索覆盖用户数`。
    - 活跃外呼覆盖率：`外呼用户数 / 活跃用户数`。
    - 人均外呼次数：`外呼次数 / 外呼用户数`。
    - 用户接通率：`接通用户数 / 外呼用户数`。
    - 电话接通率：`接通次数 / 外呼次数`。
    - 接通用户人均外呼时长（分钟）：`接通外呼总时长 / 接通用户数 / 60`。
    - 单次接通平均时长（分钟）：`接通外呼总时长 / 接通次数 / 60`。
    - 用户有效接通率：`有效接通用户数 / 外呼用户数`。
    - 电话有效接通率：`有效接通次数 / 外呼次数`。

- **计算注意**：

    - 外呼次数和接通次数都必须按 `action_id` 去重。
    - 汇总接通外呼时长前也必须先按 `action_id` 去重，再累加 `call_time_length`；不能使用 `SUM(DISTINCT call_time_length)`，因为不同时长相同的电话仍是不同外呼。
    - `call_time_length` 是呼叫时长，单位为秒；`deal_times` 是振铃时长，不能用于计算接通外呼时长。
    - 接通统一以 `is_connect = 1` 判断；有效接通以 `is_valid_connect = 1` 判断。
    - 外呼明细可能同时拆分状态、渠道、地域等维度，必须先回收为一人一行，再汇总用户数，避免同一用户重复计算。
    - 是否排除 `call_status = '外呼异常'` 尚无统一口径，查询前必须由业务确认；未确认时不默认排除。
    - 同期电销营收固定筛选：`workplace_id IN (4, 400, 702)`、`regiment_id NOT IN (303, 0, 546)`、`worker_id <> 0`、`in_salary = 1`、`is_test = false`、`status = '支付成功'`。

## 销售侧企微漏斗与组织营收

本节用于统计销售侧“活跃—企微添加—拉取入库—付费转化”漏斗，以及电销组织的日营收。该专项使用 `crm.contact_log`、`aws.clue_info`、`aws.crm_order_info` 等销售域表，不与通用订单表 `dws.topic_order_detail` 的默认口径混用。

### 日活—企微添加—拉取入库—累计转化

- **漏斗链路**：当日活跃用户 → 当日企微添加 → 添加后且次日零点前首次拉取入库 → 入库后的累计付费转化。
- **活跃用户**：来自 `aws.business_active_user_last_14_day`，按 `active_date + u_user` 去重。
- **企微添加去重**：仅保留 `source = 3`、`change_type = 'add_external_contact'` 的记录；按 `external_user_id + worker_id + channel_id + yc_user_id + 添加月份` 取首次添加。
- **同日要求**：用户活跃日期必须等于企微添加日期。
- **拉取入库**：企微添加后、次日零点前，在 `aws.clue_info` 中按添加关系取第一条入库记录。
- **转化周期**：订单支付时间晚于入库时间，不设截止日期，因此为累计转化。若需当天、3 天、7 天等固定周期，必须在订单关联条件中增加相对 `recieve_time` 的支付截止时间。
- **电销订单必加条件**：`workplace_id IN (4, 400, 702)`、`regiment_id NOT IN (0, 303, 546)`、`worker_id <> 0`、`in_salary = 1`、`is_test = false`。
- **完整 SQL**：见 `gold_cases.md` 的“日活—企微添加—拉取入库—累计转化”。

### 月活—企微添加—拉取入库—当月转化

- **标准表来源**：`aws.crm_active_user_wechat_paid_month`。
- **表用途**：按月及用户月度分层统计活跃用户、企微添加用户、拉取入库用户、入库后付费用户和付费金额。
- **当前转化周期**：宽表中的转化仅统计当月，不是累计转化。
- **周期差异**：日活漏斗 SQL 为入库后的累计转化，月活宽表为当月转化，两者不能直接比较转化量或转化率。
- **固定周期分析**：如需当天、3 天、7 天等转化，应修改明细构建或使用明细表重算，显式限定支付时间相对入库时间的上限；不能直接从当前月活宽表推导。
- **完整 SQL**：见 `gold_cases.md` 的“月活—企微添加—拉取入库—当月转化”。

### 每天团—组—个人营收

- **定义**：按支付日、职场、部门、团、负责人、组和销售个人统计电销营收、订单数及付费用户数。
- **表来源**：订单表 `aws.crm_order_info`，组织名称通过 `dw.dim_crm_organization` 按各层级组织 ID 关联。
- **金额**：`SUM(a.amount)`。
- **订单量**：`COUNT(DISTINCT a.order_id)`。
- **付费用户数**：`COUNT(DISTINCT a.user_id)`。
- **固定筛选**：
    - 职场：`workplace_id IN (4, 400, 702)`，即武汉电销和长沙电销。
    - 团队排除：`regiment_id NOT IN (303, 0, 546)`，剔除体验营、私域阿拉丁及无团队归属。
    - 人员与订单：`worker_id <> 0`、`is_test = false`、`in_salary = 1`、`status = '支付成功'`。
- **完整 SQL**：见 `gold_cases.md` 的“每天团—组—个人营收”。

## C端活跃用户月报

- **定义**：按月份统计 C 端活跃用户规模，并可拆业务分层、统计分层、GMV 归属等标签。
- **标准表来源**：`aws.business_active_user_last_14_day`
- **月活总量**：沿用“C端活跃用户数”章节，按 `user_sk + active_month` 去重。
- **分层取值**：在一人一月记录上取标签；业务分层使用 `business_user_pay_status_business_month`，统计分层使用 `business_user_pay_status_statistics_month`。
- **禁止字段**：不得使用无 `business_` 前缀的用户标签字段做知识库默认口径。

## C端活跃 ARPU

- **定义**：C 端活跃用户人均营收。
- **计算方式**：`SUM(normal_price_amount) / C端活跃用户数`
- **表来源**：`aws.business_active_user_last_14_day`
- **口径说明**：

    - 分母：先用 `aws.business_active_user_last_14_day` 圈定同月 C 端活跃用户池，按 `u_user + active_month` 或 `user_sk + active_month` 去重。
    - 分子：只使用同月 `aws.business_active_user_last_14_day.normal_price_amount`；如需对齐商业化归因，按 `business_gmv_attribution IN ('电销','商业化')` 聚合。
    - 跟活跃相关、需要以活跃用户为分母的活跃 ARPU、活跃付费转化率、活跃口径客单价，都不得默认用订单表 `dws.topic_order_detail` JOIN 活跃池计算。
    - 单独看 GMV 营收流水、商品订单营收、订单明细时才使用订单表；不要把订单营收口径混入活跃 ARPU。

## 订单明细默认表

- **默认订单表**：`dws.topic_order_detail`
- **适用场景**：单独看 GMV / 营收流水、商品订单营收、订单用户、商品类目、订单明细、注册用户付费金额。
- **不适用场景**：凡是跟活跃相关、需要以活跃用户为分母或解释活跃商业化效率的指标，例如活跃付费转化率、活跃 ARPU、活跃口径客单价，默认不用订单表直接 JOIN 活跃池计算，只用 `aws.business_active_user_last_14_day` 的金额/转化字段。
- **默认营收口径**：`SUM(sub_amount)`，并筛选 `u_user IS NOT NULL`、`is_test_user = 0`、`original_amount >= 39`、`business_gmv_attribution IN ('电销','商业化')`。
- **订单量**：该表是子订单粒度，必须使用 `COUNT(DISTINCT order_id)`。
- **状态规则**：默认不筛 `status = '支付成功'`；仅在明确要求支付成功、退款、到账或指定状态时筛选。
- **表达规则**：默认称为“正价营收”；`商业化` 对外说明为 APP 渠道，`电销` 说明为电销渠道。
- **例外**：用户明确要求全量营收或包含非正价时，才移除 `original_amount >= 39` 并说明口径变化；`dw.fact_order_detail` 不作为知识库默认订单表。

## 活跃用户转化

- **定义**：活跃用户中产生订单或支付行为的用户占比。
- **计算方式**：`pay_user_cnt / active_user_cnt`
- **表来源**：`aws.business_active_user_last_14_day`
- **注意**：

    - 月度口径下，“先活跃再付款”统一理解为“当月活跃池 + 当月付款”，不要求支付时间严格晚于某次活跃日期。
    - 看板对齐时，转化人数来自活跃表金额字段：`normal_price_amount > 0` 的活跃用户去重。
    - 不要默认用订单表 `dws.topic_order_detail` JOIN 活跃池后按订单用户数计算活跃转化率；该口径会和 `aws.business_active_channel_month` 看板不齐。
    - 默认只使用 `aws.business_active_user_last_14_day` 取活跃与活跃相关转化；`aws.business_active_channel_month` 只作为看板来源说明或对照，不作为默认取数表。

## 客单价

- **定义**：付费用户人均营收金额。
- **计算方式**：`pay_amount / pay_user_cnt`
- **表来源**：

    - 活跃相关客单价：默认使用 `aws.business_active_user_last_14_day` 的活跃口径字段。
    - 单独看订单客单价或商品订单营收：使用 `dws.topic_order_detail`。

- **注意**：

    - 跟活跃相关、需要与活跃转化率/活跃 ARPU 同看时，客单价必须和活跃口径一致：`SUM(normal_price_amount) / COUNT(DISTINCT CASE WHEN normal_price_amount > 0 THEN u_user END)`。
    - 不要默认用订单表 JOIN 活跃池后的订单用户数和 `sub_amount` 计算活跃相关客单价。
    - 单独看订单流水时，订单表筛选仍按 GMV / 营收口径执行。

## GMV

- **定义**：指定订单窗口内、归属电销/商业化的正价营收金额汇总。
- **计算方式**：`SUM(sub_amount)`
- **表来源**：`dws.topic_order_detail`
- **筛选与例外**：统一遵循“订单明细默认表”章节，不在本节重复。

## 定金与蓄水品口径

- **定义**：大促预热阶段用于拆分蓄水订单、定金订单的商品口径。
- **表来源**：`dws.topic_order_detail`
- **订单量计算方式**：`COUNT(DISTINCT order_id)`；订单表为子订单粒度，不能直接 `COUNT(*)`。
- **金额计算方式**：历史口径使用 `SUM(sub_amount)`。
- **渠道归属**：默认限定 `business_gmv_attribution IN ('商业化','电销')`；其中 `商业化` 对外说明为 APP 渠道，`电销` 对外说明为电销渠道。
- **注意**：本节为大促预热专项口径，不默认套用通用正价营收的 `original_amount >= 39`；如果业务明确只看 C 端，需要在查询中额外保留或补充 C 端限定条件。
- **转化分析规则**：
    - 定金用户分层取购买定金时的标签，不使用后置标签。
    - 尾款商品按尾款订单的实际商品类目拆解；定金贡献应按需求区分定金订单、尾款订单和定金用户后续订单。
    - 蓄水转大支付时间不得早于蓄水品支付时间。
    - **蓄水“转大”仅指转组合品**：蓄水用户后续购买组合品才算转大；购买其他正价品（≥39 元，如 498、零售品）只计入“转化”，不算转大。转大率 = 转组合品人数 / 蓄水来源用户数；转化率 = 购买任意正价品人数 / 蓄水来源用户数（转化包含转大）。
    - 累计转大包含 5、6、7 月；“7 月累计转大”只统计 7 月转大订单。
    - 去年同期低门槛承接口径通常使用“蓄水品 + 198 商品”，不能只比较蓄水品。

### 2026 年口径

- **蓄水订单**：

```sql
SELECT COUNT(DISTINCT order_id) AS xushui_order_cnt
FROM dws.topic_order_detail
WHERE paid_time_sk BETWEEN 20260522 AND 20260623
  AND good_kind_name_level_2 = '同步课加培优课'
  AND good_kind_name_level_3 = '同步课加培优课流量品'
  AND business_gmv_attribution IN ('商业化','电销');
```

- **定金订单**：

```sql
SELECT COUNT(DISTINCT order_id) AS dingjin_order_cnt
FROM dws.topic_order_detail
WHERE paid_time_sk BETWEEN 20260624 AND 20260630
  AND sku_group_good_id = '74ec057c-4a49-45aa-a0ee-0fd2a410989a'
  AND business_gmv_attribution IN ('商业化','电销');
```

### 2025 年口径

- **蓄水 APP 金额**：

```sql
SUM(IF(
    sku_group_good_id IN (
        '2ad36071-17ec-4eda-9a7a-27c005fd61fa',
        '10138aa5-ea9c-4723-9ac7-4aab637e7218'
    )
    AND paid_time_sk BETWEEN 20250603 AND 20250622,
    sub_amount,
    0
)) AS xushui_app
```

- **定金/体验机金额**：

```sql
SUM(IF(
    good_kind_id_level_2 = '9433f2e3-7908-44b6-ae84-d3ba257ad3ce'
    AND business_gmv_attribution IN ('商业化','电销')
    AND paid_time_sk BETWEEN 20250621 AND 20250630,
    sub_amount,
    0
)) AS tiyanji_tele,
SUM(IF(
    good_kind_id_level_2 = 'ee74d649-8e32-452a-a461-65de25560440'
    AND business_gmv_attribution = '电销'
    AND paid_time_sk BETWEEN 20250625 AND 20250630,
    sub_amount,
    0
)) AS dingjin_tele,
SUM(IF(
    good_kind_id_level_2 = 'ee74d649-8e32-452a-a461-65de25560440'
    AND business_gmv_attribution = '商业化'
    AND paid_time_sk BETWEEN 20250625 AND 20250630,
    sub_amount,
    0
)) AS dingjin_app
```

## 月度宏观/转化月报规范

本节用于沉淀 C 端月度宏观/转化月报的取数、归因和输出规则。用户询问“月报”“宏观简报”“转化月报”“五月大盘”等场景时，优先使用本规范。

### 适用场景

- 目标是解释某个月的大盘经营表现，而不是只回答单个指标。
- 默认同时取三个月份：

    - 目标月：用户指定月份。
    - 上月：用于环比。
    - 去年同期：用于同比。

- 分析主线以同比为主，环比用于补充短期趋势。
- 表格列顺序统一为：目标月、去年同期、上月、同比变化、环比变化。
- 看板对齐月报默认使用看板 MTD 逻辑，而不是简单把三个月都截成同一个 `start_day/end_day` 订单窗口。不同模块的 MTD 截断规则不同，必须按下方核心指标口径分别处理。

### 核心指标口径

- MAU、活跃付费转化率、活跃 ARPU、活跃口径客单价分别沿用前文对应章节，不在本节重复定义。
- 整体商业化 MTD 的活跃池按月取 `aws.business_active_user_last_14_day`，目标月、上月和去年同期统一按 `CAST(SUBSTR(CAST(day AS STRING), 7, 2) AS INT) <= DAY(CURRENT_DATE())` 截断。
- 活跃相关转化人数使用 `normal_price_amount > 0` 判断，转化金额使用 `normal_price_amount`；不得改成活跃池 JOIN 订单表。
- 商品订单营收、GMV、订单量和商品订单结构沿用“订单明细默认表”章节；商品活跃指标没有对应活跃表字段时，不得用订单口径冒充。
- **看板例外**：订单层使用 `u_user IS NOT NULL`、`original_amount >= 39`、`business_gmv_attribution IN ('电销','商业化')`，但不筛 `is_test_user = 0`；该例外覆盖通用订单默认筛选。
- `business_gmv_attribution` 默认精确匹配 `电销`、`商业化`，不含 `商业化-电商`；纳入平台电商时必须说明口径变化。
- 完整实现见 `gold_cases.md` 的“月度宏观看板聚合”；不要直接取 `aws.business_active_channel_month`。

### 归因分析规则

- 月报解释整体大盘时，优先按以下链路组织：

    1. MAU 变化：活跃规模是大盘水位。
    2. 付费转化率变化：活跃用户中有多少变成付费用户。
    3. 客单价变化：付费用户人均贡献。
    4. 活跃 ARPU 变化：营收效率综合结果。
    5. 订单营收变化：最终经营结果。

- 优先判断收入下降是由 MAU 下降、转化率下降还是客单价变化驱动。
- 如果 ARPU 上升但收入下降，应明确说明“客单价/ARPU 托底不足以抵消 MAU 或转化率下滑”。
- 如果客单价提升而转化率下滑，应说明“高客单价托底，但转化效率承压”。

### 活跃结构

- 活跃下滑需要拆分老未与非老未。
- 老未判断基于活跃表中的统计分层和业务分层字段，通常使用包含 `老未|老用户` 的规则。
- 判断“活跃下滑是否由老未用户流失导致”必须基于实际数据统计，不得只按经验或文档推断。
- `mid_active_type` 不在 `aws.business_active_user_last_14_day` 中，如需输出中学活跃类型，可从 `dws.topic_user_active_detail_day` 通过 `u_user + day` 辅助补字段。
- `dws.topic_user_active_detail_day` 只能补 `mid_active_type` 等辅助维度，不得作为活跃人数、转化人数、ARPU、客单价或金额的主计算表。
- 使用 `mid_active_type` 等辅助维度时，必须先在 `aws.business_active_user_last_14_day` 中按 `u_user + stat_month` 单独聚合 `normal_price_amount`，再 JOIN 到一人一月的活跃底表；不要在 JOIN 了 `dws.topic_user_active_detail_day` 后再 `SUM(normal_price_amount)`，否则会因辅助表多行粒度放大金额。
- 做去年同期关联时，如果输出同时包含业务分层和统计分层，JOIN 条件必须同时包含 `business_user_pay_status_business`、`business_user_pay_status_statistics`、`mid_active_type` 和月份偏移，避免统计分层缺失导致行重复放大。

### 新增流量

- 新增注册必须补充免费/付费流量拆分。
- 免费/付费流量使用注册渠道一级标签：

    - `免费` → 免费流量。
    - `付费` 或 `投放` → 付费流量。
    - 其他枚举保留为其他/未打标。

- 新增流量质量至少看：新增付费率、新增 LTV、新增客单价。
- 新增注册看板对齐时，基础用户来自 `aws.user_increase_new_add_day`，关联 `aws.user_increase_channel_label_day` 获取 `regist_channel_label1`、`regist_channel_label2`。
- 新增注册看板 MTD 的截断规则与整体商业化不同：基础注册层使用 `DAY(STR_TO_DATE(CAST(a.day AS STRING), '%Y%m%d')) <= DAY(DATE_SUB(CURRENT_DATE(), 1))`；历史月和上月也按这个 day-of-month 截注册用户。
- 新增注册的付费金额仍按注册月同月订单聚合，不按注册日 MTD 再截支付日；也就是先按 `u_user + pay_month` 汇总注册月订单，再关联注册 cohort。
- 只有看新增注册、注册用户 LTV、注册转化月维度或月报新增流量模块时，付费订单才使用新增注册看板口径；订单表仍使用 `dws.topic_order_detail`，但字段和筛选必须按看板：

```sql
SUM(arrival_amount) AS pay_amount
WHERE status IN ('支付成功', '退款成功')
```

- 新增注册看板对齐时，不要默认套用 `sub_amount`、`original_amount >= 39`、`business_gmv_attribution IN ('电销','商业化')` 或订单层 `is_test_user = 0`；这些是商业化营收默认口径，不是新增注册看板 LTV 口径。
- 非新增注册场景不得套用本条 `arrival_amount + status` 例外；整体商业化、活跃池订单、商品结构仍按对应章节的营收口径。
- 新增注册看板对齐时，必须先按看板宽表粒度 `reg_month + os + regist_channel_label1 + regist_channel_label2` 聚合，再由报表/看板层汇总指标；不要在报表查询里直接改成全局 `COUNT(DISTINCT u_user)`。
- 新增客单价按看板聚合字段计算：`SUM(pay_amount) / SUM(pay_user_num)`，其中 `pay_user_num` 来自宽表内 `SUM(is_pay)`；其中 `is_pay = IF(up.u_user IS NOT NULL, 1, 0)`，只要订单表有匹配记录即算付费，不要求 amount > 0 ；不要改成 `SUM(pay_amount) / COUNT(DISTINCT 付费 u_user)`。
- 新增注册看板的 `FULL_MONTH`、`MTD`、`MIX` 输出逻辑见 `gold_cases.md` 的“新增注册看板聚合”。
- 新增 LTV 变化要区分结构影响和质量影响：

    - 结构影响：免费/付费注册占比变化带来的 LTV 变化。
    - 质量影响：免费/付费各自 LTV 变化带来的 LTV 变化。

### 留存与回流

- 不用“目标月用户向后留存”解释目标月大盘。
- 解释目标月活跃时，使用历史 cohort 的次月、次 2 月留存趋势判断其对目标月活跃的前置影响。
- 对目标月 `M`：

    - `M-2` 月 cohort 的次 2 月留存直接进入目标月活跃。
    - `M-1` 月 cohort 的次月留存直接进入目标月活跃。

- 例如解释 2026 年 4 月：

    - 2026 年 2 月 cohort 的次 2 月留存进入 2026 年 4 月活跃。
    - 2026 年 3 月 cohort 的次月留存进入 2026 年 4 月活跃。

- “目标月用户向后留存”只用于预测后续月份，不用于解释目标月已经发生的 MAU。
- 留存率除相对变化外，需要补充绝对变化，单位为 pp。

### 商品结构

- 商品结构重点关注组合品变化。
- 组合品常规规则：`business_good_kind_name_level_1 = '组合品'`。
- 2025 年特殊规则：`good_kind_name_level_2 in ('一年积木块'、'到期型积木块')`定义为组合品。
- 2025 年积木块为 998 模式商品，但不要单独用价格 `998` 识别积木块，优先使用商品类目或修正类目。
- 私教班特殊分类规则：

    - 当 `good_kind_name_level_2 = '同步课加培优课'` 且 `good_kind_name_level_3 = '同步课加培优课流量品'` 时，商品分类归为 `私教班`。

- 从小学产品取数口径（默认按 `dws.topic_order_detail`）：

    - 从小学单科/联售/小学全科规划提分课统一按以下 `CASE WHEN` 分类：

```sql
SELECT DISTINCT
  CASE
    WHEN good_kind_name_level_3 = '拓展课'
     AND good_stage_subject_cnt = 1
     AND good_stage_subject regexp '1-2-specialCourse'
      THEN '从小学物理'
    WHEN good_kind_name_level_3 = '拓展课'
     AND good_stage_subject_cnt = 1
     AND good_stage_subject regexp '1-6-specialCourse'
      THEN '从小学生物'
    WHEN good_kind_name_level_3 = '拓展课'
     AND good_stage_subject_cnt = 1
     AND good_stage_subject regexp '1-7-specialCourse'
      THEN '从小学地理'
    WHEN good_kind_name_level_3 = '拓展课'
     AND good_stage_subject_cnt = 3
     AND good_stage_subject regexp '1-2-specialCourse'
     AND good_stage_subject regexp '1-6-specialCourse'
     AND good_stage_subject regexp '1-7-specialCourse'
      THEN '从小学物生地（3科联售）'
    WHEN business_good_kind_name_level_3 IN ('小学品加拓展')
      THEN '小学全科规划提分课'
  END AS good_kind,
  order_id
FROM dws.topic_order_detail;
```

```
- `regexp` 规则按“包含即可”理解，不要求字段等值。
- 分类顺序保持“单科条件在前、3科联售在后”，不要调整 `CASE WHEN` 顺序。
- 涉及营收时仍按默认正价营收口径执行（除非用户明确要求全量营收/包含非正价）。
```

- 商品核心指标优先级：

    1. 商品活跃 ARPU 及同比变化。
    2. 商品客单价。
    3. 商品活跃转化率。

- 非组合品仅保留收入占比和订单占比，不展开转化率、客单价、ARPU 解释。
- 如果组合品 ARPU 提升来自客单价而非转化率，要明确说明“收入托底来自客单价抬升，不是转化效率提升；若转化率继续下滑，单靠高客单价托底的持续性有限”。

### 输出结构

- 核心结论按“总-分”组织：

    1. 第一段只给一句总判断，不堆具体数据。
    2. 第二段用 3 条以内支撑说明：整体大盘、活跃/留存、商品结构。
    3. 核心结论不增加环比信息；环比放在分章节表格或正文中。
    4. 不单独增加“归因小结”，避免首尾重复。

- 月报默认章节：

    1. 整体收入与商业化。
    2. 新增流量。
    3. 活跃规模与结构。
    4. 留存与回流。
    5. 商品结构与转化。
    6. 数据文件或 SQL 附录（按需）。

- 每个章节表格后必须补一句高密度解释，说明“这个表说明了什么”，避免只罗列数据。
- 章节解释模板：

    - 整体收入章节：说明收入变化主要由 MAU、付费转化率、客单价中的哪一项驱动。
    - 新增流量章节：区分新增规模和新增质量，重点解释新增付费率、LTV 和客单价变化。
    - 活跃结构章节：说明老未/非老未对 MAU 变化的贡献。
    - 留存章节：先解释为什么看历史 cohort，再说明关键 cohort 的留存变化。
    - 商品章节：说明组合品收入/ARPU 变化来自客单价还是转化率，非组合品只看结构占比。

### 表达与数字格式

- 同比相对变化、环比相对变化：保留一位小数。
- 留存率绝对变化：保留两位小数，单位 pp。
- ARPU：保留两位小数。
- 转化率、留存率：保留两位小数。
- 客单价：保留整数。
- 营收：保留整数。
- 活跃用户数：保留整数。
- 表格中涉及同比和环比时，列顺序统一为同比在前、环比在后。
- 涉及转化率、留存率下滑时，必须明确实际下降幅度。
- 内容要从“数据罗列”推进到“经营判断”，但每个判断都必须有对应数据支撑。

## 商品体系2.0与中台策略口径

本节来自《[规则]中台策略通用数据口径2.0》，用于统一商品体系 2.0、策略、补差、多孩、续购、加购等取数口径。该规则自 **2026-01-01** 起作为商品策略类问题的优先口径。

### 适用场景

- 用户询问商品结构、组合品/非组合品、单学段/多学段、到期型/时长型、公域品/私域品等商品体系 2.0 分类。
- 用户询问策略转化、策略资格、策略用户分层、多孩策略、补差、平板加购、续购、升级率等中台策略指标。
- 用户给出 `business_good_kind_name_level_1/2/3`、`strategy_type`、`strategy_detail`、`course_timing_kind`、`course_group_kind` 等条件时，优先按本节处理。

### 核心字段

- 商品业务分类：`dws.topic_order_detail.business_good_kind_name_level_1/2/3`。

    - 这是前端业务口径商品分类，适合策略组和商品体系 2.0 口径。
    - 与 `good_kind_name_level_1/2/3` 不能混用；输出时必须说明使用哪套类目。

- 商品类型：`course_timing_kind`，用于区分到期型/时长型等商品类型。
- 商品分组：`course_group_kind`，用于区分公域品/私域品或主推品等商品分组。
- 策略类型：`strategy_type`，2026-01-01 后为业务数据，之前可能按规则清洗。
- 策略明细：`strategy_detail`，记录策略及对应优惠金额明细。
- 策略用户分层：`user_strategy_tag_day/month/year`。

    - 历史大会员拆分为可续购和不可续购，如看整体历史大会员需合并。

- 用户策略资格：`user_strategy_eligibility_day/month/year`。
- 多孩策略退差价时间：`multi_child_refund_time`。
- 商品精准识别：优先使用 `good_id`、`sku_group_good_id` 或稳定类目；`good_name`、`sku_name` 仅用于辅助模糊识别。
- 平板/学习机：优先使用 `is_pad_price_difference_order`，并结合 `model_type`、`pad_type`、`sku_name`、`good_name` 复核。

### 常用商品分类

| 商品 / 业务 | 判断规则 | 主要用途 |
| --- | --- | --- |
| 组合品 | `business_good_kind_name_level_1 = '组合品'` | 主力正价商品、组合品营收和转化 |
| 零售商品 | `business_good_kind_name_level_1 = '零售商品'` | 低门槛商品、货架承接 |
| 续购 | `business_good_kind_name_level_1 = '续购'` | 续费用户商品承接 |
| 组合品 + 续购 | `business_good_kind_name_level_1 IN ('组合品','续购')` | 高净值、续费及历史大会员承接 |
| 家庭包 | `business_good_kind_name_level_3 = '小初高品'` | 家庭包营收与订单占比 |
| 方案型商品 | `good_kind_name_level_1 = '方案型商品'` | 定金尾款、方案型转化和营收 |
| 498 商品 | `original_amount = 498` | 2026 年新注册用户当月转化分析；价格识别置信度为中 |
| 198 商品 | `original_amount = 198` | 2025 年新注册及低门槛承接分析；价格识别置信度为中 |

“从小学”、私教班/蓄水品、定金和体验机的专项识别规则沿用前文对应章节，不在本节重复。

### 金额字段

- `original_amount`：超值价/订单原价。
- `sub_amount`：到手价/实收金额；商品订单营收、GMV、商品营收流水默认使用该字段。
- `discount_amount`：实际优惠总金额，通常为“超值价 - 到手价”。
- `discount_id`：优惠券 ID。
- `discount_price`：优惠券金额。
- 金额字段不可混用；如果用户问优惠、补差或策略让利，必须明确使用 `discount_amount`、`strategy_detail`、`fix_deductible_price` 等字段，而不是直接用营收字段替代。

### 商品核心指标

- 商品营收：商品订单 `SUM(sub_amount)`。
- 商品付费用户：`COUNT(DISTINCT u_user)`。
- 商品客单价：商品营收 / 商品付费用户，不按订单量计算。
- 商品转化率：活跃池内购买该商品的去重用户数 / 活跃用户数。
- 商品 ARPU：活跃池内该商品营收 / 活跃用户数。
- 家庭包订单占比：家庭包订单量 / 组合品订单量。
- 从小学结构占比：`小学品加拓展` /（`小学品` + `小学品加拓展`）；分析营收时必须包含单科部分。
- 计算商品转化率或商品 ARPU 时必须先圈活跃用户池；商品订单不能替代活跃表 `normal_price_amount` 计算整体活跃 ARPU。

### 策略转化与加购指标

- 付费零售品用户续购率：

    - 组合品续购率分母：购买过零售品的用户。
    - 组合品续购率分子：后续购买组合品的用户。
    - 非组合品续购率分子：后续再次购买非组合品的用户。

- 付费组合品或大会员用户续购率：

    - 分母：购买过组合品的用户，需区分历史大会员用户和付费组合品用户。
    - 组合品续购率分子：购买过组合品、续购品的用户，可按商品分类拆分。
    - 非组合品续购率分子：后续再次购买非组合品的用户。

- 平板加购率：

    - 单后加购：购买后再次购买三级类目为“学习机加购-平板加购”的用户。
    - 随单加购：购买当下商品中包含平板的用户。
    - 分母：购买了积木块、组合品的用户。
    - 分子：单后加购或随单加购用户。

- 多孩加购率：

    - 分母：有多孩策略资格的用户。
    - 分子：以多孩策略购买组合品的用户。

- 小学品/小初同步品升级率：

    - 分母：有小学同步 6 年时长品补差资格的用户，或小初同步 4 年时长品补差资格的用户。
    - 分子：升级购买组合品的用户。

### 使用注意

- 单独看商品订单营收、GMV、订单量时仍遵守订单表大标准：使用 `dws.topic_order_detail`。
- 跟活跃相关、需要以活跃用户为分母的转化率、客单价、ARPU，仍使用 `aws.business_active_user_last_14_day` 作为分母主表；策略字段只作为用户分层或资格条件使用。
- 策略资格类指标优先使用 `user_strategy_eligibility_*`；策略用户身份类指标优先使用 `user_strategy_tag_*`。
- 如果需求涉及“有资格但未购买”“资格用户转化”“升级率”，必须先圈资格用户分母，再关联订单购买分子，不得直接用订单购买用户当分母。

## 易混淆术语

| 易混点 | 正确理解 |
| --- | --- |
| C端活跃 vs 全公司活跃 | `aws.business_active_user_last_14_day` 只代表 C 端/私域活跃，不代表全公司活跃 |
| C端活跃 ARPU | 必须先圈 `aws.business_active_user_last_14_day` 的 C 端活跃用户池，分子只统计该用户池内同月营收；不能用全量订单营收直接除以月活 |
| 活跃主表 vs 活跃行为辅助表 | `aws.business_active_user_last_14_day` 是 C 端活跃主表；`dws.topic_user_active_detail_day` 只能 `LEFT JOIN` 补充行为/设备/渠道字段 |
| 用户标签字段 | 牵涉用户标签时只用带 `business_` 前缀字段；统计维度用 `business_user_pay_status_statistics_month`，业务维度用 `business_user_pay_status_business_month` |
| 订单量 vs 子订单行数 | 订单量必须按 `order_id` 去重，子订单行数不能直接当订单量 |
| 商品 2.0 类目 vs 策略组商品类目 | 两套类目字段不能混用，输出时必须明确字段名 |
| LTV 金额 vs GMV | LTV 通常看注册 cohort 的到账金额，GMV 按订单或商品归属汇总 |
| 注册用户 LTV vs 注册转化月维度 | 用户问“新增注册用户 LTV”时，默认走注册转化月维度口径，输出 `pay_amount / install_users`，而不是只输出订单金额汇总 |
| 支付成功 vs 退款成功 | 看营收、GMV、ARPU 分子或付费金额时默认不筛 `status = '支付成功'`；只有用户明确要求支付成功、退款、到账或指定订单状态时才筛选订单状态 |
| 测试用户 vs 正常用户 | 订单、营收、GMV、ARPU 分子、付费金额默认必须筛 `is_test_user = 0`，排除测试用户 |
| 正价营收 vs 全量营收 | 默认营收、GMV、ARPU 分子均使用正价营收，必须筛 `original_amount >= 39`；全量营收只有在用户明确要求时使用 |
| 总营收表达 | 对外默认把“总营收”解释为“正价营收”；若用户要包含非正价部分，需明确提出“全量营收/包含非正价”并同步说明口径变化 |

## 维护原则

- 业务方确认新的稳定口径后，直接更新对应主题章节，不在文件末尾重复追加纠偏历史。
- 新口径覆盖旧口径时必须删除旧表述，避免同一指标出现多个相互冲突的版本。
- 完整 SQL 统一维护在 `gold_cases.md`，本文件只保留定义、表选择、筛选条件、场景例外和案例链接。
