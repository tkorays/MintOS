# AGENT.md - MOS 开发规范

## 项目概述

MOS 是一个基于 Python 的插件化框架，提供核心基础设施和插件管理能力。项目使用 entry_points 机制实现插件架构，支持插件的独立安装和管理。

## 技术栈

- **Python**: 3.13+（见 `.python-version`）
- **包管理**: uv（项目根目录有 `uv.lock`）
- **构建系统**: setuptools（`pyproject.toml` 中 `[build-system]`）
- **测试框架**: unittest（`pytest` 作为运行器，测试文件在 `test/` 目录）
- **Linter**: ruff（通过 pre-commit 和命令行运行）
- **类型系统**: dataclass + Enum + pydantic-settings
- **日志**: loguru
- **CLI**: Click（入口 `mos`）
- **插件机制**: Python entry_points（`importlib.metadata`）

## 项目结构

```
src/mos/
├── core/           # 核心模块
│   ├── config.py   # 配置管理
│   ├── logging.py  # 日志模块
│   ├── plugin.py   # 插件管理
│   ├── mcp.py      # MCP 协议支持
│   ├── baseconfig.py # 基础配置类
│   ├── resource.py # 资源抽象
│   ├── grafana/    # Grafana 集成
│   ├── llm/        # LLM API 抽象
│   ├── dataflow/   # 数据流抽象
│   └── task/       # 后台任务管理
│       ├── types.py         # 任务类型定义
│       ├── registry.py      # 任务注册表
│       ├── scheduler.py     # 任务调度器（基于 APScheduler）
│       ├── event_bus.py     # 事件总线
│       ├── process_manager.py # 进程管理器
│       ├── manager.py       # 统一任务管理器
│       └── storage/         # 存储后端
│           ├── base.py      # 存储抽象接口
│           └── file.py      # 文件系统存储
├── cli/            # 命令行工具
│   ├── mos.py      # Click CLI 入口
│   ├── config.py   # 配置命令
│   ├── init.py     # 初始化命令
│   ├── plugin.py   # 插件管理命令
│   ├── mcp.py      # MCP 命令
│   └ task.py       # 任务管理命令
└── __init__.py     # 包入口

tests/              # 测试目录
plugins/            # 插件目录（被 .gitignore 忽略）
├── mos_agent/      # Agent 插件（独立仓库）
├── mos_quant/      # Quant 插件（独立仓库）
└── mos_wiki/       # Wiki 插件（独立仓库）
```

## 开发环境搭建

```bash
# 安装 uv（如果尚未安装）
pip install uv

# 创建虚拟环境并安装依赖
uv sync

# 安装开发依赖
uv sync --extra dev

# 安装 pre-commit hooks
uv run pre-commit install

# 安装插件（开发模式）
uv pip install -e plugins/mos_agent -e plugins/mos_quant -e plugins/mos_wiki
```

## 常用命令

### 运行 CLI

```bash
# 查看帮助
uv run mos --help

# 查看已加载插件
uv run mos plugin list

# 初始化配置
uv run mos init

# 配置管理
uv run mos config --help

# 后台任务管理
uv run mos task --help           # 查看任务命令帮助
uv run mos task list             # 列出所有已注册任务
uv run mos task status           # 查看任务调度器状态
uv run mos task start            # 启动任务调度器（前台模式）
uv run mos task start --daemon   # 启动任务调度器（守护进程模式）
uv run mos task stop             # 停止守护进程
```

### 运行测试

```bash
# 运行所有测试
uv run pytest tests/

# 运行单个测试文件
uv run pytest tests/test_database.py

# 使用 unittest 直接运行
uv run python -m pytest tests/ -v
```

### Lint 和代码格式化

```bash
# 使用 ruff 检查代码
uv run ruff check src/ tests/

# 使用 ruff 自动修复
uv run ruff check --fix src/ tests/

# 运行 pre-commit（对所有文件）
uv run pre-commit run --all-files
```

## 代码规范

### 命名约定

- **类名**: PascalCase（如 `PluginDefinition`、`PluginRegistry`）
- **函数/方法**: snake_case（如 `load_entry_point_plugins`、`get_config`）
- **常量/枚举**: PascalCase 枚举类 + UPPER_SNAKE_CASE 成员
- **私有成员**: 单下划线前缀（如 `_registry`、`_plugins`）
- **模块名**: snake_case（如 `plugin.py`、`config.py`）

