# 模块六：基础信息-认证信息 (dms_certified_info) — 14 字段

| # | 字段英文名 | 字段中文名 | 字段类型 | 采集规则 |
|---|-----------|-----------|---------|---------|
| 1 | order_group_id | 分组号 | String | 系统生成 |
| 2 | order_id | 采集订单号 | String | 系统生成 |
| 3 | taxpayer_id | 申请人识别号 | String | 系统生成 |
| 4 | distributor_name_original | 经销商采集名称 | String | 采集字段 |
| 5 | distributor_code | 经销商编码 | String | 采集字段 |
| 6 | certified_type | 认证类型 | String | 采集字段 |
| 7 | login_phone_number | 当前登录手机号 | String | 无法采集 |
| 8 | authorized_name | 被授权人姓名 | String | 采集字段 |
| 9 | authorized_phone_number | 被授权人手机号 | String | 采集字段 |
| 10 | submit_time | 提交时间 | Datetime | 采集字段 |
| 11 | auth_info_update_time | 认证信息更新时间（来自原始采集） | Datetime | 采集字段 |
| 12 | certified_result | 认证返回结果 | String | 采集字段 |
| 13 | certified_firm_name | 认证企业名称 | String | 采集字段 |
| 14 | distributor_usc_code_original | 经销商采集统一社会信用代码 | String | 采集字段 |
