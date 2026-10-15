# 模块四：经营信息-账单明细数据 (dms_bill_details_info) — 21 字段

> 采集路径：对账管理 → 往来对账 → 点击单据号进入明细
> 数据来源：账单详情 API 或对账单逐笔交易行

| # | 字段英文名 | 字段中文名 | 字段类型 | 采集规则 |
|---|-----------|-----------|---------|---------|
| 1 | order_group_id | 分组号 | String | 系统生成 |
| 2 | order_id | 采集订单号 | String | 系统生成 |
| 3 | taxpayer_id | 申请人识别号 | String | 系统生成 |
| 4 | distributor_name_original | 经销商采集名称 | String | 采集字段 |
| 5 | distributor_code | 经销商编码 | String | 采集字段 |
| 6 | producer_name_original | 厂家采集名称 | String | 采集字段 |
| 7 | bill_no | 账单编号 | String | 采集字段 |
| 8 | transaction_date | 交易日期 | Datetime | 采集字段 |
| 9 | bill_type | 账单类型 | String | 无法采集 |
| 10 | bill_amount | 账单金额 | Decimal(20,2) | 采集字段 |
| 11 | invoice_amount | 开票金额 | Decimal(20,2) | 无法采集 |
| 12 | goods_amount | 发货金额 | Decimal(20,2) | 无法采集 |
| 13 | goods_quantity | 货物数量 | Decimal(12,2) | 无法采集 |
| 14 | quantity_unit | 数量单位 | String | 无法采集 |
| 15 | balance | 余额 | Decimal(20,2) | 采集字段 |
| 16 | amount_unit | 金额单位 | String | 无法采集 |
| 17 | abstract | 摘要 | String | 采集字段 |
| 18 | order_no | 订单编号（销售订单号） | String | 采集字段 |
| 19 | data_match | 数据是否相符 | String | 无法采集 |
| 20 | platform_brand_id | 平台品牌ID | String | 无法采集 |
| 21 | transaction_month | 交易月份 | String | 采集字段 |

> 与 `dms_bill_monthly_info` 常常同源（同一接口的头部+明细行，见 `prompts/discovery.md` §5.5「同源提示」）。若 Discovery 已在 `discovery.same_source_hints` 里标出这对表，采集时应合并为一次请求处理，不必重复取证。
