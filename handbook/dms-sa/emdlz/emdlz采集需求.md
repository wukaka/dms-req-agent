# 亿滋 emdlz（昆仑 kunlun）DMS 系统采集需求文档

> 平台：emdlz（DMS-SA 经销商端，站点「昆仑 kunlun」）｜核验日期：2026-09-20（UTC）
> 本平台共 6 张标准表：3 张 `exists`、1 张 `partial`、2 张 `absent`。论证过程、完整接口响应、curl 与排查清单见同目录《emdlz技术笔记.md》。

## 系统信息

| 项目 | 内容 |
|------|------|
| 采集网站 | https://kunlun.emdlz.com.cn |
| 系统名称 | 昆仑 kunlun（亿滋 DMS-SA，经销商端） |
| 系统架构 | Vue 2 + Element UI 单页应用（RuoYi 二次开发，`keep-alive` 组件缓存、router 动态懒加载） |
| 数据返回方式 | JSON API（SPA 渲染，非 SSR HTML；`content-type: application/json;charset=UTF-8`） |
| 鉴权方式 | Header Token（JWT）+ Cookie Session |
| 鉴权字段 | 请求头 `token: <JWT>`（取自 `localStorage.tokenKey`）；Cookie `Admin-Token`（与 token 同值）、`JSESSIONID`（服务端每次响应轮换） |
| 测试账号 | `6182035`（长沙市宏远商贸有限公司，角色仅「KL下单客户」，user.id=512） |
| 一句话登录方式 | 账号 + 密码登录（站点另有 Azure AD 单点入口 `aad/login`，本账号走账号密码），登录后 JWT 写入 `localStorage.tokenKey` 并同步到 Cookie `Admin-Token` |

栏目地图引用见 `menu_map.md`。本账号实际授权模块：订单管理、数据维护（仅 DOS 审批流）、财务管理、信控管理、配额管理、系统管理。

---

## 一、基础信息（dms_basic_info）

**结论：`partial`。** 平台**没有独立的**「基础信息 / 基本资料 / 经销商档案 / 租户品牌」业务栏目（侧边菜单 5 项 + 全量动态路由 47 条已穷举），经销商身份的载体现为**登录身份接口** `GET /mdlz-user/user/info`（`result.user.zhName` → 经销商名称、`result.user.account` → 经销商编码），页面佐证为「订单管理 > 我的订单」表格「客户」列与全局顶栏用户名。16 个标准字段中：**2 个可采集、4 个系统生成、10 个字段级无法采集**。


| 字段英文名 | 字段中文名 | 字段编号 | 字段类型 | 示例 | 采集页面路径 | 采集规则 | 字段来源 |
|---|---|---|---|---|---|---|---|
| order_group_id | 分组号 | 1 | String | — | — | 系统生成 | 无需采集，前端传入 |
| order_id | 采集订单号 | 2 | String | — | — | 系统生成 | 无需采集，前端传入 |
| taxpayer_id | 申请人识别号 | 3 | String | — | — | 系统生成 | 无需采集，前端传入 |
| platform_brand | 平台品牌 | 4 | String | — | — | 无法采集 | / |
| distributor_name_original | 经销商采集名称 | 5 | String | 长沙市宏远商贸有限公司 | 订单管理 > 我的订单 `/order/reserved`「客户」列；另见顶栏用户名、首页 `/index` 对账单「客户名称」 | 采集字段 | API：`GET /mdlz-user/user/info` → `result.user.zhName` |
| distributor_code | 经销商编码 | 6 | String | 6182035 | 同上，「客户」列方括号编号 `[6182035]`；另见顶栏身份、首页「客户编码：」 | 采集字段 | API：`GET /mdlz-user/user/info` → `result.user.account` |
| distributor_address | 经销商地址 | 7 | String | — | — | 无法采集 | / |
| contact_person | 负责人 | 8 | String | — | — | 无法采集 | / |
| contact_phone | 负责人电话 | 9 | String | — | — | 无法采集 | / |
| producer_name_original | 厂家采集名称 | 10 | String | — | — | 无法采集 | / |
| producer_dep_original | 厂家合作部门 | 11 | String | — | — | 无法采集 | / |
| producer_usc_code_original | 厂家采集统一社会信用代码 | 12 | String | — | — | 无法采集 | / |
| platform_brand_id | 平台品牌ID | 13 | String | — | — | 系统生成 | 无需采集，前端传入 |
| distributor_usc_code_original | 经销商采集统一社会信用代码 | 14 | String | — | — | 无法采集 | / |
| cooper_status | 合作状态 | 15 | String | — | — | 无法采集 | / |
| tenant_name | 品牌租户名称 | 16 | String | — | — | 无法采集 | / |

