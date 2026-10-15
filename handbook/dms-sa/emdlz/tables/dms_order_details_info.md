# dms_order_details_info（经营信息 / 订单明细数据）




## 字段采集表（23 字段，一一对应标准字段）

| # | 字段英文名 | 字段中文名 | 类型 | 页面形态 | 采集规则 | 字段来源（原始字段名一字不改） |
|---|-----------|-----------|------|---------|---------|------------------------------|
| 1 | order_group_id | 分组号 | String | 页面不可见 | 系统生成 → 无需采集 | `/`（平台无此字段，由上游采集系统生成） |
| 2 | order_id | 采集订单号 | String | 页面不可见 | 系统生成 → 无需采集 | `/`（平台内部主键为 API1 `result.records[].id` / API2 `result.main.id`，如 `2201187415293064721`，语义为平台 id 而非「采集订单号」，未采用） |
| 3 | taxpayer_id | 申请人识别号 | String | 页面不可见 | 系统生成 → 无需采集 | `/` |
| 4 | distributor_name_original | 经销商采集名称 | String | 页面不可见 | 采集字段 | API1：`result.records[].payerToName`（= `长沙市宏远商贸有限公司`，与 `soldToName` 本例同名，但人工裁定统一取付款方口径；页面「送达方」列展示的是 `soldToName`，故本字段按「接口独有」处理。列表页「客户」列实测渲染 `[payerToCode]payerToName`，与付款方口径一致）；API2：`result.main.payerToName` 同值 |
| 5 | distributor_code | 经销商编码 | String | 页面不可见 | 采集字段 | API1：`result.records[].payerToCode`（= `6182035`，与锚点 `GET /mdlz-user/user/info → result.user.account` 一致；人工裁定 2026-09-20：统一取付款方口径，与 `dms_bill_monthly_info`/`dms_bill_details_info` 的 `payerToCode` 全表一致，不用页面「送达方」列展示的 `soldToCode`=`6182036`） |
| 6 | order_no | 订单编号 | String | **页面可见** | 采集字段 | API1：`result.records[].orderNo`（页面「订单编号」列；API2 `result.main.orderNo` 同值） |
| 7 | order_amount_before_discount | 订单金额（折扣前） | Decimal(20,2) | **页面可见** | 采集字段 | API1：`result.records[].taxTotalAmount`（页面「订单金额(含税)」列，如 `37592.049`→页面 `37,592.05`）；行级冗余校验：Σ API2 `result.orderItems[].taxAmount` 同值 |
| 8 | order_amount_after_discount | 订单金额（折扣后） | Decimal(20,2) | 页面不可见 | **无法采集**（核验日期 2026-09-20） | `/`（契约已标不可采集；平台四个载体均无折扣/折后金额字段） |
| 9 | amount_unit | 金额单位 | String | 页面不可见 | **无法采集**（核验日期 2026-09-20） | `/`（页面金额列无单位标识，接口无单位字段） |
| 10 | order_quantity | 订单数量 | Decimal(12,2) | **页面可见** | 采集字段 | API1：`result.records[].orderCount`（页面「订单数量」列，与 `totalBox` 同值；行级冗余校验：Σ API2 `result.orderItems[].totalBox` 同值） |
| 11 | quantity_unit | 数量单位 | String | 页面不可见 | **无法采集**（核验日期 2026-09-20） | `/`（排查：单位仅由列名/导出列名体现，无字段来源，人工裁定不采） |
| 12 | discount_amount | 折扣金额 | Decimal(20,2) | 页面不可见 | **无法采集**（核验日期 2026-09-20） | `/`（契约已标不可采集） |
| 13 | product_name | 商品名称 | String | 页面不可见 | 采集字段 | API2：`result.orderItems[].skuName`（如 `奥利奥夹心云朵蛋糕龙井抹茶味6枚装132G`）；API3 导出列「产品名称」。接口独有：我的订单页无该列展示 |
| 14 | order_status | 订单状态 | String | **页面可见** | 采集字段 | API1：`result.records[].orderStatus`（数字码）→ 页面中文文案，映射函数见 bundle `orderStatusName`（字典见下）。**不用** API1 的 `orderStatusMsg`（与页面文案系统性不一致） |
| 15 | order_weight | 订单重量 | Decimal(20,2) | 页面不可见 | **无法采集**（核验日期 2026-09-20） | `/`（排查：订单四个载体（列表/详情/展开/导出）均无重量字段；商品主数据 `dimProduct/productInfo → result.grossWeight` 派生方案人工裁定不采用——属商品主数据快照，历史订单回算会随主数据漂移失真） |
| 16 | weight_unit | 重量单位 | String | 页面不可见 | **无法采集**（核验日期 2026-09-20） | `/`（排查：同上，人工裁定不采用派生方案） |
| 17 | order_date | 下单日期 | Datetime | **页面可见** | 采集字段 | API1：`result.records[].poDate`（页面「订货日期」列，如 `2026-09-16 10:12:20`；API2 `result.main.poDate` 同值） |
| 18 | ship_date | 发货日期 | Datetime | **页面可见** | 采集字段 | API2：`result.orderItems[].deliveryNoCreateDate`（行级，如 `2026-09-16 00:00:00`；未发货行为 `null`）；订单级冗余 `result.main.deliveryDate` = `my/orderDnInfo.deliveryDate`（展开行「发货」段「送货日期」） |
| 19 | expected_delivery_date | 期望交货日期 | Datetime | **页面可见** | 采集字段 | API1：`result.records[].rddDate`（页面「要求到货日」列，如 `2026-09-23 00:00:00`） |
| 20 | order_source | 订单来源 | String | 页面不可见 | **无法采集**（核验日期 2026-09-20） | `/`（排查：API1 `result.records[].orderSource` 实测恒为 `DT`，无中文字典可映射，人工裁定不采） |
| 21 | func_version | 功能版本 | String | 页面不可见 | **无法采集**（核验日期 2026-09-20） | `/`（契约已标不可采集；平台无此字段） |
| 22 | order_type | 订单类型 | String | 页面不可见 | 采集字段 | API1：`result.records[].orderType`（实测 `ZOR` / `PRE`）→ 中文映射见下 `getOrderType` 字典。接口独有：我的订单页无「订单类型」列（该列只在「全部订单」页展示） |
| 23 | platform_brand_id | 平台品牌ID | String | 页面不可见 | 系统生成 → 无需采集 | `/`（平台无此字段） |


