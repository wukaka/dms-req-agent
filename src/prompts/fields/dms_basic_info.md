# 模块一：基础信息 (dms_basic_info) — 16 字段

> 采集路径：个人中心 / 基本资料
> 数据来源：SSR HTML 或 API

| # | 字段英文名 | 字段中文名 | 字段类型 | 采集规则 |
|---|-----------|-----------|---------|---------|
| 1 | order_group_id | 分组号 | String | 系统生成 |
| 2 | order_id | 采集订单号 | String | 系统生成 |
| 3 | taxpayer_id | 申请人识别号 | String | 系统生成 |
| 4 | platform_brand | 平台品牌 | String | 采集字段 |
| 5 | distributor_name_original | 经销商采集名称 | String | 采集字段 |
| 6 | distributor_code | 经销商编码 | String | 采集字段 |
| 7 | distributor_address | 经销商地址 | String | 采集字段 |
| 8 | contact_person | 负责人 | String | 采集字段 |
| 9 | contact_phone | 负责人电话 | String | 采集字段 |
| 10 | producer_name_original | 厂家采集名称 | String | 无法采集 |
| 11 | producer_dep_original | 厂家合作部门 | String | 无法采集 |
| 12 | producer_usc_code_original | 厂家采集统一社会信用代码 | String | 无法采集 |
| 13 | platform_brand_id | 平台品牌ID | String | 系统生成 |
| 14 | distributor_usc_code_original | 经销商采集统一社会信用代码 | String | 无法采集 |
| 15 | cooper_status | 合作状态 | String | 无法采集 |
| 16 | tenant_name | 品牌租户名称 | String | 无法采集 |

> ⚠️ 一对一原则示例：`distributor_name_original` 取「客户名称」后，`contact_person`（负责人）若无独立字段 → 标记「无法采集」，避免两字段同源。
