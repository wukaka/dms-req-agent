# dms_basic_info（基础信息 / 经销商采集主体基础信息）




## 字段采集表（16 字段，一一对应标准字段）

| # | 字段英文名 | 字段中文名 | 类型 | 页面形态 | 采集规则 | 字段来源（原始字段名一字不改） |
|---|-----------|-----------|------|---------|---------|------------------------------|
| 1 | order_group_id | 分组号 | String | 页面不可见 | 系统生成 → 无需采集 | `/`（系统生成，前端传入） |
| 2 | order_id | 采集订单号 | String | 页面不可见 | 系统生成 → 无需采集 | `/`（系统生成，前端传入） |
| 3 | taxpayer_id | 申请人识别号 | String | 页面不可见 | 系统生成 → 无需采集 | `/`（系统生成，前端传入） |
| 4 | platform_brand | 平台品牌 | String | 页面不可见 | **无法采集**（核验日期 2026-09-20） | `/`（排查：`/mdlz-user/user/info` 无品牌字段；`/mdlz-order/dimProduct/brand/list` 返回 15 个**产品**品牌中文名（王子/奥利奥/炫迈/趣多多/菓珍…）属产品品牌字典、非平台品牌；`/order/place`「选择品牌」浮层同源；无租户/品牌上下文接口；站点固定名不得推断，规则 2） |
| 5 | distributor_name_original | 经销商采集名称 | String | **页面可见** | 采集字段 | API：`GET /mdlz-user/user/info` → `result.user.zhName`（=长沙市宏远商贸有限公司）。页面可见（：`/order/reserved` 表格「客户」列的 `[6182035]长沙市宏远商贸有限公司` 名称部分、`/index` 首页客户对账单「客户名称」、登录后全局顶栏右侧用户名、`/order/place` 客户下拉选项） |
| 6 | distributor_code | 经销商编码 | String | **页面可见**（以 `[编码]` 前缀形态） | 采集字段 | API：`GET /mdlz-user/user/info` → `result.user.account`（=6182035）。页面同现于 `/order/reserved` 表格「客户」列的方括号前缀 `[6182035]`、`/index` 首页对账单「客户编码：6182035」、`/order/place` 客户下拉选项。按规则 4 全板块统一用此来源（跨接口一致：`accountsReceivableStatement/queryList` 的 `payerToCode`=6182035、`otc-order-main/my/list` 的 `payerToCode`=6182035、`localStorage.confirmSelectionParams.payerCode`=6182035） |
| 7 | distributor_address | 经销商地址 | String | 页面不可见 | **无法采集**（核验日期 2026-09-20） | `/`（排查：仅订单侧 `dimCustomer/customerStreet` 的 `street` 与 `getAuthorizedSoldToByPayer` 的 `street` 存在（值=北京市上镜互通大街），但粒度/语义为 `soldTo` 送达地址而非基础信息档案，且 `telephone` 全量为 null；财务客户主数据对本账号无记录且无页面权限） |
| 8 | contact_person | 负责人 | String | 页面不可见 | **无法采集**（核验日期 2026-09-20） | `/`（排查：`user/info` 的 `position`=null；`otcUser/getUserContactManner` 只回 `email`/`phone`，无姓名；`/user/profile` 仅账号资料，无负责人栏） |
| 9 | contact_phone | 负责人电话 | String | 页面不可见 | **无法采集**（核验日期 2026-09-20） | `/`（排查：`user/info` 的 `phone`=null、`otcUser/getUserContactManner.phone`=null；`customerStreet` / `getAuthorizedSoldToByPayer` 的 `telephone` 全量为 null） |
| 10 | producer_name_original | 厂家采集名称 | String | 页面不可见 | **无法采集**（核验日期 2026-09-20） | `/`（排查：全站无厂家/供应商档案入口；静态 chunk 关键词检索无命中） |
| 11 | producer_dep_original | 厂家合作部门 | String | 页面不可见 | **无法采集**（核验日期 2026-09-20） | `/`（排查：同上；全部动态路由中无合作部门类栏目） |
| 12 | producer_usc_code_original | 厂家采集统一社会信用代码 | String | 页面不可见 | **无法采集**（核验日期 2026-09-20） | `/`（排查：同上；全站无厂家侧统一社会信用代码字段） |
| 13 | platform_brand_id | 平台品牌ID | String | 页面不可见 | 系统生成 → 无需采集 | `/`（系统生成，前端传入） |
| 14 | distributor_usc_code_original | 经销商采集统一社会信用代码 | String | 页面不可见 | **无法采集**（核验日期 2026-09-20） | `/`（排查：全站唯一近似字段为财务客户主数据的 `customerInvoiceTaxNo`，但本账号无页面权限、且该表按 6182035/6182036 过滤 totalCount=0；`user/info` 及各枚举接口均无税号字段） |
| 15 | cooper_status | 合作状态 | String | 页面不可见 | **无法采集**（核验日期 2026-09-20） | `/`（排查：`dimCustomerAtom/getDealerType` 返回的是 20 个经销商**类型**字典值（历史经销商/白金经销商/…），非本客户当前合作状态值；`queryCustomerAtom` 中本账号记录的 `dealerType="白金经销商"` 属信控/配额板块客户层级主数据、字段名为 dealerType 非 cooperStatus，且该接口过滤参数全部无效（全量 4234 条），不采用） |
| 16 | tenant_name | 品牌租户名称 | String | 页面不可见 | **无法采集**（核验日期 2026-09-20） | `/`（排查：`otcConfig/getValue` 为配置字典，无 tenantName 项；全部已枚举接口无租户信息） |


