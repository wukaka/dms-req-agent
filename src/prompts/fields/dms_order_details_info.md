# 模块二：经营信息-订单明细数据 (dms_order_details_info) — 23 字段

> 采集路径：订单管理 → 经销商订单 / 我的订单（可能为 SPA iframe 嵌入）
> 数据来源：列表 API + 详情 API（或 SSR HTML）

| # | 字段英文名 | 字段中文名 | 字段类型 | 采集规则 |
|---|-----------|-----------|---------|---------|
| 1 | order_group_id | 分组号 | String | 系统生成 |
| 2 | order_id | 采集订单号 | String | 系统生成 |
| 3 | taxpayer_id | 申请人识别号 | String | 系统生成 |
| 4 | distributor_name_original | 经销商采集名称 | String | 采集字段 |
| 5 | distributor_code | 经销商编码 | String | 采集字段 |
| 6 | order_no | 订单编号 | String | 采集字段 |
| 7 | order_amount_before_discount | 订单金额（折扣前） | Decimal(20,2) | 采集字段 |
| 8 | order_amount_after_discount | 订单金额（折扣后） | Decimal(20,2) | 无法采集 |
| 9 | amount_unit | 金额单位 | String | 无法采集 |
| 10 | order_quantity | 订单数量 | Decimal(12,2) | 采集字段 |
| 11 | quantity_unit | 数量单位 | String | 采集字段 |
| 12 | discount_amount | 折扣金额 | Decimal(20,2) | 无法采集 |
| 13 | product_name | 商品名称 | String | 采集字段 |
| 14 | order_status | 订单状态 | String | 采集字段 |
| 15 | order_weight | 订单重量 | Decimal(20,2) | 采集字段 |
| 16 | weight_unit | 重量单位 | String | 采集字段 |
| 17 | order_date | 下单日期 | Datetime | 采集字段 |
| 18 | ship_date | 发货日期 | Datetime | 采集字段 |
| 19 | expected_delivery_date | 期望交货日期 | Datetime | 采集字段 |
| 20 | order_source | 订单来源 | String | 无法采集 |
| 21 | func_version | 功能版本 | String | 无法采集 |
| 22 | order_type | 订单类型 | String | 采集字段 |
| 23 | platform_brand_id | 平台品牌ID | String | 系统生成 |
