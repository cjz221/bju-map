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
    return (f"https://uri.amap.com/navigation?to={lon:.6f},{lat:.6f},"
            f"{urllib.parse.quote(str(name))}&src={AMAP_SRC}&coordinate=gaode&callnative=1")


def nav_button(lon, lat, name):
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

st.markdown('<div class="lbl">搜索</div>', unsafe_allow_html=True)
q = st.text_input("搜索", placeholder="输入设施名称，例如 图书馆 / 荟聚 / 游泳馆",
                  label_visibility="collapsed")

# ================= 5. 地图 =================
m = folium.Map(location=[39.748, 116.286], zoom_start=13 if sel_mode == "bus" else 14,
               tiles='https://webrd02.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8'
                     '&x={x}&y={y}&z={z}', attr='高德地图')

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

for _, row in shown.iterrows():
    theme, sub = row["主题"], row["细分"]
    name = row["名称"] if pd.notna(row["名称"]) else "未知设施"
    lon, lat = float(row["经度"]), float(row["纬度"])

    def val(col, default="—"):
        return row[col] if col in row and pd.notna(row[col]) else default

    lines = [f"{k}：{v}" for k, v in [("类别", f"{theme} / {sub}"),
                                     ("位置", val("所在楼宇/区域", "未知")),
                                     ("时间", val("开放时间")), ("电话", val("电话", "无")),
                                     ("地址", val("地址", "未提供"))] if v not in ("—", "")]
    extra = ""
    for c in EXTRA_COLS:
        v = row.get(c)
        if v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() in ("", "nan"):
            continue
        txt = "·".join(t.strip() for t in str(v).split("|") if t.strip())
        extra += (f'<div style="margin-top:5px;padding:5px 7px;background:#f6f8fa;'
                  f'border-left:2px solid #cfd8e3;border-radius:0 3px 3px 0;">'
                  f'<div style="font-size:10.5px;color:#8a95a1;">{c}</div>'
                  f'<div style="font-size:12px;color:#33404d;line-height:1.55;">{txt}</div></div>')
    note = val("备注", "")
    popup = (f'<div style="width:210px;font-family:\'Microsoft YaHei\',sans-serif;">'
             f'<div style="border-left:3px solid {THEME_COLOR.get(theme, "#5b6673")};padding-left:7px;'
             f'font-size:13.5px;font-weight:600;color:#22303d;">{name}</div>'
             f'<div style="font-size:11.5px;color:#4a5763;line-height:1.7;margin-top:6px;">'
             + "<br>".join(lines) + f'</div>'
             + (f'<div style="margin-top:5px;font-size:11.5px;color:#5b6673;">{note}</div>'
                if note != "—" else "")
             + extra
             + f'<div style="margin-top:8px;font-size:11px;color:#93a0ac;">'
               f'想直接导航，请用下方搜索框选中该设施</div></div>')
    folium.Marker([lat, lon], popup=folium.Popup(popup, max_width=250),
                  tooltip=f"{name}（{theme}·{sub}）",
                  icon=folium.Icon(color=THEME_FA_COLOR.get(theme, "gray"),
                                   icon=SUB_ICON.get(sub, "map-marker"), prefix="fa")).add_to(m)

# 小图例
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
</style>
<div id="lg">{legend}</div>"""))

# ★ 自己实现定位（不依赖插件；按钮点击触发，兼容 iOS 的手势要求）
map_name = m.get_name()
m.get_root().script.add_child(folium.Element(f"""
<script>
(function () {{
  var tries = 0;
  var timer = setInterval(function () {{
    var map = window["{map_name}"];
    if (!map || !map.locate) {{ if (++tries > 60) clearInterval(timer); return; }}
    clearInterval(timer);

    var dot = L.divIcon({{iconSize: [18, 18], className: '', html:
      '<div style="width:16px;height:16px;border-radius:50%;background:#c0392b;border:3px solid #fff;' +
      'box-shadow:0 0 0 2px rgba(192,57,43,.45);"></div>'}});
    var marker = null, circle = null, first = true;

    map.on('locationfound', function (e) {{
      if (!marker) {{
        circle = L.circle(e.latlng, {{radius: e.accuracy || 60, color: '#c0392b', weight: 1,
                                      fillColor: '#c0392b', fillOpacity: 0.12}}).addTo(map);
        marker = L.marker(e.latlng, {{icon: dot, zIndexOffset: 1200}}).addTo(map)
                  .bindTooltip('我的位置', {{permanent: false}});
      }} else {{
        marker.setLatLng(e.latlng);
        circle.setLatLng(e.latlng).setRadius(e.accuracy || 60);
      }}
      if (first) {{ map.setView(e.latlng, Math.max(map.getZoom(), 16)); first = false; }}
    }});
    map.on('locationerror', function (e) {{
      var t = document.getElementById('locmsg');
      if (t) {{ t.style.display = 'block';
               t.innerText = '定位失败：' + (e.message || '未知原因') + '。请允许定位权限，或用 https 打开。'; }}
    }});

    var ctl = L.control({{position: 'topleft'}});
    ctl.onAdd = function () {{
      var d = L.DomUtil.create('div', '');
      d.innerHTML = '<button id="locbtn" style="background:#fff;border:2px solid rgba(0,0,0,.15);' +
        'border-radius:4px;padding:7px 9px;cursor:pointer;font:13px Microsoft YaHei;' +
        'box-shadow:0 1px 4px rgba(0,0,0,.2);">📍 我的位置</button>';
      L.DomEvent.disableClickPropagation(d);
      return d;
    }};
    ctl.addTo(map);
    document.getElementById('locbtn').onclick = function () {{
      map.locate({{enableHighAccuracy: true, timeout: 20000, watch: true, setView: true}});
    }};

    var msg = L.DomUtil.create('div', '', map.getContainer());
    msg.id = 'locmsg';
    msg.style.cssText = 'display:none;position:absolute;left:50%;top:10px;transform:translateX(-50%);' +
      'z-index:9999;background:#fff3f0;border:1px solid #f0b8ad;color:#a33a26;padding:6px 10px;' +
      'border-radius:4px;font:12px Microsoft YaHei;max-width:90%;';
  }}, 200);
}})();
</script>"""))

components.html(m._repr_html_(), height=560, scrolling=False)

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
        extra = ""
        for c in EXTRA_COLS:
            v = row.get(c)
            if v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() in ("", "nan"):
                continue
            txt = "<br>".join(t.strip() for t in str(v).split("|") if t.strip())
            extra += (f'<div style="margin-top:6px;padding:6px 9px;background:#f6f8fa;'
                      f'border-left:2px solid #cfd8e3;border-radius:0 3px 3px 0;">'
                      f'<div style="font-size:10.5px;color:#8a95a1;">{c}</div>'
                      f'<div style="font-size:12.5px;color:#33404d;line-height:1.6;">{txt}</div></div>')
        st.markdown(f"""
        <div class="card">
          <div class="t">{row['名称']}</div>
          <div class="r">
            <b>类别</b>{row['主题']} / {row['细分']}<br>
            <b>位置</b>{row['所在楼宇/区域'] if pd.notna(row['所在楼宇/区域']) else '—'}<br>
            <b>地址</b>{row['地址'] if pd.notna(row['地址']) else '未提供'}
          </div>
          {extra}
          <a class="navbtn" href="{nav_url(lon, lat, row['名称'])}" target="_blank" rel="noopener">
            在高德地图中导航到这里</a>
          <div class="hint" style="margin-top:6px;">手机上点开会唤起高德 App；
            若只打开了网页版，页面里会有"打开高德地图"按钮。</div>
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
