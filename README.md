# MOS

MOS 是一个基于 Python 的插件化框架，提供核心基础设施和插件管理能力。

## 核心特性

- **插件架构**：基于 Python entry_points 的标准插件机制
- **依赖隔离**：每个插件独立管理依赖，主仓库只包含核心框架
- **灵活安装**：插件可通过 pip 安装，支持从 Git、PyPI 或本地安装

## 可用插件

MOS 通过插件扩展功能，目前已有的插件：

| 插件 | 功能 | 安装方式 |
|------|------|----------|
| **mos-quant** | 量化交易框架，支持数据采集、回测、实盘交易 | `pip install mos-quant` |
| **mos-wiki** | 知识库管理系统，支持 Markdown 知识库管理 | `pip install mos-wiki` |
| **mos-agent** | 智能体系统，支持 LLM Agent 开发 | `pip install mos-agent` |

## 快速开始

```bash
# 安装核心框架
pip install mos

# 安装插件（从 GitHub）
pip install git+https://github.com/yourname/mos_quant.git
pip install git+https://github.com/yourname/mos_wiki.git
pip install git+https://github.com/yourname/mos_agent.git

# 查看已加载插件
mos plugin list
```