### 类型系统

- 数据模型使用 `@dataclass`（如 `PluginDefinition`、`ExternalPluginResult`）
- 配置使用 `pydantic` 的 `BaseModel` 和 `BaseSettings`
- 类型注解必须完整，使用 `typing` 模块

### 架构约定

- **核心层（core/）** 只定义抽象接口和基础设施，不依赖具体插件
- **CLI 层（cli/）** 提供命令行工具，通过 entry_points 加载插件
- **插件机制**：
  - 插件通过 `pyproject.toml` 声明 entry_points
  - 主程序通过 `importlib.metadata.entry_points()` 发现插件
  - 插件必须提供 `describe_plugin()` 函数返回 `PluginDefinition`
  - 插件可以注册 CLI 命令、MCP 工具、配置、后台任务等

### 配置管理

- 环境变量前缀：`ZQUANT_`（或 `MOS_`）
- 嵌套分隔符：`__`（如 `MOS_PLUGIN__DISABLED_PLUGINS=quant,wiki`）
- 配置文件路径：`~/.mos/config.json`
- `.env` 文件用于本地开发（不提交到版本控制）

### 日志规范

- 使用 `loguru`（通过 `mos.core.logging` 模块）
- 获取 logger：`from mos.core.logging import get_logger` → `logger = get_logger("module_name")`

### 测试规范

- 测试文件放在 `tests/` 目录，命名 `test_*.py`
- 使用 `unittest.TestCase` 编写测试类
- 每个测试类需要 `setUp()` 和 `tearDown()` 方法清理测试数据

### Pre-commit Hooks

项目配置了以下 pre-commit hooks：

1. **trailing-whitespace** - 移除行尾空白
2. **end-of-file-fixer** - 确保文件以换行符结尾
3. **check-yaml** - 验证 YAML 文件
4. **check-added-large-files** - 防止提交大文件
5. **ruff** - Python 代码检查和自动修复

## 插件开发规范

### 插件结构

```
mos-plugin/
├── pyproject.toml      # 包定义 + entry_points
├── README.md
├── .gitignore
└── src/
    └── mos_plugin/
        ├── __init__.py # describe_plugin() 入口
        ├── cli/        # CLI 命令
        └── core/       # 插件核心逻辑
```

### pyproject.toml 配置

```toml
[project]
name = "mos-plugin"
version = "0.1.0"
dependencies = [
    "mos-core>=0.1.0",  # 声明对主程序的依赖
    # 插件自己的依赖
]

[project.entry-points."mos.plugins"]
plugin_name = "mos_plugin:describe_plugin"
```

### describe_plugin() 函数

```python
from mos.core.plugin import PluginDefinition

def describe_plugin() -> PluginDefinition:
    """插件入口点函数。"""
    from mos_plugin.cli import plugin_cli
    from mos_plugin.core.config import get_config

    return PluginDefinition(
        name="plugin_name",
        command=plugin_cli,
        get_config=get_config,
        register_tasks=register_plugin_tasks,  # 可选：注册后台任务
        register_streamlit=register_streamlit,  # 可选：注册 Streamlit 页面
    )
```

## Streamlit Web 页面开发规范

插件可以注册 Streamlit Web 页面，在统一的 `mos streamlit` 界面中展示。

### 页面注册流程

1. **创建页面函数**：将 Streamlit 页面代码封装为函数
2. **实现注册函数**：返回 `StreamlitPluginInfo` 信息
3. **在 describe_plugin 中注册**：添加 `register_streamlit` 字段

### 页面函数示例

```python
# mos_plugin/web/pages/my_page.py

def my_page():
    """页面函数，不要调用 st.set_page_config"""
    import streamlit as st

    st.title("📊 我的页面")
    st.markdown("---")

    # 页面逻辑
    ...
```

**注意**：页面函数内部**不要调用** `st.set_page_config`，它由 MOS 主入口统一设置。

### 注册函数示例

