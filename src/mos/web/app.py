"""MOS Streamlit 主入口文件."""
import streamlit as st

from mos.core.config import get_config
from mos.core.plugin import get_registry, load_entry_point_plugins
from mos.core.streamlit import StreamlitPluginInfo

# 设置页面配置
st.set_page_config(
    page_title="MOS 管理平台",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 加载所有插件（仅首次加载，避免重复注册）
registry = get_registry()
if len(registry.list_names()) == 0:
    cfg = get_config()
    disabled_plugins = list(cfg.plugin.disabled_plugins)
    load_entry_point_plugins(disabled_plugins)

# 定义主页函数
def home_page():
    """MOS 主页"""
    st.title("🏠 MOS 管理平台")
    st.markdown("---")

    st.header("欢迎使用 MOS 管理平台")
    st.markdown("""
    MOS 是一个插件化管理平台，提供多种功能模块。

    ### 已安装插件

    请在左侧导航栏选择相应插件模块。
    """)

    # 显示已注册插件列表
    registry = get_registry()
    plugins = registry.all()

    if plugins:
        st.subheader("插件列表")
        for plugin in plugins:
            if plugin.register_streamlit:
                try:
                    info = plugin.register_streamlit()
                    st.markdown(f"- **{info.icon} {info.name}**")
                    if info.description:
                        st.markdown(f"  {info.description}")
                    for page in info.pages:
                        st.markdown(f"  - {page.icon} {page.title}")
                except Exception as e:
                    st.error(f"加载插件 {plugin.name} Streamlit 信息失败: {e}")

    st.sidebar.markdown("---")
    st.sidebar.markdown("### 系统信息")
    st.sidebar.info(f"已加载 {len(plugins)} 个插件")


# 收集所有插件的 Streamlit 页面
def build_navigation():
    """构建导航结构"""
    registry = get_registry()
    plugin_pages = {}

    for plugin in registry.all():
        if plugin.register_streamlit:
            try:
                info: StreamlitPluginInfo = plugin.register_streamlit()
                # 为每个插件创建页面列表
                pages = []
                for page_def in info.pages:
                    pages.append(
                        st.Page(
                            page_def.func,
                            title=page_def.title,
                            icon=page_def.icon,
                            url_path=page_def.url_path,
                        )
                    )
                plugin_pages[info.name] = pages
            except Exception as e:
                from mos.core.logging import get_logger
                logger = get_logger("mos.streamlit")
                logger.error(f"加载插件 {plugin.name} Streamlit 页面失败: {e}")

    return plugin_pages


# 构建导航并运行
plugin_pages = build_navigation()

# 添加主页
home = st.Page(home_page, title="主页", icon="🏠", url_path="home")

# 将主页和插件页面组合
# Streamlit 的 navigation 支持字典形式，键为分组名称
all_pages = {"主页": [home]}
all_pages.update(plugin_pages)

# 创建导航
pg = st.navigation(all_pages, position="sidebar")
pg.run()