### 订单状态字典（bundle `orderStatusName` 为准，与页面下拉 15 项一致）

```
orderStatusName(code):
 1 → 客户可修改
 2 → 退单
 3|4|6 → 处理中
 5 → 未到订单处理日
 7 → 待信控确认
 8|9|10 → 待生成送货单
 11 → 已生成送货单
 12 → 已取消
 13 → 仓库已发货
 14 → 已收货
 15 → 已开票
 16 → 已收款
 17 → 已清账
 18 → 整单未满足
 其它 → 状态未定义
```

实测对照（同一条记录，接口值 vs 页面文案）：`orderStatus`=4 → API `orderStatusMsg`「待审核」但页面「处理中」；=18 →「已完成」但页面「整单未满足」。→ `order_status` 必须用**页面文案字典**，不用 `orderStatusMsg`。

### 订单类型字典（bundle `getOrderType`）

```
ZFTT → 免费品订单
ZPRJ → 市场部领用单
ZCC → 内部领用单
ZOR → 普通订单
PRE → 预订单
AGE → 旧货单
default → 原值
```




## 待截图字段清单

| 字段编号 | 字段英文名 | 承载页（menu_path / route） | 页面列标题 / 位置 |
|---|---|---|---|
| 6 | order_no | 订单管理 > 我的订单 `/order/reserved` | 「订单编号」列 |
| 7 | order_amount_before_discount | 订单管理 > 我的订单 `/order/reserved` | 「订单金额(含税)」列（表格横向滚动 296px 后可见） |
| 10 | order_quantity | 订单管理 > 我的订单 `/order/reserved` | 「订单数量」列（表格横向滚动 296px 后可见） |
| 14 | order_status | 订单管理 > 我的订单 `/order/reserved` | 「订单状态」列 |
| 17 | order_date | 订单管理 > 我的订单 `/order/reserved` | 「订货日期」列 |
| 18 | ship_date | 订单管理 > 我的订单 `/order/reserved` | 展开行「发货」段的「送货日期」（列表页无独立列） |
| 19 | expected_delivery_date | 订单管理 > 我的订单 `/order/reserved` | 「要求到货日」列 |

`product_name`、`order_type` 为接口独有（页面无独立展示）；`distributor_name_original`/`distributor_code` 人工裁定改取付款方口径后，页面「送达方」列展示的是 `soldToName`/`soldToCode`（不同值），按「接口独有」处理，不列入本清单。




### 截图 0：订单管理 > 我的订单 `/order/reserved`（列表页左半，未横向滚动）

