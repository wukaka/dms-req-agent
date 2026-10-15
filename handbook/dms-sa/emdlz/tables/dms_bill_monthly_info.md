# dms_bill_monthly_info（经营信息·账单分月数据）




## 字段采集表（22 字段，一一对应标准字段）

| # | 字段英文名 | 字段中文名 | 类型 | 页面形态 | 采集规则 | 字段来源（原始字段名一字不改） |
|---|-----------|-----------|------|---------|---------|------------------------------|
| 1 | order_group_id | 分组号 | String | 页面不可见 | 系统生成 → 无需采集 | `/`（系统生成，前端传入） |
| 2 | order_id | 采集订单号 | String | 页面不可见 | 系统生成 → 无需采集 | `/`（系统生成，前端传入） |
| 3 | taxpayer_id | 申请人识别号 | String | 页面不可见 | 系统生成 → 无需采集 | `/`（系统生成，前端传入） |
| 4 | distributor_name_original | 经销商采集名称 | String | **页面可见** | 采集字段 | API：`POST /mdlz-order/accountsReceivableStatement/queryList` → `result[0][0].payerToName`（=长沙市宏远商贸有限公司）。页面可见（：抬头区「客户名称：」，页面同时 SSR 渲染同一份数据） |
| 5 | distributor_code | 经销商编码 | String | **页面可见** | 采集字段 | API：`queryList` → `result[0][0].payerToCode`（=6182035）。页面可见（：抬头区「客户编码：」）。全平台统一 `payerToCode` 口径（人工裁定 2026-09-20，不用 `soldToCode=6182036`） |
| 6 | contact_person | 负责人 | String | 页面不可见 | **无法采集**（核验日期 2026-09-20） | `/`（排查：菜单/权限串/页面抬头与明细表头/接口全量 key/78 期数据/导出 Excel 全字段核对均无负责人字段；正则 `person\|contact` 零命中） |
| 7 | contact_phone | 负责人电话 | String | 页面不可见 | **无法采集**（核验日期 2026-09-20） | `/`（排查：同上，全链路无电话字段） |
| 8 | producer_name_original | 厂家采集名称 | String | 页面不可见 | **无法采集**（核验日期 2026-09-20） | `/`（排查：全链路无厂家/供应商名称字段；正则 `producer\|factory\|brand` 零命中） |
| 9 | producer_dep_original | 厂家合作部门 | String | 页面不可见 | **无法采集**（核验日期 2026-09-20） | `/`（排查：同上，全部动态路由中无合作部门类栏目） |
| 10 | bill_no | 账单编号 | String | 页面不可见 | **无法采集**（核验日期 2026-09-20） | `/`（排查：页面/接口均无「账单编号」概念；`fileNameMonth` 已供 `transaction_month`、`fileName` 为导出文件名 `260901-KL.xlsx`，人工裁定均不采用） |
| 11 | transaction_month | 交易月份 | String | **页面可见** | 采集字段 | API：`queryList` → `result[0][0].fileNameMonth`（YYMM0X 半月期号，如 `260901` → 2026 年 9 月上半月）。页面可见（：抬头区「清单期间：」） |
| 12 | opening_balance | 期初余额 | Decimal(20,2) | **页面可见** | 采集字段 | API：`queryList` → `result[0][0].openingBalance`。页面可见（：抬头区「期初余额：」）；金额接口返回带千分位的字符串（如 `-159,000.00`） |
| 13 | closing_balance | 打款金额 | Decimal(20,2) | 页面不可见 | **无法采集**（核验日期 2026-09-20） | `/`（排查：候选 `result[0][0].cashSaleLoanTotal`（现销贷款合计）语义错配，且 78 期非零期皆为负，人工裁定不采用） |
| 14 | purchase_amount | 进货金额 | Decimal(20,2) | 页面不可见 | 采集字段 | API：`queryList` → `result[0][0].salesTotal`（销售额；与 `billingTotalAmount` 78/78 期完全相等，人工裁定取 `salesTotal`）。接口独有，页面无独立编号列 |
| 15 | purchase_quantity | 进货数量 | Decimal(12,2) | 页面不可见 | **无法采集**（核验日期 2026-09-20） | `/`（排查：全链路无数量字段；正则 `qty\|quantity\|num\|count` 零命中） |
| 16 | return_amount | 退货金额 | Decimal(20,2) | 页面不可见 | **无法采集**（核验日期 2026-09-20） | `/`（排查：无 return 命名字段；78 期全量 628 行中唯一负值行（期号 `240502` / `systemCredentialNo=8693301777`，`billingAmount=sales=-104,972.15`）不足以建立退货口径） |
| 17 | return_quantity | 退货数量 | Decimal(12,2) | 页面不可见 | **无法采集**（核验日期 2026-09-20） | `/`（排查：同上，78 期全量无退货数量字段） |
| 18 | quantity_unit | 数量单位 | String | 页面不可见 | **无法采集**（核验日期 2026-09-20） | `/`（排查：数量本身不存在，单位无从谈起；系统默认/固定值不可推断采集） |
| 19 | ending_balance | 期末余额 | Decimal(20,2) | **页面可见** | 采集字段 | API：`queryList` → `result[0][0].endingBalance`。页面可见（：抬头区「期末余额：」） |
| 20 | amount_unit | 金额单位 | String | 页面不可见 | **无法采集**（核验日期 2026-09-20） | `/`（排查：金额均为系统默认「元」，无返回字段可提取；系统默认/固定值不可推断采集） |
| 21 | abstract | 摘要 | String | 页面不可见 | **无法采集**（核验日期 2026-09-20） | `/`（排查：页面/接口/导出均无 `remark`/`abstract`/`summary`，78 期零命中，人工裁定） |
| 22 | discount_amount | 折扣金额 | Decimal(20,2) | 页面不可见 | **无法采集**（核验日期 2026-09-20） | `/`（排查：页面/接口/导出均无 discount 类字段，78 期零命中，人工裁定） |




## 待截图字段清单

| 字段编号 | 字段英文名 | 承载页（menu_path / route） | 页面列标题 / 位置 |
|---|---|---|---|
| 4 | distributor_name_original | 订单管理 > 应收账款对账单 `/order/accountsReceivableStatement` | 抬头「客户名称：」 |
| 5 | distributor_code | 订单管理 > 应收账款对账单 `/order/accountsReceivableStatement` | 抬头「客户编码：」 |
| 11 | transaction_month | 订单管理 > 应收账款对账单 `/order/accountsReceivableStatement` | 抬头「清单期间：」 |
| 12 | opening_balance | 订单管理 > 应收账款对账单 `/order/accountsReceivableStatement` | 抬头「期初余额：」 |
| 19 | ending_balance | 订单管理 > 应收账款对账单 `/order/accountsReceivableStatement` | 抬头「期末余额：」 |

其余字段中 `purchase_amount` 为接口独有（页面无独立展示）；`bill_no`、`closing_balance`、`abstract`、`discount_amount` 已判无法采集，与系统生成字段一样不参与截图标注。明细表 11 列与合计行为对账明细，非本表 22 个标准字段的承载列。




### 未能完成的截图

| 目标 | 状态 | 说明 |
|---|---|---|
| 订单管理 > 应收账款对账单 `/order/accountsReceivableStatement`（保持 260901 期只读渲染状态） | **未落盘** | 会话内 SPA 路由自发循环、视图无法稳定渲染出数据态，待人工恢复可用会话后按上方清单补拍 |