> 10 个「无法采集」字段的逐条排查（候选接口、判定依据、核验日期）见技术笔记 §一。人工裁定（2026-09-20）已确认：财务客户主数据接口 `POST /mdlz-financial/btcCustomer/query` 虽含税号/地址/电话字段，但本账号无页面权限且过滤 `6182035` 无记录，**不换账号重核**，相关字段判无法采集。

---

## 二、经营信息-订单明细数据（dms_order_details_info）

**结论：`exists`。** 唯一载体 =「订单管理 > 我的订单」`/order/reserved` + 下钻详情接口 `GET /mdlz-order/otc-order-main/detail`；列表 595 条订单；**落库粒度 = 订单 × 商品行**（行键 `orderNo` + `lineNo`，商品级字段只存在于 `detail.orderItems[]` 与导出 xlsx，订单级字段在行级冗余）。23 个标准字段中：11 个可采集、4 个系统生成、8 个无法采集。




| 字段英文名 | 字段中文名 | 字段编号 | 字段类型 | 示例 | 采集页面路径 | 采集规则 | 字段来源 |
|---|---|---|---|---|---|---|---|
| order_group_id | 分组号 | 1 | String | — | — | 系统生成 | 无需采集，前端传入 |
| order_id | 采集订单号 | 2 | String | — | — | 系统生成 | 无需采集，前端传入 |
| taxpayer_id | 申请人识别号 | 3 | String | — | — | 系统生成 | 无需采集，前端传入 |
| distributor_name_original | 经销商采集名称 | 4 | String | 长沙市宏远商贸有限公司 | 订单管理 > 我的订单「客户」列；由接口解析 | 采集字段 | API1 `POST /mdlz-order/otc-order-main/my/list` → `result.records[].payerToName`（API2 `result.main.payerToName` 同值） |
| distributor_code | 经销商编码 | 5 | String | 6182035 | 订单管理 > 我的订单「客户」列方括号前缀 | 采集字段 | API1 → `result.records[].payerToCode`（= 登录账号；全表统一 payer 口径，不用 `soldToCode`=6182036） |
| order_no | 订单编号 | 6 | String | ZORNML260916000666 | 订单管理 > 我的订单「订单编号」列 | 采集字段 | API1 → `result.records[].orderNo`（API2 `result.main.orderNo` 同值） |
| order_amount_before_discount | 订单金额（折扣前） | 7 | Decimal(20,2) | 37,592.05 | 订单管理 > 我的订单「订单金额(含税)」列 | 采集字段 | API1 → `result.records[].taxTotalAmount`（= Σ API2 `orderItems[].taxAmount`） |
| order_amount_after_discount | 订单金额（折扣后） | 8 | Decimal(20,2) | — | — | 无法采集 | / |
| amount_unit | 金额单位 | 9 | String | — | — | 无法采集 | / |
| order_quantity | 订单数量 | 10 | Decimal(12,2) | 300 | 订单管理 > 我的订单「订单数量」列 | 采集字段 | API1 → `result.records[].orderCount`（= `totalBox` = Σ API2 `orderItems[].totalBox`） |
| quantity_unit | 数量单位 | 11 | String | — | — | 无法采集 | /（页面上仅列名体现「箱」，无字段来源；人工裁定 2026-09-20 不采） |
| discount_amount | 折扣金额 | 12 | Decimal(20,2) | — | — | 无法采集 | / |
| product_name | 商品名称 | 13 | String | 奥利奥夹心云朵蛋糕龙井抹茶味6枚装132G | 接口独有（页面无独立展示） | 采集字段 | API2 `GET /mdlz-order/otc-order-main/detail?id=` → `result.orderItems[].skuName`（API3 导出列「产品名称」） |
| order_status | 订单状态 | 14 | String | 处理中 | 订单管理 > 我的订单「订单状态」列 | 采集字段 | API1 → `result.records[].orderStatus`（数字码），按页面文案字典 `orderStatusName` 映射；**不用** `orderStatusMsg` |
| order_weight | 订单重量 | 15 | Decimal(20,2) | — | — | 无法采集 | /（订单四载体均无重量字段；商品主数据派生方案人工裁定不采用） |
| weight_unit | 重量单位 | 16 | String | — | — | 无法采集 | / |
| order_date | 下单日期 | 17 | Datetime | 2026-09-16 10:12:20 | 订单管理 > 我的订单「订货日期」列 | 采集字段 | API1 → `result.records[].poDate` |
| ship_date | 发货日期 | 18 | Datetime | 2026-09-16 00:00:00 | 订单管理 > 我的订单 展开行「分配」段「送货日期」（列表页无独立列） | 采集字段 | API2 → `result.orderItems[].deliveryNoCreateDate`（未发货为 `null`；订单级冗余 `result.main.deliveryDate`） |
| expected_delivery_date | 期望交货日期 | 19 | Datetime | 2026-09-23 00:00:00 | 订单管理 > 我的订单「要求到货日」列 | 采集字段 | API1 → `result.records[].rddDate` |
| order_source | 订单来源 | 20 | String | — | — | 无法采集 | /（接口值恒为 `DT`，无中文字典可映射，人工裁定 2026-09-20 不采） |
| func_version | 功能版本 | 21 | String | — | — | 无法采集 | / |
| order_type | 订单类型 | 22 | String | ZOR（普通订单） | 接口独有（本页无「订单类型」列） | 采集字段 | API1 → `result.records[].orderType`，按字典 `getOrderType` 映射 |
| platform_brand_id | 平台品牌ID | 23 | String | — | — | 系统生成 | 无需采集，前端传入 |

