---
granularity_required: 月
finer_than: [半月, 旬, 周, 日, 天, 期号]
---

# 模块三：经营信息-账单分月数据 (dms_bill_monthly_info) — 22 字段

> 采集路径：对账管理 → 往来对账 / 我的钱包 → 我的对账单
> 数据来源：SSR 列表 HTML + 导出 Excel

| # | 字段英文名 | 字段中文名 | 字段类型 | 采集规则 |
|---|-----------|-----------|---------|---------|
| 1 | order_group_id | 分组号 | String | 系统生成 |
| 2 | order_id | 采集订单号 | String | 系统生成 |
| 3 | taxpayer_id | 申请人识别号 | String | 系统生成 |
| 4 | distributor_name_original | 经销商采集名称 | String | 采集字段 |
| 5 | distributor_code | 经销商编码 | String | 采集字段 |
| 6 | contact_person | 负责人 | String | 无法采集 |
| 7 | contact_phone | 负责人电话 | String | 无法采集 |
| 8 | producer_name_original | 厂家采集名称 | String | 无法采集 |
| 9 | producer_dep_original | 厂家合作部门 | String | 无法采集 |
| 10 | bill_no | 账单编号 | String | 采集字段 |
| 11 | transaction_month | 交易月份 | String | 采集字段 |
| 12 | opening_balance | 期初余额 | Decimal(20,2) | 采集字段 |
| 13 | closing_balance | 打款金额 | Decimal(20,2) | 采集字段 |
| 14 | purchase_amount | 进货金额 | Decimal(20,2) | 采集字段 |
| 15 | purchase_quantity | 进货数量 | Decimal(12,2) | 无法采集 |
| 16 | return_amount | 退货金额 | Decimal(20,2) | 无法采集 |
| 17 | return_quantity | 退货数量 | Decimal(12,2) | 无法采集 |
| 18 | quantity_unit | 数量单位 | String | 无法采集 |
| 19 | ending_balance | 期末余额 | Decimal(20,2) | 采集字段 |
| 20 | amount_unit | 金额单位 | String | 无法采集 |
| 21 | abstract | 摘要 | String | 采集字段 |
| 22 | discount_amount | 折扣金额 | Decimal(20,2) | 采集字段 |

> ⚠️ **查询规则（CRITICAL）**：**必须采用整月查询**（机器无法整月时的人工裁定例外见下条）。历史月份整月查询（该月 1 号 ~ 月末最后一天）；仅当前月截止当前日期。禁止按月内任意区间拆分查询（否则期初/期末余额及汇总口径不完整）。若系统有多个账号，`customer` 需**遍历所有账号**。
>
> **若站点只能提供比「月」更细的粒度**（半月期号、旬、周……），不要强行合并成自然月——判 `existence: granularity_mismatch`，`actual_granularity` 写实际粒度，交给人工拍板是否按实际粒度采集。**人工裁定接受该粒度后**（`manifest.json` 里该表 `existence` 已按裁定更新、`actual_granularity` 有记录、粒度告警进了 `acknowledged`），就按系统实际期号/区间**逐期查询**并覆盖每期完整区间，不要再拿整月参数去试。这条纪律来自 emdlz 的真实教训：该站点只给半月期号，一度被强行当成"月度账单"记录。
