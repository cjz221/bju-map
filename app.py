import streamlit as st
import pandas as pd
import folium
from streamlit_folium import folium_static

# ================= 1. 页面全局设置 =================
st.set_page_config(page_title="北建大民生与人口专题图", page_icon="🏫", layout="wide")
st.title("🏫 北建大民生与人口专题图")

# 添加网页描述
st.markdown("""
> **数据说明**：本系统基于高德API爬取的北建大校园内民生设施数据。
> 涵盖餐饮、学习、居住等多种分类，支持空间可视化与人群匹配分析。
> *   **坐标系**：GCJ-02（高德坐标系） | **技术栈**：Python + Streamlit + Folium
""")
st.divider() # 添加分割线

# ================= 2. 数据加载与清洗 =================
@st.cache_data # 缓存数据，加快加载
def load_data():
    # 注意：请确保 bju_poi.xlsx 和本代码在同一文件夹
    df = pd.read_excel('bju_poi.xlsx')
    
    # 去除列名可能存在的空格
    df.columns = df.columns.str.strip()
    
    # 强制经纬度转为数字，防止空值报错
    df['经度'] = pd.to_numeric(df['经度'], errors='coerce')
    df['纬度'] = pd.to_numeric(df['纬度'], errors='coerce')
    
    # 剔除经纬度为空的行
    df = df.dropna(subset=['经度', '纬度'])
    
    return df

try:
    df = load_data()
except Exception as e:
    st.error(f"❌ 数据读取失败！请检查文件名是否为 'bju_poi.xlsx' 且与代码同目录。错误信息: {e}")
    st.stop()

# ================= 3. 侧边栏交互设置 =================
st.sidebar.header("🔍 数据筛选")

# 分类筛选
category_list = df['一级分类'].dropna().unique().tolist()
selected_categories = st.sidebar.multiselect("选择一级分类", category_list, default=category_list)

# 适用人群筛选
audience_list = df['适用人群'].dropna().unique().tolist()
selected_audiences = st.sidebar.multiselect("选择适用人群", audience_list, default=audience_list)

# 名称搜索框
search_query = st.sidebar.text_input("🔎 搜索设施名称 (如: 图书馆)", "")

# 应用筛选逻辑
filtered_df = df[
    (df['一级分类'].isin(selected_categories)) & 
    (df['适用人群'].isin(selected_audiences))
]
if search_query:
    filtered_df = filtered_df[filtered_df['名称'].astype(str).str.contains(search_query, case=False, na=False)]

# 侧边栏数据展示
st.sidebar.markdown("---")
st.sidebar.metric(label="当前展示设施数量", value=len(filtered_df))
st.sidebar.write("### 适用人群分布")
if not filtered_df.empty:
    st.sidebar.bar_chart(filtered_df['适用人群'].value_counts())
else:
    st.sidebar.warning("当前筛选无数据")

# ================= 4. 地图生成 =================
# 计算地图中心点
# 强制设定为北建大大兴校区中心点 (高德坐标系 GCJ-02)
center_lat, center_lon = 39.748, 116.286

# 使用高德底图 (必须使用高德底图才不会有坐标偏移)
amap_tiles = 'https://webrd02.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}'

m = folium.Map(
    location=[center_lat, center_lon],
    zoom_start=16,
    tiles=amap_tiles,
    attr='高德地图'
)

# 颜色与图标映射逻辑 (Font Awesome 图标)
def get_icon_info(category):
    if '餐饮' in str(category):
        return 'red', 'cutlery'      # 餐厅图标
    elif '学习' in str(category) or '游' in str(category):
        return 'blue', 'book'        # 书本图标
    elif '居住' in str(category):
        return 'green', 'home'       # 房子图标
    elif '服务' in str(category):
        return 'orange', 'info-sign' # 信息图标
    else:
        return 'gray', 'map-marker'  # 默认图标

# 遍历数据添加点位
for index, row in filtered_df.iterrows():
    marker_color, icon_name = get_icon_info(row['一级分类'])
    
    # 优雅地处理缺失值
    name = row['名称'] if pd.notna(row['名称']) else '未知设施'
    building = row['所在楼宇/区域'] if pd.notna(row['所在楼宇/区域']) else '未知区域'
    time = row['开放时间'] if pd.notna(row['开放时间']) else '未提供'
    audience = row['适用人群'] if pd.notna(row['适用人群']) else '未知'
    source = row['数据来源'] if pd.notna(row['数据来源']) else '未知'

    # 构建精美弹窗
    popup_html = f"""
    <div style="width:220px; font-family: 'Microsoft YaHei', sans-serif;">
        <h4 style="margin-bottom:5px; color:{marker_color};">{name}</h4>
        <p style="margin:3px 0;"><b>分类:</b> {row['一级分类']}</p>
        <p style="margin:3px 0;"><b>位置:</b> {building}</p>
        <p style="margin:3px 0;"><b>时间:</b> {time}</p>
        <p style="margin:3px 0;"><b>人群:</b> {audience}</p>
        <p style="margin:3px 0; font-size:12px; color:gray;">来源: {source}</p>
    </div>
    """

    folium.Marker(
        location=[row['纬度'], row['经度']],
        popup=folium.Popup(popup_html, max_width=250),
        tooltip=f"{name} ({row['一级分类']})", 
        # 这里使用了 fontawesome 前缀，调用自定义图标
        icon=folium.Icon(color=marker_color, icon=icon_name, prefix='fa')
    ).add_to(m)

# ================= 5. 主页面标签页布局 =================
tab1, tab2 = st.tabs(["🗺️ 交互地图展示", "📊 详细数据表"])

with tab1:
    st.subheader("📍 空间分布图")
    # 渲染地图
    folium_static(m, width=1200, height=600)

with tab2:
    st.subheader("📋 设施明细数据")
    st.dataframe(filtered_df, use_container_width=True)