> 订单状态/订单类型的中文映射字典（bundle `orderStatusName` / `getOrderType`）、`order_weight` 派生方案被否的依据、四层入口粒度实测，均见技术笔记 §二。

---

## 三、经营信息-账单分月数据（dms_bill_monthly_info）

**结论：`exists`，但实际粒度为「半月」，与契约要求的「月」不一致（`granularity_mismatch`），已由人工裁定接受按半月实际采集。**
**载体唯一**：「订单管理 > 应收账款对账单」`/order/accountsReceivableStatement` + `POST /mdlz-order/accountsReceivableStatement/queryList`（全站账单类对象仅此一个，权限串 15 条中账单相关 4 条全部指向该页）。
**粒度证据（2026-09-20 逐期实查）**：`GET .../queryFileNameMonth` 返回 78 个期号，**全部为 `YYMM0X` 形态**（`01`=上半月 1–15 日、`02`=下半月 16 日–月末），无任何整月形态；相邻两期首尾严格衔接（260501 期末 −107,363.01 = 260502 期初；260801 期末 −9,951.65 = 260802 期初；260802 期末 −5,922.05 = 260901 期初）；整月探针 `2609`/`202609`/`260900` 均返回 `result:[]`，自定义区间参数被忽略。
22 个标准字段中：6 个可采集、3 个系统生成、13 个无法采集（均已人工裁定关闭）。