| 标注 | 位置（viewport 坐标，DPR=1） | 含义 |
|---|---|---|
| 红色矩形 | 左侧边栏 `(0,0,140,992)` | **采集路径**：侧边栏「订单管理」分组 |
| 红色矩形 | 顶部标签导航 `(140,50,1780,34)` | **采集路径**：站点导航/Tags-View（`首页 / 我的订单`） |
| 红色矩形 | 侧栏菜单项「我的订单」`(0,100,140,30)` | **采集路径**：菜单 订单管理 > 我的订单（`a[href="/order/reserved"]`，route `/order/reserved`） |
| 红色矩形 | 表头列「订单编号」`(271,145,200,67)` | 字段 **6** `order_no` 承载列（取值行 = 数据行的该列单元格） |
| **marker 6** | 指向 `(371,178)` | 字段编号 **6** `order_no`（订单编号） |
| 红色矩形 | 表头列「订单状态」`(471,145,200,67)` | 字段 **14** `order_status` 承载列 |
| **marker 14** | 指向 `(571,178)` | 字段编号 **14** `order_status`（订单状态，页面中文文案为准） |
| 红色矩形 | 表头列「客户」`(821,145,150,67)` | 字段 **4** / **5** 承载列（实测值 `[6182035]长沙市宏远商贸有限公司` = `[payerToCode]payerToName`，与字段来源同源） |
| **marker 4** | 指向 `(850,178)` | 字段编号 **4** `distributor_name_original`（经销商采集名称，取「客户」列的名称部分） |
| **marker 5** | 指向 `(940,178)` | 字段编号 **5** `distributor_code`（经销商编码，取「客户」列的方括号编码部分，`6182035`） |
| 红色矩形 | 表头列「订货日期」`(1121,145,250,67)` | 字段 **17** `order_date` 承载列 |
| **marker 17** | 指向 `(1246,178)` | 字段编号 **17** `order_date`（下单日期） |
| 红色矩形 | 表头列「要求到货日」`(1621,145,250,67)` | 字段 **19** `expected_delivery_date` 承载列 |
| **marker 19** | 指向 `(1746,178)` | 字段编号 **19** `expected_delivery_date`（期望交货日期） |

### 截图 1：订单管理 > 我的订单 `/order/reserved`（列表页右半，表格横向滚动 296px）

> 「订单数量」「订单金额(含税)」两列在默认视口外（表格 `scrollWidth` 2020 / viewport 1739），故横向滚动 `el-table__body-wrapper.scrollLeft = 296` 后单独截图。

| 标注 | 位置（viewport 坐标，DPR=1） | 含义 |
|---|---|---|
| 红色矩形 | 顶部标签导航 `(140,50,1780,34)` | **采集路径**：站点导航/Tags-View |
| 红色矩形 | 侧栏菜单项「我的订单」`(0,100,140,30)` | **采集路径**：菜单 订单管理 > 我的订单 |
| 红色矩形 | 表头列「订单数量」`(1575,145,150,67)` | 字段 **10** `order_quantity` 承载列 |
| **marker 10** | 指向 `(1650,178)` | 字段编号 **10** `order_quantity`（订单数量） |
| 红色矩形 | 表头列「订单金额(含税)」`(1725,145,195,67)` | 字段 **7** `order_amount_before_discount` 承载列 |
| **marker 7** | 指向 `(1822,178)` | 字段编号 **7** `order_amount_before_discount`（订单金额（折扣前），页面「订单金额(含税)」） |

### 截图 2：订单管理 > 我的订单 `/order/reserved`（展开行「分配」段）

> 列表页无独立发货日期列，`ship_date` 只在**展开行**体现。展开方式：`evaluate_script` 内对目标行的 `.el-table__expand-icon` 派发 `MouseEvent('click',{bubbles:true,cancelable:true,view:window})`（用 `click_element` 会误触发导航）。本例展开的是第 4 行订单 `ZORNML260916000666`（已生成送货单，`orderStatus=11`）；未发货订单（如 `ZORNML260918001999`）展开后只有「订货」段，无「分配/发货」段。

| 标注 | 位置（viewport 坐标，DPR=1） | 含义 |
|---|---|---|
| 红色矩形 | 顶部标签导航 `(140,50,1780,34)` | **采集路径**：站点导航/Tags-View |
| 红色矩形 | 侧栏菜单项「我的订单」`(0,100,140,30)` | **采集路径**：菜单 订单管理 > 我的订单 |
| 红色矩形 | 展开行「分配」（发货）段 `(210,676,780,72)` | 字段 **18** `ship_date` 承载区（该段列标题为 单号 / 送货数量 / **送货日期** / 金额（未税）/ 金额（含税）） |
| **marker 18** | 指向 `(908,701)` | 字段编号 **18** `ship_date`（发货日期，取「送货日期」列，值 `2026-09-16` = `orderItems[].deliveryNoCreateDate` / `my/orderDnInfo.deliveryDate`）；未发货行该列无「分配」段即表示为空（`null`） |
