"""
公司名称规范化：
- 统一常见别称（字节/腾讯/百度等）为约定中文全称。
- **阿里巴巴系**：标题或正文出现「淘宝/天猫/菜鸟/阿里云/蚂蚁」等时，不得笼统写成「阿里巴巴」；
  无更细线索时集团向内容仍可用「阿里巴巴」。
- 公司为空时，可根据帖子标题（或题目摘要）做轻量推断。

入库：question_extractor / two_stage `_normalize_question_item` 调用 `normalize_company_field`。
全库批处理：`python -m backend.scripts.normalize_companies apply`。
"""
from __future__ import annotations

import re
import unicodedata
from typing import List, Tuple

# 先匹配子公司/具体业务（含其他大厂），再匹配「阿里巴巴」集团名（同长度时子公司条目应排在前列）
_SUBSIDIARY_AND_PEER_RULES: List[Tuple[str, str]] = [
    ("阿里云智能", "阿里云"),
    ("阿里巴巴云", "阿里云"),
    ("alibaba cloud", "阿里云"),
    ("阿里云", "阿里云"),
    ("平头哥半导体", "平头哥半导体"),
    ("平头哥", "平头哥半导体"),
    ("达摩院", "达摩院"),
    ("菜鸟网络", "菜鸟"),
    ("菜鸟", "菜鸟"),
    ("cainiao", "菜鸟"),
    ("蚂蚁金服", "蚂蚁集团"),
    ("蚂蚁集团", "蚂蚁集团"),
    ("ant group", "蚂蚁集团"),
    ("蚂蚁", "蚂蚁集团"),
    ("淘天集团", "淘天集团"),
    ("淘天", "淘天集团"),
    ("天猫", "天猫"),
    ("tmall", "天猫"),
    ("淘宝", "淘宝"),
    ("taobao", "淘宝"),
    ("饿了么", "饿了么"),
    ("ele.me", "饿了么"),
    ("口碑", "口碑"),
    ("盒马鲜生", "盒马"),
    ("盒马", "盒马"),
    ("飞猪", "飞猪"),
    ("fliggy", "飞猪"),
    ("闲鱼", "闲鱼"),
    ("钉钉", "钉钉"),
    ("dingtalk", "钉钉"),
    ("高德地图", "高德地图"),
    ("高德", "高德地图"),
    ("amap", "高德地图"),
    ("阿里健康", "阿里健康"),
    ("优酷", "优酷"),
    ("youku", "优酷"),
    ("阿里大文娱", "阿里大文娱"),
    ("灵犀互娱", "灵犀互娱"),
    ("1688", "1688"),
    ("淘特", "淘特"),
    ("lazada", "Lazada"),
    ("字节跳动", "字节跳动"),
    ("bytedance", "字节跳动"),
    ("抖音", "抖音"),
    ("tiktok", "TikTok"),
    ("今日头条", "今日头条"),
    ("腾讯云", "腾讯云"),
    ("腾讯音乐", "腾讯音乐"),
    ("qq音乐", "QQ音乐"),
    ("微信", "微信"),
    ("weixin", "微信"),
    ("wechat", "微信"),
    ("腾讯", "腾讯"),
    ("tencent", "腾讯"),
    ("百度", "百度"),
    ("baidu", "百度"),
    ("美团", "美团"),
    ("meituan", "美团"),
    ("京东", "京东"),
    ("jd.com", "京东"),
    ("拼多多", "拼多多"),
    ("pinduoduo", "拼多多"),
    ("快手", "快手"),
    ("kuaishou", "快手"),
    ("小红书", "小红书"),
    ("rednote", "小红书"),
    ("哔哩哔哩", "哔哩哔哩"),
    ("bilibili", "哔哩哔哩"),
    ("b站", "哔哩哔哩"),
    ("华为", "华为"),
    ("huawei", "华为"),
    ("荣耀", "荣耀"),
    ("honor", "荣耀"),
    ("小米", "小米"),
    ("xiaomi", "小米"),
    ("滴滴", "滴滴"),
    ("didi", "滴滴"),
    ("网易", "网易"),
    ("netease", "网易"),
    ("携程", "携程"),
    ("ctrip", "携程"),
    ("新浪", "新浪"),
    ("微博", "微博"),
    ("爱奇艺", "爱奇艺"),
    ("iqiyi", "爱奇艺"),
    ("理想汽车", "理想汽车"),
    ("蔚来", "蔚来"),
    ("小鹏", "小鹏"),
    ("shein", "SHEIN"),
]

