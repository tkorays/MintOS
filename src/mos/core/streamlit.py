"""Streamlit integration for MOS plugins.

This module defines the data structures for plugin Streamlit page registration.
Plugins can register their Streamlit pages through the `register_streamlit`
field in PluginDefinition.

Example:
    ```python
    from mos.core.streamlit import StreamlitPageDef, StreamlitPluginInfo

    def telegram_viewer_page():
        import streamlit as st
        st.title("新闻查看")
        # ... page logic

    def register_streamlit() -> StreamlitPluginInfo:
        return StreamlitPluginInfo(
            name="财联社电报",
            icon="📰",
            pages=[
                StreamlitPageDef(
                    func=telegram_viewer_page,
                    title="新闻查看",
                    icon="📰",
                ),
            ],
        )
    ```
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class StreamlitPageDef:
    """Definition of a single Streamlit page within a plugin.

    Attributes:
        func: The page function that contains the Streamlit logic.
        title: Page title displayed in the navigation menu (二级菜单).
        icon: Page icon (emoji or Material symbol).
        url_path: Optional URL path. If not provided, Streamlit infers from title.
    """

    func: Callable
    title: str
    icon: str
    url_path: Optional[str] = None


@dataclass
class StreamlitPluginInfo:
    """Information about a plugin's Streamlit integration.

    Attributes:
        name: Plugin name displayed in the main navigation (一级菜单).
        icon: Plugin icon (emoji or Material symbol).
        pages: List of Streamlit pages provided by this plugin.
        description: Optional description shown on plugin home page.
    """

    name: str
    icon: str
    pages: list[StreamlitPageDef]
    description: Optional[str] = None
