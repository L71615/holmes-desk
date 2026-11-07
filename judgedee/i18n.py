"""界面双语：中文原文即键，英文查表。

设计上故意不用 gettext：界面文案都写在控件里，用「中文原文 → 英文」的字典做映射，
没收录的条目自动回落到中文，不会出现空字符串或 key 名泄漏。

切换语言需要重启窗口（Tk 控件建好之后再改文案很麻烦），设置页里会提示这一点。
"""

from __future__ import annotations

LANGS = ("zh", "en")
LANG_LABELS = {"zh": "中文", "en": "English"}

_current = "zh"

# 中文原文 → English
CATALOG: dict[str, str] = {
    # 顶部导航与状态栏
    "检索": "Search",
    "追踪": "Trace",
    "图谱": "Graph",
    "站点库": "Sites",
    "历史": "History",
    "设置": "Settings",
    "就绪": "Ready",
    "本地单机": "Local only",
    "站点库：": "Sites: ",
    # 检索页
    "用户名": "Username",
    "站点预设": "Site preset",
    "站点（留空 = 全部站点，可手填）": "Sites (blank = all, comma separated)",
    "附加站点（可选，逗号分隔）": "Extra sites (optional)",
    "多个用户名用空格或逗号分隔；填 {?} 会自动展开成 _ - . 三种变体": (
        "Separate usernames with spaces or commas; {?} expands to _ - . variants"
    ),
    "代理": "Proxy",
    "超时（秒）": "Timeout (s)",
    "包含 NSFW 站点": "Include NSFW",
    "结果里显示未注册": "Show unregistered",
    "自查模式（只查我，个人信息打码）": "Self-check (only me, mask personal info)",
    "导出": "Export",
    "结果目录": "Output folder",
    "浏览…": "Browse…",
    "开始检索": "Start",
    "停止": "Stop",
    "复核已注册": "Re-verify",
    "身份分析": "Analyze identity",
    "换名同人": "Aliases",
    "变体扫查": "Variant sweep",
    "人物看板": "Persona",
    "导出报告": "Export report",
    "打开结果目录": "Open folder",
    "筛选": "Filter",
    "清空": "Clear",
    "站点范围": "Site scope",
    "勾选分组或单个站点；一个都不勾 = 用右边的站点框": (
        "Tick groups or sites; tick nothing = use the box on the right"
    ),
    "全选": "All",
    "已选": "Selected",
    "站": "sites",
    "命中": "hits",
    "显示": "shown",
    "条": "rows",
    "个命中": "hits",
    "用时": "took",
    "秒": "s",
    # 结果表列
    "状态": "Status",
    "档案": "Persona",
    "来源": "Source",
    "复核": "Verified",
    "链接": "Link",
    "耗时": "Took",
    "值": "Value",
    "字段": "Field",
    # 状态文案
    "已注册": "Registered",
    "未注册": "Not found",
    "未知": "Unknown",
    "格式不符": "Bad format",
    "被拦截": "Blocked",
    "复核通过": "Confirmed",
    "存疑": "Suspect",
    # 追踪页
    "IP 归属地": "IP location",
    "手机号归属地": "Phone location",
    "查询": "Look up",
    "我的 IP": "My IP",
    "解析": "Parse",
    "打开地图": "Open map",
    "复制全部": "Copy all",
    "复制 E.164": "Copy E.164",
    "IP 查询完成": "IP lookup done",
    "号码解析完成": "Phone parse done",
    # 图谱页
    "重新布局": "Re-layout",
    "只看强证据": "Strong only",
    "显示全部证据": "Show all evidence",
    "隐藏弱证据": "Hide weak",
    "显示弱证据": "Show weak",
    "合并为同一人": "Merge as one",
    "标记为不同人": "Mark different",
    "清除该对约束": "Clear constraint",
    "选中节点": "Selected node",
    "没有选中节点。": "Nothing selected.",
    "底色＝同一档案 · 圈大＝证据强 · 深蓝实线＝强证据": (
        "Halo = one persona · bigger dot = stronger evidence · solid blue = strong link"
    ),
    # 站点库
    "新增站点": "New site",
    "导入…": "Import…",
    "导出…": "Export…",
    "编辑": "Edit",
    "启用 / 禁用": "Enable / disable",
    "恢复内置": "Reset built-in",
    "删除自定义站点": "Delete custom",
    "备注": "Label",
    "分组": "Group",
    "URL 模板": "URL template",
    "全部": "All",
    # 历史
    "刷新": "Refresh",
    "删除选中": "Delete selected",
    "清空历史": "Clear history",
    "和上一次对比": "Compare with previous",
    "时间": "Time",
    "站点数": "Sites",
    "导出目录": "Export folder",
    "这次的结果": "Results of this run",
    # 设置
    "检索默认值": "Search defaults",
    "默认导出": "Default export",
    "默认包含 NSFW 站点": "Include NSFW by default",
    "默认显示未注册结果": "Show unregistered by default",
    "保存设置": "Save settings",
    "我的用户名": "My username",
    "检索页默认勾上「自查模式」": "Tick self-check by default",
    "语言": "Language",
    "界面语言（重启后生效）": "UI language (restart to apply)",
    "数据": "Data",
    "站点表": "Site table",
    "用户配置": "User config",
    "历史库": "History DB",
    "打开配置目录": "Open config folder",
    "关于": "About",
    "打开项目主页": "Open project page",
    "查看许可": "View license",
    # 对话框
    "身份档案 · 证据视图": "Identity records · evidence",
    "换名同人建议": "Alias suggestions",
    "人物看板 · 详情": "Persona details",
    "两次检索对比": "Compare two runs",
    "关闭": "Close",
    "复制摘要": "Copy summary",
    "复制线索": "Copy clues",
    "查一下并加入": "Look up & add",
    "打开账号 A": "Open account A",
    "打开账号 B": "Open account B",
    "打开链接": "Open link",
    "线索": "Clues",
    "昵称": "Name",
    "邮箱": "Email",
    "即时通讯": "Messaging",
    "个人站点": "Website",
    "一句话结论": "Summary",
    "类别覆盖": "Category coverage",
    "各站说法不一致": "Conflicting details",
    # 身份档案窗口
    "身份档案": "Identity records",
    "档案与账号": "Records & accounts",
    "档案 / 站点": "Record / site",
    "证据": "Evidence",
    # 人物看板线索卡
    "贴一个 IP 或手机号（带 +86 更准），解析结果会记在这张卡上，也会进报告。": (
        "Paste an IP or phone number (include +86 for accuracy); results land on this card and in the report."
    ),
    "先贴一个 IP 或手机号": "Paste an IP or phone number first",
    "解析中…": "Parsing…",
    "还没有可对外核实的线索（主页没公开邮箱 / IM / 外链）": (
        "No verifiable clues yet (the profile shows no email / IM / website)"
    ),
    "已复制到剪贴板": "Copied to clipboard",
    "线索已复制到剪贴板": "Clues copied to clipboard",
    "复制失败": "Copy failed",
    "还没有线索可复制": "Nothing to copy yet",
    # 站点库对话框
    "NSFW 站点": "NSFW site",
    "保存": "Save",
    "取消": "Cancel",
    "启用": "Enabled",
    "这是内置站点：改动会作为覆盖保存在用户配置里，可随时「恢复内置」。": (
        "Built-in site: changes are stored as an override in your config and can be reset anytime."
    ),
    # 检索页动态文案
    "命中 0 个": "0 hits",
    "已选 0 站": "0 sites selected",
    "深入主页（跟进简介里的同站链接）": "Deep profile (follow same-site links)",
    # 设置页反馈
    "保存失败": "Save failed",
    "设置已保存": "Settings saved",
    # 追踪页
    "IPv4 / IPv6 的国家、城市、经纬度、运营商与机房标记；不记录查询历史。": (
        "Country, city, coordinates, ISP and hosting flags for IPv4 / IPv6; queries are not logged."
    ),
    "填一个 IP 回车，或点「我的 IP」查自己": "Type an IP and press Enter, or use “My IP”",
    "一键安装号码库（约 2.5 MB）": "Install number DB (~2.5 MB)",
    "正在下载并安装 phonenumbers，稍等十几秒…": "Downloading phonenumbers, this takes a few seconds…",
    "安装中…": "Installing…",
    "重试安装": "Retry install",
    "带国家码更准，例如 +86 138 0013 8000": "Include the country code, e.g. +86 138 0013 8000",
    "离线解析：归属地、运营商、时区、号码类型；号码不会发往任何服务器。": (
        "Offline: region, carrier, time zone and type; the number never leaves your machine."
    ),
    "聚类以「用户名相同」为前提，所以不同名字之间再像也不会被自动并档。选中一行点「合并为同一人」，会写进 constraints.json 并立即重新聚类。": (
        "Clustering assumes the same username, so different names are never merged automatically. "
        "Pick a row and hit “Merge as one” — it writes to constraints.json and re-clusters immediately."
    ),
}


def current() -> str:
    return _current


def set_language(code: str) -> None:
    global _current
    _current = code if code in LANGS else "zh"


def t(text: str) -> str:
    """中文原文 → 当前语言文案；没收录就原样返回。"""
    if _current == "zh":
        return text
    return CATALOG.get(text, text)


def is_en() -> bool:
    return _current == "en"


# 第二批：应用名、分组名、若干表头
CATALOG.update(
    {
        "JudgeDee 人物情报": "JudgeDee",
        "站点": "Site",
        "常用": "Common",
        "开发 / 代码": "Dev / code",
        "安全 / CTF": "Security / CTF",
        "社交 / 社区": "Social / community",
        "游戏": "Games",
        "影音 / 创作": "Media / creative",
        "未分组": "Ungrouped",
        "全部站点": "All sites",
        "多个用户名用空格或逗号分隔；填 {?} 会自动展开成 _ - . 三种变体": (
            "Separate usernames with spaces or commas; {?} expands to _ - . variants"
        ),
    }
)


def t_group(name: str) -> str:
    """分组名：英文模式下查表，其余原样返回。"""
    return CATALOG.get(name, name) if _current == "en" else name