**⚠️ 待人工补拍截图**：本表截图未产出（会话内 SPA 路由自发循环、视图渲染丢失，详见技术笔记 §三），字段承载位置见下表与技术笔记「待截图字段清单」。

| 字段英文名 | 字段中文名 | 字段编号 | 字段类型 | 示例 | 采集页面路径 | 采集规则 | 字段来源 |
|---|---|---|---|---|---|---|---|
| order_group_id | 分组号 | 1 | String | — | — | 系统生成 | 无需采集，前端传入 |
| order_id | 采集订单号 | 2 | String | — | — | 系统生成 | 无需采集，前端传入 |
| taxpayer_id | 申请人识别号 | 3 | String | — | — | 系统生成 | 无需采集，前端传入 |
| distributor_name_original | 经销商采集名称 | 4 | String | 长沙市宏远商贸有限公司 | 订单管理 > 应收账款对账单 抬头「客户名称：」 | 采集字段 | API1 `POST /mdlz-order/accountsReceivableStatement/queryList` → `result[0][0].payerToName` |
| distributor_code | 经销商编码 | 5 | String | 6182035 | 订单管理 > 应收账款对账单 抬头「客户编码：」 | 采集字段 | API1 → `result[0][0].payerToCode`（全表统一 payer 口径） |
| contact_person | 负责人 | 6 | String | — | — | 无法采集 | / |
| contact_phone | 负责人电话 | 7 | String | — | — | 无法采集 | / |
| producer_name_original | 厂家采集名称 | 8 | String | — | — | 无法采集 | / |
| producer_dep_original | 厂家合作部门 | 9 | String | — | — | 无法采集 | / |
| bill_no | 账单编号 | 10 | String | — | — | 无法采集 | /（页面/接口无「账单编号」概念；人工裁定 2026-09-20） |
| transaction_month | 交易月份 | 11 | String | 260901（=2026 年 9 月上半月） | 订单管理 > 应收账款对账单 抬头「清单期间：」 | 采集字段 | API1 → `result[0][0].fileNameMonth`（YYMM0X 半月期号） |
| opening_balance | 期初余额 | 12 | Decimal(20,2) | -5,922.05 | 订单管理 > 应收账款对账单 抬头「期初余额：」 | 采集字段 | API1 → `result[0][0].openingBalance` |
| closing_balance | 打款金额 | 13 | Decimal(20,2) | — | — | 无法采集 | /（候选 `cashSaleLoanTotal` 语义错配，人工裁定 2026-09-20） |
| purchase_amount | 进货金额 | 14 | Decimal(20,2) | 147,288.11 | 接口独有（页面无独立展示） | 采集字段 | API1 → `result[0][0].salesTotal`（与 `billingTotalAmount` 78/78 期恒等，人工裁定取 `salesTotal`） |
| purchase_quantity | 进货数量 | 15 | Decimal(12,2) | — | — | 无法采集 | / |
| return_amount | 退货金额 | 16 | Decimal(20,2) | — | — | 无法采集 | / |
| return_quantity | 退货数量 | 17 | Decimal(12,2) | — | — | 无法采集 | / |
| quantity_unit | 数量单位 | 18 | String | — | — | 无法采集 | / |
| ending_balance | 期末余额 | 19 | Decimal(20,2) | -17,633.94 | 订单管理 > 应收账款对账单 抬头「期末余额：」 | 采集字段 | API1 → `result[0][0].endingBalance` |
| amount_unit | 金额单位 | 20 | String | — | — | 无法采集 | /（金额均为系统默认「元」，无字段可提取） |
| abstract | 摘要 | 21 | String | — | — | 无法采集 | /（78 期零命中，人工裁定 2026-09-20） |
| discount_amount | 折扣金额 | 22 | Decimal(20,2) | — | — | 无法采集 | /（78 期零命中，人工裁定 2026-09-20） |

