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
│   └── dataflow/   # 数据流抽象
├── cli/            # 命令行工具
│   ├── mos.py      # Click CLI 入口
│   ├── config.py   # 配置命令
│   ├── init.py     # 初始化命令
│   ├── plugin.py   # 插件管理命令
│   └── mcp.py      # MCP 命令
└── __init__.py     # 包入口

test/               # 测试目录
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
```

### 运行测试

```bash
# 运行所有测试
uv run pytest test/

# 运行单个测试文件
uv run pytest test/test_database.py

# 使用 unittest 直接运行
uv run python -m pytest test/ -v
```

### Lint 和代码格式化

```bash
# 使用 ruff 检查代码
uv run ruff check src/ test/

# 使用 ruff 自动修复
uv run ruff check --fix src/ test/

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
  - 插件可以注册 CLI 命令、MCP 工具、配置等

### 配置管理

- 环境变量前缀：`ZQUANT_`（或 `MOS_`）
- 嵌套分隔符：`__`（如 `MOS_PLUGIN__DISABLED_PLUGINS=quant,wiki`）
- 配置文件路径：`~/.mos/config.json`
- `.env` 文件用于本地开发（不提交到版本控制）

### 日志规范

- 使用 `loguru`（通过 `mos.core.logging` 模块）
- 获取 logger：`from mos.core.logging import get_logger` → `logger = get_logger("module_name")`

### 测试规范

- 测试文件放在 `test/` 目录，命名 `test_*.py`
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
    "mos>=0.1.0",  # 声明对主程序的依赖
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
    )
```

## 注意事项

- **插件目录**（`plugins/`）被 `.gitignore` 忽略，插件应独立提交到 Git 仓库
- **依赖隔离**：主仓库只包含核心框架依赖，插件依赖在各自的 `pyproject.toml` 中管理
- **entry_points**：插件必须通过 entry_points 注册，不支持其他加载方式
- **禁用插件**：通过 `mos plugin disable <name>` 或配置 `disabled_plugins` 实现
