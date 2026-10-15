# 公共规则（全体 agent 共用）

## 字段采集规则

| # | 规则 | 说明 | 错误示例 | 正确示例 |
|---|------|------|---------|---------|
| 1 | **以标准字段为准** | 只匹配下方「标准字段定义」，接口/页面多余字段忽略 | 把所有字段写入文档 | 严格按标准字段逐行匹配 |
| 2 | **系统默认/固定值无法提取 → 无法采集** | 即使能推断默认值也不行 | `amount_unit` 推断为"元" | `amount_unit` → 无法采集 |
| 3 | **一对一原则** | 一个采集字段只能有一个获取来源，**不能一对多/多对一** | 两字段同取「客户名称」 | 各字段来源互不相同 |
| 4 | **编码一致性** | `distributor_code` 跨板块使用同一来源 | 基础信息用 `orgstructid`，订单用 `customercode` | 全部用同一业务编码 |
| 5 | **中文映射优先** | 状态/单位查找网站字典映射，找不到 → 无法采集 | `order_status` 写 "5" | `order_status` 写 "已交货"（5→已交货） |
| 6 | **原始字段名一字不改** | 记录接口/DOM 真实字段名与完整嵌套路径，不能改写成"好听"的命名风格 | 把 `soldToPartyName` 记成 `distributor_name` | 原样记 `soldToPartyName`，映射关系另写一列 |

## 数据捕获规则

| # | 规则 | 说明 |
|---|------|------|
| 7 | **禁止对未知接口 curl** | 只能通过浏览器页面导航触发自然请求；确需 curl 复用必须在文档中保留完整示例 |
| 8 | **SPA 点击，不 reload** | 已登录会话是单点、不可再生的，绝不 `navigate_page`/刷新页面；跳转一律用 SPA 点击/`select_frame`。本项目里这条规则同时是结构性约束：`mcp_client.py` 的 `disable_tools` 已经从 MCP 工具列表里移除了 `navigate_page`/`new_page`，你不会看到这两个工具，遇到卡住的页面不要试图绕过去。 |
| 9 | **HAR 备用** | 站点检测到自动化工具（MCP）时，请用户导出 HAR 文件替代 |
| 10 | **JS 调试器恢复** | 请求 `[pending]` 时反复暂停/恢复，或直接读响应体（MCP 可能已缓存） |
| 11 | **原始返回存档** | 每个板块的重要请求返回结果必须保存到 `files/` 目录（HTML/JSON/Excel），作为解析依据 |

## 执行与验证规则

| # | 规则 | 说明 |
|---|------|------|
| 13 | **登录鉴权方式识别** | 各系统登录后鉴权方式不同，必须识别并记录：Header Token / Cookie Session / 自定义参数。写入 `manifest.json` 的 `auth_method`/`auth_fields`，并体现在主文档「系统信息」表 |
| 14 | **数据返回方式识别** | 判断系统返回 **JSON API** 还是 **SSR HTML**：SSR 需 HTML 解析；SPA 需观察 XHR/Fetch 捕获 JSON。写入 `manifest.json` 的 `data_mode`，并体现在主文档「系统信息」表 |
| 15 | **复合字段先判断能否派生** | 不能直接下"不存在"的结论，先看能否从已有字段计算/拼接得到 |
| 16 | **"不可采集"结论必须附排查清单 + 核验日期** | 字段级写进分片文档的字段表（采集规则列写「无法采集」+ 排查过程），并在 `EvidenceTable` 里为该字段**留空 `path`**、`mapped_to` 仍填该标准字段名——**不要用 `/`、`-`、`N/A` 之类占位符填 `path`**（schema 校验会直接拒绝，因为 `path` 是取值路径，占位符会被一致性检查读成"一个路径对应多个字段"）；需要人工拍板的字段级疑难按规则 18 填 `deferred_questions`。**manifest 里没有 `unsupported` 这个字段**，不要往那里写。整张表不存在则判本设计的 `existence: absent`，同样写清排查过程 |
| 17 | **截图证据只能来自只读页面** | 误入编辑/表单页要先取消退出，再重新截图 |
| 18 | **需要人工拍板的问题写进 `deferred_questions`，不能只写进 Markdown** | 你自己判不了、必须人工看一眼才能继续的问题（存在性存疑、跨表字段归属冲突等），除了在分片文档里叙述来龙去脉，**必须**同时把它写成一句自包含的问句，填进 `structured_output`（`TableVerdict`/`EvidenceTable`）的 `deferred_questions` 列表——只有这个字段会被收进 `questions.md` 真正问到人，写在 Markdown 正文里的「待人工确认」之类小节不会被任何代码读取。已经在文档里写明是"已裁定"的问题不要再放进这个列表 |

（规则 13/14 在本架构下主要由 Discovery 承担并写入 `manifest.json` 的
`auth_method`/`auth_fields`/`data_mode`——业务 agent 通常不需要重新判断，
除非 Discovery 遗漏。）