> 例外期号提示：78 期中 `230603` 为唯一例外（期间 2023/01/01–2023/06/30 半年、`*_Total` 汇总字段为 `null`），人工裁定忽略该期例外、不做特殊处理，明细照采、汇总为 `null` 即留空。

---

## 四、经营信息-账单明细数据（dms_bill_details_info）

**结论：`exists`。** 与第三节**同源**（同一次 `POST /mdlz-order/accountsReceivableStatement/queryList`：`result[0][0]` = 账单抬头＝分月口径，`result[0][0].detailList[]` = 逐笔明细＝明细口径），已由人工裁定合并为一次请求取证。行粒度 = 单据级交易行（一次查询 `customer=6182035&fileNameMonth=260901` 返回 6 条明细行），对账单表格行不可点击、无二级明细页。21 个标准字段中：8 个可采集、3 个系统生成、10 个无法采集。

**⚠️ 待人工补拍截图**：本表截图未产出（同第三节，载体页在会话内无法稳定渲染出数据态），承载位置见下表与技术笔记「待截图字段清单」。


| 字段英文名 | 字段中文名 | 字段编号 | 字段类型 | 示例 | 采集页面路径 | 采集规则 | 字段来源 |
|---|---|---|---|---|---|---|---|
| order_group_id | 分组号 | 1 | String | — | — | 系统生成 | 无需采集，前端传入 |
| order_id | 采集订单号 | 2 | String | — | — | 系统生成 | 无需采集，前端传入 |
| taxpayer_id | 申请人识别号 | 3 | String | — | — | 系统生成 | 无需采集，前端传入 |
| distributor_name_original | 经销商采集名称 | 4 | String | 长沙市宏远商贸有限公司 | 订单管理 > 应收账款对账单 抬头「客户名称：」 | 采集字段 | API1 → `result[0][0].payerToName` |
| distributor_code | 经销商编码 | 5 | String | 6182035 | 订单管理 > 应收账款对账单 抬头「客户编码：」 | 采集字段 | API1 → `result[0][0].payerToCode` |
| producer_name_original | 厂家采集名称 | 6 | String | — | — | 无法采集 | / |
| bill_no | 账单编号 | 7 | String | 1400060403 | 订单管理 > 应收账款对账单 明细列「系统凭证号码」 | 采集字段 | API1 → `result[0][0].detailList[].systemCredentialNo`（人工裁定 2026-09-20：取行级凭证号，不用抬头 `fileName`） |
| transaction_date | 交易日期 | 8 | Datetime | 2026-09-04 | 订单管理 > 应收账款对账单 明细列「系统凭证日期」 | 采集字段 | API1 → `result[0][0].detailList[].systemCredentialDate`（原始 `2026/09/04`，页面按 `yyyy-M-d` 渲染） |
| bill_type | 账单类型 | 9 | String | — | — | 无法采集 | / |
| bill_amount | 账单金额 | 10 | Decimal(20,2) | — | — | 无法采集 | /（原条件口径与 `invoice_amount` 同源重叠，人工裁定 2026-09-20） |
| invoice_amount | 开票金额 | 11 | Decimal(20,2) | 49,073.95 | 订单管理 > 应收账款对账单 明细列「发票金额」 | 采集字段 | API1 → `result[0][0].detailList[].billingAmount` |
| goods_amount | 发货金额 | 12 | Decimal(20,2) | — | — | 无法采集 | / |
| goods_quantity | 货物数量 | 13 | Decimal(12,2) | — | — | 无法采集 | / |
| quantity_unit | 数量单位 | 14 | String | — | — | 无法采集 | / |
| balance | 余额 | 15 | Decimal(20,2) | -17,633.94 | 订单管理 > 应收账款对账单 抬头「期末余额：」 | 采集字段 | API1 → `result[0][0].endingBalance` |
| amount_unit | 金额单位 | 16 | String | — | — | 无法采集 | /（系统默认「元」，不可推断采集） |
| abstract | 摘要 | 17 | String | — | — | 无法采集 | / |
| order_no | 销售订单号 | 18 | String | — | — | 无法采集 | /（明细行无真实销售订单号；同一列 `systemCredentialNo` 已供 `bill_no`，人工裁定 2026-09-20） |
| data_match | 数据是否相符 | 19 | String | — | — | 无法采集 | / |
| platform_brand_id | 平台品牌ID | 20 | String | — | — | 无法采集 | / |
| transaction_month | 交易月份 | 21 | String | 260901 | 接口独有（对账月份仅作查询条件，不作数据行展示） | 采集字段 | API1 → `result[0][0].fileNameMonth` |