```python
# mos_plugin/web/streamlit_register.py

from mos.core.streamlit import StreamlitPageDef, StreamlitPluginInfo

def register_streamlit() -> StreamlitPluginInfo:
    """注册插件的 Streamlit 页面"""
    from mos_plugin.web.pages.my_page import my_page
    from mos_plugin.web.pages.another_page import another_page

    return StreamlitPluginInfo(
        name="我的插件",       # 一级菜单名称
        icon="📊",            # 插件图标
        description="插件描述", # 可选
        pages=[
            StreamlitPageDef(
                func=my_page,
                title="页面一",  # 二级菜单名称
                icon="📈",
            ),
            StreamlitPageDef(
                func=another_page,
                title="页面二",
                icon="📉",
            ),
        ],
    )
```

### 导航结构

MOS Streamlit 的导航结构：

- **一级菜单**：插件入口（`StreamlitPluginInfo.name`）
- **二级菜单**：插件页面（`StreamlitPageDef.title`）

例如：
```
主页
财联社电报
  └─ 新闻查看
量化交易
  ├─ 数据管理
  ├─ K线查看
  ├─ 回测运行
  └─ 实盘交易
```

### 依赖配置

插件需要在 `pyproject.toml` 中声明 streamlit 依赖：

```toml
[project.optional-dependencies]
web = [
    "streamlit>=1.30.0",
    "pandas>=2.0.0",
]
```

安装方式：
```bash
pip install "mos-plugin[web]"
```

## 后台任务开发规范

### 任务类型

MOS 支持三种任务触发类型：

1. **Cron 任务**: 使用标准 cron 表达式定时执行
2. **Interval 任务**: 按固定时间间隔执行
3. **Event 任务**: 由事件触发执行

### 注册任务函数

插件通过 `register_tasks()` 函数注册后台任务：

```python
from mos.core.task import TaskDefinition, TaskTriggerType, TaskRegistry, EventBus

def register_plugin_tasks(registry: TaskRegistry, event_bus: EventBus):
    """注册插件的后台任务"""

    # Cron 任务示例：每天早上 9 点执行
    registry.register(TaskDefinition(
        name="plugin.daily_task",
        func=daily_task_func,
        trigger_type=TaskTriggerType.CRON,
        trigger_config={"cron": "0 9 * * 1-5"},
        description="每日定时任务",
    ))

    # Interval 任务示例：每 5 分钟执行
    registry.register(TaskDefinition(
        name="plugin.interval_task",
        func=interval_task_func,
        trigger_type=TaskTriggerType.INTERVAL,
        trigger_config={"minutes": 5},
        description="间隔执行任务",
    ))

    # Event 任务示例：响应事件
    registry.register(TaskDefinition(
        name="plugin.event_task",
        func=event_task_func,
        trigger_type=TaskTriggerType.EVENT,
        trigger_config={"event_type": "data_update"},
        description="事件驱动任务",
    ))
    event_bus.subscribe("data_update", "plugin.event_task")
```

### 任务函数定义

任务函数应该简洁、无阻塞：

```python
def daily_task_func():
    """每日任务函数"""
    from mos.core.logging import get_logger
    logger = get_logger("plugin")

    logger.info("开始执行每日任务")
    try:
        # 执行任务逻辑
        ...
        logger.info("每日任务执行成功")
    except Exception as e:
        logger.error(f"每日任务执行失败: {e}")

def event_task_func(event_data):
    """事件驱动任务函数（接收事件数据）"""
    from mos.core.logging import get_logger
    logger = get_logger("plugin")

    logger.info(f"收到事件数据: {event_data}")
    # 处理事件
    ...
```

### 任务命名规范

- 使用 `插件名.任务名` 格式（如 `quant.update_stock_list`）
- 任务名使用 snake_case
- 描述清晰说明任务用途

### 存储后端

任务状态和执行日志存储在 `~/.mos/tasks/` 目录：
- 任务定义：`tasks.json`
- 执行日志：`logs/{task_name}.jsonl`
- 守护进程状态：`daemon_status.json`

支持可插拔存储后端，后续可扩展至 DuckDB 或其他数据库。

## 注意事项

- **插件目录**（`plugins/`）被 `.gitignore` 忽略，插件应独立提交到 Git 仓库
- **依赖隔离**：主仓库只包含核心框架依赖，插件依赖在各自的 `pyproject.toml` 中管理
- **entry_points**：插件必须通过 entry_points 注册，不支持其他加载方式
- **禁用插件**：通过 `mos plugin disable <name>` 或配置 `disabled_plugins` 实现
