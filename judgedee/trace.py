"""IP 与手机号的追踪：IP 归属地走公开接口，号码解析完全在本地做。

这一块把 GhostTrack 里「IP Tracker / Phone Tracker」的能力重写成了可被界面调用的
纯函数：函数只返回数据，不打印、不写文件。

- IP：先试 ip-api.com（免 key、字段全），失败再退 ipinfo.io；
- 手机号：用 phonenumbers 的离线号码库推算归属地、运营商、时区、号码类型，
  这个过程不联网，也不会把号码发给任何第三方。
"""

from __future__ import annotations

import ipaddress
from typing import Any
from urllib.parse import quote

IP_API_FIELDS = (
    "status,message,query,country,countryCode,region,regionName,city,zip,"
    "lat,lon,timezone,isp,org,as,mobile,proxy,hosting"
)
IP_API = "http://ip-api.com/json/{}?fields=" + IP_API_FIELDS
IPINFO_API = "https://ipinfo.io/{}/json"
MY_IP_API = "https://api.ipify.org/?format=json"
DEFAULT_TIMEOUT = 12.0
PHONE_DEFAULT_REGION = "CN"

# phonenumbers.PhoneNumberType 是整数枚举，这里按值翻译成中文
PHONE_TYPE_TEXT = {
    0: "固话",
    1: "手机",
    2: "固话或手机",
    3: "免费电话",
    4: "高费率号码",
    5: "分摊费用号码",
    6: "网络电话",
    7: "个人号码",
    8: "寻呼",
    9: "企业总机",
    10: "语音信箱",
    99: "未知",
}

USER_AGENT = "JudgeDee/1.0 (+https://github.com/L71615/judgedee)"


def _session(proxy: str | None):
    import requests

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
    if proxy:
        session.proxies.update({"http": proxy, "https": proxy})
    return session


def _get_json(url: str, proxy: str | None, timeout: float) -> dict[str, Any]:
    response = _session(proxy).get(url, timeout=timeout)
    response.raise_for_status()
    return response.json()


def normalize_ip(text: str) -> str:
    """去掉首尾空白、剥掉 IPv6 的方括号；非法就抛 ValueError。"""
    value = (text or "").strip().strip("[]")
    if not value:
        raise ValueError("请输入 IP 地址")
    return str(ipaddress.ip_address(value))


def _maps_url(latitude, longitude) -> str:
    if isinstance(latitude, (int, float)) and isinstance(longitude, (int, float)):
        return f"https://www.google.com/maps/@{round(latitude, 4)},{round(longitude, 4)},10z"
    return ""


def _fields_from_ipapi(data: dict) -> tuple[list[tuple[str, str]], str]:
    region = data.get("regionName") or data.get("region")
    latitude, longitude = data.get("lat"), data.get("lon")
    fields = [
        ("IP", str(data.get("query") or "—")),
        ("国家", str(data.get("country") or "—")),
        ("国家代码", str(data.get("countryCode") or "—")),
        ("地区", str(region or "—")),
        ("城市", str(data.get("city") or "—")),
        ("邮编", str(data.get("zip") or "—")),
        ("纬度", str(latitude if latitude is not None else "—")),
        ("经度", str(longitude if longitude is not None else "—")),
        ("时区", str(data.get("timezone") or "—")),
        ("ISP", str(data.get("isp") or "—")),
        ("组织", str(data.get("org") or "—")),
        ("ASN", str(data.get("as") or "—")),
        ("移动网络", "是" if data.get("mobile") else "否"),
        ("代理 / VPN", "是" if data.get("proxy") else "否"),
        ("机房 / 托管", "是" if data.get("hosting") else "否"),
    ]
    return fields, _maps_url(latitude, longitude)


def _fields_from_ipinfo(data: dict) -> tuple[list[tuple[str, str]], str]:
    latitude = longitude = None
    location = str(data.get("loc") or "")
    if "," in location:
        left, right = location.split(",", 1)
        try:
            latitude, longitude = float(left), float(right)
        except ValueError:
            latitude = longitude = None
    org = str(data.get("org") or "")
    asn = org.split(" ", 1)[0] if org.startswith("AS") else "—"
    fields = [
        ("IP", str(data.get("ip") or "—")),
        ("国家", str(data.get("country") or "—")),
        ("地区", str(data.get("region") or "—")),
        ("城市", str(data.get("city") or "—")),
        ("邮编", str(data.get("postal") or "—")),
        ("纬度", str(latitude if latitude is not None else "—")),
        ("经度", str(longitude if longitude is not None else "—")),
        ("时区", str(data.get("timezone") or "—")),
        ("组织", org or "—"),
        ("ASN", asn),
        ("主机名", str(data.get("hostname") or "—")),
    ]
    return fields, _maps_url(latitude, longitude)