> **采集必须剔除前端注入的「合计」行**：组件在 `pageSize === 对账单数组长度` 时 `detailList.push(...)` 一行汇总（判定：`systemCredentialNo === null && tsNo === null`），否则会多出一条假明细。

---

## 五、基础信息-合同信息（dms_contract_sign_info）

**结论：`absent`（人工裁定 2026-09-20）—— 本平台不存在该业务板块，无字段采集表。**
证据：全量菜单树（6 个一级模块 / 47 条路由）对「合同 / 协议 / 签约 / 签订 / 契约 / 经销协议」**零命中**；前端 bundle 检索仅得两处弱证据 `btcCustomerContractDeduction`（合同**扣款额**导入导出）与 `doRenewalOfContract`，服务于财务 KA 账单（`/mdlz-financial/btcBillingMain`、`btcKaBillingMain`），语义为账单侧合同扣款额而非合同签约，且不对本账号开放（属无权限，非存在）。完整排查记录见技术笔记 §五。

---

## 六、基础信息-认证信息（dms_certified_info）

**结论：`absent`（人工裁定 2026-09-20）—— 本平台不存在该业务板块，无字段采集表。**
证据：全量菜单树对「认证 / 资质 / 授权 / 证书 / 资格 / 备案」**零命中**；bundle 唯一命中 `uploadCertificate:function(){}` 为**空函数体**（占位无实现），且位于财务 KA 计费页上下文。注意歧义：站点中 `aad/login`、`otcCsrSoldtoMapping/upload`、`getAuthorizedPayer` 的 "authorized" 均指**登录授权/客户授权关系**，与「资质认证」业务对象无关。完整排查记录见技术笔记 §六。

---

## 待人工确认

1. **截图补拍（`dms_bill_monthly_info` / `dms_bill_details_info`）**：两表同源，均无截图产出。需人工恢复可用登录会话后，进入「订单管理 > 应收账款对账单」把「客户」选为 `[6182035]长沙市宏远商贸有限公司`、「对账日期」选 `260901`、点「搜索」，待抬头 + 11 列明细渲染后一次截完两张表（待标注字段清单见技术笔记 §三/§四）。
2. **可选佐证截图（`dms_basic_info`）**：「订单管理 > 下达订单」`/order/place` 客户下拉、首页 `/index` 客户对账单「客户编码 / 客户名称」标签，均未落盘（字段 5/6 已由「我的订单」页截图完整覆盖，同源同值）。
3. 以下事项**已裁定完毕、无需再决策**，列出仅为闭环：半月粒度接受按实际采集（§三）；`distributor_code` 全表统一 `payerToCode`=6182035，不用 `soldToCode`=6182036；`dms_basic_info` 判 `partial` 且不换账号重核财务客户主数据；`order_weight`/`weight_unit` 不采用商品主数据派生；`bill_no` 取行级 `systemCredentialNo`；`order_no`、`bill_amount`、`closing_balance`、`abstract`、`discount_amount` 判无法采集；`dms_contract_sign_info`、`dms_certified_info` 判 `absent`。