## 待截图字段清单

| 字段编号 | 字段英文名 | 承载页（menu_path / route） | 页面列标题 / 位置 |
|---|---|---|---|
| 5 | distributor_name_original | 订单管理 > 下达订单 `/order/place` | 「请选择客户」下拉的选项文本 `[6182035]长沙市宏远商贸有限公司`（名称部分） |
| 5 | distributor_name_original | 订单管理 > 我的订单 `/order/reserved` | 表格「客户」列（值形如 `[6182035]长沙市宏远商贸有限公司`，名称部分） |
| 5 | distributor_name_original | 订单管理 > 我的订单 `/order/reserved` | 非表格列：登录后全局顶栏右侧用户名（显示「长沙市宏远商贸有限公司」） |
| 6 | distributor_code | 订单管理 > 下达订单 `/order/place` | 「请选择客户」下拉选项文本中方括号编号部分 `[6182035]` |
| 6 | distributor_code | 订单管理 > 我的订单 `/order/reserved` | 表格「客户」列值中方括号编号部分 `[6182035]` |



### 截图 1：订单管理 > 我的订单 `/order/reserved`

| 标注 | 位置（viewport 坐标，DPR=1） | 含义 |
|---|---|---|
| 红色矩形 | 左侧菜单 `(0,0,140,992)` | **采集路径**：侧边栏（订单管理菜单组） |
| 红色矩形 | 左侧菜单「我的订单」项 `(0,100,140,30)` | **采集路径**：`订单管理 > 我的订单`（当前激活菜单，本页即该板块载体页） |
| 红色矩形 | 顶栏 `(140,0,1780,50)` | **采集路径**：站点导航栏（订单管理 / 数据维护 / 当前登录身份） |
| 红色矩形 | 表头「客户」列 `(821,145,150,67)` | 字段编号 **5** `distributor_name_original` 的承载列（表头行定位；取值行为数据行） |
| **marker 5** | 指向 `(896,178)` | 字段编号 **5** `distributor_name_original`（「客户」列中 `[6182035]长沙市宏远商贸有限公司` 的**名称**部分） |
| 红色矩形 | 数据首行 `[6182035]` 前缀 `(829,272,71,22)` | 字段编号 **6** `distributor_code` 的页面形态（「客户」列值的方括号编号部分，非独立列） |
| **marker 6** | 指向 `(864,283)` | 字段编号 **6** `distributor_code`（值 `6182035`；页面以 `[6182035]` 前缀呈现） |
| 蓝色虚线框 | 顶栏右侧用户名 `(1684,19,198,21)` | 字段编号 **5** 的补充页面佐证：全局顶栏用户名「长沙市宏远商贸有限公司」（同名登录身份） |


### 未能完成的截图

| 目标 | 状态 | 说明 |
|---|---|---|
| 订单管理 > 下达订单 `/order/place`（「请选择客户」下拉 `[6182035]长沙市宏远商贸有限公司`） | **未落盘** | 见下方「notes / 遗留问题」第 2 条 |
| 首页 `/index` 客户对账单（「客户编码：6182035」「客户名称：长沙市宏远商贸有限公司」） | **未落盘** | 该页为 `/index` 默认首页（非待截图清单所列页），但实测可见字段 5/6 的独立标签形态，建议后续补拍 |

