# -*- coding: utf-8 -*-
"""北建大兴校区 · 生活服务可达性地图（移动端优先）"""
import json
import math
import os
import re
import urllib.parse

import folium
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from shapely.geometry import box, mapping, shape
from shapely.ops import unary_union
from shapely.prepared import prep

# ================= 1. 页面设置 =================
st.set_page_config(page_title="北建大 · 生活服务地图", page_icon="◧",
                   layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
  #MainMenu, [data-testid="stToolbar"], [data-testid="stDecoration"], footer {display: none !important;}
  header[data-testid="stHeader"] {background: transparent;}
  .block-container {padding: .5rem 1.1rem 1.6rem; max-width: 1200px;}
  html, body, [class*="css"] {font-family: "Microsoft YaHei", "PingFang SC", sans-serif;}

  /* 顶部标题条：一行，很矮 */
  .bar {display:flex; align-items:center; gap:10px; padding:8px 14px; margin-bottom:8px;
        background:linear-gradient(100deg,#0f3a63,#1d5f96); border-radius:6px; color:#fff;}
  .bar .m {width:30px; height:30px; border-radius:4px; background:rgba(255,255,255,.16);
           display:flex; align-items:center; justify-content:center; font-size:11px; font-weight:700;}
  .bar h1 {font-size:15px; margin:0; font-weight:600; letter-spacing:.3px;}
  .bar small {display:block; font-size:11px; opacity:.8; margin-top:1px;}

  /* 控件区：紧凑 */
  .lbl {font-size:11px; font-weight:600; color:#68737e; letter-spacing:1.2px; margin:6px 0 2px;}

  /* 设施卡片 */
  .card {border:1px solid #e6e9ed; border-radius:7px; padding:11px 13px; margin-top:8px;
         background:#fff; box-shadow:0 1px 3px rgba(15,58,99,.06);}
  .card .t {font-size:15px; font-weight:600; color:#22303d; margin-bottom:6px;}
  .card .r {font-size:12.5px; color:#4a5763; line-height:1.85;}
  .card .r b {color:#8a95a1; font-weight:500; display:inline-block; min-width:44px;}
  .navbtn {display:block; text-align:center; padding:10px 0; margin-top:10px; border-radius:6px;
           background:#1d5f96; color:#fff !important; text-decoration:none; font-size:14px;
           font-weight:600; letter-spacing:.5px;}
  .navbtn2 {background:#fff; color:#1d5f96 !important; border:1px solid #b9cede;
            font-weight:500; margin-top:8px; font-size:13px;}
  .hint {font-size:11px; color:#93a0ac; line-height:1.6;}
  table.clean {border-collapse:collapse; width:100%; font-size:12.5px;}
  table.clean th {background:#f1f4f7; color:#41505f; text-align:left; padding:6px 9px;
                  font-weight:600; border-bottom:1px solid #dde3e9; white-space:nowrap;}
  table.clean td {padding:5px 9px; border-bottom:1px solid #eef1f4;}
  table.clean td.num {text-align:right; font-variant-numeric:tabular-nums;}

  @media (max-width: 640px) {
    .block-container {padding: .3rem .6rem 1.2rem;}
    .bar {padding:6px 10px; gap:8px; margin-bottom:6px;}
    .bar .m {width:26px; height:26px; font-size:10px;}
    .bar h1 {font-size:13.5px;}
    .bar small {display:none;}
    .lbl {margin:4px 0 1px; font-size:10.5px;}
    /* 单选行再紧凑一点 */
    [data-testid="stRadio"] > div {gap:.1rem;}
    [data-testid="stRadio"] label p {font-size:13px;}
    [data-testid="stTextInput"] input {font-size:13px;}
    table.clean th, table.clean td {padding:4px 6px; font-size:11.5px;}
  }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="bar">
  <div class="m">BUCEA</div>
  <h1>北建大兴校区 · 生活服务可达性地图
    <small>以 15 栋宿舍为起点，按真实路网计算可达范围与设施数量</small>
  </h1>
</div>
""", unsafe_allow_html=True)

# ================= 2. 常量 =================
ISO_STYLE = "smooth"
DATA_FILES = ("bju_poi.xlsx", "poi_core.xlsx")


def iso_path(mode):
    if ISO_STYLE == "smooth":
        p = f"iso_{mode}_smooth_gcj.geojson"
        if os.path.exists(p):
            return p
    return f"iso_{mode}_gcj.geojson"


MODE_LABEL = {"walk": "步行", "bike": "骑行", "drive": "驾车", "bus": "公交"}
MODE_COLOR = {"walk": "#1f6fb2", "bike": "#2a8f7f", "drive": "#6b4fa8", "bus": "#c05621"}
MODE_KEYS = list(MODE_LABEL)
ISO_MODES = list(MODE_LABEL)
ISO_FILES = {m: iso_path(m) for m in ISO_MODES}
SCAPE_FILE = iso_path("drive")

THEME_ORDER = ["宜居", "宜业", "宜乐"]
THEME_COLOR = {"宜居": "#2f7d5d", "宜业": "#2f5f9e", "宜乐": "#b96a1b"}
THEME_FA_COLOR = {"宜居": "green", "宜业": "blue", "宜乐": "orange"}
THEME_ALIAS = {"宜游": "宜乐"}
FALLBACK_KEYWORDS = {
    "宜居": ["餐饮", "食堂", "超市", "便利", "购物", "居住", "宿舍", "生活", "服务",
             "交通", "医疗", "卫生", "快递", "洗浴", "银行"],
    "宜业": ["学习", "科研", "教学", "实验", "办公", "行政", "政务", "就业", "图书", "自习"],
    "宜乐": ["休闲", "娱乐", "运动", "体育", "健身", "文化", "旅游", "游", "艺术", "活动"],
}
SUB_ICON = {"餐饮": "cutlery", "交通": "bus", "服务": "info-sign", "医疗": "medkit",
            "购物": "shopping-cart", "综合": "home", "学习": "book",
            "运动": "futbol-o", "休闲": "coffee", "活动": "star"}
AMAP_SRC = urllib.parse.quote("i北建大")
STD_COLS = {"id", "名称", "一级分类", "所在楼宇/区域", "经度", "纬度", "坐标系", "地址",
            "开放时间", "电话", "适用人群", "数据来源", "备注", "_来源文件", "主题", "细分"}


def nav_url(lon, lat, name):
    """高德 URI：显式带 mode=car&policy=1，落地直接是路线页"""
    return (f"https://uri.amap.com/navigation?to={lon:.6f},{lat:.6f},"
            f"{urllib.parse.quote(str(name))}&mode=car&policy=1&src={AMAP_SRC}"
            f"&coordinate=gaode&callnative=1")


def _user_agent():
    try:
        return st.context.headers.get("User-Agent", "") or ""
    except Exception:
        return ""


UA = _user_agent()
IS_IOS = bool(re.search(r"iPhone|iPad|iPod", UA))
IS_ANDROID = "Android" in UA
IS_WECHAT = "MicroMessenger" in UA


def app_nav_url(lon, lat, name):
    """高德 App 的原生 scheme（坐标是 GCJ-02，所以 dev=0 不再转换）"""
    nm = urllib.parse.quote(str(name))
    q = f"sourceApplication=BUCEA&poiname={nm}&lat={lat:.6f}&lon={lon:.6f}&dev=0&style=2"
    if IS_IOS:
        return f"iosamap://navi?{q}"
    if IS_ANDROID:
        return f"androidamap://navi?{q}"
    return nav_url(lon, lat, name)


def nav_button(lon, lat, name):
    """地图外（Streamlit 主文档）用的链接，直接可点"""
    return (f'<a class="navbtn" href="{nav_url(lon, lat, name)}" target="_blank" '
            f'rel="noopener">导航到这里</a>')


def parse_cat(raw):
    s = str(raw).strip()
    m = re.match(r"^(宜[居业乐游])\s*[（(](.+?)[）)]\s*$", s)
    if m:
        return THEME_ALIAS.get(m.group(1), m.group(1)), m.group(2).strip()
    m = re.match(r"^(宜[居业乐游])$", s)
    if m:
        return THEME_ALIAS.get(m.group(1), m.group(1)), "综合"
    for t in THEME_ORDER:
        if any(k in s for k in FALLBACK_KEYWORDS[t]):
            return t, "综合"
    return None, None


# ================= 3. 数据 =================
@st.cache_data
def load_data(files):
    frames = []
    for f in files:
        if not os.path.exists(f):
            continue
        try:
            d = pd.read_excel(f)
            d.columns = d.columns.str.strip()
            d["经度"] = pd.to_numeric(d["经度"], errors="coerce")
            d["纬度"] = pd.to_numeric(d["纬度"], errors="coerce")
            frames.append(d.dropna(subset=["经度", "纬度"]))
        except Exception:
            continue
    return pd.concat(frames, ignore_index=True) if frames else None


@st.cache_data
def load_iso(path):
    return json.load(open(path, encoding="utf-8"))


def band_of(gj, t):
    for f in gj["features"]:
        if f["properties"]["layer"] == "band" and f["properties"]["time"] == t:
            return shape(f["geometry"])
    return None


@st.cache_data
def bright_and_mask(mode_file, mode_time, scape_file, scape_time, half=0.4):
    m, s = load_iso(mode_file), load_iso(scape_file)
    sel, scape = band_of(m, mode_time), band_of(s, scape_time)
    if sel is None:
        return None, None
    bbox = box(116.286 - half, 39.748 - half, 116.286 + half, 39.748 + half)
    bright = unary_union([g for g in (scape, sel) if g is not None]).simplify(1e-5, True)
    return mapping(bright), mapping(bbox.difference(bright))


@st.cache_data
def reach_table(points, key):
    from shapely.geometry import Point
    pts = [Point(float(x), float(y)) for x, y in points]
    rows = []
    for mode in ISO_MODES:
        try:
            gj = load_iso(ISO_FILES[mode])
        except Exception:
            continue
        cells = []
        for t in gj.get("times", []):
            b = band_of(gj, t)
            cells.append(None if b is None else sum(1 for p in pts if prep(b).contains(p)))
        rows.append((MODE_LABEL[mode], list(gj.get("times", [])), cells))
    return rows


df_raw = load_data(DATA_FILES)
if df_raw is None:
    st.error("数据读取失败：请确认 bju_poi.xlsx 与 poi_core.xlsx 在同一目录。")
    st.stop()
EXTRA_COLS = [c for c in df_raw.columns if c not in STD_COLS]

df = df_raw.copy()
keep_rows = []
for _, r in df.iterrows():
    dup = False
    for k in keep_rows:
        dx, dy = abs(r["经度"] - k["经度"]) * 85000, abs(r["纬度"] - k["纬度"]) * 111000
        if dx * dx + dy * dy > 80 ** 2:
            continue
        a, b = str(k["名称"]).strip(), str(r["名称"]).strip()
        if a == b or (min(len(a), len(b)) >= 4 and (a in b or b in a)
                      and min(len(a), len(b)) / max(len(a), len(b)) >= 0.6):
            dup = True
            break
    if not dup:
        keep_rows.append(r)
df = pd.DataFrame(keep_rows)
df[["主题", "细分"]] = df["一级分类"].apply(lambda v: pd.Series(parse_cat(v)))
df = df[df["主题"].notna()].copy()

# ================= 4. 顶部控件（3 行）=================
c1, c2 = st.columns([1, 1], gap="small")
with c1:
    st.markdown('<div class="lbl">出行方式</div>', unsafe_allow_html=True)
    sel_mode = st.radio("出行方式", MODE_KEYS, index=0, horizontal=True,
                        format_func=lambda m: MODE_LABEL[m], label_visibility="collapsed")
with c2:
    st.markdown('<div class="lbl">出行时间</div>', unsafe_allow_html=True)
    try:
        iso = load_iso(ISO_FILES[sel_mode])
        avail = list(iso.get("times", [5, 10, 15]))
    except Exception:
        iso, avail = None, [5, 10, 15]
    if st.session_state.get("sel_time") not in avail:
        st.session_state["sel_time"] = avail[-1]
    sel_time = st.radio("出行时间", avail, key="sel_time", horizontal=True,
                        format_func=lambda t: f"{t} 分钟", label_visibility="collapsed")

st.markdown('<div class="lbl">设施类别</div>', unsafe_allow_html=True)
theme_pick = st.radio("设施类别", ["全部"] + THEME_ORDER, index=0, horizontal=True,
                      label_visibility="collapsed")
shown = df if theme_pick == "全部" else df[df["主题"] == theme_pick]
shown = shown.copy()

st.markdown('''<div class="lbl">搜索</div>''', unsafe_allow_html=True)
q = st.text_input("搜索", placeholder="输入设施名称，例如 图书馆 / 荟聚 / 游泳馆",
                  label_visibility="collapsed")
if IS_WECHAT:
    st.markdown('<div class="hint" style="color:#a33a26;background:#fff3f0;'
                'border:1px solid #f0b8ad;border-radius:5px;padding:7px 10px;margin-top:6px;">'
                '微信内无法直接唤起高德 App：请点右上角 ··· → 在浏览器中打开本页，'
                '跳转就能直达高德。</div>', unsafe_allow_html=True)

# ================= 5. 地图 =================
# scrollWheelZoom=False：页面里滚动时不抢滚轮，避免地图被"以鼠标位置为中心"莫名放大
m = folium.Map(location=[39.748, 116.286], zoom_start=13 if sel_mode == "bus" else 14,
               tiles='https://webrd02.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8'
                     '&x={x}&y={y}&z={z}', attr='高德地图',
               scrollWheelZoom=False)

scape_time = None
if iso is not None:
    try:
        scape_time = max(list(load_iso(SCAPE_FILE).get("times", [15])))
    except Exception:
        scape_time = None
    _, mask = bright_and_mask(ISO_FILES[sel_mode], sel_time, SCAPE_FILE, scape_time)
    if mask is not None:
        folium.GeoJson(data=mask, style_function=lambda x: {
            'fillColor': '#10202f', 'color': '#10202f', 'weight': 0, 'fillOpacity': 0.60}).add_to(m)
    for other in ISO_MODES:
        if other == sel_mode:
            continue
        try:
            g = load_iso(ISO_FILES[other])
        except Exception:
            continue
        if sel_time not in list(g.get("times", [])):
            continue
        geom = band_of(g, sel_time)
        if geom is None:
            continue
        folium.GeoJson(
            data={"type": "FeatureCollection", "features": [{
                "type": "Feature", "properties": {}, "geometry": mapping(geom)}]},
            style_function=lambda x, c=MODE_COLOR[other]: {
                'fillColor': c, 'color': c, 'weight': 1.3, 'fillOpacity': 0, 'dashArray': '5,4'},
            tooltip=f"{MODE_LABEL[other]} {sel_time} 分钟").add_to(m)
    sel_geom = band_of(iso, sel_time)
    if sel_geom is not None:
        folium.GeoJson(
            data={"type": "FeatureCollection", "features": [{
                "type": "Feature", "properties": {}, "geometry": mapping(sel_geom)}]},
            style_function=lambda x: {'fillColor': MODE_COLOR[sel_mode], 'color': MODE_COLOR[sel_mode],
                                      'weight': 2.0, 'fillOpacity': 0.30},
            tooltip=f"{MODE_LABEL[sel_mode]} {sel_time} 分钟可达").add_to(m)

DORMS = {"1号楼": (39.749687, 116.283006), "2号楼": (39.749694, 116.284058),
         "3号楼": (39.750094, 116.282957), "4号楼": (39.750106, 116.284042),
         "5号楼": (39.750516, 116.282885), "6号楼": (39.748431, 116.288781),
         "7号楼": (39.751023, 116.282985), "8号楼": (39.751013, 116.284007),
         "9号楼": (39.751496, 116.283033), "10号楼": (39.751524, 116.284066),
         "11号楼": (39.750314, 116.288369), "硕博公寓1": (39.752257, 116.287544),
         "硕博公寓2": (39.752347, 116.288479), "硕博公寓3": (39.751854, 116.288442),
         "硕博公寓4": (39.751357, 116.288442)}
for name, (lat, lon) in DORMS.items():
    folium.CircleMarker([lat, lon], radius=3.5, color='#1a1a1a', weight=1, fill=True,
                        fill_color='#e8b923', fill_opacity=1, tooltip=f"起点 · {name}").add_to(m)

# ===== 点位数据：只打包必要字段，marker 由 JS 统一生成（体积是 folium.Marker 的 1/5）=====
poi_rows = []
for _, row in shown.iterrows():
    theme, sub = row["主题"], row["细分"]

    def val(col, default=""):
        v = row[col] if col in row else None
        return "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v).strip()

    ex = []
    for c in EXTRA_COLS:
        t = val(c)
        if t:
            # 支持 | 或单元格内换行（Excel 里 Alt+Enter）做多行
            ex.append([c, "·".join(s.strip() for s in re.split(r"[|\n]+", t) if s.strip())])
    poi_rows.append({
        "n": val("名称") or "未知设施", "x": round(float(row["经度"]), 6),
        "y": round(float(row["纬度"]), 6), "g": theme, "s": sub,
        "a": val("所在楼宇/区域"), "b": val("开放时间"), "c": val("电话"),
        "d": val("地址"), "e": val("备注"), "f": ex,
    })

# 小图例 + 我的位置（蓝点）样式
legend = "".join(
    f'<div style="margin:2px 0;"><span style="display:inline-block;width:8px;height:8px;'
    f'background:{THEME_COLOR[t]};border-radius:1px;margin-right:6px;"></span>{t}</div>'
    for t in THEME_ORDER)
m.get_root().html.add_child(folium.Element(f"""
<style>
  #lg {{position:fixed;bottom:12px;right:12px;z-index:9999;background:rgba(255,255,255,.93);
       padding:7px 10px;border:1px solid #e6e9ed;border-radius:5px;
       font:11px/1.55 'Microsoft YaHei',sans-serif;color:#33404d;}}
  @media (max-width:640px) {{ #lg {{font-size:10px;padding:5px 7px;bottom:7px;right:7px;}} }}

  /* 弹窗统一样式（放这里，避免每个 marker 重复写内联样式） */
  .pw {{width:200px;font-family:'Microsoft YaHei',sans-serif;}}
  .pt {{border-left:3px solid #5b6673;padding-left:7px;font-size:13.5px;font-weight:600;color:#22303d;}}
  .pr {{font-size:11.5px;color:#4a5763;line-height:1.7;margin-top:6px;}}
  .pn {{font-size:11.5px;color:#5b6673;margin-top:5px;}}
  .px {{margin-top:5px;padding:5px 7px;background:#f6f8fa;border-left:2px solid #cfd8e3;border-radius:0 3px 3px 0;}}
  .pxk {{font-size:10.5px;color:#8a95a1;}}
  .pxv {{font-size:12px;color:#33404d;line-height:1.55;}}
  .pb {{display:block;text-align:center;margin-top:9px;padding:9px 0;border-radius:5px;
       background:#1d5f96;color:#fff;text-decoration:none;font-size:13.5px;font-weight:600;}}

  /* 地图点位图钉（比 folium 默认 marker 省 90% 体积） */
  .pin {{width:22px;height:30px;position:relative;filter:drop-shadow(0 1px 2px rgba(0,0,0,.35));}}
  .pin i {{position:absolute;left:0;top:0;width:22px;height:22px;background:var(--c);
          border:2px solid #fff;border-radius:50% 50% 50% 0;transform:rotate(-45deg);
          display:flex;align-items:center;justify-content:center;box-sizing:border-box;}}
  .pin i b {{transform:rotate(45deg);color:#fff;font:600 10px/1 'Microsoft YaHei',sans-serif;}}

  /* 我的位置：高德风格的蓝点 + 呼吸光晕 */
  .medot {{ position:relative; width:16px; height:16px; border-radius:50%;
           background:#1a73e8; border:3px solid #fff;
           box-shadow:0 1px 5px rgba(26,115,232,.55); }}
  .medot::after {{ content:''; position:absolute; left:-9px; top:-9px; width:28px; height:28px;
                  border-radius:50%; background:rgba(26,115,232,.30);
                  animation:mpulse 1.9s ease-out infinite; }}
  @keyframes mpulse {{ 0% {{transform:scale(.45);opacity:.85}}
                       70% {{transform:scale(1.5);opacity:0}}
                       100% {{transform:scale(1.5);opacity:0}} }}
</style>
<div id="lg">{legend}</div>"""))

# ★ 自己实现定位（不依赖插件；按钮点击触发，兼容 iOS 的手势要求）
# 注意：加进 get_root().script 的必须是「裸 JS」，不能再包 <script> 标签，
# 否则会和 folium 自己的 <script> 嵌套，导致后面的 JS 被当成文字显示。
_POI_JSON = json.dumps(poi_rows, ensure_ascii=False, separators=(",", ":"))
_JS = r"""
window.POI = __POIJSON__;
window.POI_COLOR = {"宜居": "#2f7d5d", "宜业": "#2f5f9e", "宜乐": "#b96a1b"};
window.POI_GLYPH = {"宜居": "居", "宜业": "业", "宜乐": "乐"};

// ===== WGS-84 → GCJ-02 纠偏 =====
// 浏览器定位返回 WGS-84，高德底图是 GCJ-02（火星坐标），
// 北京大兴一带两者差 500 米以上，不纠偏蓝点会明显偏西南。
function _outOfChina(lng, lat) {
  return (lng < 72.004 || lng > 137.8347 || lat < 0.8293 || lat > 55.8271);
}
function _tLat(x, y) {
  var r = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * Math.sqrt(Math.abs(x));
  r += (20.0 * Math.sin(6.0 * x * Math.PI) + 20.0 * Math.sin(2.0 * x * Math.PI)) * 2.0 / 3.0;
  r += (20.0 * Math.sin(y * Math.PI) + 40.0 * Math.sin(y / 3.0 * Math.PI)) * 2.0 / 3.0;
  r += (160.0 * Math.sin(y / 12.0 * Math.PI) + 320 * Math.sin(y * Math.PI / 30.0)) * 2.0 / 3.0;
  return r;
}
function _tLng(x, y) {
  var r = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * Math.sqrt(Math.abs(x));
  r += (20.0 * Math.sin(6.0 * x * Math.PI) + 20.0 * Math.sin(2.0 * x * Math.PI)) * 2.0 / 3.0;
  r += (20.0 * Math.sin(x * Math.PI) + 40.0 * Math.sin(x / 3.0 * Math.PI)) * 2.0 / 3.0;
  r += (150.0 * Math.sin(x / 12.0 * Math.PI) + 300.0 * Math.sin(x / 30.0 * Math.PI)) * 2.0 / 3.0;
  return r;
}
function wgs84ToGcj02(lng, lat) {
  if (_outOfChina(lng, lat)) { return [lng, lat]; }
  var dLat = _tLat(lng - 105.0, lat - 35.0);
  var dLng = _tLng(lng - 105.0, lat - 35.0);
  var radLat = lat / 180.0 * Math.PI;
  var magic = Math.sin(radLat);
  magic = 1 - 0.00669342162296594323 * magic * magic;
  var sq = Math.sqrt(magic);
  dLat = (dLat * 180.0) /
         ((6378245.0 * (1 - 0.00669342162296594323)) / (magic * sq) * Math.PI);
  dLng = (dLng * 180.0) / (6378245.0 / sq * Math.cos(radLat) * Math.PI);
  return [lng + dLng, lat + dLat];
}

// 由数据批量生成点位（比 folium.Marker 省 90% 体积）
(function () {
  var tries = 0;
  var t = setInterval(function () {
    var map = window["__MAPNAME__"];
    if (!map || !window.L) { if (++tries > 80) { clearInterval(t); } return; }
    clearInterval(t);
    // 再保险一次：滚动页面时不要被地图抢走滚轮
    if (map.scrollWheelZoom) { map.scrollWheelZoom.disable(); }
    window.POI.forEach(function (p) {
      var c = window.POI_COLOR[p.g] || "#5b6673";
      var ico = L.divIcon({
        className: "", iconSize: [22, 30], iconAnchor: [11, 30], popupAnchor: [0, -28],
        html: '<div class="pin" style="--c:' + c + '"><i><b>' +
              (window.POI_GLYPH[p.g] || "点") + '</b></i></div>'
      });
      var body = "类别：" + p.g + " / " + p.s;
      if (p.a) { body += "<br>位置：" + p.a; }
      if (p.b) { body += "<br>时间：" + p.b; }
      if (p.c) { body += "<br>电话：" + p.c; }
      if (p.d) { body += "<br>地址：" + p.d; }
      var h = '<div class="pw"><div class="pt" style="border-color:' + c + '">' + p.n +
              '</div><div class="pr">' + body + '</div>';
      if (p.e) { h += '<div class="pn">' + p.e + '</div>'; }
      (p.f || []).forEach(function (kv) {
        h += '<div class="px"><div class="pxk">' + kv[0] + '</div><div class="pxv">' +
             kv[1] + '</div></div>';
      });
      var u = 'https://uri.amap.com/navigation?to=' + p.x.toFixed(6) + ',' + p.y.toFixed(6) + ',' +
              encodeURIComponent(p.n) + '&mode=car&policy=1&src=BUCEA&coordinate=gaode&callnative=1';
      h += '<a class="pb" href="' + u + '" data-lon="' + p.x + '" data-lat="' + p.y +
           '" data-nm="' + p.n.replace(/"/g, '&quot;') +
           '" onclick="return jumpAmap(this);">导航到这里</a></div>';
      L.marker([p.y, p.x], {icon: ico}).addTo(map)
        .bindPopup(h, {maxWidth: 250}).bindTooltip(p.n);
    });
  }, 120);
})();

// 弹窗里的「导航到这里」：优先用高德 App 原生 scheme（在点击手势里触发，手机才认），
// 没装 App 或系统拦了，再回落到高德网页版路线页。
window.jumpAmap = function (el) {
  var lon = el.dataset.lon || '', lat = el.dataset.lat || '';
  var nm = encodeURIComponent(el.dataset.nm || '目的地');
  var web = el.href;
  var ua = navigator.userAgent || '';
  var scheme = null;
  if (/android/i.test(ua)) {
    scheme = 'androidamap://navi?sourceApplication=BUCEA&poiname=' + nm +
             '&lat=' + lat + '&lon=' + lon + '&dev=0&style=2';
  } else if (/iphone|ipad|ipod/i.test(ua)) {
    scheme = 'iosamap://navi?sourceApplication=BUCEA&poiname=' + nm +
             '&lat=' + lat + '&lon=' + lon + '&dev=0&style=2';
  }
  if (/MicroMessenger/i.test(ua)) {
    alert('微信内无法直接唤起高德：请点右上角 ··· → 在浏览器中打开本页');
    return false;
  }
  if (scheme) {
    // 唤起成功时页面会失焦/隐藏；只有「还停在本页」才回落到网页版，
    // 否则 iOS 的确认框还没点就又被网页覆盖了。
    var left = false;
    window.addEventListener('blur', function () { left = true; });
    document.addEventListener('visibilitychange', function () {
      if (document.hidden) { left = true; }
    });
    setTimeout(function () {
      if (!left && !document.hidden) {
        try { window.top.location.href = web; } catch (e) { location.href = web; }
      }
    }, 2800);
    try {
      if (window.top && window.top.location) { window.top.location.href = scheme; }
      else { location.href = scheme; }
    } catch (e) { location.href = scheme; }
    return false;
  }
  try { window.top.location.href = web; } catch (e) { window.open(web, '_blank'); }
  return false;
};

// 定位：打开就自动请求一次，加载蓝点 + 精度圈；失败给出原因提示
(function () {
  var tries = 0;
  var timer = setInterval(function () {
    var map = window["__MAPNAME__"];
    if (!map || !map.locate) { if (++tries > 60) { clearInterval(timer); } return; }
    clearInterval(timer);

    var dot = L.divIcon({iconSize: [16, 16], className: '',
                         html: '<div class="medot"></div>'});
    var marker = null, circle = null, first = true;

    map.on('locationfound', function (e) {
      // 关键：把 WGS-84 转成 GCJ-02 再画，否则和高德底图差 500 米
      var g = wgs84ToGcj02(e.latlng.lng, e.latlng.lat);
      var ll = L.latLng(g[1], g[0]);
      if (!marker) {
        circle = L.circle(ll, {radius: e.accuracy || 60, color: '#1a73e8', weight: 1,
                               fillColor: '#1a73e8', fillOpacity: 0.12}).addTo(map);
        marker = L.marker(ll, {icon: dot, zIndexOffset: 1200}).addTo(map)
                  .bindTooltip('我的位置（精度 ±' + Math.round(e.accuracy || 0) + ' 米）');
      } else {
        marker.setLatLng(ll);
        circle.setLatLng(ll).setRadius(e.accuracy || 60);
      }
      var m1 = document.getElementById('locmsg');
      if (m1) { m1.style.display = 'none'; }
      // 注意：这里绝对不要 map.setView()——否则 GPS 迟到时地图会自己飞走。
      // 只有用户点「我的位置」按钮时才跳（那个用 setView: true）。
      var km = map.distance(ll, L.latLng(39.748, 116.286)) / 1000;
      if (km > 2 && m1) {
        m1.style.background = '#eef6ff';
        m1.style.borderColor = '#b9d4ee';
        m1.style.color = '#1d5f96';
        m1.style.display = 'block';
        m1.innerText = '已定位到你（距校区约 ' + km.toFixed(1) +
                       ' 公里）。点左上角「我的位置」可跳转过去。';
      }
    });
    map.on('locationerror', function (e) {
      var m2 = document.getElementById('locmsg');
      if (m2) {
        m2.style.display = 'block';
        m2.innerText = '定位失败：' + (e.message || '未知原因') +
                       '　请允许浏览器定位权限，并用 https 打开本页。';
      }
    });

    var ctl = L.control({position: 'topleft'});
    ctl.onAdd = function () {
      var d = L.DomUtil.create('div', '');
      d.innerHTML = '<button id="locbtn" style="background:#fff;border:2px solid rgba(0,0,0,.15);' +
        'border-radius:4px;padding:7px 9px;cursor:pointer;font:13px Microsoft YaHei;' +
        'box-shadow:0 1px 4px rgba(0,0,0,.2);">我的位置</button>' +
        '<button id="homebtn" style="display:block;margin-top:6px;background:#fff;' +
        'border:2px solid rgba(0,0,0,.15);border-radius:4px;padding:6px 9px;cursor:pointer;' +
        'font:12px Microsoft YaHei;box-shadow:0 1px 4px rgba(0,0,0,.2);">回到校区</button>';
      L.DomEvent.disableClickPropagation(d);
      return d;
    };
    ctl.addTo(map);
    document.getElementById('locbtn').onclick = function () {
      map.locate({enableHighAccuracy: true, timeout: 20000, watch: true, setView: true});
    };
    document.getElementById('homebtn').onclick = function () {
      map.setView([39.748, 116.286], 14);
    };

    var msg = L.DomUtil.create('div', '', map.getContainer());
    msg.id = 'locmsg';
    msg.style.cssText = 'display:none;position:absolute;left:50%;top:10px;' +
      'transform:translateX(-50%);z-index:9999;background:#fff3f0;border:1px solid #f0b8ad;' +
      'color:#a33a26;padding:6px 10px;border-radius:4px;font:12px Microsoft YaHei;max-width:90%;';

    setTimeout(function () {
      // 只定位、不移动地图（setView:false），避免 GPS 迟到时地图自己跳走
      map.locate({enableHighAccuracy: true, timeout: 20000, watch: true, setView: false});
    }, 600);
  }, 200);
})();
"""

m.get_root().script.add_child(
    folium.Element(_JS.replace("__POIJSON__", _POI_JSON).replace("__MAPNAME__", m.get_name())))

# ★ 注意：必须用 get_root().render()，_repr_html_() 返回的是转义后的 HTML（会显示成文字）
components.html(m.get_root().render(), height=560, scrolling=False)

# ================= 6. 搜索选中的设施卡片（在 iframe 外，导航链接一定能点）=================
if q.strip():
    hit = shown[shown["名称"].astype(str).str.contains(q.strip(), na=False)].head(20)
    if hit.empty:
        st.markdown('<div class="hint">没有匹配的设施，换个关键词试试。</div>', unsafe_allow_html=True)
    else:
        labels = [f"{r['名称']}（{r['主题']}·{r['细分']}）" for _, r in hit.iterrows()]
        pick = st.selectbox("选择设施", labels, label_visibility="collapsed")
        row = hit.iloc[labels.index(pick)]
        lon, lat = float(row["经度"]), float(row["纬度"])
        extra, links = "", ""
        for c in EXTRA_COLS:
            v = row.get(c)
            if v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() in ("", "nan"):
                continue
            txt = str(v).strip()
            # 列名里带「链接 / 小程序 / 网址」的，直接渲染成按钮（瑞幸点餐、电影票等）
            if any(k in c for k in ("链接", "小程序", "网址", "预订", "点餐", "购票")) \
                    and txt.startswith(("http", "weixin://", "alipays://")):
                links += (f'<a class="navbtn" style="background:#b96a1b;margin-top:8px;" '
                          f'href="{txt}" target="_blank" rel="noopener">{c}</a>')
                continue
            txt = "<br>".join(t.strip() for t in re.split(r"[|\n]+", txt) if t.strip())
            extra += (f'<div style="margin-top:6px;padding:6px 9px;background:#f6f8fa;'
                      f'border-left:2px solid #cfd8e3;border-radius:0 3px 3px 0;">'
                      f'<div style="font-size:10.5px;color:#8a95a1;">{c}</div>'
                      f'<div style="font-size:12.5px;color:#33404d;line-height:1.6;">{txt}</div></div>')
        is_phone = IS_IOS or IS_ANDROID
        primary_href = app_nav_url(lon, lat, row['名称']) if is_phone \
            else nav_url(lon, lat, row['名称'])
        primary_label = "直接打开高德地图 App 导航" if is_phone else "打开高德地图导航"
        st.markdown(f"""
        <div class="card">
          <div class="t">{row['名称']}</div>
          <div class="r">
            <b>类别</b>{row['主题']} / {row['细分']}<br>
            <b>位置</b>{row['所在楼宇/区域'] if pd.notna(row['所在楼宇/区域']) else '—'}<br>
            <b>地址</b>{row['地址'] if pd.notna(row['地址']) else '未提供'}
          </div>
          {extra}
          <a class="navbtn" href="{primary_href}" rel="noopener">{primary_label}</a>
          <a class="navbtn navbtn2" href="{nav_url(lon, lat, row['名称'])}" target="_blank"
             rel="noopener">网页版高德（没装 App 时用）</a>
          {links}
          <div class="hint" style="margin-top:6px;">
            第一个按钮直接唤起高德 App；没装或系统拦截时，用第二个。
          </div>
        </div>""", unsafe_allow_html=True)
else:
    st.markdown('<div class="hint">提示：点地图上的点位看详情；想直接导航，在上方搜索框输入名称后选中即可。'
                '</div>', unsafe_allow_html=True)

# ================= 7. 统计表 =================
with st.expander("各出行方式可达设施数量统计", expanded=False):
    pts = tuple((float(x), float(y)) for x, y in zip(shown["经度"], shown["纬度"]))
    rows = reach_table(pts, str(len(shown)) + theme_pick)
    if rows:
        all_t = sorted({t for _, ts, _ in rows for t in ts})
        head = "".join(f"<th>{t} 分钟</th>" for t in all_t)
        body = ""
        for label, times, cells in rows:
            mm = dict(zip(times, cells))
            body += (f"<tr><td>{label}</td>" +
                     "".join(f'<td class="num">{mm.get(t, "—")}</td>' for t in all_t) + "</tr>")
        st.markdown(f'<table class="clean"><tr><th>出行方式</th>{head}</tr>{body}</table>',
                    unsafe_allow_html=True)
        st.markdown('<div class="hint">统计口径：设施点位落在对应方式、对应时间档的可达圈内。</div>',
                    unsafe_allow_html=True)
