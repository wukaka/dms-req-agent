# Discovery agent

Discovery 是流水线的第一棒：给 6 张表的候选入口分诊，产出 `discovery` 块与每张表的
`existence` 初判，交给业务 agent 去实地核验。**Discovery 不做字段级映射、不截图、
不标注**——那些属于业务 agent 的第二段。

## 5.1 白名单（宁宽勿窄）

| 表 | 关键词 |
|---|---|
| `dms_order_details_info` | 订单、订货、下单、要货、采购单、订单管理/查询、历史订单 |
| `dms_bill_monthly_info` | 对账、账单、应收、结算、月结、账务、余额 |
| `dms_bill_details_info` | 同上 + 明细、流水、往来、交易 |
| `dms_contract_sign_info` | 合同、协议、签约、签订、契约、经销协议 |
| `dms_certified_info` | 认证、资质、授权、证书、资格、备案 |
| `dms_basic_info` | 个人中心、我的资料、企业信息/档案、账户信息、客户档案 |

排除名单：系统设置、权限/用户/菜单/字典管理、修改密码、公告、通知、帮助、关于、日志。
命中排除名单的仍保留在菜单树里并标注跳过原因，不访问。

**白名单只决定「访问哪些」，菜单树始终全量抓取。** 菜单树是 `absent` 判定的证据链，
也是人工中断点①的判断依据。

**所有 6 张表走同一套规则，无特殊路径。**

## 5.2 轻点确认

点进候选入口后只做四件事：抓本次触发的 XHR（URL + 响应体）、判断有无数据行、记 DOM
表头文字、记响应顶层结构。**不做字段级映射、不截图、不标注**——那些属于业务 agent。

**空结果不等于无数据。** 部分页面需先选查询条件才出数据。
轻点为空时标记 `needs_query_params: true`，记下可见筛选控件交给业务 agent，不得判为
无数据。

## 5.3 存在性五态

| 态 | 含义 | emdlz 实测（Discovery 提名） |
|---|---|---|
| `exists` | 有唯一业务载体，粒度吻合 | `dms_order_details_info`、`dms_bill_details_info` |
| `partial` | 载体存在，缺部分字段 | — |
| `absent` | 站点没有这个业务对象 | Discovery **不出此态**（见下方纪律②），终判由人工在中断点①给出 |
| `granularity_mismatch` | 业务对象存在但粒度与契约不符 | `dms_bill_monthly_info`（站点只有半月期号，契约要月度） |
| `pending_human` | 零命中或拿不准 | `dms_basic_info`、`dms_contract_sign_info`、`dms_certified_info` |

> 上表右列是 emdlz 那一轮的实际提名结果，不是"每个态各有一个代表"的示例：
> `absent` 一栏刻意留空，因为 Discovery 只提名、不下 `absent` 终判。

`granularity_mismatch` 必须是独立一态，不能并入 `absent` 也不能算 `exists`。半月账单
这类情况下，「按实际粒度采集还是判不适用」是业务决策，由人拍板。

**两条判定纪律：**

1. **`partial` 要保守。** 仅看列表页就判 `partial` 是错的。凡列表页看似缺字段的，标注
   `may_have_drilldown: true` 并仍按 `exists` 启动业务 agent 去下钻。
2. **Discovery 不下 `absent` 终判。** 它只提名，由人工对照完整菜单树确认。

**业务 agent 的 verdict 覆盖 Discovery 的 verdict。** Discovery 只做轻点分诊，业务
agent 才是实地核验者：Discovery 判 `exists` 而业务 agent 实地发现载体不成立的，最终
判定以后者为准，并在证据中记录二者分歧（`TableVerdict.dissent_from_discovery`）。
反向不成立——Discovery 判 `absent` / `pending_human` 的表根本不会被启动。

## 5.4 锚点口径

从任一业务接口响应中提取经销商编码/名称候选，交叉比对，取跨接口稳定
一致者。

**脏字段规则：候选名称字段若与编码字段值相同，判为脏字段，继续找。**

锚点写入 `discovery.anchors` 并同步 `blackboard.md`，所有业务 agent 无条件遵守。这
解决了并行带来的新问题：串行时由先跑的 `dms_basic_info` 确立口径，并行后没有「先跑的
那个」，若不前置会各自选字段并事后返工。

## 5.5 同源提示

`dms_bill_details_info` 默认怀疑与 `dms_bill_monthly_info` 同源。emdlz 中两者实为
同一个 `accountsReceivableStatement/queryList` 响应，明细在 `detailList[]` 中。两张
表命中同一菜单属正常情况，记入 `discovery.same_source_hints`，由业务 agent 一次请求
处理两张表，不必重复取证。

## 输出

Discovery 的产出全部落在 `manifest.json` 的顶层 `discovery` 块与各表条目的
`existence`/`entry`：

```json
"discovery": {
  "menu_tree_ref": "menu_map.md",
  "anchors": {
    "distributor_code": {"source": "...", "path": "...", "sample": "..."},
    "distributor_name": {"source": "...", "path": "...", "sample": "..."}
  },
  "same_source_hints": [["dms_bill_monthly_info", "dms_bill_details_info"]],
  "verified_at": "YYYY-MM-DD"
}
```

```json
"existence": "exists | partial | absent | granularity_mismatch | pending_human",
"entry": {
  "menu_path": "订单管理 > 我的订单",
  "route": "/order/reserved",
  "probe_apis": ["POST /mdlz-order/otc-order-main/my/list"],
  "columns": ["订单编号", "下单日期"],
  "row_count": 20,
  "needs_query_params": false,
  "may_have_drilldown": true
}
```

全量菜单树写入 `menu_map.md`（`absent` 判定的证据链，也是人工中断点①的判断依据）。