> **关于缺失的规则 12**：规则编号里没有 12，不是漏抄。原「规则 12（逐表串行执行）」
> 已删除——串行/并发由 `orchestrator.py` 的状态流转加浏览器叫号接管，不再要求 agent
> 自己遵守。其余编号保持不变，以免打断既有交叉引用（规则 3、8、16、18 等）。

---

# 字段的页面形态（决定字段表怎么写）

> **截图标注不在你这一段做。** 截图与标注已经拆成独立的阶段三，由专门的截图 agent
> 在**人工审核确认字段映射之后**才跑（规则见 `prompts/screenshot_rules.md`）。
> 你现在只需要在字段表里写清每个字段的页面形态（页面可见 / 接口独有 / 系统生成或
> 无法采集）——「页面可见」的字段稍后由截图 agent 按你写下的字段编号去标注。
> 不要调用 `take_screenshot` / `annotate_screenshot`，也不要在文档里编造截图路径。

## 接口字段说明方式（页面无体现字段）

> 适用于**接口返回、页面无对应展示**的字段（SSR HTML 未渲染、JSON 响应独有字段）。此类字段**不截图标注**，直接在字段表与采集说明中描述字段来源与映射，**字段不能因页面无展示而省略或漏填**。

```markdown
字段采集表（字段来源列写接口路径）：
| 字段英文名 | 字段中文名 | ... | 字段来源 |
| order_status | 订单状态 | ... | API列表：`kx_order[].status_text`（status="90"→已完成） |

采集说明：
> **接口独有字段**：`order_status` 等字段由接口返回、页面无独立展示，采集时直接从 API 响应解析，与截图标注无关。
```

> **字段表每条记录必须满足三选一（必选其一，不可留空）**：
> - **页面可见** → 字段来源写「见截图（第 N 张，`<列标题>` 列）+ SSR：… / API：…」，
>   并在下方「待截图字段清单」里列出它，供阶段三的截图 agent 照单标注
> - **接口独有** → 字段来源写接口路径（`API{n}: resp_data.<实体>.<字段>`），采集说明补充映射
> - **系统生成 / 无法采集** → 系统生成 → 无需采集，前端传入；无法采集 → `/`

## 待截图字段清单（交给阶段三）

分片文档里必须有这么一节，把**页面可见**的字段挑出来，写清它在哪个页面、哪一列。
截图 agent 拿到的就是这份清单加你的字段表，它不会重新判断哪些字段该标：

```markdown
## 待截图字段清单

| 字段编号 | 字段英文名 | 承载页（menu_path / route） | 页面列标题 |
|---|---|---|---|
| 4 | distributor_name_original | 订单管理 > 我的订单 `/order/reserved` | 送达方 |
| 6 | order_no | 订单管理 > 我的订单 `/order/reserved` | 订单编号 |
```

页面可见字段为 0 的表（字段全是接口独有 / 无法采集）写「无页面可见字段，无需截图标注」，
阶段三的截图 agent 读到后直接返回 `skipped=true`、不截图。

---

# 原始返回存档（files/）

> 目标：将每张表**重要请求的返回结果**保存为原始文件（HTML/JSON/Excel），供后续采集与解析开发直接复用（不再依赖抓包）。

## 文件命名规范

**文件名必须以你自己的表名加下划线开头**，后面接板块与序号：

```
{本表名}_{板块名称}_{序号}.{ext}

例（假设你负责 dms_order_details_info）：
- dms_order_details_info_列表页_0.html
- dms_order_details_info_详情页_1.html
- dms_order_details_info_列表接口_0.json
- dms_order_details_info_导出_2026-08-01至08-13.xlsx   # 导出 Excel（含日期区间）
```

这个前缀不是美观要求：`files/` 是所有表共用的目录，前缀是本轮中断后
下一轮据以认出「哪些存档是这张表的」的唯一依据。写别的名字会被
`write_file` 直接拒绝，下一轮也找不回来。

## 各类型存档方法

> `mcp__JSReverser-Strong-MCP__evaluate_script` 只有 `function` 一个参数，**没有 `outputFile`**——返回值会作为工具调用结果回传给你，落盘要用你工具面里的 `write_file` 工具另外写一次，不要凭空假设这个 MCP 能直接写文件。`write_file` 接受 `relative_path`（只能是 `tables/<本表名>.md`，或以 `files/<本表名>_` 开头的存档文件，相对本平台目录，不带 `handbook/dms-sa/<平台名>/` 前缀）、`content`、`encoding`（`utf-8` 或 `base64`）。配套的 `read_file` 读回同样范围内的文件，参数是 `relative_path` 和 `encoding`。

