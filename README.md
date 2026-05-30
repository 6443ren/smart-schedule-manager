# smart-schedule-manager

一个基于 Python Tkinter 开发的个人智能日程管理系统，具备任务管理、提醒通知、习惯打卡、日历查看、统计分析和天气同步等功能，使用本地 JSON 文件完成数据持久化。

## 项目特性

- 任务管理：支持新增、修改、删除、完成/未完成标记
- 提醒通知：支持定时提醒、提前提醒、系统通知和弹窗提示
- 习惯打卡：支持自定义习惯、每日打卡和连续天数统计
- 日历查看：支持月视图切换和日期任务标记
- 统计分析：支持任务完成率和分类统计展示
- 天气同步：接入 Open-Meteo 免费天气接口，无需 API Key
- 本地存储：使用 JSON 文件保存任务、打卡记录和设置
- 跨平台：可在 Windows、macOS 和 Linux 环境运行

## 技术栈

- Python 3.x
- Tkinter
- requests
- plyer
- pillow
- JSON 本地数据存储

## 项目结构

```text
smart-schedule-manager/
├── smart_schedule_manager.py
├── requirements.txt
├── README.md
├── LICENSE
├── .gitignore
└── smart_schedule_data.json
安装依赖
建议先创建虚拟环境，再安装依赖：

pip install -r requirements.txt
如果你没有使用 requirements.txt，也可以手动安装：

pip install requests plyer pillow
运行项目
python smart_schedule_manager.py
如果你的主程序文件名不是这个，请将命令改成对应的文件名。

功能说明
1. 任务管理
新增任务
编辑任务
删除任务
标记完成状态
自动保存到本地 JSON
2. 提醒通知
根据任务时间进行提醒
支持提前提醒
触发系统通知和弹窗提示
3. 习惯打卡
支持自定义习惯名称
每日打卡记录
连续天数统计
打卡状态可视化
4. 日历查看
月历展示
日期切换
任务日期标记
点击日期查看对应任务
5. 统计分析
任务完成率统计
任务分类统计
图表展示
6. 天气同步
接入 Open-Meteo API
展示天气信息
无需额外申请 API Key
数据说明
程序会在本地生成并维护一个 JSON 数据文件，用于保存：

任务列表
打卡记录
用户设置
日程状态
如果数据文件损坏，程序会自动重建。

注意事项
程序首次运行时可能需要几秒钟初始化界面和数据文件
提醒功能依赖后台线程，请保持程序运行
如果系统缺少依赖，请先执行 pip install -r requirements.txt
截图展示

