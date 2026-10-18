import json
import math
import os
import re
import urllib.parse

import folium
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from folium.plugins import LocateControl
from shapely.geometry import box, mapping, shape
from shapely.ops import unary_union
from shapely.prepared import prep


def show_map(m, height=620):
    """直接把 folium 生成的 HTML 塞进 iframe。
    不用 st_folium：它依赖自定义组件的静态资源，云端装到别的版本组合时容易渲染成空白。"""
    components.html(m._repr_html_(), height=height, scrolling=False)

# ================= 1. 页面设置 =================
st.set_page_config(page_title="北建大兴校区 · 生活服务可达性地图", page_icon="◧",
                   layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
  /* 只藏 Deploy 菜单 / 汉堡菜单 / 页脚 */
  #MainMenu, [data-testid="stToolbar"], [data-testid="stDecoration"], footer {display: none !important;}
  header[data-testid="stHeader"] {background: transparent; backdrop-filter: none;}
  .block-container {padding: .6rem 1.4rem 2rem; max-width: 1200px;}
  html, body, [class*="css"] {font-family: "Microsoft YaHei", "PingFang SC", "Helvetica Neue", sans-serif;}

  /* 顶部标题条：手机上自动变小、副标题隐藏 */
  .appbar {display:flex; align-items:center; gap:14px; padding:12px 18px; margin-bottom:10px;
           background:linear-gradient(100deg,#0f3a63 0%,#1d5f96 100%);
           border-radius:7px; color:#fff;}
  .appbar .mark {flex:0 0 auto; width:36px; height:36px; border-radius:5px;
                 background:rgba(255,255,255,.15); display:flex; align-items:center;
                 justify-content:center; font-size:14px; font-weight:700; letter-spacing:.5px;}
  .appbar h1 {font-size:17px; margin:0; font-weight:600; letter-spacing:.4px; line-height:1.35;}
  .appbar p {margin:3px 0 0; font-size:12px; opacity:.82; line-height:1.5;}

  .side-title {font-size:11.5px; font-weight:600; color:#5c6874; letter-spacing:1.6px;
               margin:12px 0 6px; padding-bottom:5px; border-bottom:1px solid #e6e9ed;}

  .statbar {display:flex; flex-wrap:wrap; gap:6px 14px; align-items:baseline;
            background:#f7f9fb; border:1px solid #e6e9ed; border-radius:6px;
            padding:8px 12px; margin:10px 0; font-size:12.5px; color:#41505f;}
  .statbar b {color:#0f3a63; font-size:15px; font-weight:600;}
  .statbar span.sep {color:#cfd6de;}

  table.clean {border-collapse:collapse; width:100%; font-size:12.5px; margin-top:4px;}
  table.clean th {background:#f1f4f7; color:#41505f; text-align:left; padding:7px 10px;
                  font-weight:600; border-bottom:1px solid #dde3e9; white-space:nowrap;}
  table.clean td {padding:6px 10px; border-bottom:1px solid #eef1f4; color:#33404d;}
  table.clean tr:last-child td {border-bottom:none;}
  table.clean td.num {text-align:right; font-variant-numeric:tabular-nums;}
  .hint {font-size:11.5px; color:#8a95a1; line-height:1.7;}

  /* ===== 手机端适配 ===== */
  @media (max-width: 640px) {
    .block-container {padding: .4rem .7rem 1.6rem;}
    .appbar {padding:9px 12px; gap:10px; margin-bottom:8px;}
    .appbar .mark {width:30px; height:30px; font-size:12px;}
    .appbar h1 {font-size:15px;}
    .appbar p {display:none;}
    .side-title {margin:9px 0 4px; font-size:11px;}
    .statbar {font-size:11.5px; padding:6px 10px; gap:4px 10px;}
    .statbar b {font-size:13.5px;}
    table.clean th, table.clean td {padding:5px 6px; font-size:11.5px;}
    /* 单选框/复选框的行距收紧 */
    [data-testid="stRadio"] > div, [data-testid="stCheckbox"] {gap:.15rem;}
    [data-testid="stRadio"] label p, [data-testid="stCheckbox"] label p {font-size:13px;}
  }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="appbar">
  <div class="mark">BUCEA</div>
  <div>
    <h1>北建大兴校区 · 生活服务可达性地图</h1>
    <p>以 15 栋宿舍为起点，按真实路网计算步行 / 骑行 / 驾车 / 公交的可达范围，并统计范围内公共设施数量</p>
  </div>
</div>
""", unsafe_allow_html=True)

ISO_STYLE = "smooth"
DATA_FILES = ("bju_poi.xlsx", "poi_core.xlsx")        # 校内精细标注 + 周边重点场所


def iso_path(mode):
    if ISO_STYLE == "smooth":
        p = f"iso_{mode}_smooth_gcj.geojson"
        if os.path.exists(p):
            return p
    return f"iso_{mode}_gcj.geojson"


MODE_LABEL = {"walk": "步行", "bike": "骑行", "drive": "驾车", "bus": "公交"}
MODE_COLOR = {"walk": "#1f6fb2", "bike": "#2a8f7f", "drive": "#6b4fa8", "bus": "#c05621"}
MODE_KEYS = ["walk", "bike", "drive", "bus"]
ISO_MODES = ["walk", "bike", "drive", "bus"]
MODE_NOTE = {
    "walk": "1.2 m/s（4.3 km/h）",
    "bike": "13.3 km/h，按高德实测标定",
    "drive": "均速 22.8 km/h，按高德实测标定",
    "bus": "候车 20 分钟 + 车速 25 km/h",
}
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


def nav_button(lon, lat, name):
    nm = urllib.parse.quote(str(name))
    url = (f"https://uri.amap.com/navigation?to={lon:.6f},{lat:.6f},{nm}"
           f"&src={AMAP_SRC}&coordinate=gaode&callnative=1")
    return (f'<a href="{url}" target="_blank" rel="noopener" style="display:block;'
            f'text-align:center;padding:7px 0;margin-top:10px;border-radius:5px;'
            f'background:#1d5f96;color:#fff;text-decoration:none;font-size:13px;'
            f'letter-spacing:.5px;">导航到这里</a>')


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


def sec(title):
    """分组小标题（写到当前容器里，不再用 st.sidebar）"""
    st.markdown(f'<div class="side-title">{title}</div>', unsafe_allow_html=True)


# ================= 2. 数据 =================
@st.cache_data
def load_data(files):
    frames, counts = [], {}
    for f in files:
        if not os.path.exists(f):
            continue
        try:
            d = pd.read_excel(f)
            d.columns = d.columns.str.strip()
            d["经度"] = pd.to_numeric(d["经度"], errors="coerce")
            d["纬度"] = pd.to_numeric(d["纬度"], errors="coerce")
            d = d.dropna(subset=["经度", "纬度"])
            d["_来源文件"] = f
            frames.append(d)
            counts[f] = len(d)
        except Exception:
            continue
    if not frames:
        return None, {}
    return pd.concat(frames, ignore_index=True), counts


@st.cache_data
def load_iso(path):
    return json.load(open(path, encoding="utf-8"))


def band_of(gj, t):
    for f in gj["features"]:
        if f["properties"]["layer"] == "band" and f["properties"]["time"] == t:
            return shape(f["geometry"])
    return None


@st.cache_data
def bright_and_mask(mode_file, mode_time, scape_file, scape_time, half=0.4, simplify=1e-5):
    m, s = load_iso(mode_file), load_iso(scape_file)
    sel, scape = band_of(m, mode_time), band_of(s, scape_time)
    bbox = box(116.286 - half, 39.748 - half, 116.286 + half, 39.748 + half)
    if sel is None:
        return None, None
    bright = unary_union([g for g in (scape, sel) if g is not None])
    bright = bright.simplify(simplify, preserve_topology=True)
    return mapping(bright), mapping(bbox.difference(bright))


@st.cache_data
def reach_table(points, dataset_key):
    """各方式各时间档能覆盖多少设施（点在面内判定）"""
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
            if b is None:
                cells.append(None)
                continue
            p = prep(b)
            cells.append(sum(1 for pt in pts if p.contains(pt)))
        rows.append((MODE_LABEL[mode], list(gj.get("times", [])), cells))
    return rows


# ================= 3. 侧边栏 =================
df_raw, src_count = load_data(DATA_FILES)
if df_raw is None:
    st.error("数据读取失败：请确认 bju_poi.xlsx 与 poi_core.xlsx 在同一目录。")
    st.stop()

# 表格里除标准字段以外的列，都会作为「属性卡片」显示在弹窗里
STD_COLS = {"id", "名称", "一级分类", "所在楼宇/区域", "经度", "纬度", "坐标系", "地址",
            "开放时间", "电话", "适用人群", "数据来源", "备注", "_来源文件", "主题", "细分"}
EXTRA_COLS = [c for c in df_raw.columns if c not in STD_COLS]

df = df_raw.copy()
keep_rows = []
for _, r in df.iterrows():
    dup = False
    for k in keep_rows:
        dx = abs(r["经度"] - k["经度"]) * 85000
        dy = abs(r["纬度"] - k["纬度"]) * 111000
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

# ===== 移动优先：单列布局（控件在上、地图紧跟，避免手机上被挤到最下面）=====
sec("出行方式")
sel_mode = st.radio("出行方式", MODE_KEYS, index=0, horizontal=True,
                    format_func=lambda m: MODE_LABEL[m], label_visibility="collapsed")

iso, iso_err, sel_time = None, None, None
if sel_mode != "none":
    try:
        iso = load_iso(ISO_FILES[sel_mode])
        if iso.get("schema") != "bucea-isochrone-v2":
            raise ValueError("圈层文件版本不匹配")
    except Exception as e:
        iso_err = str(e)
    sec("出行时间")
    if iso is not None:
        avail = list(iso.get("times", [5, 10, 15]))
        if st.session_state.get("sel_time") not in avail:
            st.session_state["sel_time"] = avail[-1]
        sel_time = st.radio("出行时间", avail, key="sel_time", horizontal=True,
                            format_func=lambda t: f"{t} 分钟",
                            label_visibility="collapsed")
    else:
        st.error(iso_err)

picked = []
with st.expander("设施类别", expanded=True):
    for theme in THEME_ORDER:
        sub = df[df["主题"] == theme]
        on = st.checkbox(f"{theme}（{len(sub)}）", value=True, key=f"th_{theme}")
        if not on or sub.empty:
            continue
        subs = sorted(sub["细分"].unique().tolist())
        if len(subs) > 1:
            with st.expander("细分", expanded=False):
                for s in subs:
                    n = int((sub["细分"] == s).sum())
                    if st.checkbox(f"{s}（{n}）", value=True, key=f"sub_{theme}_{s}"):
                        picked.append((theme, s))
        else:
            picked.extend([(theme, s) for s in subs])

shown = df[df.apply(lambda r: (r["主题"], r["细分"]) in picked, axis=1)] if picked else df.iloc[0:0]

# 紧凑信息条（替代原来三张卡，手机上不占高度）
st.markdown(
    '<div class="statbar">'
    f'<span><b>{len(shown)}</b> 个设施</span><span class="sep">|</span>'
    f'<span>宜居 <b>{int((df["主题"] == "宜居").sum())}</b></span>'
    f'<span>宜业 <b>{int((df["主题"] == "宜业").sum())}</b></span>'
    f'<span>宜乐 <b>{int((df["主题"] == "宜乐").sum())}</b></span>'
    '<span class="sep">|</span><span>15 栋宿舍起点</span>'
    '</div>', unsafe_allow_html=True)

# ================= 4. 地图 =================
m = folium.Map(location=[39.748, 116.286], zoom_start=13 if sel_mode == "bus" else 14,
               tiles='https://webrd02.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8'
                     '&x={x}&y={y}&z={z}',
               attr='高德地图')

# ★ 一打开就自动定位（浏览器会弹权限请求）；左上角按钮可再次定位
LocateControl(auto_start=True, position="topleft", flyTo=True, keepCurrentZoomLevel=False,
              draw_circle=True, marker_class="fa fa-user-circle", marker_size=(26, 26),
              locateOptions={"enableHighAccuracy": True, "watch": True, "maximumAge": 0,
                             "timeout": 20000, "setView": "untilPanOrZoom"},
              strings={"title": "定位我的位置", "popup": "我的位置", "metersUnit": "米"}).add_to(m)

scape_time = None
if iso is not None and sel_time is not None:
    try:
        scape_time = max(list(load_iso(SCAPE_FILE).get("times", [15])))
    except Exception:
        scape_time = None
    _, mask = bright_and_mask(ISO_FILES[sel_mode], sel_time, SCAPE_FILE, scape_time)
    if mask is not None:
        folium.GeoJson(data=mask, style_function=lambda x: {
            'fillColor': '#10202f', 'color': '#10202f', 'weight': 0, 'fillOpacity': 0.62}).add_to(m)
    if scape_time is not None:
        folium.GeoJson(
            data={"type": "FeatureCollection", "features": [{
                "type": "Feature", "properties": {},
                "geometry": mapping(band_of(load_iso(SCAPE_FILE), scape_time))}]},
            style_function=lambda x: {'fillColor': '#ffffff', 'color': '#7c8894',
                                      'weight': 1.4, 'fillOpacity': 0.05, 'dashArray': '7,6'},
            tooltip=f"亮区范围：驾车 {scape_time} 分钟").add_to(m)
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
                'fillColor': c, 'color': c, 'weight': 1.4, 'fillOpacity': 0, 'dashArray': '5,4'},
            tooltip=f"{MODE_LABEL[other]} {sel_time} 分钟").add_to(m)
    sel_geom = band_of(iso, sel_time)
    if sel_geom is not None:
        folium.GeoJson(
            data={"type": "FeatureCollection", "features": [{
                "type": "Feature", "properties": {}, "geometry": mapping(sel_geom)}]},
            style_function=lambda x: {'fillColor': MODE_COLOR[sel_mode], 'color': MODE_COLOR[sel_mode],
                                      'weight': 2.0, 'fillOpacity': 0.30},
            tooltip=f"{MODE_LABEL[sel_mode]} {sel_time} 分钟可达（15 栋宿舍合并）").add_to(m)

# ===== 我的位置：由 LocateControl 自动定位并在地图上显示 =====
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

for _, row in shown.iterrows():
    theme, sub = row["主题"], row["细分"]
    name = row["名称"] if pd.notna(row["名称"]) else "未知设施"
    lon, lat = float(row["经度"]), float(row["纬度"])

    def val(col, default="—"):
        return row[col] if col in row and pd.notna(row[col]) else default

    rows_html = "".join(
        f'<tr><td style="color:#7b8794;padding:2px 8px 2px 0;white-space:nowrap;">{k}</td>'
        f'<td style="padding:2px 0;">{v}</td></tr>'
        for k, v in [("类别", f"{theme} / {sub}"), ("位置", val("所在楼宇/区域", "未知")),
                     ("时间", val("开放时间")), ("电话", val("电话", "无")),
                     ("地址", val("地址", "未提供"))])

    # ★ 表格里自定义的列（例如「楼层分布」「容纳人数」「图片」）自动变成属性卡片
    extra_html = ""
    for col in EXTRA_COLS:
        v = row.get(col)
        if v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() in ("", "nan", "None"):
            continue
        txt = str(v).strip()
        if col in ("图片", "照片", "图片链接") and txt.startswith("http"):
            extra_html += (f'<div style="margin-top:7px;"><img src="{txt}" '
                           f'style="width:100%;border-radius:4px;"></div>')
            continue
        if "|" in txt:
            txt = "<br>".join(t.strip() for t in txt.split("|") if t.strip())
        extra_html += (
            f'<div style="margin-top:6px;padding:6px 8px;background:#f6f8fa;'
            f'border-left:2px solid #cfd8e3;border-radius:0 3px 3px 0;">'
            f'<div style="font-size:11px;color:#8a95a1;margin-bottom:2px;">{col}</div>'
            f'<div style="font-size:12px;color:#33404d;line-height:1.6;">{txt}</div></div>')

    note = val("备注", "")
    note_html = f'<p style="margin:6px 0 0;color:#5b6673;font-size:12px;">{note}</p>' if note != "—" else ""
    popup_html = f"""
    <div style="width:236px; font-family:'Microsoft YaHei',sans-serif;">
      <div style="border-left:3px solid {THEME_COLOR.get(theme, '#5b6673')}; padding-left:8px;">
        <div style="font-size:14px; font-weight:600; color:#22303d;">{name}</div>
      </div>
      <table style="width:100%; font-size:12px; color:#33404d; border-collapse:collapse;
                    margin-top:7px; font-family:inherit;">{rows_html}</table>
      {note_html}{extra_html}
      {nav_button(lon, lat, name)}
    </div>"""
    folium.Marker(
        location=[lat, lon],
        popup=folium.Popup(popup_html, max_width=280),
        tooltip=f"{name}（{theme}·{sub}）",
        icon=folium.Icon(color=THEME_FA_COLOR.get(theme, "gray"),
                         icon=SUB_ICON.get(sub, "map-marker"), prefix="fa")).add_to(m)

# 图例（右下角，低调一些）
theme_legend = "".join(
    f'<div style="margin:3px 0;"><span style="display:inline-block;width:9px;height:9px;'
    f'background:{THEME_COLOR[t]};border-radius:1px;margin-right:7px;"></span>{t}</div>'
    for t in THEME_ORDER)
if sel_mode == "none":
    iso_legend = '<div style="margin-top:7px;padding-top:6px;border-top:1px solid #e6e9ed;' \
                 'color:#8a95a1;">未显示可达圈</div>'
else:
    time_txt = f"{sel_time} 分钟" if sel_time else "—"
    others = "".join(
        f'<div style="margin:3px 0;"><span style="display:inline-block;width:13px;'
        f'border-top:1.5px dashed {MODE_COLOR[o]};margin-right:7px;vertical-align:middle;"></span>'
        f'{MODE_LABEL[o]} {time_txt}</div>' for o in ISO_MODES if o != sel_mode)
    iso_legend = (
        '<div style="margin-top:7px;padding-top:6px;border-top:1px solid #e6e9ed;">'
        f'<div style="margin:3px 0;"><span style="display:inline-block;width:9px;height:9px;'
        f'background:{MODE_COLOR[sel_mode]};opacity:.65;border-radius:1px;margin-right:7px;">'
        f'</span>{MODE_LABEL[sel_mode]} {time_txt}</div>{others}</div>')
m.get_root().html.add_child(folium.Element(f"""
<style>
  #lg {{ position:fixed; bottom:16px; right:16px; z-index:9999; background:rgba(255,255,255,.94);
        padding:9px 12px; border:1px solid #e6e9ed; border-radius:6px;
        font:12px/1.6 'Microsoft YaHei',sans-serif; color:#33404d;
        box-shadow:0 1px 4px rgba(15,58,99,.10); max-width:150px; }}
  @media (max-width: 640px) {{
    #lg {{ font-size:10.5px; padding:5px 7px; bottom:8px; right:8px; max-width:104px; line-height:1.45; }}
    #lg .lg-t {{ display:none; }}
  }}
</style>
<div id="lg">
  <div class="lg-t" style="font-weight:600;color:#41505f;margin-bottom:3px;">图例</div>
  {theme_legend}{iso_legend}
</div>"""))

# ================= 5. 地图 + 统计表 =================
show_map(m, height=560)

with st.expander("各出行方式可达设施数量统计", expanded=False):
    pts_key = tuple((float(x), float(y)) for x, y in zip(shown["经度"], shown["纬度"]))
    rows = reach_table(pts_key, str(len(shown)))
    if not rows:
        st.markdown('<div class="hint">没有可统计的圈层数据。</div>', unsafe_allow_html=True)
    else:
        all_times = sorted({t for _, ts, _ in rows for t in ts})
        head = "".join(f"<th>{t} 分钟</th>" for t in all_times)
        body = ""
        for label, times, cells in rows:
            m_ = dict(zip(times, cells))
            tds = "".join(f'<td class="num">{m_.get(t, "—")}</td>' for t in all_times)
            body += f"<tr><td>{label}</td>{tds}</tr>"
            st.markdown(f'<table class="clean"><tr><th>出行方式</th>{head}</tr>{body}</table>',
                        unsafe_allow_html=True)
            st.markdown('<div class="hint">统计口径：设施点位落在对应出行方式、对应时间档的可达圈内'
                        '（步行/骑行/驾车为 5/10/15 分钟，公交为 30/45/60 分钟）。</div>',
                        unsafe_allow_html=True)