**SSR HTML 页面存档**：
```js
// 1. evaluate_script 取回渲染后 DOM
mcp__JSReverser-Strong-MCP__evaluate_script(
  function="() => document.documentElement.outerHTML"
)
// 2. 把返回的字符串原样用 write_file 存到 files/<本表名>_列表页_0.html
write_file(relative_path="files/<本表名>_列表页_0.html", content="<返回的字符串>", encoding="utf-8")
```

**JSON API 响应存档**（SPA 平台）：
```js
// 1. evaluate_script 里用 fetch 取接口响应
mcp__JSReverser-Strong-MCP__evaluate_script(
  function="async () => { const r = await fetch('<api_url>', {headers:{'token':'<ACCESS_TOKEN>'}}); return await r.json(); }"
)
// 2. 把返回的 JSON 用 write_file 存到 files/<本表名>_列表接口_0.json
write_file(relative_path="files/<本表名>_列表接口_0.json", content="<返回 JSON 的字符串形式>", encoding="utf-8")
```

**Excel 导出存档**（导出按钮 / exportExcel 接口）：
```js
// 1. evaluate_script 里 fetch 导出接口，取回 base64 字符串
mcp__JSReverser-Strong-MCP__evaluate_script(
  function="async () => { const r = await fetch('<export_api_url>'); const buf = await r.arrayBuffer(); return btoa(String.fromCharCode(...new Uint8Array(buf))); }"
)
// 2. 把返回的 base64 字符串直接用 write_file 写入，encoding 设为 base64——工具会先解码再落盘，
//    不需要先存一份 base64 文本再手动解码
write_file(relative_path="files/<本表名>_导出_2026-08.xlsx", content="<返回的 base64 字符串>", encoding="base64")
```

## 文档存档清单

每张表分片文档必须包含「存档文件」表：

```markdown
**存档文件**：

| 文件 | 路径 |
|------|------|
| 列表页 HTML 存档 | [files/<本表名>_列表页_0.html](../files/<本表名>_列表页_0.html) |
| 导出 Excel | [files/<本表名>_导出_2026-08-01至08-13.xlsx](../files/<本表名>_导出_2026-08-01至08-13.xlsx) |
```

## 表级文档产出（tables/<表名>.md）

> 结构化的 `existence`/`fields` 判定走 `structured_output`（`TableVerdict`/`EvidenceTable`），
> 不经过 `write_file`；但 Judge 的一致性自检（`check_negation_conflict` 等）和最终合稿都要读
> 这张表的**自然语言分片文档**，这份文档只能靠你自己在完成判定（以及 `existence` 为
> `exists`/`partial` 时的字段映射）之后主动用 `write_file` 写出，没有其它机制会替你生成它。

字段映射（或 `absent`/`granularity_mismatch` 判定）完成后，把本节及上方「待截图字段清单」
「原始返回存档」「重要请求 curl 保留」几节要求的内容整理成一份 Markdown，调用：

```
write_file(relative_path="tables/<表名>.md", content="<完整 Markdown 正文>", encoding="utf-8")
```

`existence` 为 `absent`/`granularity_mismatch`/`pending_human` 时也要写这份文档，只是内容简化为
结论 + 排查过程（规则 16），不需要字段表、待截图清单、存档清单这几节。

**这份文档是给人工审核看的草稿**：人工确认字段映射之后，阶段三的截图 agent 会读回它、
把截图小节补上再写回。所以截图小节你只留占位，原样写下面这一段，不要自己编图片路径：

```markdown
## 截图标注说明

> 待人工确认字段映射后，由阶段三截图 agent 补充。待标注字段见上方「待截图字段清单」。
```

## 重要请求 curl 保留

每张表核心请求必须以 **curl 形式内嵌分片文档**（不单独存文件），包含完整 Header/Cookie/Token：

```bash
curl -s 'https://<domain>/<api路径>?<参数>' \
  -H 'User-Agent: Mozilla/5.0 ... Chrome/151.0.0.0 Safari/537.36' \
  -H 'Accept: application/json, text/plain, */*' \
  -H 'token: <ACCESS_TOKEN>' \
  --compressed
```

---

# 故障处理速查

| 症状 | 解决 |
|------|------|
| API 请求全部 `[pending]` | 反复暂停/恢复调试器（可能需要多次） |
| 站点检测到自动化工具（MCP）/ 页面异常 | 请用户手动操作，导出 HAR 文件替代 |
| 点击菜单无反应 | `select_frame` 检查 iframe |
| 浏览器进程被杀 | `select_page` 重连（`new_page` 已在本项目禁用，见规则 8） |
| 导出的 Excel 无法解析 | 检查是否 JSON 包裹（去引号）、PK 魔数 `\x50\x4B\x03\x04` |
| HTML 存档是 JSON 字符串 | 解码：`json.loads` 后写回纯 HTML |
| 系统无合同/认证功能 | 判 `existence: absent`，不写字段采集表，仅强调板块不存在 |
| 登录后 API 鉴权失败 | 检查鉴权方式是否正确识别（Header vs Cookie vs CSRFToken） |
