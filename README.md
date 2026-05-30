# 个人智能日程管理系统

一款基于 Python + Tkinter 开发的桌面端日程管理工具，集成了任务管理、习惯打卡、日历视图、天气同步、提醒设置、统计分析与个性化配置等功能，旨在帮助用户更高效地管理日常学习与生活安排。

---

## 项目简介

随着学习与生活节奏不断加快，如何高效安排任务、养成良好习惯、合理设置提醒，成为许多人日常管理中的核心需求。  
本项目围绕“轻量、直观、可扩展”的设计目标，开发了一款基于桌面端的智能日程管理系统，提供任务记录、状态切换、习惯追踪、提醒管理、天气信息同步和统计分析等能力。

项目采用 `Tkinter` 构建图形界面，配合本地 JSON 数据存储，实现了无需联网也可使用的核心日程管理功能。

---

## 功能特点

- **任务管理**
  - 新增、编辑、删除日程/任务
  - 支持任务完成状态切换
  - 支持任务备注记录
  - 支持任务颜色分类与可视化展示

- **习惯打卡**
  - 支持每日习惯记录
  - 可查看连续打卡情况
  - 便于培养学习、运动、早睡等长期习惯

- **日历与时间视图**
  - 可视化查看日程安排
  - 结合时间线展示每日任务

- **提醒设置**
  - 支持设置提醒事项
  - 可开启/关闭提醒功能
  - 支持提前提醒时间配置

- **天气同步**
  - 支持配置城市
  - 可同步天气信息，便于结合天气安排外出或活动

- **统计分析**
  - 统计任务完成情况
  - 统计习惯打卡数据
  - 辅助用户了解自身执行效率

- **个性化设置**
  - 可修改昵称
  - 可设置头像
  - 可调整天气城市等配置项

- **本地数据保存**
  - 所有数据自动保存到本地 JSON 文件
  - 程序重启后数据仍可保留

---

## 项目截图 

### 主页面
![主页面](assets/screenshots/主页面.png)

### 任务清单页面
![任务清单页面](assets/screenshots/任务清单页面.png)

### 习惯打卡页面
![习惯打卡页面](assets/screenshots/习惯打卡页面.png)

### 提醒设置页面
![提醒设置页面](assets/screenshots/提醒设置页面.png)

### 天气同步页面
![天气同步页面](assets/screenshots/天气同步页面.png)

### 统计分析页面
![统计分析页面](assets/screenshots/统计分析页面.png)

### 设置中心页面
![设置中心页面](assets/screenshots/设置中心页面.png)

---

## 技术栈

- Python 3
- Tkinter
- ttk
- requests
- pillow
- plyer

---

## 运行环境

- Python 3.9 及以上
- Windows / macOS / Linux
- 建议安装依赖：

```bash
pip install requests plyer pillow
快速开始
1. 克隆项目
git clone https://github.com/6443ren/smart-schedule-manager.git
cd smart-schedule-manager
2. 安装依赖
pip install -r requirements.txt
如果你的环境中依赖未完整安装，也可手动执行：

pip install requests plyer pillow
3. 运行程序
python smart_schedule_manager.py
项目结构
smart-schedule-manager/
├── assets/
│   └── screenshots/
│       ├── home.png
│       ├── 主页面.png
│       ├── 习惯打卡页面.png
│       ├── 任务清单页面.png
│       ├── 天气同步页面.png
│       ├── 提醒设置页面.png
│       ├── 统计分析页面.png
│       └── 设置中心页面.png
├── .gitignore
├── LICENSE
├── README.md
├── requirements.txt
└── smart_schedule_manager.py
数据存储说明
项目运行时会自动在程序目录下生成并使用以下数据文件：

smart_schedule_data.json
该文件用于保存任务、提醒、习惯记录、用户设置等内容。

如果你不希望将其提交到 Git 仓库，可将其加入 .gitignore：

smart_schedule_data.json
依赖说明
程序内会检查以下第三方库是否可用：

requests
plyer
pillow
若提示缺少依赖，请执行：

pip install requests plyer pillow
使用说明
任务管理
在“任务清单”页面中，可对日程进行新增、编辑、删除、完成状态切换等操作。

习惯打卡
在“习惯打卡”页面中，可记录每日习惯完成情况，帮助养成长期自律习惯。

提醒管理
在“提醒设置”页面中，可配置提醒事项与提醒时间，程序运行时会自动检测并弹出通知。

天气同步
在“天气同步”页面中，可设置城市并同步天气信息，用于辅助日程规划。

统计分析
在“统计分析”页面中，可查看任务、习惯等数据统计结果，帮助评估执行情况。

设置中心
在“设置中心”页面中，可修改昵称、头像、天气城市等个性化配置。