def lookup_ip(ip: str, proxy: str | None = None, timeout: float = DEFAULT_TIMEOUT) -> dict[str, Any]:
    """查一个 IP 的归属地；返回 {"ok", "error", "fields", "maps", "source", "raw"}。"""
    try:
        target = normalize_ip(ip)
    except ValueError as exc:
        return {"ok": False, "error": f"IP 不合法：{exc}", "fields": [], "maps": "", "source": "", "raw": {}}

    errors: list[str] = []
    providers = (
        ("ip-api.com", IP_API.format(target), _fields_from_ipapi, lambda d: d.get("status") == "success"),
        ("ipinfo.io", IPINFO_API.format(target), _fields_from_ipinfo, lambda d: bool(d.get("ip"))),
    )
    for name, url, parser, ok_check in providers:
        try:
            data = _get_json(url, proxy, timeout)
        except Exception as exc:  # noqa: BLE001 - 换个数据源继续试
            errors.append(f"{name}: {type(exc).__name__}")
            continue
        if not ok_check(data):
            errors.append(f"{name}: {data.get('message') or '没有返回结果'}")
            continue
        fields, maps = parser(data)
        fields.append(("数据源", name))
        return {"ok": True, "error": "", "fields": fields, "maps": maps, "source": name, "raw": data}

    return {
        "ok": False,
        "error": "；".join(errors) or "查询失败",
        "fields": [],
        "maps": "",
        "source": "",
        "raw": {},
    }


def my_ip(proxy: str | None = None, timeout: float = 8.0) -> dict[str, Any]:
    """查本机出口 IP；只取地址本身，不多要别的字段。"""
    try:
        response = _session(proxy).get(MY_IP_API, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
        return {"ok": True, "ip": str(payload.get("ip") or ""), "error": ""}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "ip": "", "error": f"{type(exc).__name__}: {exc}"}


def map_link(address: str) -> str:
    """把地址/地名变成地图搜索链接（界面上的「在地图上看看」）。"""
    return "https://www.google.com/maps/search/" + quote(address or "")


def _phone_error(message: str) -> dict[str, Any]:
    return {"ok": False, "error": message, "fields": [], "e164": "", "valid": False, "region": ""}


def parse_phone(
    number: str, region: str = PHONE_DEFAULT_REGION, language: str = "zh"
) -> dict[str, Any]:
    """解析一个手机号 / 固定电话：归属地、运营商、时区、号码类型、各种格式。"""
    try:
        from . import phone_setup

        phone_setup.ensure_path()  # 打包版把号码库放在 vendor 目录里
    except Exception:  # noqa: BLE001 - 没有这个模块也不该挡路
        pass
    try:
        import phonenumbers
        from phonenumbers import carrier, geocoder, timezone
    except ImportError:
        return _phone_error("未安装号码库 phonenumbers，在「追踪」页点一键安装即可")

    text = (number or "").strip()
    if not text:
        return _phone_error("请输入手机号或固定电话")

    try:
        parsed = phonenumbers.parse(text, region or PHONE_DEFAULT_REGION)
    except Exception as exc:  # noqa: BLE001 - 解析失败就是输入有问题
        return _phone_error(f"号码解析失败：{exc}")

    e164 = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    valid = phonenumbers.is_valid_number(parsed)
    possible = phonenumbers.is_possible_number(parsed)
    region_code = phonenumbers.region_code_for_number(parsed) or "—"
    location = geocoder.description_for_number(parsed, language) or "—"
    operator = carrier.name_for_number(parsed, language) or "—"
    zones = ", ".join(timezone.time_zones_for_number(parsed)) or "—"
    number_type = PHONE_TYPE_TEXT.get(int(phonenumbers.number_type(parsed)), "未知")

    fields: list[tuple[str, str]] = [
        ("号码类型", number_type),
        ("是否有效", "有效" if valid else "无效"),
        ("格式合法", "是" if possible else "否"),
        ("国家 / 地区", region_code),
        ("归属地", location),
        ("运营商", operator),
        ("时区", zones),
        ("国际格式", phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL)),
        ("本地格式", phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.NATIONAL)),
        ("E.164", e164),
        ("国家码", str(parsed.country_code)),
        ("国内号码", str(parsed.national_number)),
    ]
    return {
        "ok": True,
        "error": "",
        "fields": fields,
        "e164": e164,
        "valid": valid,
        "region": region_code,
        "location": location,
        "operator": operator,
    }