# 集团/控股名（仅当上面未命中时使用）
_PARENT_ALI_RULES: List[Tuple[str, str]] = [
    ("阿里巴巴集团", "阿里巴巴"),
    ("alibaba group", "阿里巴巴"),
    ("阿里巴巴", "阿里巴巴"),
    ("alibaba", "阿里巴巴"),
]

# 关键词长度降序；同长度时子公司/业务规则（_s1）排在集团规则（_s2）之前
_s1 = sorted(_SUBSIDIARY_AND_PEER_RULES, key=lambda x: -len(x[0]))
_s2 = sorted(_PARENT_ALI_RULES, key=lambda x: -len(x[0]))
# 长词优先：合并后再次按长度降序，同长度时子公司列表优先（在 _s1 中的先于 _s2）
_all_rules = _s1 + _s2
_TITLE_RULES_ORDERED = sorted(_all_rules, key=lambda x: (-len(x[0]), _all_rules.index(x)))


# 整串别称（不含单独「阿里」，单独在逻辑里处理）
_CANONICAL_EXACT: dict[str, str] = {
    "字节": "字节跳动",
    "字節": "字节跳动",
    "字节跳动有限公司": "字节跳动",
    "bytedance": "字节跳动",
    "腾讯公司": "腾讯",
    "tencent": "腾讯",
    "深圳市腾讯": "腾讯",
    "阿里巴巴中国": "阿里巴巴",
    "淘天": "淘天集团",
    "菜鸟网络科技": "菜鸟",
    "蚂蚁金服": "蚂蚁集团",
    "蚂蚁科技": "蚂蚁集团",
    "alibaba": "阿里巴巴",
    "阿里巴巴集团": "阿里巴巴",
    "taobao": "淘宝",
    "tmall": "天猫",
    "cainiao": "菜鸟",
}

_ALI_PARENT_CANONICAL = frozenset(
    {
        "阿里巴巴",
        "阿里巴巴集团",
        "Alibaba",
        "Alibaba Group",
        "alibaba",
    }
)

_FORBIDDEN_VAGUE = frozenset({"大厂", "互联网公司", "某公司", "xx公司", "互联网大厂"})


def _strip_cf(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", str(s)).strip()
    s = re.sub(r"\s+", " ", s)
    return s


def infer_company_from_text(text: str) -> str:
    """从标题或短文本推断公司；无法判断时返回 ""。长关键词优先。"""
    t = _strip_cf(text)
    if not t:
        return ""
    tl = t.lower()
    for needle, canonical in _TITLE_RULES_ORDERED:
        if needle.lower() in tl or needle in t:
            return canonical
    return ""


def normalize_company_field(
    company: str,
    *,
    post_title: str = "",
    hint_text: str = "",
) -> str:
    """
    归一化单条 company。
    - post_title: 帖子标题（优先用于阿里系细分与补全）
    - hint_text: 额外线索（如题目正文前若干字），在标题无结果时使用
    """
    raw = _strip_cf(company)
    if raw and any(v in raw for v in _FORBIDDEN_VAGUE):
        raw = ""

    inferred = infer_company_from_text(post_title)
    if not inferred:
        inferred = infer_company_from_text((hint_text or "")[:1200])

    # 单独「阿里」暂不映射成集团，先看标题能否细分
    raw_lc = raw.lower()
    if raw_lc in ("阿里", "ali") or raw == "阿里":
        if inferred:
            return inferred
        return "阿里巴巴"

    if not raw:
        return inferred or ""

    if raw_lc in _CANONICAL_EXACT:
        raw = _CANONICAL_EXACT[raw_lc]

    # 已是集团名，但标题能识别更细主体 → 用细分名
    if raw in _ALI_PARENT_CANONICAL or raw == "阿里巴巴":
        if inferred and inferred != "阿里巴巴":
            return inferred
        return "阿里巴巴"

    if raw == "阿里巴巴" and inferred == "阿里巴巴":
        return "阿里巴巴"

    # 其他已填具体名，若与标题强烈冲突（少见）：保留已填值
    return raw


def normalize_company_for_row(
    company: str,
    post_title: str,
    question_text: str = "",
) -> str:
    """供批处理脚本：标题 + 题干作线索。"""
    return normalize_company_field(
        company, post_title=post_title or "", hint_text=question_text or ""
    )
