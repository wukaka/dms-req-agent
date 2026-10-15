# dms_bill_details_info（经营信息 / 账单明细数据）




## 字段采集表（21 字段，一一对应标准字段）

| # | 字段英文名 | 字段中文名 | 类型 | 页面形态 | 采集规则 | 字段来源（原始字段名一字不改） |
|---|-----------|-----------|------|---------|---------|------------------------------|
| 1 | order_group_id | 分组号 | String | 页面不可见 | 系统生成 → 无需采集 | `/`（系统生成，前端传入） |
| 2 | order_id | 采集订单号 | String | 页面不可见 | 系统生成 → 无需采集 | `/`（系统生成，前端传入） |
| 3 | taxpayer_id | 申请人识别号 | String | 页面不可见 | 系统生成 → 无需采集 | `/`（系统生成，前端传入） |
| 4 | distributor_name_original | 经销商采集名称 | String | **页面可见** | 采集字段 | API：`POST /mdlz-order/accountsReceivableStatement/queryList` → `result[0][0].payerToName`（=长沙市宏远商贸有限公司）。页面可见（：页面上方抬头区「客户名称：」） |
| 5 | distributor_code | 经销商编码 | String | **页面可见** | 采集字段 | API：`queryList` → `result[0][0].payerToCode`（=6182035）。页面可见（：页面上方抬头区「客户编码：」）。全表统一用该业务编码 |
| 6 | producer_name_original | 厂家采集名称 | String | 页面不可见 | **无法采集**（核验日期 2026-09-20） | `/`（排查：全载体无厂家/供应商/品牌名称字段；页面抬头 6 项仅客户信息；导出字符串与接口均无相关键） |
| 7 | bill_no | 账单编号 | String | **页面可见** | 采集字段 | API：`queryList` → `result[0][0].detailList[].systemCredentialNo`（=1400060403）。页面可见（：「系统凭证号码」列）。人工裁定（2026-09-20）：取行级 `systemCredentialNo`，不取抬头 `fileName` |
| 8 | transaction_date | 交易日期 | Datetime | **页面可见** | 采集字段 | API：`queryList` → `result[0][0].detailList[].systemCredentialDate`（=2026/09/04）。页面可见（：「系统凭证日期」列，按 `timeFormatMain('yyyy-M-d')` 渲染为 `2026-9-4`） |
| 9 | bill_type | 账单类型 | String | 页面不可见 | **无法采集**（核验日期 2026-09-20） | `/`（排查：载体无账单类型/类型编码字段；无字典可映射；对账单只有一个统一模板，不可派生） |
| 10 | bill_amount | 账单金额 | Decimal(20,2) | 页面不可见 | **无法采集**（核验日期 2026-09-20） | `—`（排查：原条件口径（发票行取 `billingAmount`、现销行取 `cashSaleLoan`）在发票行与 `invoice_amount` 同值，同一来源不得供两个标准字段；人工裁定不采，`billingAmount` 归 `invoice_amount`） |
| 11 | invoice_amount | 开票金额 | Decimal(20,2) | **页面可见** | 采集字段 | API：`queryList` → `result[0][0].detailList[].billingAmount`（行级，=49,073.95）。页面可见（：「发票金额」列） |
| 12 | goods_amount | 发货金额 | Decimal(20,2) | 页面不可见 | **无法采集**（核验日期 2026-09-20） | `/`（排查：页面金额列仅 发票金额/销售额/现销贷款/赊销贷款/应收调整，无「发货金额」；`deliveryNo` 只有单号无金额；销售额 ≠ 发货金额，不可臆断） |
| 13 | goods_quantity | 货物数量 | Decimal(12,2) | 页面不可见 | **无法采集**（核验日期 2026-09-20） | `/`（排查：页面 11 列与接口均无任何数量字段） |
| 14 | quantity_unit | 数量单位 | String | 页面不可见 | **无法采集**（核验日期 2026-09-20） | `/`（排查：数量本身不存在，单位无从谈起；无单位字典字段） |
| 15 | balance | 余额 | Decimal(20,2) | **页面可见** | 采集字段 | API：`queryList` → `result[0][0].endingBalance`（=-17,633.94）。页面可见（：页面上方抬头区「期末余额：」） |
| 16 | amount_unit | 金额单位 | String | 页面不可见 | **无法采集**（核验日期 2026-09-20） | `/`（排查：金额均为系统默认「元」，无返回字段可提取；系统默认/固定值不可推断采集） |
| 17 | abstract | 摘要 | String | 页面不可见 | **无法采集**（核验日期 2026-09-20） | `/`（排查：页面 11 列 + 抬头 6 项 + 脚注 4 行均无「摘要」；导出全部字符串无「摘要」；接口无 `abstract`/`remark` 类键；不可派生） |
| 18 | order_no | 销售订单号 | String | 页面不可见 | **无法采集**（核验日期 2026-09-20） | `—`（排查：明细行无真实销售订单号字段，`tsNo`/`systemCredentialNo`/`deliveryNo`/`vatBillingNo` 形态均与本系统销售订单号 `PRENML260807024777`/`ZORNML260918001999` 不符；`systemCredentialNo` 已供 `bill_no`，不一对多复用） |
| 19 | data_match | 数据是否相符 | String | 页面不可见 | **无法采集**（核验日期 2026-09-20） | `/`（排查：载体无相符/差异标记字段；`settleAccount`（清账 Y/N）语义为清账状态，非「数据是否相符」） |
| 20 | platform_brand_id | 平台品牌ID | String | 页面不可见 | **无法采集**（核验日期 2026-09-20） | `/`（排查：全载体无品牌/平台品牌字段；客户维度标识仅有 `payerToCode`，已用于 `distributor_code`，不一对多复用） |
| 21 | transaction_month | 交易月份 | String | 页面不可见 | 采集字段 | API：`queryList` → `result[0][0].fileNameMonth`（=260901，格式 YYMMDD → 交易月份 `2026-09`）。接口独有，页面无独立展示 |




## 待截图字段清单

| 字段编号 | 字段英文名 | 承载页（menu_path / route） | 页面列标题 / 位置 |
|---|---|---|---|
| 4 | distributor_name_original | 订单管理 > 应收账款对账单 `/order/accountsReceivableStatement` | 页面上方抬头区「客户名称：」 |
| 5 | distributor_code | 订单管理 > 应收账款对账单 `/order/accountsReceivableStatement` | 页面上方抬头区「客户编码：」 |
| 7 | bill_no | 订单管理 > 应收账款对账单 `/order/accountsReceivableStatement` | 「系统凭证号码」列 |
| 8 | transaction_date | 订单管理 > 应收账款对账单 `/order/accountsReceivableStatement` | 「系统凭证日期」列 |
| 11 | invoice_amount | 订单管理 > 应收账款对账单 `/order/accountsReceivableStatement` | 「发票金额」列 |
| 15 | balance | 订单管理 > 应收账款对账单 `/order/accountsReceivableStatement` | 页面上方抬头区「期末余额：」 |

其余字段均为接口独有 / 系统生成 / 无法采集，无页面可标注。




### 未能完成的截图

| 目标 | 状态 | 说明 |
|---|---|---|
| 订单管理 > 应收账款对账单 `/order/accountsReceivableStatement`（客户编码 `6182035`、对账月份 `260901`） | **未落盘** | 会话内 SPA 路由自发循环、视图无法稳定渲染出数据态，待人工恢复可用会话后按上方清单补拍 |
