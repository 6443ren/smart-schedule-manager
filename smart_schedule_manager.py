
# -*- coding: utf-8 -*-
"""
个人智能日程管理系统 - 功能完整可运行版
========================================================
依赖安装：
    pip install requests plyer pillow

运行：
    python smart_schedule_complete.py

功能：
1. 任务管理：新增、修改、删除、标记完成/未完成，选中自动回填编辑区，立即保存 JSON。
2. 数据持久化：任务、打卡记录、设置统一保存到 JSON，启动自动加载，文件损坏自动重建。
3. 定时提醒：后台线程监听任务时间，支持提前提醒，系统通知 + 弹窗 + 提示音。
4. 习惯打卡：可添加自定义习惯，每日打卡，连续天数统计，圆点状态可视化。
5. 日历功能：月视图、任务日期标记、月份切换、点击日期跳转。
6. 统计图表：任务完成率柱状图、任务分类饼图，Tkinter Canvas 原生显示。
7. 天气同步：Open-Meteo 免费天气 API，无需 API Key。
"""

import calendar
import json
import os
import platform
import queue
import sys
import threading
import time
import tkinter as tk
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from tkinter import messagebox, ttk
from tkinter import font as tkfont
from uuid import uuid4

try:
    import requests
except Exception:
    requests = None

try:
    from plyer import notification
except Exception:
    notification = None

try:
    from PIL import Image, ImageDraw, ImageTk
except Exception:
    Image = ImageDraw = ImageTk = None


APP_NAME = "个人智能日程管理系统"
def get_app_dir():
    """兼容源码运行和 PyInstaller EXE 运行的数据目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


APP_DIR = get_app_dir()
DATA_FILE = APP_DIR / "smart_schedule_data.json"


COLORS = {
    "bg": "#F5F8FC",
    "sidebar": "#F8FAFD",
    "card": "#FFFFFF",
    "card2": "#FBFCFE",
    "line": "#E6EDF5",
    "text": "#1F2937",
    "sub": "#7A869A",
    "blue": "#5BA7FF",
    "blue_light": "#EAF4FF",
    "pink": "#FF6B9A",
    "pink_light": "#FFEAF1",
    "green": "#52C989",
    "green_light": "#EAF9F0",
    "orange": "#FFB547",
    "orange_light": "#FFF3DD",
    "purple": "#8B7CF6",
    "purple_light": "#F0EEFF",
    "red": "#FF5B70",
    "red_light": "#FFE9ED",
    "gray": "#A8B2C1",
}

TYPE_COLORS = {
    "学习": ("#5BA7FF", "#EAF4FF"),
    "工作": ("#52C989", "#EAF9F0"),
    "生活": ("#FFB547", "#FFF3DD"),
    "其他": ("#8B7CF6", "#F0EEFF"),
}

PRIORITY_COLORS = {
    "高": ("#FF5B70", "#FFE9ED"),
    "中": ("#FFB547", "#FFF3DD"),
    "低": ("#52C989", "#EAF9F0"),
}


def today_str():
    return date.today().strftime("%Y-%m-%d")


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def center_window(win, width=1200, height=800):
    win.update_idletasks()
    sw = win.winfo_screenwidth()
    sh = win.winfo_screenheight()
    x = int((sw - width) / 2)
    y = int((sh - height) / 2)
    win.geometry(f"{width}x{height}+{x}+{y}")


def parse_datetime(date_text, time_text):
    return datetime.strptime(f"{date_text} {time_text}", "%Y-%m-%d %H:%M")


def safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def format_cn_date(d=None):
    d = d or date.today()
    week_names = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    return f"{d.year}年{d.month}月{d.day}日  {week_names[d.weekday()]}"


def simple_lunar_text(d=None):
    """
    简化农历风格显示。
    不额外引入农历库，避免作业运行环境依赖过多。
    """
    d = d or date.today()
    months = ["正", "二", "三", "四", "五", "六", "七", "八", "九", "十", "冬", "腊"]
    nums = "一二三四五六七八九"
    day = d.day
    if day <= 9:
        day_text = "初" + nums[day - 1]
    elif day == 10:
        day_text = "初十"
    elif day < 20:
        day_text = "十" + nums[day - 11]
    elif day == 20:
        day_text = "二十"
    elif day < 30:
        day_text = "廿" + nums[day - 21]
    else:
        day_text = "三十"
    return f"农历{months[(d.month - 1) % 12]}月{day_text}"


def weather_code_text(code):
    mapping = {
        0: "晴",
        1: "大部晴朗",
        2: "多云",
        3: "阴",
        45: "雾",
        48: "雾凇",
        51: "小毛毛雨",
        53: "毛毛雨",
        55: "大毛毛雨",
        61: "小雨",
        63: "中雨",
        65: "大雨",
        71: "小雪",
        73: "中雪",
        75: "大雪",
        80: "阵雨",
        81: "中等阵雨",
        82: "强阵雨",
        95: "雷暴",
    }
    return mapping.get(code, "未知天气")


def weather_icon(desc):
    desc = str(desc)
    if "雨" in desc:
        return "☔"
    if "雪" in desc:
        return "❄"
    if "雷" in desc:
        return "⚡"
    if "云" in desc or "阴" in desc:
        return "☁"
    return "☀"


@dataclass
class Task:
    id: str = field(default_factory=lambda: uuid4().hex)
    title: str = ""
    task_date: str = field(default_factory=today_str)
    task_time: str = "09:00"
    priority: str = "中"
    category: str = "学习"
    note: str = ""
    completed: bool = False
    reminder_enabled: bool = True
    remind_minutes: int = 5
    reminded: bool = False
    created_at: str = field(default_factory=now_str)

    @property
    def dt(self):
        try:
            return parse_datetime(self.task_date, self.task_time)
        except Exception:
            return None

    def to_dict(self):
        return asdict(self)

    @staticmethod
    def from_dict(data):
        return Task(
            id=data.get("id", uuid4().hex),
            title=data.get("title", data.get("content", "")),
            task_date=data.get("task_date", data.get("item_date", today_str())),
            task_time=data.get("task_time", data.get("item_time", "09:00")),
            priority=data.get("priority", "中"),
            category=data.get("category", "学习"),
            note=data.get("note", ""),
            completed=bool(data.get("completed", False)),
            reminder_enabled=bool(data.get("reminder_enabled", True)),
            remind_minutes=safe_int(data.get("remind_minutes", 5), 5),
            reminded=bool(data.get("reminded", False)),
            created_at=data.get("created_at", now_str()),
        )


@dataclass
class Habit:
    id: str = field(default_factory=lambda: uuid4().hex)
    name: str = ""
    icon: str = "⭐"
    color: str = "#5BA7FF"
    records: list = field(default_factory=list)
    created_at: str = field(default_factory=now_str)

    def to_dict(self):
        return asdict(self)

    @staticmethod
    def from_dict(data):
        records = data.get("records", [])
        if not isinstance(records, list):
            records = []
        return Habit(
            id=data.get("id", uuid4().hex),
            name=data.get("name", ""),
            icon=data.get("icon", "⭐"),
            color=data.get("color", "#5BA7FF"),
            records=sorted(set(records)),
            created_at=data.get("created_at", now_str()),
        )

    def checked_today(self):
        return today_str() in self.records

    def toggle_today(self):
        t = today_str()
        if t in self.records:
            self.records.remove(t)
            return False
        self.records.append(t)
        self.records = sorted(set(self.records))
        return True

    def streak(self):
        record_set = set(self.records)
        d = date.today()
        count = 0
        while d.strftime("%Y-%m-%d") in record_set:
            count += 1
            d -= timedelta(days=1)
        return count


class DataManager:
    def __init__(self):
        self.tasks = []
        self.habits = []
        self.settings = {
            "username": "学习者",
            "avatar": "👤",
            "city": "杭州",
            "selected_date": today_str(),
        }

    def load(self):
        if not DATA_FILE.exists():
            self.create_default_data()
            self.save()
            return

        try:
            raw = json.loads(DATA_FILE.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("JSON 根对象不是字典")

            settings = raw.get("settings", {})
            if isinstance(settings, dict):
                self.settings.update(settings)

            tasks = raw.get("tasks", [])
            habits = raw.get("habits", [])
            self.tasks = [Task.from_dict(x) for x in tasks if isinstance(x, dict)]
            self.habits = [Habit.from_dict(x) for x in habits if isinstance(x, dict)]

            if not self.habits:
                self.habits = self.default_habits()
                self.save()

        except Exception:
            try:
                DATA_FILE.replace(DATA_FILE.with_suffix(".broken.json"))
            except Exception:
                pass
            self.create_default_data()
            self.save()

    def create_default_data(self):
        self.tasks = []
        self.habits = self.default_habits()
        self.settings = {
            "username": "学习者",
            "avatar": "👤",
            "city": "杭州",
            "selected_date": today_str(),
        }

    def default_habits(self):
        return [
            Habit(name="早起", icon="☀", color=COLORS["orange"]),
            Habit(name="喝水", icon="💧", color=COLORS["blue"]),
            Habit(name="阅读", icon="📖", color=COLORS["pink"]),
            Habit(name="运动", icon="🏃", color=COLORS["purple"]),
        ]

    def save(self):
        data = {
            "settings": self.settings,
            "tasks": [task.to_dict() for task in self.tasks],
            "habits": [habit.to_dict() for habit in self.habits],
            "saved_at": now_str(),
        }
        try:
            DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            return True
        except Exception as exc:
            messagebox.showerror("保存失败", f"数据保存失败：{exc}")
            return False

    def get_task(self, task_id):
        for task in self.tasks:
            if task.id == task_id:
                return task
        return None

    def get_habit(self, habit_id):
        for habit in self.habits:
            if habit.id == habit_id:
                return habit
        return None


class WeatherService:
    @staticmethod
    def fetch(city):
        if requests is None:
            raise RuntimeError("缺少 requests 库，请执行 pip install requests")

        geo_res = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1, "language": "zh", "format": "json"},
            timeout=10,
        )
        geo_res.raise_for_status()
        results = geo_res.json().get("results") or []
        if not results:
            raise RuntimeError(f"未找到城市：{city}")

        place = results[0]
        lat = place["latitude"]
        lon = place["longitude"]
        display_city = place.get("name", city)

        weather_res = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
                "timezone": "auto",
            },
            timeout=10,
        )
        weather_res.raise_for_status()
        current = weather_res.json().get("current", {})

        desc = weather_code_text(current.get("weather_code"))
        temp = current.get("temperature_2m", "--")
        humidity = current.get("relative_humidity_2m", "--")
        wind = current.get("wind_speed_10m", "--")

        tips = []
        if "雨" in desc:
            tips.append("记得带伞")
        try:
            if float(temp) >= 30:
                tips.append("防暑降温")
        except Exception:
            pass

        return {
            "city": display_city,
            "desc": desc,
            "icon": weather_icon(desc),
            "temp": temp,
            "humidity": humidity,
            "wind": wind,
            "tips": " / ".join(tips) if tips else "天气舒适，适合高效安排",
        }


class UI:
    @staticmethod
    def label(parent, text="", size=10, weight="normal", fg=None, bg=None, **kwargs):
        return tk.Label(
            parent,
            text=text,
            fg=fg or COLORS["text"],
            bg=bg or parent.cget("bg"),
            font=("Microsoft YaHei", size, weight),
            **kwargs,
        )

    @staticmethod
    def card(parent, bg=None):
        return tk.Frame(parent, bg=bg or COLORS["card"], highlightthickness=1, highlightbackground=COLORS["line"])

    @staticmethod
    def button(parent, text, command, bg=None, fg="white", width=None):
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=bg or COLORS["blue"],
            fg=fg,
            activebackground=bg or COLORS["blue"],
            activeforeground=fg,
            bd=0,
            relief="flat",
            cursor="hand2",
            padx=12,
            pady=7,
            width=width,
            font=("Microsoft YaHei", 10, "bold"),
        )

    @staticmethod
    def entry(parent, var=None, width=20):
        return tk.Entry(
            parent,
            textvariable=var,
            width=width,
            bd=0,
            bg="#F7F9FD",
            fg=COLORS["text"],
            insertbackground=COLORS["blue"],
            font=("Microsoft YaHei", 10),
        )

    @staticmethod
    def badge(parent, text, fg, bg):
        return tk.Label(
            parent,
            text=text,
            fg=fg,
            bg=bg,
            padx=8,
            pady=2,
            font=("Microsoft YaHei", 9, "bold"),
        )


class SmartScheduleApp:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_NAME)
        self.root.minsize(1000, 700)
        center_window(self.root, 1200, 800)
        self.root.configure(bg=COLORS["bg"])

        self.data = DataManager()
        self.data.load()

        self.current_page = "日程计划"
        self.selected_task_id = None
        self.weather_data = None
        self.calendar_year = date.today().year
        self.calendar_month = date.today().month
        self.current_schedule_view = "日视图"

        self.running = True
        self.reminder_queue = queue.Queue()
        self.normal_font = tkfont.Font(family="Microsoft YaHei", size=10)
        self.done_font = tkfont.Font(family="Microsoft YaHei", size=10, overstrike=1)

        self.setup_style()
        self.build_base_layout()
        self.show_page("日程计划")
        self.update_clock()

        threading.Thread(target=self.reminder_worker, daemon=True).start()
        self.poll_reminders()
        self.fetch_weather_async()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def setup_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("Treeview", rowheight=34, font=("Microsoft YaHei", 10), borderwidth=0)
        style.configure("Treeview.Heading", font=("Microsoft YaHei", 10, "bold"), background="#F7F9FD")
        style.map("Treeview", background=[("selected", COLORS["blue_light"])], foreground=[("selected", COLORS["text"])])
        style.configure("TCombobox", font=("Microsoft YaHei", 10), padding=4)

    def build_base_layout(self):
        self.sidebar = tk.Frame(self.root, width=230, bg=COLORS["sidebar"])
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y)
        self.sidebar.pack_propagate(False)

        self.main = tk.Frame(self.root, bg=COLORS["bg"])
        self.main.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.build_sidebar()

    def build_sidebar(self):
        top = tk.Frame(self.sidebar, bg=COLORS["sidebar"], padx=20, pady=24)
        top.pack(fill=tk.X)

        self.avatar_canvas = tk.Canvas(
            top,
            width=58,
            height=58,
            bg=COLORS["sidebar"],
            highlightthickness=0,
            cursor="hand2"
        )
        self.avatar_canvas.pack(side=tk.LEFT)
        self.avatar_canvas.create_oval(4, 4, 54, 54, fill=COLORS["pink_light"], outline="")
        self.avatar_text_item = self.avatar_canvas.create_text(
            29,
            30,
            text=self.data.settings.get("avatar", "👤"),
            font=("Microsoft YaHei", 25)
        )
        self.avatar_canvas.bind("<Button-1>", lambda event: self.open_avatar_picker_dialog())

        text = tk.Frame(top, bg=COLORS["sidebar"])
        text.pack(side=tk.LEFT, padx=12)

        # 昵称区域使用 Canvas，昵称过长时可按住左右拖动查看完整内容；
        # 点击但不拖动时，打开修改昵称窗口。
        self.greeting_canvas = tk.Canvas(
            text,
            width=126,
            height=28,
            bg=COLORS["sidebar"],
            highlightthickness=0,
            cursor="hand2"
        )
        self.greeting_canvas.pack(anchor="w")

        self.greeting_text_item = self.greeting_canvas.create_text(
            0,
            14,
            text=f"你好，{self.data.settings.get('username', '学习者')}",
            anchor="w",
            fill=COLORS["text"],
            font=("Microsoft YaHei", 13, "bold")
        )
        self.greeting_canvas.configure(scrollregion=self.greeting_canvas.bbox("all"))

        self._greeting_drag_start_x = 0
        self._greeting_drag_moved = False

        self.greeting_canvas.bind("<ButtonPress-1>", self.on_greeting_press)
        self.greeting_canvas.bind("<B1-Motion>", self.on_greeting_drag)
        self.greeting_canvas.bind("<ButtonRelease-1>", self.on_greeting_release)
        self.greeting_canvas.bind("<Shift-MouseWheel>", self.on_greeting_shift_mousewheel)

        UI.label(text, "点击昵称可修改", 9, fg=COLORS["sub"], bg=COLORS["sidebar"]).pack(anchor="w", pady=(4, 0))

        self.nav_buttons = {}
        nav_items = [
            ("日程计划", "📅"),
            ("任务清单", "☑"),
            ("提醒设置", "🔔"),
            ("习惯打卡", "🌱"),
            ("天气同步", "☁"),
            ("统计分析", "📊"),
            ("设置中心", "⚙"),
        ]

        nav = tk.Frame(self.sidebar, bg=COLORS["sidebar"], padx=14)
        nav.pack(fill=tk.X, pady=8)

        for name, icon in nav_items:
            btn = tk.Button(
                nav,
                text=f"{icon}   {name}",
                anchor="w",
                bd=0,
                relief="flat",
                cursor="hand2",
                padx=16,
                pady=12,
                font=("Microsoft YaHei", 12),
                bg=COLORS["sidebar"],
                fg=COLORS["text"],
                activebackground=COLORS["blue_light"],
                command=lambda n=name: self.show_page(n),
            )
            btn.pack(fill=tk.X, pady=4)
            self.nav_buttons[name] = btn

        bottom = tk.Frame(self.sidebar, bg=COLORS["sidebar"], padx=20, pady=18)
        bottom.pack(side=tk.BOTTOM, fill=tk.X)
        UI.label(bottom, "🌿 清新日程 · 自动保存", 10, fg=COLORS["sub"], bg=COLORS["sidebar"]).pack(anchor="w")
        UI.label(bottom, "任务 / 提醒 / 打卡 / 统计", 9, fg=COLORS["sub"], bg=COLORS["sidebar"]).pack(anchor="w", pady=(5, 0))

    def refresh_user_profile(self):
        """刷新左侧头像和问候语。"""
        username = self.data.settings.get("username", "学习者")
        avatar = self.data.settings.get("avatar", "👤") or "👤"

        try:
            if hasattr(self, "greeting_canvas") and self.greeting_canvas.winfo_exists():
                self.greeting_canvas.itemconfig(self.greeting_text_item, text=f"你好，{username}")
                self.greeting_canvas.configure(scrollregion=self.greeting_canvas.bbox("all"))
                self.greeting_canvas.xview_moveto(0)

            if hasattr(self, "avatar_canvas") and self.avatar_canvas.winfo_exists():
                self.avatar_canvas.itemconfig(self.avatar_text_item, text=avatar)
        except tk.TclError:
            pass

    def on_greeting_press(self, event):
        """记录昵称区域按下位置，用于区分点击和拖动。"""
        self._greeting_drag_start_x = event.x
        self._greeting_drag_moved = False
        try:
            self.greeting_canvas.scan_mark(event.x, event.y)
        except Exception:
            pass

    def on_greeting_drag(self, event):
        """昵称过长时，按住左右拖动查看完整文字。"""
        if abs(event.x - getattr(self, "_greeting_drag_start_x", 0)) > 3:
            self._greeting_drag_moved = True
        try:
            self.greeting_canvas.scan_dragto(event.x, event.y, gain=1)
        except Exception:
            pass

    def on_greeting_release(self, event):
        """点击昵称打开修改窗口；拖动时不弹窗。"""
        if not getattr(self, "_greeting_drag_moved", False):
            self.open_nickname_dialog()

    def on_greeting_shift_mousewheel(self, event):
        """Shift + 鼠标滚轮可横向查看长昵称。"""
        try:
            self.greeting_canvas.xview_scroll(int(-1 * (event.delta / 120)), "units")
        except Exception:
            pass

    def open_nickname_dialog(self):
        """点击左上角昵称后，弹出昵称修改窗口。"""
        win = tk.Toplevel(self.root)
        win.title("修改昵称")
        win.geometry(f"360x220+{self.root.winfo_rootx()+260}+{self.root.winfo_rooty()+150}")
        win.configure(bg=COLORS["bg"])
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()

        body = UI.card(win)
        body.pack(fill=tk.BOTH, expand=True, padx=18, pady=18)

        UI.label(body, "修改昵称", 17, "bold", bg=COLORS["card"]).pack(anchor="w", padx=20, pady=(18, 10))

        name_var = tk.StringVar(value=self.data.settings.get("username", "学习者"))
        entry = UI.entry(body, name_var, 28)
        entry.pack(fill=tk.X, padx=20, ipady=8, pady=(4, 16))

        action = tk.Frame(body, bg=COLORS["card"])
        action.pack(fill=tk.X, padx=20)

        def save_name():
            name = name_var.get().strip()
            if not name:
                messagebox.showwarning("输入错误", "昵称不能为空。")
                return
            self.data.settings["username"] = name
            self.data.save()
            self.refresh_user_profile()
            win.destroy()
            messagebox.showinfo("成功", "昵称已更新。")

        UI.button(action, "取消", win.destroy, COLORS["gray"]).pack(side=tk.RIGHT, padx=(8, 0))
        UI.button(action, "保存昵称", save_name, COLORS["blue"]).pack(side=tk.RIGHT)

        entry.focus_set()
        entry.select_range(0, tk.END)

    def open_avatar_picker_dialog(self):
        """点击左上角头像后，弹出可滚动的头像选择窗口，底部保存按钮固定显示。"""
        win = tk.Toplevel(self.root)
        win.title("修改头像")
        win.geometry(f"520x560+{self.root.winfo_rootx()+250}+{self.root.winfo_rooty()+90}")
        win.minsize(480, 500)
        win.configure(bg=COLORS["bg"])
        win.transient(self.root)
        win.grab_set()

        outer = tk.Frame(win, bg=COLORS["card"], highlightthickness=1, highlightbackground=COLORS["line"])
        outer.pack(fill=tk.BOTH, expand=True, padx=18, pady=18)
        outer.rowconfigure(2, weight=1)
        outer.columnconfigure(0, weight=1)

        header = tk.Frame(outer, bg=COLORS["card"])
        header.grid(row=0, column=0, columnspan=2, sticky="ew", padx=20, pady=(18, 8))
        UI.label(header, "选择头像", 17, "bold", bg=COLORS["card"]).pack(anchor="w")
        UI.label(header, "选择一个喜欢的头像，点击底部“保存头像”即可。", 10, fg=COLORS["sub"], bg=COLORS["card"]).pack(anchor="w", pady=(6, 0))

        current_var = tk.StringVar(value=self.data.settings.get("avatar", "👤") or "👤")

        preview = tk.Frame(outer, bg=COLORS["blue_light"], highlightthickness=1, highlightbackground=COLORS["line"])
        preview.grid(row=1, column=0, columnspan=2, sticky="ew", padx=20, pady=(0, 12))

        preview_canvas = tk.Canvas(preview, width=64, height=64, bg=COLORS["blue_light"], highlightthickness=0)
        preview_canvas.pack(side=tk.LEFT, padx=14, pady=10)
        preview_canvas.create_oval(5, 5, 59, 59, fill=COLORS["pink_light"], outline="")
        preview_item = preview_canvas.create_text(32, 33, text=current_var.get(), font=("Microsoft YaHei", 27))

        UI.label(preview, "当前头像预览", 12, "bold", bg=COLORS["blue_light"]).pack(side=tk.LEFT, padx=8)

        # 中间头像选择区：可上下滚动
        canvas = tk.Canvas(outer, bg=COLORS["card"], highlightthickness=0)
        ybar = ttk.Scrollbar(outer, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=ybar.set)

        canvas.grid(row=2, column=0, sticky="nsew", padx=(20, 0), pady=(0, 10))
        ybar.grid(row=2, column=1, sticky="ns", padx=(0, 12), pady=(0, 10))

        grid = tk.Frame(canvas, bg=COLORS["card"])
        grid_window = canvas.create_window((0, 0), window=grid, anchor="nw")

        def update_scroll_region(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfigure(grid_window, width=canvas.winfo_width())

        grid.bind("<Configure>", update_scroll_region)
        canvas.bind("<Configure>", update_scroll_region)

        def dialog_mousewheel(event):
            try:
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            except Exception:
                pass

        canvas.bind("<MouseWheel>", dialog_mousewheel)
        grid.bind("<MouseWheel>", dialog_mousewheel)

        avatar_options = [
            "👩‍🎓", "🧑‍🎓", "👨‍🎓", "👩‍💻", "🧑‍💻", "👨‍💻",
            "👩‍🎨", "🧑‍🎨", "👸", "🤴", "🧚", "🧸",
            "🌸", "🌷", "🌙", "⭐", "✨", "💎",
            "🍀", "🌿", "🌈", "☁️", "🦋", "🍓",
            "🐱", "🐰", "🐼", "🦊", "🐻", "🐧",
            "📚", "🎧", "📝", "🎀", "💡", "🚀"
        ]

        bg_options = [
            COLORS["pink_light"],
            COLORS["blue_light"],
            COLORS["green_light"],
            COLORS["orange_light"],
            COLORS["purple_light"],
            COLORS["card2"],
        ]

        def choose_avatar(icon):
            current_var.set(icon)
            preview_canvas.itemconfig(preview_item, text=icon)

        for i, icon in enumerate(avatar_options):
            row = i // 6
            col = i % 6
            card_bg = bg_options[i % len(bg_options)]
            btn = tk.Button(
                grid,
                text=icon,
                bg=card_bg,
                fg=COLORS["text"],
                activebackground=COLORS["blue_light"],
                bd=0,
                width=4,
                height=2,
                cursor="hand2",
                font=("Microsoft YaHei", 18),
                command=lambda x=icon: choose_avatar(x),
            )
            btn.grid(row=row, column=col, padx=7, pady=7, sticky="nsew")

        for col in range(6):
            grid.columnconfigure(col, weight=1)

        # 底部按钮区固定显示，不会随头像列表滚动
        action = tk.Frame(outer, bg=COLORS["card"])
        action.grid(row=3, column=0, columnspan=2, sticky="ew", padx=20, pady=(4, 18))

        UI.label(action, "提示：头像较多时，可滚动中间区域。", 9, fg=COLORS["sub"], bg=COLORS["card"]).pack(side=tk.LEFT)

        def save_avatar():
            avatar = current_var.get().strip() or "👤"
            self.data.settings["avatar"] = avatar
            self.data.save()
            self.refresh_user_profile()
            win.destroy()
            messagebox.showinfo("成功", "头像已更新。")

        UI.button(action, "取消", win.destroy, COLORS["gray"]).pack(side=tk.RIGHT, padx=(8, 0))
        UI.button(action, "保存头像", save_avatar, COLORS["pink"]).pack(side=tk.RIGHT)


    def set_nav_active(self):
        for name, btn in self.nav_buttons.items():
            if name == self.current_page:
                btn.config(bg=COLORS["blue_light"], fg=COLORS["blue"], font=("Microsoft YaHei", 12, "bold"))
            else:
                btn.config(bg=COLORS["sidebar"], fg=COLORS["text"], font=("Microsoft YaHei", 12))

    def clear_main(self):
        for child in self.main.winfo_children():
            child.destroy()

    def show_page(self, name):
        self.current_page = name
        self.set_nav_active()
        self.clear_main()
        self.selected_task_id = None

        if name == "日程计划":
            self.page_dashboard()
        elif name == "任务清单":
            self.page_tasks()
        elif name == "提醒设置":
            self.page_reminders()
        elif name == "习惯打卡":
            self.page_habits()
        elif name == "天气同步":
            self.page_weather()
        elif name == "统计分析":
            self.page_stats()
        elif name == "设置中心":
            self.page_settings()

    def page_header(self, parent):
        header = UI.card(parent)
        header.pack(fill=tk.X, padx=18, pady=(18, 12))
        header.configure(height=95)
        header.pack_propagate(False)

        left = tk.Frame(header, bg=COLORS["card"])
        left.pack(side=tk.LEFT, padx=22, pady=16)

        self.clock_label = UI.label(left, "00:00:00", 24, "bold", bg=COLORS["card"])
        self.clock_label.pack(side=tk.LEFT)

        date_box = tk.Frame(left, bg=COLORS["card"])
        date_box.pack(side=tk.LEFT, padx=26)
        self.date_label = UI.label(date_box, format_cn_date(), 12, "bold", bg=COLORS["card"])
        self.date_label.pack(anchor="w")
        self.lunar_label = UI.label(date_box, simple_lunar_text(), 10, fg=COLORS["sub"], bg=COLORS["card"])
        self.lunar_label.pack(anchor="w", pady=(4, 0))

        weather_box = tk.Frame(header, bg=COLORS["card"], highlightthickness=1, highlightbackground=COLORS["line"])
        weather_box.pack(side=tk.RIGHT, padx=22, pady=14)

        self.weather_icon_label = UI.label(weather_box, "☁", 25, bg=COLORS["card"], fg=COLORS["orange"])
        self.weather_icon_label.pack(side=tk.LEFT, padx=(14, 8), pady=8)

        wtext = tk.Frame(weather_box, bg=COLORS["card"])
        wtext.pack(side=tk.LEFT)
        self.weather_main_label = UI.label(wtext, "天气同步中", 12, "bold", bg=COLORS["card"])
        self.weather_main_label.pack(anchor="w")
        self.weather_sub_label = UI.label(wtext, "正在获取天气", 9, fg=COLORS["sub"], bg=COLORS["card"])
        self.weather_sub_label.pack(anchor="w", pady=(4, 0))

        tk.Button(
            weather_box,
            text="⟳",
            command=self.fetch_weather_async,
            bg=COLORS["card"],
            fg=COLORS["blue"],
            bd=0,
            font=("Microsoft YaHei", 18),
            cursor="hand2",
        ).pack(side=tk.RIGHT, padx=14)

    # ==================== 首页 ====================

    def page_dashboard(self):
        self.page_header(self.main)

        body = tk.Frame(self.main, bg=COLORS["bg"])
        body.pack(fill=tk.BOTH, expand=True, padx=18, pady=(0, 12))

        left = UI.card(body)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 12))

        middle = tk.Frame(body, bg=COLORS["bg"], width=340)
        middle.pack(side=tk.LEFT, fill=tk.BOTH, padx=(0, 12))
        middle.pack_propagate(False)

        right = tk.Frame(body, bg=COLORS["bg"], width=280)
        right.pack(side=tk.RIGHT, fill=tk.BOTH)
        right.pack_propagate(False)

        self.build_timeline(left)
        self.build_today_task_card(middle)
        self.build_habit_summary_card(middle)
        self.build_calendar_card(right)
        self.build_recent_reminder_card(right)
        self.build_today_stats_card(right)

        bottom = UI.card(self.main)
        bottom.pack(fill=tk.X, padx=18, pady=(0, 14))
        bottom.configure(height=58)
        bottom.pack_propagate(False)
        UI.button(bottom, "+ 新建日程", self.open_schedule_dialog, COLORS["pink"]).pack(side=tk.LEFT, padx=18, pady=9)
        UI.button(bottom, "视图切换", lambda: self.show_page("任务清单"), COLORS["blue"]).pack(side=tk.LEFT, padx=8, pady=9)
        UI.label(bottom, "● 数据已自动保存", 10, fg=COLORS["green"], bg=COLORS["card"]).pack(side=tk.RIGHT, padx=18)

    def set_schedule_selected_date(self, date_text):
        """切换日程计划正在查看的日期。"""
        try:
            datetime.strptime(date_text, "%Y-%m-%d")
        except Exception:
            messagebox.showwarning("日期错误", "日期格式错误，请使用 YYYY-MM-DD。")
            return

        self.data.settings["selected_date"] = date_text
        self.data.save()
        self.show_page("日程计划")

    def apply_timeline_date(self):
        """应用日程标题栏输入框中的日期。"""
        if hasattr(self, "timeline_date_var"):
            self.set_schedule_selected_date(self.timeline_date_var.get().strip())

    def prev_schedule_date(self):
        """日程标题栏：切换到前一天。"""
        try:
            d = datetime.strptime(self.data.settings.get("selected_date", today_str()), "%Y-%m-%d").date()
        except Exception:
            d = date.today()
        self.set_schedule_selected_date((d - timedelta(days=1)).strftime("%Y-%m-%d"))

    def next_schedule_date(self):
        """日程标题栏：切换到后一天。"""
        try:
            d = datetime.strptime(self.data.settings.get("selected_date", today_str()), "%Y-%m-%d").date()
        except Exception:
            d = date.today()
        self.set_schedule_selected_date((d + timedelta(days=1)).strftime("%Y-%m-%d"))

    def go_today_schedule_date(self):
        """日程标题栏：切换到今天。"""
        self.set_schedule_selected_date(today_str())

    def build_timeline(self, parent):
        head = tk.Frame(parent, bg=COLORS["card"])
        head.pack(fill=tk.X, padx=16, pady=(14, 8))
        UI.label(head, "时间轴日程视图", 14, "bold", bg=COLORS["card"]).pack(side=tk.LEFT)

        selected = self.data.settings.get("selected_date", today_str())

        date_tools = tk.Frame(head, bg=COLORS["card"])
        date_tools.pack(side=tk.RIGHT)

        UI.button(date_tools, "‹ 前一天", self.prev_schedule_date, COLORS["blue"]).pack(side=tk.LEFT, padx=(0, 6))
        UI.button(date_tools, "今天", self.go_today_schedule_date, COLORS["green"]).pack(side=tk.LEFT, padx=(0, 6))
        UI.button(date_tools, "后一天 ›", self.next_schedule_date, COLORS["blue"]).pack(side=tk.LEFT, padx=(0, 8))

        self.timeline_date_var = tk.StringVar(value=selected)
        UI.entry(date_tools, self.timeline_date_var, 12).pack(side=tk.LEFT, ipady=5)
        UI.button(date_tools, "选择日期", lambda: self.open_date_picker(self.timeline_date_var, self.apply_timeline_date), COLORS["pink"]).pack(side=tk.LEFT, padx=(8, 0))

        tabs = tk.Frame(parent, bg="#F7F9FD")
        tabs.pack(fill=tk.X, padx=16, pady=(0, 8))
        for view_name in ["日视图", "周视图", "月视图", "日历视图"]:
            active = self.current_schedule_view == view_name
            tk.Button(
                tabs,
                text=view_name,
                bg=COLORS["pink_light"] if active else "#F7F9FD",
                fg=COLORS["pink"] if active else COLORS["text"],
                activebackground=COLORS["pink_light"],
                activeforeground=COLORS["pink"],
                bd=0,
                cursor="hand2",
                font=("Microsoft YaHei", 10, "bold" if active else "normal"),
                padx=18,
                pady=7,
                command=lambda v=view_name: self.set_schedule_view(v),
            ).pack(side=tk.LEFT, expand=True, fill=tk.X)

        canvas_frame = tk.Frame(parent, bg=COLORS["card"])
        canvas_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))
        canvas_frame.rowconfigure(0, weight=1)
        canvas_frame.columnconfigure(0, weight=1)

        self.timeline_canvas = tk.Canvas(canvas_frame, bg=COLORS["card"], highlightthickness=0)

        y_scrollbar = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=self.timeline_canvas.yview)
        x_scrollbar = ttk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL, command=self.timeline_canvas.xview)

        self.timeline_canvas.configure(
            yscrollcommand=y_scrollbar.set,
            xscrollcommand=x_scrollbar.set
        )

        self.timeline_canvas.grid(row=0, column=0, sticky="nsew")
        y_scrollbar.grid(row=0, column=1, sticky="ns")
        x_scrollbar.grid(row=1, column=0, sticky="ew")

        self.timeline_canvas.bind("<Double-Button-1>", lambda e: self.open_schedule_dialog())
        self.timeline_canvas.bind("<Configure>", lambda e: self.draw_timeline())

        # 鼠标滚轮：普通滚轮上下滚动，Shift + 滚轮左右滚动
        self.timeline_canvas.bind("<MouseWheel>", self.on_timeline_mousewheel)
        self.timeline_canvas.bind("<Shift-MouseWheel>", self.on_timeline_shift_mousewheel)

    def on_timeline_mousewheel(self, event):
        """时间轴普通滚轮：纵向滚动。"""
        try:
            self.timeline_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        except Exception:
            pass

    def on_timeline_shift_mousewheel(self, event):
        """时间轴 Shift + 滚轮：横向滚动。"""
        try:
            self.timeline_canvas.xview_scroll(int(-1 * (event.delta / 120)), "units")
        except Exception:
            pass

    def set_schedule_view(self, view_name):
        """切换日程计划页面的日/周/月/日历视图。"""
        self.current_schedule_view = view_name
        self.show_page("日程计划")

    def draw_timeline(self):
        if not hasattr(self, "timeline_canvas") or not self.timeline_canvas.winfo_exists():
            return

        view = getattr(self, "current_schedule_view", "日视图")
        if view == "周视图":
            self.draw_week_view()
        elif view == "月视图":
            self.draw_month_view()
        elif view == "日历视图":
            self.draw_calendar_view_on_canvas()
        else:
            self.draw_day_view()

    def draw_day_view(self):
        c = self.timeline_canvas
        c.delete("all")

        width = max(560, c.winfo_width())
        start_hour, end_hour = 7, 23
        hour_h = 58
        top = 24
        left = 62
        selected = self.data.settings.get("selected_date", today_str())

        for hour in range(start_hour, end_hour + 1):
            y = top + (hour - start_hour) * hour_h
            c.create_text(30, y + 4, text=f"{hour:02d}:00", fill=COLORS["text"], font=("Microsoft YaHei", 9))
            c.create_line(left, y, width - 25, y, fill=COLORS["line"])

        tasks = sorted([t for t in self.data.tasks if t.task_date == selected], key=lambda x: x.task_time)
        for task in tasks:
            dt = task.dt
            if not dt:
                continue

            hour_value = dt.hour + dt.minute / 60
            y = top + (hour_value - start_hour) * hour_h
            if y < top:
                y = top

            color, light = TYPE_COLORS.get(task.category, TYPE_COLORS["其他"])
            x1, x2 = left + 12, width - 46
            block_h = 48
            tag = f"schedule_task_{task.id}"

            self.round_rect(c, x1, y + 6, x2, y + block_h, 10, fill=light, outline="", tags=(tag,))
            c.create_rectangle(x1, y + 6, x1 + 4, y + block_h, fill=color, outline="", tags=(tag,))
            title = task.title + ("  ✓" if task.completed else "")
            title_color = COLORS["gray"] if task.completed else COLORS["text"]
            c.create_text(x1 + 14, y + 20, text=f"{task.task_time}  {title}", anchor="w", fill=title_color, font=("Microsoft YaHei", 10, "bold"), tags=(tag,))
            c.create_text(x1 + 14, y + 38, text=task.note[:36], anchor="w", fill=COLORS["sub"], font=("Microsoft YaHei", 8), tags=(tag,))
            self.round_rect(c, x2 - 58, y + 17, x2 - 10, y + 39, 8, fill="#FFFFFF", outline="", tags=(tag,))
            c.create_text(x2 - 34, y + 28, text=task.category, fill=color, font=("Microsoft YaHei", 9, "bold"), tags=(tag,))

            c.tag_bind(tag, "<Button-1>", lambda event, tid=task.id: self.open_schedule_edit_dialog(tid))
            c.tag_bind(tag, "<Enter>", lambda event: c.config(cursor="hand2"))
            c.tag_bind(tag, "<Leave>", lambda event: c.config(cursor=""))

        if selected == today_str():
            now = datetime.now()
            if start_hour <= now.hour <= end_hour:
                y = top + ((now.hour + now.minute / 60) - start_hour) * hour_h
                c.create_line(left, y, width - 25, y, fill=COLORS["pink"], width=2)
                c.create_oval(left - 5, y - 5, left + 5, y + 5, fill=COLORS["pink"], outline="")
                c.create_text(30, y, text=now.strftime("%H:%M"), fill=COLORS["pink"], font=("Microsoft YaHei", 9, "bold"))

        c.create_text(
            width - 160,
            14,
            text="提示：点击日程可编辑/删除",
            fill=COLORS["sub"],
            font=("Microsoft YaHei", 9)
        )

        c.configure(scrollregion=(0, 0, width, top + (end_hour - start_hour + 1) * hour_h + 30))

    def draw_week_view(self):
        c = self.timeline_canvas
        c.delete("all")

        visible_width = max(620, c.winfo_width())
        col_w = 170
        width = max(visible_width, col_w * 7 + 80)

        selected_text = self.data.settings.get("selected_date", today_str())
        try:
            selected_date = datetime.strptime(selected_text, "%Y-%m-%d").date()
        except Exception:
            selected_date = date.today()

        week_start = selected_date - timedelta(days=selected_date.weekday())
        days = [week_start + timedelta(days=i) for i in range(7)]
        top = 55
        row_h = 72
        canvas_h = 620

        c.create_text(
            width / 2,
            24,
            text=f"周视图：{week_start.strftime('%Y-%m-%d')} 至 {(week_start + timedelta(days=6)).strftime('%Y-%m-%d')}",
            fill=COLORS["text"],
            font=("Microsoft YaHei", 13, "bold")
        )

        c.create_text(
            width - 180,
            24,
            text="点击日程可编辑/删除",
            fill=COLORS["sub"],
            font=("Microsoft YaHei", 9)
        )

        week_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        for i, d in enumerate(days):
            x = 30 + i * col_w
            bg = COLORS["pink_light"] if d.strftime("%Y-%m-%d") == selected_text else COLORS["blue_light"] if d == date.today() else "#F7F9FD"
            self.round_rect(c, x + 4, top, x + col_w - 8, top + 42, 10, fill=bg, outline="")
            c.create_text(x + col_w / 2, top + 14, text=week_names[i], fill=COLORS["text"], font=("Microsoft YaHei", 10, "bold"))
            c.create_text(x + col_w / 2, top + 31, text=d.strftime("%m-%d"), fill=COLORS["sub"], font=("Microsoft YaHei", 9))

            day_tasks = sorted([t for t in self.data.tasks if t.task_date == d.strftime("%Y-%m-%d")], key=lambda x: x.task_time)
            y = top + 58
            if not day_tasks:
                c.create_text(x + col_w / 2, y + 20, text="暂无", fill=COLORS["gray"], font=("Microsoft YaHei", 9))

            for task in day_tasks[:8]:
                color, light = TYPE_COLORS.get(task.category, TYPE_COLORS["其他"])
                tag = f"schedule_task_{task.id}"

                self.round_rect(c, x + 6, y, x + col_w - 10, y + 46, 8, fill=light, outline="", tags=(tag,))
                c.create_text(
                    x + 14,
                    y + 14,
                    text=f"{task.task_time} {task.title[:10]}",
                    anchor="w",
                    fill=COLORS["gray"] if task.completed else COLORS["text"],
                    font=("Microsoft YaHei", 9, "bold"),
                    tags=(tag,)
                )
                c.create_text(x + 14, y + 32, text=task.category, anchor="w", fill=color, font=("Microsoft YaHei", 8), tags=(tag,))

                c.tag_bind(tag, "<Button-1>", lambda event, tid=task.id: self.open_schedule_edit_dialog(tid))
                c.tag_bind(tag, "<Enter>", lambda event: c.config(cursor="hand2"))
                c.tag_bind(tag, "<Leave>", lambda event: c.config(cursor=""))

                y += row_h
                canvas_h = max(canvas_h, y + 60)

        c.configure(scrollregion=(0, 0, width + 30, canvas_h))

    def draw_month_view(self):
        c = self.timeline_canvas
        c.delete("all")

        width = max(620, c.winfo_width())
        selected_text = self.data.settings.get("selected_date", today_str())
        try:
            selected_date = datetime.strptime(selected_text, "%Y-%m-%d").date()
        except Exception:
            selected_date = date.today()

        year, month = selected_date.year, selected_date.month
        c.create_text(width / 2, 24, text=f"月视图：{year}年{month}月", fill=COLORS["text"], font=("Microsoft YaHei", 13, "bold"))
        c.create_text(width - 170, 24, text="点击日程可编辑/删除", fill=COLORS["sub"], font=("Microsoft YaHei", 9))

        month_days = calendar.monthrange(year, month)[1]
        x_left = 40
        y = 60
        row_h = 54

        for day in range(1, month_days + 1):
            d = date(year, month, day)
            ds = d.strftime("%Y-%m-%d")
            day_tasks = sorted([t for t in self.data.tasks if t.task_date == ds], key=lambda x: x.task_time)
            bg = COLORS["pink_light"] if ds == selected_text else COLORS["blue_light"] if d == date.today() else COLORS["card2"]
            self.round_rect(c, x_left, y, width - 40, y + 42, 10, fill=bg, outline="")
            c.create_text(x_left + 16, y + 21, text=f"{day:02d}日", anchor="w", fill=COLORS["text"], font=("Microsoft YaHei", 10, "bold"))

            if day_tasks:
                tx = x_left + 90
                for idx, task in enumerate(day_tasks[:3]):
                    tag = f"schedule_task_{task.id}"
                    display = f"{task.task_time} {task.title[:8]}"
                    c.create_text(
                        tx,
                        y + 21,
                        text=display,
                        anchor="w",
                        fill=COLORS["blue"] if not task.completed else COLORS["gray"],
                        font=("Microsoft YaHei", 9, "bold"),
                        tags=(tag,)
                    )
                    bbox = c.bbox(tag)
                    if bbox:
                        tx = bbox[2] + 18
                    c.tag_bind(tag, "<Button-1>", lambda event, tid=task.id: self.open_schedule_edit_dialog(tid))
                    c.tag_bind(tag, "<Enter>", lambda event: c.config(cursor="hand2"))
                    c.tag_bind(tag, "<Leave>", lambda event: c.config(cursor=""))

                if len(day_tasks) > 3:
                    c.create_text(tx, y + 21, text=f"等{len(day_tasks)}项", anchor="w", fill=COLORS["sub"], font=("Microsoft YaHei", 9))
            else:
                c.create_text(x_left + 90, y + 21, text="暂无日程", anchor="w", fill=COLORS["gray"], font=("Microsoft YaHei", 9))

            y += row_h

        c.configure(scrollregion=(0, 0, width, y + 30))

    def draw_calendar_view_on_canvas(self):
        c = self.timeline_canvas
        c.delete("all")

        width = max(620, c.winfo_width())
        selected_text = self.data.settings.get("selected_date", today_str())
        try:
            selected_date = datetime.strptime(selected_text, "%Y-%m-%d").date()
        except Exception:
            selected_date = date.today()

        year, month = selected_date.year, selected_date.month
        task_dates = {t.task_date for t in self.data.tasks}
        c.create_text(width / 2, 24, text=f"日历视图：{year}年{month}月", fill=COLORS["text"], font=("Microsoft YaHei", 13, "bold"))

        x0, y0 = 55, 62
        col_w = (width - 110) / 7
        row_h = 74
        week_names = ["日", "一", "二", "三", "四", "五", "六"]

        for i, name in enumerate(week_names):
            c.create_text(x0 + i * col_w + col_w / 2, y0, text=name, fill=COLORS["sub"], font=("Microsoft YaHei", 10, "bold"))

        weeks = calendar.Calendar(firstweekday=6).monthdatescalendar(year, month)
        for r, week in enumerate(weeks):
            for col, d in enumerate(week):
                x = x0 + col * col_w
                y = y0 + 25 + r * row_h
                ds = d.strftime("%Y-%m-%d")
                is_selected = ds == selected_text
                is_today = d == date.today()
                has_task = ds in task_dates
                bg = COLORS["pink_light"] if is_selected else COLORS["blue_light"] if is_today else COLORS["card2"]
                self.round_rect(c, x + 4, y, x + col_w - 6, y + 58, 10, fill=bg, outline="")
                fg = COLORS["gray"] if d.month != month else COLORS["text"]
                c.create_text(x + 14, y + 15, text=str(d.day), anchor="w", fill=fg, font=("Microsoft YaHei", 10, "bold"))

                if has_task:
                    count = len([t for t in self.data.tasks if t.task_date == ds])
                    c.create_text(x + 14, y + 38, text=f"● {count}项日程", anchor="w", fill=COLORS["blue"], font=("Microsoft YaHei", 8, "bold"))
                else:
                    c.create_text(x + 14, y + 38, text="无日程", anchor="w", fill=COLORS["gray"], font=("Microsoft YaHei", 8))

        c.configure(scrollregion=(0, 0, width, y0 + 25 + len(weeks) * row_h + 30))

    @staticmethod
    def round_rect(canvas, x1, y1, x2, y2, r, **kwargs):
        points = [
            x1 + r, y1,
            x2 - r, y1,
            x2, y1,
            x2, y1 + r,
            x2, y2 - r,
            x2, y2,
            x2 - r, y2,
            x1 + r, y2,
            x1, y2,
            x1, y2 - r,
            x1, y1 + r,
            x1, y1,
        ]
        return canvas.create_polygon(points, smooth=True, **kwargs)

    def build_today_task_card(self, parent):
        card = UI.card(parent)
        card.pack(fill=tk.BOTH, expand=True, pady=(0, 12))

        selected = self.data.settings.get("selected_date", today_str())
        tasks = sorted([t for t in self.data.tasks if t.task_date == selected], key=lambda x: x.task_time)

        head = tk.Frame(card, bg=COLORS["card"])
        head.pack(fill=tk.X, padx=14, pady=(14, 6))
        UI.label(head, f"当日任务清单（{len(tasks)}）", 13, "bold", bg=COLORS["card"]).pack(side=tk.LEFT)
        tk.Button(head, text="全部 ›", bg=COLORS["card"], fg=COLORS["blue"], bd=0, command=lambda: self.show_page("任务清单")).pack(side=tk.RIGHT)

        box = tk.Frame(card, bg=COLORS["card"])
        box.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))

        if not tasks:
            UI.label(box, "这一天还没有任务，点击左侧“任务清单”新增。", 10, fg=COLORS["sub"], bg=COLORS["card"]).pack(pady=35)
            return

        for task in tasks[:8]:
            self.compact_task_row(box, task)

    def compact_task_row(self, parent, task):
        row = tk.Frame(parent, bg=COLORS["card"], height=48, highlightthickness=1, highlightbackground=COLORS["line"])
        row.pack(fill=tk.X, pady=4)
        row.pack_propagate(False)

        var = tk.BooleanVar(value=task.completed)
        tk.Checkbutton(
            row,
            variable=var,
            bg=COLORS["card"],
            activebackground=COLORS["card"],
            bd=0,
            command=lambda: self.toggle_task_by_id(task.id, var.get()),
        ).pack(side=tk.LEFT, padx=6)

        text_box = tk.Frame(row, bg=COLORS["card"])
        text_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, pady=5)

        font = self.done_font if task.completed else self.normal_font
        fg = COLORS["gray"] if task.completed else COLORS["text"]
        tk.Label(text_box, text=task.title, bg=COLORS["card"], fg=fg, font=font, anchor="w").pack(anchor="w")
        UI.label(text_box, f"截止：{task.task_time}", 8, fg=COLORS["sub"], bg=COLORS["card"]).pack(anchor="w")

        pfg, pbg = PRIORITY_COLORS.get(task.priority, PRIORITY_COLORS["中"])
        UI.badge(row, task.priority, pfg, pbg).pack(side=tk.RIGHT, padx=8)

    def build_habit_summary_card(self, parent):
        card = UI.card(parent)
        card.pack(fill=tk.BOTH, expand=True)

        head = tk.Frame(card, bg=COLORS["card"])
        head.pack(fill=tk.X, padx=14, pady=(12, 6))
        UI.label(head, "习惯打卡", 13, "bold", bg=COLORS["card"]).pack(side=tk.LEFT)
        tk.Button(head, text="更多 ›", bg=COLORS["card"], fg=COLORS["blue"], bd=0, command=lambda: self.show_page("习惯打卡")).pack(side=tk.RIGHT)

        for habit in self.data.habits[:4]:
            row = tk.Frame(card, bg=COLORS["card"], height=46, highlightthickness=1, highlightbackground=COLORS["line"])
            row.pack(fill=tk.X, padx=14, pady=5)
            row.pack_propagate(False)
            tk.Label(row, text=habit.icon, bg=COLORS["card"], fg=habit.color, font=("Microsoft YaHei", 17)).pack(side=tk.LEFT, padx=10)
            UI.label(row, f"{habit.name}\n已坚持 {habit.streak()} 天", 9, bg=COLORS["card"], justify=tk.LEFT).pack(side=tk.LEFT)
            dots = tk.Frame(row, bg=COLORS["card"])
            dots.pack(side=tk.RIGHT, padx=8)
            self.draw_habit_dots(dots, habit, 7)

    def build_calendar_card(self, parent):
        card = UI.card(parent)
        card.pack(fill=tk.X, pady=(0, 12))

        head = tk.Frame(card, bg=COLORS["card"])
        head.pack(fill=tk.X, padx=14, pady=(12, 6))
        UI.label(head, "迷你日历", 13, "bold", bg=COLORS["card"]).pack(side=tk.LEFT)
        tk.Button(head, text="‹", bg=COLORS["card"], bd=0, font=("Microsoft YaHei", 15), command=self.prev_month).pack(side=tk.RIGHT)
        tk.Button(head, text="›", bg=COLORS["card"], bd=0, font=("Microsoft YaHei", 15), command=self.next_month).pack(side=tk.RIGHT)

        self.calendar_frame = tk.Frame(card, bg=COLORS["card"])
        self.calendar_frame.pack(fill=tk.X, padx=10, pady=(0, 12))
        self.draw_calendar(self.calendar_frame)

    def draw_calendar(self, parent):
        for child in parent.winfo_children():
            child.destroy()

        year = self.calendar_year
        month = self.calendar_month
        selected = self.data.settings.get("selected_date", today_str())
        task_dates = {task.task_date for task in self.data.tasks}

        UI.label(parent, f"{year}年{month}月", 11, "bold", bg=COLORS["card"]).grid(row=0, column=0, columnspan=7, pady=6)

        for i, name in enumerate(["日", "一", "二", "三", "四", "五", "六"]):
            UI.label(parent, name, 9, fg=COLORS["sub"], bg=COLORS["card"]).grid(row=1, column=i, padx=5, pady=4)

        weeks = calendar.Calendar(firstweekday=6).monthdatescalendar(year, month)
        for r, week in enumerate(weeks, start=2):
            for c, d in enumerate(week):
                ds = d.strftime("%Y-%m-%d")
                is_today = ds == today_str()
                is_selected = ds == selected
                has_task = ds in task_dates

                bg = COLORS["pink"] if is_selected else COLORS["blue_light"] if is_today else COLORS["card"]
                fg = "white" if is_selected else COLORS["blue"] if is_today else COLORS["text"] if d.month == month else COLORS["gray"]
                text = str(d.day) + ("•" if has_task else "")

                btn = tk.Button(
                    parent,
                    text=text,
                    bg=bg,
                    fg=fg,
                    activebackground=COLORS["blue_light"],
                    bd=0,
                    width=3,
                    font=("Microsoft YaHei", 9, "bold" if is_today or is_selected else "normal"),
                    command=lambda x=ds: self.select_date(x),
                )
                btn.grid(row=r, column=c, padx=4, pady=4)

    def prev_month(self):
        if self.calendar_month == 1:
            self.calendar_month = 12
            self.calendar_year -= 1
        else:
            self.calendar_month -= 1
        self.show_page(self.current_page)

    def next_month(self):
        if self.calendar_month == 12:
            self.calendar_month = 1
            self.calendar_year += 1
        else:
            self.calendar_month += 1
        self.show_page(self.current_page)

    def select_date(self, ds):
        self.data.settings["selected_date"] = ds
        self.data.save()
        self.show_page("日程计划")

    def build_recent_reminder_card(self, parent):
        card = UI.card(parent)
        card.pack(fill=tk.BOTH, expand=True, pady=(0, 12))
        UI.label(card, "近期提醒", 13, "bold", bg=COLORS["card"]).pack(anchor="w", padx=14, pady=(12, 8))

        upcoming = [t for t in self.data.tasks if not t.completed and t.dt and t.dt >= datetime.now()]
        upcoming.sort(key=lambda x: x.dt)

        if not upcoming:
            UI.label(card, "暂无即将到来的提醒", 10, fg=COLORS["sub"], bg=COLORS["card"]).pack(pady=28)
            return

        for task in upcoming[:5]:
            row = tk.Frame(card, bg=COLORS["card2"], height=50, highlightthickness=1, highlightbackground=COLORS["line"])
            row.pack(fill=tk.X, padx=12, pady=5)
            row.pack_propagate(False)

            pfg, _ = PRIORITY_COLORS.get(task.priority, PRIORITY_COLORS["中"])
            tk.Label(row, text="🔔", bg=COLORS["card2"], fg=pfg, font=("Microsoft YaHei", 15)).pack(side=tk.LEFT, padx=8)

            mins = int((task.dt - datetime.now()).total_seconds() // 60)
            left_text = f"还有 {mins} 分钟" if mins < 120 else f"还有 {mins // 60} 小时 {mins % 60} 分钟"

            text = tk.Frame(row, bg=COLORS["card2"])
            text.pack(side=tk.LEFT, fill=tk.X, expand=True)
            UI.label(text, f"{task.task_time}  {task.title[:12]}", 9, "bold", bg=COLORS["card2"]).pack(anchor="w")
            UI.label(text, left_text, 8, fg=pfg, bg=COLORS["card2"]).pack(anchor="w")

    def build_today_stats_card(self, parent):
        card = UI.card(parent)
        card.pack(fill=tk.X)

        UI.label(card, "今日统计", 13, "bold", bg=COLORS["card"]).pack(anchor="w", padx=14, pady=(12, 8))

        today_tasks = [task for task in self.data.tasks if task.task_date == today_str()]
        done = len([task for task in today_tasks if task.completed])
        total = len(today_tasks)
        habits_done = len([habit for habit in self.data.habits if habit.checked_today()])

        grid = tk.Frame(card, bg=COLORS["card"])
        grid.pack(fill=tk.X, padx=10, pady=(0, 12))

        stats = [
            ("☑", "任务完成", f"{done}/{total}", COLORS["green"]),
            ("🔔", "提醒事项", str(len([t for t in today_tasks if t.reminder_enabled])), COLORS["blue"]),
            ("🌱", "习惯打卡", f"{habits_done}/{len(self.data.habits)}", COLORS["orange"]),
            ("📈", "完成率", f"{int(done / total * 100) if total else 0}%", COLORS["purple"]),
        ]

        for i, (icon, name, value, color) in enumerate(stats):
            cell = tk.Frame(grid, bg=COLORS["card2"], width=118, height=58, highlightthickness=1, highlightbackground=COLORS["line"])
            cell.grid(row=i // 2, column=i % 2, padx=5, pady=5, sticky="nsew")
            cell.pack_propagate(False)
            tk.Label(cell, text=icon, bg=COLORS["card2"], fg=color, font=("Microsoft YaHei", 14)).pack(side=tk.LEFT, padx=8)
            UI.label(cell, f"{name}\n{value}", 9, bg=COLORS["card2"], justify=tk.LEFT).pack(side=tk.LEFT)

        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)


    # ==================== 日程计划页：弹窗新增日程 ====================

    def open_date_picker(self, target_var, on_select_callback=None):
        """弹出月历选择日期。
        修复：某些月份有 6 行日期时，底部日期会被遮住的问题。
        现在日期区域支持上下滚动，底部按钮固定显示。
        """
        try:
            base_date = datetime.strptime(target_var.get().strip(), "%Y-%m-%d").date()
        except Exception:
            base_date = date.today()

        picker = tk.Toplevel(self.root)
        picker.title("选择日期")
        picker.geometry(f"500x560+{self.root.winfo_rootx()+370}+{self.root.winfo_rooty()+90}")
        picker.minsize(480, 520)
        picker.configure(bg=COLORS["bg"])
        picker.resizable(False, False)
        picker.transient(self.root)
        picker.grab_set()

        state = {"year": base_date.year, "month": base_date.month}

        outer = tk.Frame(picker, bg=COLORS["card"], highlightthickness=1, highlightbackground=COLORS["line"])
        outer.pack(fill=tk.BOTH, expand=True, padx=16, pady=16)
        outer.rowconfigure(1, weight=1)
        outer.columnconfigure(0, weight=1)

        header = tk.Frame(outer, bg=COLORS["card"])
        header.grid(row=0, column=0, columnspan=2, sticky="ew", padx=18, pady=(16, 8))
        header.columnconfigure(1, weight=1)

        title_label = UI.label(header, "", 15, "bold", bg=COLORS["card"])
        tk.Button(
            header,
            text="‹",
            bg=COLORS["card"],
            fg=COLORS["blue"],
            bd=0,
            font=("Microsoft YaHei", 20),
            cursor="hand2",
            command=lambda: prev_m()
        ).grid(row=0, column=0, padx=(0, 8))
        title_label.grid(row=0, column=1)
        tk.Button(
            header,
            text="›",
            bg=COLORS["card"],
            fg=COLORS["blue"],
            bd=0,
            font=("Microsoft YaHei", 20),
            cursor="hand2",
            command=lambda: next_m()
        ).grid(row=0, column=2, padx=(8, 0))

        # 中间日期区域：使用 Canvas + 滚动条，避免底部日期被遮住
        canvas = tk.Canvas(outer, bg=COLORS["card"], highlightthickness=0)
        ybar = ttk.Scrollbar(outer, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=ybar.set)

        canvas.grid(row=1, column=0, sticky="nsew", padx=(18, 0), pady=(0, 8))
        ybar.grid(row=1, column=1, sticky="ns", padx=(0, 14), pady=(0, 8))

        cal_box = tk.Frame(canvas, bg=COLORS["card"])
        cal_window = canvas.create_window((0, 0), window=cal_box, anchor="nw")

        def update_scroll_region(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfigure(cal_window, width=canvas.winfo_width())

        cal_box.bind("<Configure>", update_scroll_region)
        canvas.bind("<Configure>", update_scroll_region)

        def date_mousewheel(event):
            try:
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            except Exception:
                pass

        canvas.bind("<MouseWheel>", date_mousewheel)
        cal_box.bind("<MouseWheel>", date_mousewheel)

        def redraw():
            for w in cal_box.winfo_children():
                w.destroy()

            year = state["year"]
            month = state["month"]
            title_label.config(text=f"{year}年{month}月")

            for i in range(7):
                cal_box.columnconfigure(i, weight=1, uniform="datecols")

            for i, name in enumerate(["日", "一", "二", "三", "四", "五", "六"]):
                UI.label(
                    cal_box,
                    name,
                    10,
                    "bold",
                    fg=COLORS["sub"],
                    bg=COLORS["card"],
                    width=5
                ).grid(row=0, column=i, padx=3, pady=(4, 8), sticky="nsew")

            weeks = calendar.Calendar(firstweekday=6).monthdatescalendar(year, month)
            for r, week in enumerate(weeks, start=1):
                for c, d in enumerate(week):
                    ds = d.strftime("%Y-%m-%d")
                    is_today = ds == today_str()
                    is_current_month = d.month == month

                    bg = COLORS["blue_light"] if is_today else COLORS["card2"] if is_current_month else COLORS["card"]
                    fg = COLORS["blue"] if is_today else COLORS["text"] if is_current_month else COLORS["gray"]

                    btn = tk.Button(
                        cal_box,
                        text=str(d.day),
                        bg=bg,
                        fg=fg,
                        activebackground=COLORS["pink_light"],
                        bd=0,
                        width=5,
                        height=2,
                        cursor="hand2",
                        font=("Microsoft YaHei", 11, "bold" if is_today else "normal"),
                        command=lambda x=ds: choose(x),
                    )
                    btn.grid(row=r, column=c, padx=3, pady=4, sticky="nsew")

            update_scroll_region()
            canvas.yview_moveto(0)

        def prev_m():
            if state["month"] == 1:
                state["month"] = 12
                state["year"] -= 1
            else:
                state["month"] -= 1
            redraw()

        def next_m():
            if state["month"] == 12:
                state["month"] = 1
                state["year"] += 1
            else:
                state["month"] += 1
            redraw()

        def choose(ds):
            target_var.set(ds)
            picker.destroy()
            if on_select_callback:
                on_select_callback()

        action = tk.Frame(outer, bg=COLORS["card"])
        action.grid(row=2, column=0, columnspan=2, sticky="ew", padx=18, pady=(6, 16))

        UI.label(action, "提示：日期较多时可滚动查看。", 9, fg=COLORS["sub"], bg=COLORS["card"]).pack(side=tk.LEFT)
        UI.button(action, "取消", picker.destroy, COLORS["gray"]).pack(side=tk.RIGHT)

        redraw()

    def open_reminder_dialog(self):
        """提醒设置页面直接添加带提醒的事项；弹窗支持滚动，底部确认按钮固定可见。"""
        win = tk.Toplevel(self.root)
        win.title("添加提醒")
        win.geometry(f"540x660+{self.root.winfo_rootx()+340}+{self.root.winfo_rooty()+70}")
        win.minsize(500, 580)
        win.configure(bg=COLORS["bg"])
        win.transient(self.root)
        win.grab_set()

        outer = tk.Frame(win, bg=COLORS["card"], highlightthickness=1, highlightbackground=COLORS["line"])
        outer.pack(fill=tk.BOTH, expand=True, padx=18, pady=18)
        outer.rowconfigure(1, weight=1)
        outer.columnconfigure(0, weight=1)

        header = tk.Frame(outer, bg=COLORS["card"])
        header.grid(row=0, column=0, sticky="ew", padx=22, pady=(18, 8))
        UI.label(header, "添加提醒", 18, "bold", bg=COLORS["card"]).pack(anchor="w")
        UI.label(header, "填写提醒事项后，点击底部“确认添加提醒”保存。", 10, fg=COLORS["sub"], bg=COLORS["card"]).pack(anchor="w", pady=(6, 0))

        canvas = tk.Canvas(outer, bg=COLORS["card"], highlightthickness=0)
        ybar = ttk.Scrollbar(outer, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=ybar.set)
        canvas.grid(row=1, column=0, sticky="nsew", padx=(22, 0), pady=(0, 8))
        ybar.grid(row=1, column=1, sticky="ns", padx=(0, 12), pady=(0, 8))

        form = tk.Frame(canvas, bg=COLORS["card"])
        form_window = canvas.create_window((0, 0), window=form, anchor="nw")

        def update_scroll_region(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfigure(form_window, width=canvas.winfo_width())

        form.bind("<Configure>", update_scroll_region)
        canvas.bind("<Configure>", update_scroll_region)

        def dialog_mousewheel(event):
            try:
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            except Exception:
                pass

        canvas.bind("<MouseWheel>", dialog_mousewheel)
        form.bind("<MouseWheel>", dialog_mousewheel)

        title_var = tk.StringVar()
        date_var = tk.StringVar(value=self.data.settings.get("selected_date", today_str()))
        time_var = tk.StringVar(value="09:00")
        priority_var = tk.StringVar(value="中")
        category_var = tk.StringVar(value="其他")
        remind_min_var = tk.StringVar(value="5")

        def add_entry(label_text, var):
            UI.label(form, label_text, 10, "bold", fg=COLORS["sub"], bg=COLORS["card"]).pack(anchor="w", pady=(8, 4))
            entry = UI.entry(form, var)
            entry.pack(fill=tk.X, ipady=8, padx=(0, 6))
            return entry

        first_entry = add_entry("提醒内容", title_var)

        UI.label(form, "日期（YYYY-MM-DD）", 10, "bold", fg=COLORS["sub"], bg=COLORS["card"]).pack(anchor="w", pady=(8, 4))
        date_row = tk.Frame(form, bg=COLORS["card"])
        date_row.pack(fill=tk.X, padx=(0, 6))
        UI.entry(date_row, date_var).pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=8)
        UI.button(date_row, "选择日期", lambda: self.open_date_picker(date_var), COLORS["blue"]).pack(side=tk.LEFT, padx=(8, 0))

        add_entry("时间（HH:MM）", time_var)

        UI.label(form, "提前提醒", 10, "bold", fg=COLORS["sub"], bg=COLORS["card"]).pack(anchor="w", pady=(10, 4))
        ttk.Combobox(form, textvariable=remind_min_var, values=["0", "5", "10", "30", "60"], state="readonly").pack(fill=tk.X, ipady=4, padx=(0, 6))

        UI.label(form, "优先级", 10, "bold", fg=COLORS["sub"], bg=COLORS["card"]).pack(anchor="w", pady=(10, 4))
        ttk.Combobox(form, textvariable=priority_var, values=["高", "中", "低"], state="readonly").pack(fill=tk.X, ipady=4, padx=(0, 6))

        UI.label(form, "类型", 10, "bold", fg=COLORS["sub"], bg=COLORS["card"]).pack(anchor="w", pady=(10, 4))
        ttk.Combobox(form, textvariable=category_var, values=["学习", "工作", "生活", "其他"], state="readonly").pack(fill=tk.X, ipady=4, padx=(0, 6))

        UI.label(form, "备注", 10, "bold", fg=COLORS["sub"], bg=COLORS["card"]).pack(anchor="w", pady=(10, 4))
        note_text = tk.Text(form, height=5, bg="#F7F9FD", bd=0, font=("Microsoft YaHei", 10))
        note_text.insert("1.0", "提醒设置页面添加")
        note_text.pack(fill=tk.BOTH, expand=True, padx=(0, 6), pady=(0, 12))

        action = tk.Frame(outer, bg=COLORS["card"])
        action.grid(row=2, column=0, columnspan=2, sticky="ew", padx=22, pady=(8, 18))
        UI.label(action, "提示：确认后会自动开启提醒并保存到 JSON。", 9, fg=COLORS["sub"], bg=COLORS["card"]).pack(side=tk.LEFT)

        def confirm_add_reminder():
            title = title_var.get().strip()
            task_date = date_var.get().strip()
            task_time = time_var.get().strip()
            priority = priority_var.get().strip()
            category = category_var.get().strip()
            note = note_text.get("1.0", tk.END).strip()

            if not title:
                messagebox.showwarning("输入错误", "提醒内容不能为空。")
                return

            try:
                parse_datetime(task_date, task_time)
            except Exception:
                messagebox.showwarning("输入错误", "日期或时间格式错误，请使用 YYYY-MM-DD 和 HH:MM。")
                return

            task = Task(
                title=title,
                task_date=task_date,
                task_time=task_time,
                priority=priority,
                category=category,
                note=note,
                reminder_enabled=True,
                remind_minutes=safe_int(remind_min_var.get(), 5),
                reminded=False,
            )

            self.data.tasks.append(task)
            self.data.settings["selected_date"] = task_date
            self.data.save()
            win.destroy()
            messagebox.showinfo("添加成功", "提醒已添加，并已保存到 JSON 文件。")
            self.show_page("提醒设置")

        UI.button(action, "取消", win.destroy, COLORS["gray"]).pack(side=tk.RIGHT, padx=(8, 0))
        UI.button(action, "确认添加提醒", confirm_add_reminder, COLORS["pink"]).pack(side=tk.RIGHT)

        first_entry.focus_set()

    def open_schedule_dialog(self):
        """在日程计划页面直接弹窗新增日程；弹窗支持滚动，底部确认按钮固定可见。"""
        win = tk.Toplevel(self.root)
        win.title("添加日程")
        win.geometry(f"560x720+{self.root.winfo_rootx()+320}+{self.root.winfo_rooty()+40}")
        win.minsize(520, 620)
        win.configure(bg=COLORS["bg"])
        win.transient(self.root)
        win.grab_set()

        outer = tk.Frame(win, bg=COLORS["card"], highlightthickness=1, highlightbackground=COLORS["line"])
        outer.pack(fill=tk.BOTH, expand=True, padx=18, pady=18)
        outer.rowconfigure(1, weight=1)
        outer.columnconfigure(0, weight=1)

        header = tk.Frame(outer, bg=COLORS["card"])
        header.grid(row=0, column=0, sticky="ew", padx=22, pady=(18, 8))
        UI.label(header, "添加新日程", 18, "bold", bg=COLORS["card"]).pack(anchor="w")
        UI.label(header, "填写信息后点击底部“确认添加”，内容会保存并显示在日程计划中。", 10, fg=COLORS["sub"], bg=COLORS["card"]).pack(anchor="w", pady=(6, 0))

        # 中间内容区可上下滚动
        canvas = tk.Canvas(outer, bg=COLORS["card"], highlightthickness=0)
        ybar = ttk.Scrollbar(outer, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=ybar.set)
        canvas.grid(row=1, column=0, sticky="nsew", padx=(22, 0), pady=(0, 8))
        ybar.grid(row=1, column=1, sticky="ns", padx=(0, 12), pady=(0, 8))

        form = tk.Frame(canvas, bg=COLORS["card"])
        form_window = canvas.create_window((0, 0), window=form, anchor="nw")

        def update_scroll_region(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfigure(form_window, width=canvas.winfo_width())

        form.bind("<Configure>", update_scroll_region)
        canvas.bind("<Configure>", update_scroll_region)

        def dialog_mousewheel(event):
            try:
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            except Exception:
                pass

        canvas.bind("<MouseWheel>", dialog_mousewheel)
        form.bind("<MouseWheel>", dialog_mousewheel)

        title_var = tk.StringVar()
        date_var = tk.StringVar(value=self.data.settings.get("selected_date", today_str()))
        time_var = tk.StringVar(value="09:00")
        priority_var = tk.StringVar(value="中")
        category_var = tk.StringVar(value="学习")
        reminder_var = tk.BooleanVar(value=True)
        remind_min_var = tk.StringVar(value="5")

        def add_entry(label_text, var):
            UI.label(form, label_text, 10, "bold", fg=COLORS["sub"], bg=COLORS["card"]).pack(anchor="w", pady=(8, 4))
            entry = UI.entry(form, var)
            entry.pack(fill=tk.X, ipady=8, padx=(0, 6))
            return entry

        first_entry = add_entry("日程内容", title_var)

        UI.label(form, "日期（YYYY-MM-DD）", 10, "bold", fg=COLORS["sub"], bg=COLORS["card"]).pack(anchor="w", pady=(8, 4))
        date_row = tk.Frame(form, bg=COLORS["card"])
        date_row.pack(fill=tk.X, padx=(0, 6))
        UI.entry(date_row, date_var).pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=8)
        UI.button(date_row, "选择日期", lambda: self.open_date_picker(date_var), COLORS["blue"]).pack(side=tk.LEFT, padx=(8, 0))

        add_entry("时间（HH:MM）", time_var)

        UI.label(form, "优先级", 10, "bold", fg=COLORS["sub"], bg=COLORS["card"]).pack(anchor="w", pady=(10, 4))
        ttk.Combobox(form, textvariable=priority_var, values=["高", "中", "低"], state="readonly").pack(fill=tk.X, ipady=4, padx=(0, 6))

        UI.label(form, "类型", 10, "bold", fg=COLORS["sub"], bg=COLORS["card"]).pack(anchor="w", pady=(10, 4))
        ttk.Combobox(form, textvariable=category_var, values=["学习", "工作", "生活", "其他"], state="readonly").pack(fill=tk.X, ipady=4, padx=(0, 6))

        reminder_box = tk.Frame(form, bg=COLORS["pink_light"], highlightthickness=1, highlightbackground=COLORS["line"])
        reminder_box.pack(fill=tk.X, pady=(14, 10), padx=(0, 6))

        tk.Checkbutton(
            reminder_box,
            text="开启提醒",
            variable=reminder_var,
            bg=COLORS["pink_light"],
            activebackground=COLORS["pink_light"],
            fg=COLORS["text"],
            font=("Microsoft YaHei", 10, "bold"),
        ).pack(side=tk.LEFT, padx=12, pady=10)

        UI.label(reminder_box, "提前", 10, bg=COLORS["pink_light"]).pack(side=tk.LEFT, padx=(10, 4))
        ttk.Combobox(reminder_box, textvariable=remind_min_var, values=["0", "5", "10", "30", "60"], width=8, state="readonly").pack(side=tk.LEFT)
        UI.label(reminder_box, "分钟", 10, bg=COLORS["pink_light"]).pack(side=tk.LEFT, padx=4)

        UI.label(form, "备注", 10, "bold", fg=COLORS["sub"], bg=COLORS["card"]).pack(anchor="w", pady=(6, 4))
        note_text = tk.Text(form, height=8, bg="#F7F9FD", bd=0, font=("Microsoft YaHei", 10))
        note_text.pack(fill=tk.BOTH, expand=True, padx=(0, 6), pady=(0, 12))

        # 底部按钮固定，不随内容区滚动
        action = tk.Frame(outer, bg=COLORS["card"])
        action.grid(row=2, column=0, columnspan=2, sticky="ew", padx=22, pady=(8, 18))

        UI.label(action, "提示：如果内容较多，可滚动中间表单区域。", 9, fg=COLORS["sub"], bg=COLORS["card"]).pack(side=tk.LEFT)

        def confirm_add_schedule():
            title = title_var.get().strip()
            task_date = date_var.get().strip()
            task_time = time_var.get().strip()
            priority = priority_var.get().strip()
            category = category_var.get().strip()
            note = note_text.get("1.0", tk.END).strip()

            if not title:
                messagebox.showwarning("输入错误", "日程内容不能为空。")
                return

            try:
                parse_datetime(task_date, task_time)
            except Exception:
                messagebox.showwarning("输入错误", "日期或时间格式错误，请使用 YYYY-MM-DD 和 HH:MM，例如 2026-05-21 和 09:30。")
                return

            if priority not in PRIORITY_COLORS:
                messagebox.showwarning("输入错误", "优先级必须是：高、中、低。")
                return

            if category not in TYPE_COLORS:
                messagebox.showwarning("输入错误", "类型必须是：学习、工作、生活、其他。")
                return

            task = Task(
                title=title,
                task_date=task_date,
                task_time=task_time,
                priority=priority,
                category=category,
                note=note,
                reminder_enabled=reminder_var.get(),
                remind_minutes=safe_int(remind_min_var.get(), 5),
                reminded=False,
            )

            self.data.tasks.append(task)
            self.data.settings["selected_date"] = task_date
            self.data.save()
            win.destroy()
            messagebox.showinfo("添加成功", "日程已添加，并已保存到 JSON 文件。")
            self.show_page("日程计划")

        UI.button(action, "取消", win.destroy, COLORS["gray"]).pack(side=tk.RIGHT, padx=(8, 0))
        UI.button(action, "确认添加", confirm_add_schedule, COLORS["pink"]).pack(side=tk.RIGHT)

        first_entry.focus_set()


    def open_schedule_edit_dialog(self, task_id):
        """从日程计划页面点击日程后，弹出编辑/删除窗口。"""
        task = self.data.get_task(task_id)
        if not task:
            messagebox.showwarning("提示", "该日程不存在，可能已被删除。")
            self.show_page("日程计划")
            return

        win = tk.Toplevel(self.root)
        win.title("编辑日程")
        win.geometry(f"560x720+{self.root.winfo_rootx()+320}+{self.root.winfo_rooty()+40}")
        win.minsize(520, 620)
        win.configure(bg=COLORS["bg"])
        win.transient(self.root)
        win.grab_set()

        outer = tk.Frame(win, bg=COLORS["card"], highlightthickness=1, highlightbackground=COLORS["line"])
        outer.pack(fill=tk.BOTH, expand=True, padx=18, pady=18)
        outer.rowconfigure(1, weight=1)
        outer.columnconfigure(0, weight=1)

        header = tk.Frame(outer, bg=COLORS["card"])
        header.grid(row=0, column=0, sticky="ew", padx=22, pady=(18, 8))
        UI.label(header, "编辑日程", 18, "bold", bg=COLORS["card"]).pack(anchor="w")
        UI.label(header, "修改后点击底部“保存修改”，也可以直接删除该日程。", 10, fg=COLORS["sub"], bg=COLORS["card"]).pack(anchor="w", pady=(6, 0))

        canvas = tk.Canvas(outer, bg=COLORS["card"], highlightthickness=0)
        ybar = ttk.Scrollbar(outer, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=ybar.set)
        canvas.grid(row=1, column=0, sticky="nsew", padx=(22, 0), pady=(0, 8))
        ybar.grid(row=1, column=1, sticky="ns", padx=(0, 12), pady=(0, 8))

        form = tk.Frame(canvas, bg=COLORS["card"])
        form_window = canvas.create_window((0, 0), window=form, anchor="nw")

        def update_scroll_region(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfigure(form_window, width=canvas.winfo_width())

        form.bind("<Configure>", update_scroll_region)
        canvas.bind("<Configure>", update_scroll_region)

        def dialog_mousewheel(event):
            try:
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            except Exception:
                pass

        canvas.bind("<MouseWheel>", dialog_mousewheel)
        form.bind("<MouseWheel>", dialog_mousewheel)

        title_var = tk.StringVar(value=task.title)
        date_var = tk.StringVar(value=task.task_date)
        time_var = tk.StringVar(value=task.task_time)
        priority_var = tk.StringVar(value=task.priority)
        category_var = tk.StringVar(value=task.category)
        reminder_var = tk.BooleanVar(value=task.reminder_enabled)
        remind_min_var = tk.StringVar(value=str(task.remind_minutes))
        completed_var = tk.BooleanVar(value=task.completed)

        def add_entry(label_text, var):
            UI.label(form, label_text, 10, "bold", fg=COLORS["sub"], bg=COLORS["card"]).pack(anchor="w", pady=(8, 4))
            entry = UI.entry(form, var)
            entry.pack(fill=tk.X, ipady=8, padx=(0, 6))
            return entry

        first_entry = add_entry("日程内容", title_var)

        UI.label(form, "日期（YYYY-MM-DD）", 10, "bold", fg=COLORS["sub"], bg=COLORS["card"]).pack(anchor="w", pady=(8, 4))
        date_row = tk.Frame(form, bg=COLORS["card"])
        date_row.pack(fill=tk.X, padx=(0, 6))
        UI.entry(date_row, date_var).pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=8)
        UI.button(date_row, "选择日期", lambda: self.open_date_picker(date_var), COLORS["blue"]).pack(side=tk.LEFT, padx=(8, 0))

        add_entry("时间（HH:MM）", time_var)

        UI.label(form, "优先级", 10, "bold", fg=COLORS["sub"], bg=COLORS["card"]).pack(anchor="w", pady=(10, 4))
        ttk.Combobox(form, textvariable=priority_var, values=["高", "中", "低"], state="readonly").pack(fill=tk.X, ipady=4, padx=(0, 6))

        UI.label(form, "类型", 10, "bold", fg=COLORS["sub"], bg=COLORS["card"]).pack(anchor="w", pady=(10, 4))
        ttk.Combobox(form, textvariable=category_var, values=["学习", "工作", "生活", "其他"], state="readonly").pack(fill=tk.X, ipady=4, padx=(0, 6))

        state_box = tk.Frame(form, bg=COLORS["green_light"], highlightthickness=1, highlightbackground=COLORS["line"])
        state_box.pack(fill=tk.X, pady=(14, 6), padx=(0, 6))
        tk.Checkbutton(
            state_box,
            text="标记为已完成",
            variable=completed_var,
            bg=COLORS["green_light"],
            activebackground=COLORS["green_light"],
            fg=COLORS["text"],
            font=("Microsoft YaHei", 10, "bold"),
        ).pack(side=tk.LEFT, padx=12, pady=10)

        reminder_box = tk.Frame(form, bg=COLORS["pink_light"], highlightthickness=1, highlightbackground=COLORS["line"])
        reminder_box.pack(fill=tk.X, pady=(8, 10), padx=(0, 6))
        tk.Checkbutton(
            reminder_box,
            text="开启提醒",
            variable=reminder_var,
            bg=COLORS["pink_light"],
            activebackground=COLORS["pink_light"],
            fg=COLORS["text"],
            font=("Microsoft YaHei", 10, "bold"),
        ).pack(side=tk.LEFT, padx=12, pady=10)

        UI.label(reminder_box, "提前", 10, bg=COLORS["pink_light"]).pack(side=tk.LEFT, padx=(10, 4))
        ttk.Combobox(reminder_box, textvariable=remind_min_var, values=["0", "5", "10", "30", "60"], width=8, state="readonly").pack(side=tk.LEFT)
        UI.label(reminder_box, "分钟", 10, bg=COLORS["pink_light"]).pack(side=tk.LEFT, padx=4)

        UI.label(form, "备注", 10, "bold", fg=COLORS["sub"], bg=COLORS["card"]).pack(anchor="w", pady=(6, 4))
        note_text = tk.Text(form, height=8, bg="#F7F9FD", bd=0, font=("Microsoft YaHei", 10))
        note_text.insert("1.0", task.note)
        note_text.pack(fill=tk.BOTH, expand=True, padx=(0, 6), pady=(0, 12))

        action = tk.Frame(outer, bg=COLORS["card"])
        action.grid(row=2, column=0, columnspan=2, sticky="ew", padx=22, pady=(8, 18))

        UI.label(action, "提示：保存或删除后会立即更新 JSON。", 9, fg=COLORS["sub"], bg=COLORS["card"]).pack(side=tk.LEFT)

        def save_changes():
            title = title_var.get().strip()
            task_date = date_var.get().strip()
            task_time = time_var.get().strip()
            priority = priority_var.get().strip()
            category = category_var.get().strip()
            note = note_text.get("1.0", tk.END).strip()

            if not title:
                messagebox.showwarning("输入错误", "日程内容不能为空。")
                return

            try:
                parse_datetime(task_date, task_time)
            except Exception:
                messagebox.showwarning("输入错误", "日期或时间格式错误，请使用 YYYY-MM-DD 和 HH:MM。")
                return

            if priority not in PRIORITY_COLORS:
                messagebox.showwarning("输入错误", "优先级必须是：高、中、低。")
                return

            if category not in TYPE_COLORS:
                messagebox.showwarning("输入错误", "类型必须是：学习、工作、生活、其他。")
                return

            task.title = title
            task.task_date = task_date
            task.task_time = task_time
            task.priority = priority
            task.category = category
            task.note = note
            task.completed = completed_var.get()
            task.reminder_enabled = reminder_var.get()
            task.remind_minutes = safe_int(remind_min_var.get(), 5)
            task.reminded = False

            self.data.settings["selected_date"] = task_date
            self.data.save()
            win.destroy()
            messagebox.showinfo("保存成功", "日程已修改，并已保存到 JSON 文件。")
            self.show_page("日程计划")

        def delete_schedule():
            if not messagebox.askyesno("确认删除", f"确定删除日程“{task.title}”吗？"):
                return
            self.data.tasks = [t for t in self.data.tasks if t.id != task.id]
            self.data.save()
            win.destroy()
            messagebox.showinfo("删除成功", "日程已删除，并已更新 JSON 文件。")
            self.show_page("日程计划")

        UI.button(action, "删除日程", delete_schedule, COLORS["red"]).pack(side=tk.RIGHT, padx=(8, 0))
        UI.button(action, "取消", win.destroy, COLORS["gray"]).pack(side=tk.RIGHT, padx=(8, 0))
        UI.button(action, "保存修改", save_changes, COLORS["blue"]).pack(side=tk.RIGHT)

        first_entry.focus_set()

    # ==================== 任务管理：新增、修改、删除、完成、保存 ====================

    def page_tasks(self):
        wrap = tk.Frame(self.main, bg=COLORS["bg"])
        wrap.pack(fill=tk.BOTH, expand=True, padx=18, pady=18)

        top = UI.card(wrap)
        top.pack(fill=tk.X, pady=(0, 12))
        top.configure(height=74)
        top.pack_propagate(False)
        UI.label(top, "任务清单", 20, "bold", bg=COLORS["card"]).pack(side=tk.LEFT, padx=18)
        UI.button(top, "清空编辑区", self.clear_task_form_safe, COLORS["gray"]).pack(side=tk.RIGHT, padx=18)

        content = tk.Frame(wrap, bg=COLORS["bg"])
        content.pack(fill=tk.BOTH, expand=True)

        left = UI.card(content)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 12))

        right = UI.card(content)
        right.pack(side=tk.RIGHT, fill=tk.Y)
        right.configure(width=360)
        right.pack_propagate(False)

        self.build_task_filters(left)
        self.build_task_table(left)
        self.build_task_editor(right)
        self.refresh_task_table()

    def build_task_filters(self, parent):
        frame = tk.Frame(parent, bg=COLORS["card"], height=56)
        frame.pack(fill=tk.X, padx=12, pady=(12, 0))
        frame.pack_propagate(False)

        self.filter_date = tk.StringVar(value="全部")
        self.filter_priority = tk.StringVar(value="全部")
        self.filter_status = tk.StringVar(value="全部")

        filter_items = [
            ("日期", self.filter_date, ["全部", "今日", "本周", "逾期"]),
            ("优先级", self.filter_priority, ["全部", "高", "中", "低"]),
            ("状态", self.filter_status, ["全部", "未完成", "已完成"]),
        ]

        for name, var, values in filter_items:
            UI.label(frame, f"{name}：", 10, "bold", bg=COLORS["card"]).pack(side=tk.LEFT, padx=(12, 4))
            box = ttk.Combobox(frame, textvariable=var, values=values, state="readonly", width=9)
            box.pack(side=tk.LEFT)
            box.bind("<<ComboboxSelected>>", lambda e: self.refresh_task_table())

        UI.button(frame, "重置", self.reset_filters, COLORS["blue"]).pack(side=tk.RIGHT, padx=12)

    def build_task_table(self, parent):
        table_frame = tk.Frame(parent, bg=COLORS["card"])
        table_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        cols = ("title", "date", "time", "priority", "category", "status", "remind")
        self.task_tree = ttk.Treeview(table_frame, columns=cols, show="headings", selectmode="browse")

        headers = ["任务内容", "日期", "时间", "优先级", "类型", "状态", "提醒"]
        widths = [260, 110, 80, 70, 80, 80, 100]
        for col, header, width in zip(cols, headers, widths):
            self.task_tree.heading(col, text=header)
            self.task_tree.column(col, width=width, anchor=tk.CENTER if col != "title" else tk.W)

        self.task_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.task_tree.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.task_tree.configure(yscrollcommand=scroll.set)

        self.task_tree.tag_configure("done", foreground=COLORS["gray"], font=self.done_font)
        self.task_tree.tag_configure("high", foreground=COLORS["red"])
        self.task_tree.tag_configure("middle", foreground=COLORS["orange"])
        self.task_tree.tag_configure("low", foreground=COLORS["green"])

        self.task_tree.bind("<<TreeviewSelect>>", self.on_task_select)
        self.task_tree.bind("<Double-Button-1>", self.on_task_select)

    def build_task_editor(self, parent):
        UI.label(parent, "编辑任务", 17, "bold", bg=COLORS["card"]).pack(anchor="w", padx=18, pady=(18, 12))

        form = tk.Frame(parent, bg=COLORS["card"])
        form.pack(fill=tk.BOTH, expand=True, padx=18)

        self.title_var = tk.StringVar()
        self.date_var = tk.StringVar(value=self.data.settings.get("selected_date", today_str()))
        self.time_var = tk.StringVar(value="09:00")
        self.priority_var = tk.StringVar(value="中")
        self.category_var = tk.StringVar(value="学习")
        self.reminder_var = tk.BooleanVar(value=True)
        self.remind_min_var = tk.StringVar(value="5")

        self.form_entry(form, "任务内容", self.title_var)

        UI.label(form, "日期（YYYY-MM-DD）", 10, "bold", fg=COLORS["sub"], bg=COLORS["card"]).pack(anchor="w", pady=(8, 4))
        task_date_row = tk.Frame(form, bg=COLORS["card"])
        task_date_row.pack(fill=tk.X)
        UI.entry(task_date_row, self.date_var).pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=8)
        UI.button(task_date_row, "选择日期", lambda: self.open_date_picker(self.date_var), COLORS["blue"]).pack(side=tk.LEFT, padx=(8, 0))

        self.form_entry(form, "时间（HH:MM）", self.time_var)

        UI.label(form, "优先级", 10, "bold", fg=COLORS["sub"], bg=COLORS["card"]).pack(anchor="w", pady=(8, 4))
        ttk.Combobox(form, textvariable=self.priority_var, values=["高", "中", "低"], state="readonly").pack(fill=tk.X, ipady=3)

        UI.label(form, "类型", 10, "bold", fg=COLORS["sub"], bg=COLORS["card"]).pack(anchor="w", pady=(10, 4))
        ttk.Combobox(form, textvariable=self.category_var, values=["学习", "工作", "生活", "其他"], state="readonly").pack(fill=tk.X, ipady=3)

        reminder_row = tk.Frame(form, bg=COLORS["card"])
        reminder_row.pack(fill=tk.X, pady=12)
        tk.Checkbutton(
            reminder_row,
            text="开启提醒",
            variable=self.reminder_var,
            bg=COLORS["card"],
            activebackground=COLORS["card"],
            font=("Microsoft YaHei", 10),
        ).pack(side=tk.LEFT)
        UI.label(reminder_row, "提前", 10, bg=COLORS["card"]).pack(side=tk.LEFT, padx=(12, 4))
        ttk.Combobox(reminder_row, textvariable=self.remind_min_var, values=["0", "5", "10", "30", "60"], state="readonly", width=8).pack(side=tk.LEFT)
        UI.label(reminder_row, "分钟", 10, bg=COLORS["card"]).pack(side=tk.LEFT, padx=4)

        UI.label(form, "备注", 10, "bold", fg=COLORS["sub"], bg=COLORS["card"]).pack(anchor="w", pady=(4, 4))
        self.note_text = tk.Text(form, height=8, bg="#F7F9FD", bd=0, font=("Microsoft YaHei", 10))
        self.note_text.pack(fill=tk.BOTH, expand=True)

        actions = tk.Frame(parent, bg=COLORS["card"])
        actions.pack(fill=tk.X, padx=18, pady=18)
        UI.button(actions, "新增任务", self.add_task_from_form, COLORS["pink"]).pack(side=tk.LEFT)
        UI.button(actions, "保存修改", self.update_task_from_form, COLORS["blue"]).pack(side=tk.LEFT, padx=8)
        UI.button(actions, "删除", self.delete_selected_task, COLORS["red"]).pack(side=tk.LEFT)
        UI.button(actions, "完成/未完成", self.toggle_selected_task, COLORS["green"]).pack(side=tk.LEFT, padx=8)

    def form_entry(self, parent, label, var):
        UI.label(parent, label, 10, "bold", fg=COLORS["sub"], bg=COLORS["card"]).pack(anchor="w", pady=(8, 4))
        UI.entry(parent, var).pack(fill=tk.X, ipady=8)

    def validate_task_form(self):
        title = self.title_var.get().strip()
        task_date = self.date_var.get().strip()
        task_time = self.time_var.get().strip()
        priority = self.priority_var.get().strip()
        category = self.category_var.get().strip()
        note = self.note_text.get("1.0", tk.END).strip()

        if not title:
            messagebox.showwarning("输入错误", "任务内容不能为空。")
            return None

        try:
            parse_datetime(task_date, task_time)
        except Exception:
            messagebox.showwarning("输入错误", "日期或时间格式错误，请使用 YYYY-MM-DD 和 HH:MM，例如 2026-05-21 和 09:30。")
            return None

        if priority not in PRIORITY_COLORS:
            messagebox.showwarning("输入错误", "优先级必须是：高、中、低。")
            return None

        if category not in TYPE_COLORS:
            messagebox.showwarning("输入错误", "类型必须是：学习、工作、生活、其他。")
            return None

        return {
            "title": title,
            "task_date": task_date,
            "task_time": task_time,
            "priority": priority,
            "category": category,
            "note": note,
            "reminder_enabled": self.reminder_var.get(),
            "remind_minutes": safe_int(self.remind_min_var.get(), 5),
        }

    def add_task_from_form(self):
        data = self.validate_task_form()
        if not data:
            return

        task = Task(**data)
        self.data.tasks.append(task)
        self.data.save()
        self.selected_task_id = None
        self.refresh_task_table()
        self.clear_task_form_safe()
        messagebox.showinfo("成功", "任务已新增，并已自动保存到 JSON 文件。")

    def update_task_from_form(self):
        if not self.selected_task_id:
            messagebox.showinfo("提示", "请先在左侧表格选择要修改的任务。")
            return

        task = self.data.get_task(self.selected_task_id)
        if not task:
            messagebox.showwarning("错误", "选中的任务不存在，可能已被删除。")
            return

        data = self.validate_task_form()
        if not data:
            return

        for key, value in data.items():
            setattr(task, key, value)

        task.reminded = False
        self.data.save()
        self.refresh_task_table()
        messagebox.showinfo("成功", "任务已修改，并已自动保存。")

    def delete_selected_task(self):
        if not self.selected_task_id:
            messagebox.showinfo("提示", "请先选择要删除的任务。")
            return

        task = self.data.get_task(self.selected_task_id)
        if not task:
            messagebox.showwarning("错误", "选中的任务不存在。")
            return

        if messagebox.askyesno("确认删除", f"确定删除任务“{task.title}”吗？"):
            self.data.tasks = [t for t in self.data.tasks if t.id != self.selected_task_id]
            self.selected_task_id = None
            self.data.save()
            self.refresh_task_table()
            self.clear_task_form_safe()
            messagebox.showinfo("成功", "任务已删除，并已更新 JSON 文件。")

    def toggle_selected_task(self):
        if not self.selected_task_id:
            messagebox.showinfo("提示", "请先选择任务。")
            return

        task = self.data.get_task(self.selected_task_id)
        if not task:
            return

        task.completed = not task.completed
        if not task.completed:
            task.reminded = False

        self.data.save()
        self.refresh_task_table()
        self.fill_task_form(task)

    def toggle_task_by_id(self, task_id, value):
        task = self.data.get_task(task_id)
        if not task:
            return

        task.completed = value
        if not value:
            task.reminded = False

        self.data.save()
        self.show_page(self.current_page)

    def clear_task_form_safe(self):
        if not hasattr(self, "title_var"):
            return

        self.selected_task_id = None
        self.title_var.set("")
        self.date_var.set(self.data.settings.get("selected_date", today_str()))
        self.time_var.set("09:00")
        self.priority_var.set("中")
        self.category_var.set("学习")
        self.reminder_var.set(True)
        self.remind_min_var.set("5")

        if hasattr(self, "note_text") and self.note_text.winfo_exists():
            self.note_text.delete("1.0", tk.END)

        if hasattr(self, "task_tree") and self.task_tree.winfo_exists():
            self.task_tree.selection_remove(self.task_tree.selection())

    def on_task_select(self, _event=None):
        selection = self.task_tree.selection()
        if not selection:
            return

        task_id = selection[0]
        task = self.data.get_task(task_id)
        if not task:
            return

        self.selected_task_id = task_id
        self.fill_task_form(task)

    def fill_task_form(self, task):
        self.title_var.set(task.title)
        self.date_var.set(task.task_date)
        self.time_var.set(task.task_time)
        self.priority_var.set(task.priority)
        self.category_var.set(task.category)
        self.reminder_var.set(task.reminder_enabled)
        self.remind_min_var.set(str(task.remind_minutes))
        self.note_text.delete("1.0", tk.END)
        self.note_text.insert("1.0", task.note)

    def task_visible_by_filters(self, task):
        fd = self.filter_date.get() if hasattr(self, "filter_date") else "全部"
        fp = self.filter_priority.get() if hasattr(self, "filter_priority") else "全部"
        fs = self.filter_status.get() if hasattr(self, "filter_status") else "全部"

        dt = task.dt
        d = dt.date() if dt else None
        current = date.today()

        if fd == "今日" and d != current:
            return False
        if fd == "本周":
            start = current - timedelta(days=current.weekday())
            end = start + timedelta(days=6)
            if not d or not (start <= d <= end):
                return False
        if fd == "逾期" and (not dt or task.completed or dt >= datetime.now()):
            return False

        if fp != "全部" and task.priority != fp:
            return False

        if fs == "未完成" and task.completed:
            return False
        if fs == "已完成" and not task.completed:
            return False

        return True

    def refresh_task_table(self):
        if not hasattr(self, "task_tree") or not self.task_tree.winfo_exists():
            return

        for item in self.task_tree.get_children():
            self.task_tree.delete(item)

        for task in sorted(self.data.tasks, key=lambda x: (x.task_date, x.task_time)):
            if not self.task_visible_by_filters(task):
                continue

            if task.completed:
                tags = ("done",)
            elif task.priority == "高":
                tags = ("high",)
            elif task.priority == "中":
                tags = ("middle",)
            else:
                tags = ("low",)

            self.task_tree.insert(
                "",
                tk.END,
                iid=task.id,
                values=(
                    task.title,
                    task.task_date,
                    task.task_time,
                    task.priority,
                    task.category,
                    "已完成" if task.completed else "未完成",
                    f"提前{task.remind_minutes}分钟" if task.reminder_enabled else "关闭",
                ),
                tags=tags,
            )

    def reset_filters(self):
        self.filter_date.set("全部")
        self.filter_priority.set("全部")
        self.filter_status.set("全部")
        self.refresh_task_table()

    # ==================== 提醒设置 ====================

    def page_reminders(self):
        wrap = tk.Frame(self.main, bg=COLORS["bg"])
        wrap.pack(fill=tk.BOTH, expand=True, padx=18, pady=18)

        top = UI.card(wrap)
        top.pack(fill=tk.X, pady=(0, 12))
        top.configure(height=86)
        top.pack_propagate(False)

        UI.label(top, "提醒设置", 20, "bold", bg=COLORS["card"]).pack(side=tk.LEFT, padx=18)
        UI.label(top, "支持开启/关闭提醒，并设置提前 0/5/10/30/60 分钟提醒", 10, fg=COLORS["sub"], bg=COLORS["card"]).pack(side=tk.LEFT, padx=16)
        UI.button(top, "+ 添加提醒", self.open_reminder_dialog, COLORS["pink"]).pack(side=tk.RIGHT, padx=18)

        card = UI.card(wrap)
        card.pack(fill=tk.BOTH, expand=True)

        pending = sorted([t for t in self.data.tasks if not t.completed], key=lambda x: x.dt or datetime.max)

        if not pending:
            UI.label(card, "暂无待提醒任务", 12, fg=COLORS["sub"], bg=COLORS["card"]).pack(pady=40)
            return

        for task in pending:
            row = tk.Frame(card, bg=COLORS["card"], height=70, highlightthickness=1, highlightbackground=COLORS["line"])
            row.pack(fill=tk.X, padx=18, pady=8)
            row.pack_propagate(False)

            enabled_var = tk.BooleanVar(value=task.reminder_enabled)
            tk.Checkbutton(
                row,
                text="开启",
                variable=enabled_var,
                bg=COLORS["card"],
                activebackground=COLORS["card"],
                font=("Microsoft YaHei", 10),
                command=lambda t=task, v=enabled_var: self.set_task_reminder(t, v.get()),
            ).pack(side=tk.LEFT, padx=16)

            info = tk.Frame(row, bg=COLORS["card"])
            info.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, pady=10)

            UI.label(info, task.title, 11, "bold", bg=COLORS["card"]).pack(anchor="w")
            UI.label(info, f"{task.task_date} {task.task_time} · {task.category} · 优先级{task.priority}", 9, fg=COLORS["sub"], bg=COLORS["card"]).pack(anchor="w", pady=(5, 0))

            minutes_var = tk.StringVar(value=str(task.remind_minutes))
            combo = ttk.Combobox(row, textvariable=minutes_var, values=["0", "5", "10", "30", "60"], width=8, state="readonly")
            combo.pack(side=tk.RIGHT, padx=16)
            combo.bind("<<ComboboxSelected>>", lambda e, t=task, v=minutes_var: self.set_task_remind_minutes(t, v.get()))
            UI.label(row, "提前分钟", 9, fg=COLORS["sub"], bg=COLORS["card"]).pack(side=tk.RIGHT)

    def set_task_reminder(self, task, enabled):
        task.reminder_enabled = enabled
        task.reminded = False
        self.data.save()

    def set_task_remind_minutes(self, task, minutes):
        task.remind_minutes = safe_int(minutes, 5)
        task.reminded = False
        self.data.save()

    # ==================== 习惯打卡 ====================

    def page_habits(self):
        wrap = tk.Frame(self.main, bg=COLORS["bg"])
        wrap.pack(fill=tk.BOTH, expand=True, padx=18, pady=18)

        top = UI.card(wrap)
        top.pack(fill=tk.X, pady=(0, 12))
        top.configure(height=86)
        top.pack_propagate(False)

        UI.label(top, "习惯打卡", 20, "bold", bg=COLORS["card"]).pack(side=tk.LEFT, padx=18)
        UI.button(top, "+ 添加打卡", self.add_habit_dialog, COLORS["green"]).pack(side=tk.RIGHT, padx=18)

        card = UI.card(wrap)
        card.pack(fill=tk.BOTH, expand=True)

        if not self.data.habits:
            UI.label(card, "还没有习惯，点击“添加习惯”开始。", 12, fg=COLORS["sub"], bg=COLORS["card"]).pack(pady=50)
            return

        for habit in self.data.habits:
            row = tk.Frame(card, bg=COLORS["card"], height=92, highlightthickness=1, highlightbackground=COLORS["line"])
            row.pack(fill=tk.X, padx=18, pady=9)
            row.pack_propagate(False)

            tk.Label(row, text=habit.icon, bg=COLORS["card"], fg=habit.color, font=("Microsoft YaHei", 26)).pack(side=tk.LEFT, padx=18)

            info = tk.Frame(row, bg=COLORS["card"])
            info.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, pady=14)

            UI.label(info, habit.name, 13, "bold", bg=COLORS["card"]).pack(anchor="w")
            UI.label(info, f"连续打卡 {habit.streak()} 天 · 总打卡 {len(habit.records)} 天", 9, fg=COLORS["sub"], bg=COLORS["card"]).pack(anchor="w", pady=(5, 0))

            dots = tk.Frame(info, bg=COLORS["card"])
            dots.pack(anchor="w", pady=(8, 0))
            self.draw_habit_dots(dots, habit, 14)

            checked = habit.checked_today()
            UI.button(row, "今日已打卡" if checked else "今日打卡", lambda h=habit: self.toggle_habit(h), COLORS["gray"] if checked else COLORS["green"]).pack(side=tk.RIGHT, padx=8)
            UI.button(row, "删除", lambda h=habit: self.delete_habit(h), COLORS["red"]).pack(side=tk.RIGHT, padx=8)

    def draw_habit_dots(self, parent, habit, days=7):
        for child in parent.winfo_children():
            child.destroy()

        records = set(habit.records)
        for i in range(days - 1, -1, -1):
            d = date.today() - timedelta(days=i)
            done = d.strftime("%Y-%m-%d") in records
            tk.Label(
                parent,
                text="●",
                bg=parent.cget("bg"),
                fg=habit.color if done else COLORS["line"],
                font=("Microsoft YaHei", 9),
            ).pack(side=tk.LEFT, padx=2)

    def add_habit_dialog(self):
        """添加自定义打卡；弹窗支持上下滚动，底部确认按钮固定可见。"""
        win = tk.Toplevel(self.root)
        win.title("添加打卡")
        win.geometry(f"460x520+{self.root.winfo_rootx()+390}+{self.root.winfo_rooty()+140}")
        win.minsize(420, 430)
        win.configure(bg=COLORS["bg"])
        win.transient(self.root)
        win.grab_set()

        outer = tk.Frame(win, bg=COLORS["card"], highlightthickness=1, highlightbackground=COLORS["line"])
        outer.pack(fill=tk.BOTH, expand=True, padx=18, pady=18)
        outer.rowconfigure(1, weight=1)
        outer.columnconfigure(0, weight=1)

        header = tk.Frame(outer, bg=COLORS["card"])
        header.grid(row=0, column=0, sticky="ew", padx=22, pady=(18, 8))
        UI.label(header, "添加打卡", 17, "bold", bg=COLORS["card"]).pack(anchor="w")
        UI.label(header, "填写打卡信息后点击底部按钮保存。", 10, fg=COLORS["sub"], bg=COLORS["card"]).pack(anchor="w", pady=(6, 0))

        canvas = tk.Canvas(outer, bg=COLORS["card"], highlightthickness=0)
        ybar = ttk.Scrollbar(outer, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=ybar.set)

        canvas.grid(row=1, column=0, sticky="nsew", padx=(22, 0), pady=(0, 8))
        ybar.grid(row=1, column=1, sticky="ns", padx=(0, 12), pady=(0, 8))

        form = tk.Frame(canvas, bg=COLORS["card"])
        form_window = canvas.create_window((0, 0), window=form, anchor="nw")

        def update_scroll_region(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfigure(form_window, width=canvas.winfo_width())

        form.bind("<Configure>", update_scroll_region)
        canvas.bind("<Configure>", update_scroll_region)

        def dialog_mousewheel(event):
            try:
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            except Exception:
                pass

        canvas.bind("<MouseWheel>", dialog_mousewheel)
        form.bind("<MouseWheel>", dialog_mousewheel)

        name_var = tk.StringVar()
        icon_var = tk.StringVar(value="⭐")
        color_var = tk.StringVar(value="淡蓝")

        UI.label(form, "打卡名称", 10, "bold", fg=COLORS["sub"], bg=COLORS["card"]).pack(anchor="w", pady=(8, 4))
        name_entry = UI.entry(form, name_var)
        name_entry.pack(fill=tk.X, ipady=8, padx=(0, 6))

        UI.label(form, "打卡图标", 10, "bold", fg=COLORS["sub"], bg=COLORS["card"]).pack(anchor="w", pady=(14, 4))
        UI.entry(form, icon_var).pack(fill=tk.X, ipady=8, padx=(0, 6))

        quick_icons = tk.Frame(form, bg=COLORS["card"])
        quick_icons.pack(anchor="w", pady=(8, 6))
        for icon in ["⭐", "📖", "🏃", "💧", "☀", "🌱", "🎧", "📝"]:
            tk.Button(
                quick_icons,
                text=icon,
                bg=COLORS["card2"],
                fg=COLORS["text"],
                activebackground=COLORS["green_light"],
                bd=0,
                width=3,
                font=("Microsoft YaHei", 13),
                cursor="hand2",
                command=lambda x=icon: icon_var.set(x),
            ).pack(side=tk.LEFT, padx=3)

        UI.label(form, "颜色", 10, "bold", fg=COLORS["sub"], bg=COLORS["card"]).pack(anchor="w", pady=(14, 4))
        ttk.Combobox(
            form,
            textvariable=color_var,
            values=["淡蓝", "淡绿", "淡粉", "淡橙", "淡紫"],
            state="readonly"
        ).pack(fill=tk.X, ipady=4, padx=(0, 6))

        preview = tk.Frame(form, bg=COLORS["green_light"], highlightthickness=1, highlightbackground=COLORS["line"])
        preview.pack(fill=tk.X, pady=(18, 12), padx=(0, 6))

        preview_label = UI.label(
            preview,
            "示例：⭐ 每日打卡  ·  连续打卡 0 天",
            10,
            "bold",
            fg=COLORS["green"],
            bg=COLORS["green_light"]
        )
        preview_label.pack(anchor="w", padx=12, pady=10)

        def update_preview(*_):
            name = name_var.get().strip() or "每日打卡"
            icon = icon_var.get().strip() or "⭐"
            preview_label.config(text=f"示例：{icon} {name}  ·  连续打卡 0 天")

        name_var.trace_add("write", update_preview)
        icon_var.trace_add("write", update_preview)

        action = tk.Frame(outer, bg=COLORS["card"])
        action.grid(row=2, column=0, columnspan=2, sticky="ew", padx=22, pady=(8, 18))

        UI.label(action, "确认后会保存到 JSON。", 9, fg=COLORS["sub"], bg=COLORS["card"]).pack(side=tk.LEFT)

        def save_habit():
            name = name_var.get().strip()
            icon = icon_var.get().strip() or "⭐"

            if not name:
                messagebox.showwarning("输入错误", "打卡名称不能为空。")
                return

            color_map = {
                "淡蓝": COLORS["blue"],
                "淡绿": COLORS["green"],
                "淡粉": COLORS["pink"],
                "淡橙": COLORS["orange"],
                "淡紫": COLORS["purple"],
            }

            habit = Habit(
                name=name,
                icon=icon,
                color=color_map.get(color_var.get(), COLORS["blue"])
            )
            self.data.habits.append(habit)
            self.data.save()
            win.destroy()
            messagebox.showinfo("添加成功", "打卡已添加，并已保存到 JSON 文件。")
            self.show_page("习惯打卡")

        UI.button(action, "取消", win.destroy, COLORS["gray"]).pack(side=tk.RIGHT, padx=(8, 0))
        UI.button(action, "确认添加打卡", save_habit, COLORS["green"]).pack(side=tk.RIGHT)

        name_entry.focus_set()

    def toggle_habit(self, habit):
        habit.toggle_today()
        self.data.save()
        self.show_page("习惯打卡")

    def delete_habit(self, habit):
        if messagebox.askyesno("确认删除", f"确定删除习惯“{habit.name}”吗？"):
            self.data.habits = [h for h in self.data.habits if h.id != habit.id]
            self.data.save()
            self.show_page("习惯打卡")

    # ==================== 天气同步 ====================

    def page_weather(self):
        wrap = tk.Frame(self.main, bg=COLORS["bg"])
        wrap.pack(fill=tk.BOTH, expand=True, padx=18, pady=18)

        top = UI.card(wrap)
        top.pack(fill=tk.X, pady=(0, 12))
        top.configure(height=86)
        top.pack_propagate(False)

        UI.label(top, "天气同步", 20, "bold", bg=COLORS["card"]).pack(side=tk.LEFT, padx=18)

        city_var = tk.StringVar(value=self.data.settings.get("city", "杭州"))
        UI.label(top, "城市：", 11, "bold", bg=COLORS["card"]).pack(side=tk.LEFT, padx=(28, 6))
        UI.entry(top, city_var, 18).pack(side=tk.LEFT, ipady=8)
        UI.button(top, "保存并同步", lambda: self.set_city(city_var.get()), COLORS["blue"]).pack(side=tk.LEFT, padx=12)

        card = UI.card(wrap)
        card.pack(fill=tk.BOTH, expand=True)

        inner = tk.Frame(card, bg=COLORS["card"])
        inner.place(relx=0.5, rely=0.5, anchor="center")

        data = self.weather_data or {}
        tk.Label(inner, text=data.get("icon", "☁"), bg=COLORS["card"], fg=COLORS["orange"], font=("Microsoft YaHei", 70)).pack()
        UI.label(inner, data.get("city", self.data.settings.get("city", "杭州")), 24, "bold", bg=COLORS["card"]).pack(pady=(8, 2))
        UI.label(inner, f"{data.get('temp', '--')}℃  {data.get('desc', '等待同步')}", 18, "bold", fg=COLORS["blue"], bg=COLORS["card"]).pack(pady=4)
        UI.label(inner, f"湿度：{data.get('humidity', '--')}%   风速：{data.get('wind', '--')} km/h", 12, fg=COLORS["sub"], bg=COLORS["card"]).pack(pady=6)
        UI.label(inner, data.get("tips", "点击保存并同步获取天气"), 13, "bold", fg=COLORS["pink"], bg=COLORS["card"]).pack(pady=10)

    def set_city(self, city):
        city = city.strip()
        if not city:
            messagebox.showwarning("输入错误", "城市不能为空。")
            return

        self.data.settings["city"] = city
        self.data.save()
        self.fetch_weather_async()
        messagebox.showinfo("天气同步", "城市已保存，正在同步天气。")

    def fetch_weather_async(self):
        city = self.data.settings.get("city", "杭州")
        threading.Thread(target=self.weather_worker, args=(city,), daemon=True).start()

    def weather_worker(self, city):
        try:
            self.weather_data = WeatherService.fetch(city)
        except Exception as exc:
            self.weather_data = {
                "city": city,
                "desc": "同步失败",
                "icon": "☁",
                "temp": "--",
                "humidity": "--",
                "wind": "--",
                "tips": f"天气同步失败：{exc}",
            }

        self.root.after(0, self.update_weather_ui)

    def update_weather_ui(self):
        data = self.weather_data or {}

        try:
            if hasattr(self, "weather_icon_label") and self.weather_icon_label.winfo_exists():
                self.weather_icon_label.config(text=data.get("icon", "☁"))
            if hasattr(self, "weather_main_label") and self.weather_main_label.winfo_exists():
                self.weather_main_label.config(text=f"{data.get('city', '')}  {data.get('temp', '--')}℃  {data.get('desc', '')}")
            if hasattr(self, "weather_sub_label") and self.weather_sub_label.winfo_exists():
                self.weather_sub_label.config(text=f"湿度{data.get('humidity', '--')}%  风速{data.get('wind', '--')}  {data.get('tips', '')}")
        except tk.TclError:
            pass

        if self.current_page == "天气同步":
            self.show_page("天气同步")

    # ==================== 统计分析 ====================

    def page_stats(self):
        wrap = tk.Frame(self.main, bg=COLORS["bg"])
        wrap.pack(fill=tk.BOTH, expand=True, padx=18, pady=18)

        top = UI.card(wrap)
        top.pack(fill=tk.X, pady=(0, 12))
        top.configure(height=84)
        top.pack_propagate(False)
        UI.label(top, "统计分析", 20, "bold", bg=COLORS["card"]).pack(side=tk.LEFT, padx=18)

        summary = tk.Frame(wrap, bg=COLORS["bg"])
        summary.pack(fill=tk.X, pady=(0, 12))

        today_tasks = [t for t in self.data.tasks if t.task_date == today_str()]
        week_start = date.today() - timedelta(days=date.today().weekday())
        week_end = week_start + timedelta(days=6)
        week_tasks = [t for t in self.data.tasks if t.dt and week_start <= t.dt.date() <= week_end]

        items = [
            ("今日完成率", self.percent_text(today_tasks), COLORS["green"]),
            ("本周完成率", self.percent_text(week_tasks), COLORS["blue"]),
            ("总任务数", str(len(self.data.tasks)), COLORS["purple"]),
            ("习惯打卡", f"{len([h for h in self.data.habits if h.checked_today()])}/{len(self.data.habits)}", COLORS["orange"]),
        ]

        for title, value, color in items:
            card = UI.card(summary)
            card.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 12))
            card.configure(height=88)
            card.pack_propagate(False)
            UI.label(card, title, 11, fg=COLORS["sub"], bg=COLORS["card"]).pack(anchor="w", padx=18, pady=(14, 2))
            UI.label(card, value, 22, "bold", fg=color, bg=COLORS["card"]).pack(anchor="w", padx=18)

        charts = tk.Frame(wrap, bg=COLORS["bg"])
        charts.pack(fill=tk.BOTH, expand=True)

        bar_card = UI.card(charts)
        bar_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 12))
        UI.label(bar_card, "任务完成率柱状图", 14, "bold", bg=COLORS["card"]).pack(anchor="w", padx=16, pady=14)
        self.bar_canvas = tk.Canvas(bar_card, bg=COLORS["card"], highlightthickness=0)
        self.bar_canvas.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)
        self.bar_canvas.bind("<Configure>", lambda e: self.draw_completion_bar())

        pie_card = UI.card(charts)
        pie_card.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        UI.label(pie_card, "任务分类饼图", 14, "bold", bg=COLORS["card"]).pack(anchor="w", padx=16, pady=14)
        self.pie_canvas = tk.Canvas(pie_card, bg=COLORS["card"], highlightthickness=0)
        self.pie_canvas.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)
        self.pie_canvas.bind("<Configure>", lambda e: self.draw_category_pie())

    def percent_text(self, tasks):
        if not tasks:
            return "0%"
        done = len([task for task in tasks if task.completed])
        return f"{int(done / len(tasks) * 100)}%"

    def draw_completion_bar(self):
        if not hasattr(self, "bar_canvas") or not self.bar_canvas.winfo_exists():
            return

        c = self.bar_canvas
        c.delete("all")
        w = c.winfo_width()
        h = c.winfo_height()

        if w <= 20 or h <= 20:
            return

        current = date.today()
        week_start = current - timedelta(days=current.weekday())
        days = [week_start + timedelta(days=i) for i in range(7)]

        rates = []
        counts = []
        for d in days:
            tasks = [task for task in self.data.tasks if task.task_date == d.strftime("%Y-%m-%d")]
            done = len([task for task in tasks if task.completed])
            rate = int(done / len(tasks) * 100) if tasks else 0
            rates.append(rate)
            counts.append((done, len(tasks)))

        left = 55
        bottom = h - 44
        top = 35
        usable_h = bottom - top
        gap = (w - 100) / 7
        bar_w = max(24, gap * 0.52)

        c.create_line(left, top, left, bottom, fill=COLORS["line"])
        c.create_line(left, bottom, w - 35, bottom, fill=COLORS["line"])

        week_names = "一二三四五六日"
        palette = [COLORS["blue"], COLORS["green"], COLORS["pink"], COLORS["orange"], COLORS["purple"], COLORS["blue"], COLORS["green"]]

        for i, rate in enumerate(rates):
            x = left + i * gap + gap * 0.25
            bar_h = usable_h * rate / 100
            c.create_rectangle(x, bottom - bar_h, x + bar_w, bottom, fill=palette[i], outline="")
            c.create_text(x + bar_w / 2, bottom - bar_h - 14, text=f"{rate}%", fill=COLORS["text"], font=("Microsoft YaHei", 9, "bold"))
            c.create_text(x + bar_w / 2, bottom + 18, text=week_names[i], fill=COLORS["sub"], font=("Microsoft YaHei", 9))
            c.create_text(x + bar_w / 2, bottom + 34, text=f"{counts[i][0]}/{counts[i][1]}", fill=COLORS["sub"], font=("Microsoft YaHei", 8))

    def draw_category_pie(self):
        if not hasattr(self, "pie_canvas") or not self.pie_canvas.winfo_exists():
            return

        c = self.pie_canvas
        c.delete("all")
        w = c.winfo_width()
        h = c.winfo_height()

        if w <= 20 or h <= 20:
            return

        counts = {name: 0 for name in TYPE_COLORS}
        for task in self.data.tasks:
            counts[task.category] = counts.get(task.category, 0) + 1

        total = sum(counts.values())
        if total == 0:
            c.create_text(w / 2, h / 2, text="暂无任务数据", fill=COLORS["sub"], font=("Microsoft YaHei", 14))
            return

        size = min(w, h) * 0.48
        x1 = w * 0.12
        y1 = h * 0.18
        x2 = x1 + size
        y2 = y1 + size

        start = 0
        for name, count in counts.items():
            if count <= 0:
                continue
            extent = count / total * 360
            color = TYPE_COLORS.get(name, TYPE_COLORS["其他"])[0]
            c.create_arc(x1, y1, x2, y2, start=start, extent=extent, fill=color, outline="white", width=2)
            start += extent

        c.create_oval(x1 + size * 0.32, y1 + size * 0.32, x2 - size * 0.32, y2 - size * 0.32, fill=COLORS["card"], outline="")
        c.create_text((x1 + x2) / 2, (y1 + y2) / 2, text=f"{total}\n总数", fill=COLORS["text"], font=("Microsoft YaHei", 13, "bold"))

        lx = x2 + 36
        ly = y1 + 10
        for i, (name, count) in enumerate(counts.items()):
            color = TYPE_COLORS.get(name, TYPE_COLORS["其他"])[0]
            percent = count / total * 100 if total else 0
            c.create_rectangle(lx, ly + i * 30, lx + 13, ly + i * 30 + 13, fill=color, outline="")
            c.create_text(lx + 22, ly + i * 30 + 7, text=f"{name}  {count}个  {percent:.1f}%", anchor="w", fill=COLORS["text"], font=("Microsoft YaHei", 10))

    # ==================== 设置中心 ====================

    def page_settings(self):
        wrap = tk.Frame(self.main, bg=COLORS["bg"])
        wrap.pack(fill=tk.BOTH, expand=True, padx=18, pady=18)

        card = UI.card(wrap)
        card.pack(fill=tk.BOTH, expand=True)

        UI.label(card, "设置中心", 20, "bold", bg=COLORS["card"]).pack(anchor="w", padx=24, pady=(24, 10))
        UI.label(card, "管理个人资料与天气城市。", 10, fg=COLORS["sub"], bg=COLORS["card"]).pack(anchor="w", padx=24, pady=(0, 18))

        form = tk.Frame(card, bg=COLORS["card"])
        form.pack(anchor="nw", fill=tk.X, padx=24)

        username_var = tk.StringVar(value=self.data.settings.get("username", "学习者"))
        avatar_var = tk.StringVar(value=self.data.settings.get("avatar", "👤"))
        city_var = tk.StringVar(value=self.data.settings.get("city", "杭州"))

        profile_card = tk.Frame(form, bg=COLORS["blue_light"], highlightthickness=1, highlightbackground=COLORS["line"])
        profile_card.pack(fill=tk.X, pady=(0, 18))

        preview_canvas = tk.Canvas(profile_card, width=72, height=72, bg=COLORS["blue_light"], highlightthickness=0)
        preview_canvas.pack(side=tk.LEFT, padx=18, pady=16)
        preview_canvas.create_oval(6, 6, 66, 66, fill=COLORS["pink_light"], outline="")
        preview_avatar_text = preview_canvas.create_text(36, 37, text=avatar_var.get() or "👤", font=("Microsoft YaHei", 30))

        profile_text = tk.Frame(profile_card, bg=COLORS["blue_light"])
        profile_text.pack(side=tk.LEFT, fill=tk.X, expand=True)
        preview_name = UI.label(profile_text, f"你好，{username_var.get() or '学习者'}", 15, "bold", bg=COLORS["blue_light"])
        preview_name.pack(anchor="w")
        UI.label(profile_text, "点击左侧头像或昵称可快速修改", 10, fg=COLORS["sub"], bg=COLORS["blue_light"]).pack(anchor="w", pady=(5, 0))

        def update_preview(*_):
            preview_name.config(text=f"你好，{username_var.get().strip() or '学习者'}")
            preview_canvas.itemconfig(preview_avatar_text, text=avatar_var.get().strip() or "👤")

        username_var.trace_add("write", update_preview)
        avatar_var.trace_add("write", update_preview)

        left = tk.Frame(form, bg=COLORS["card"])
        left.pack(side=tk.LEFT, anchor="n", fill=tk.BOTH, expand=True, padx=(0, 18))

        right = tk.Frame(form, bg=COLORS["card"])
        right.pack(side=tk.LEFT, anchor="n", fill=tk.BOTH, expand=True)

        UI.label(left, "修改昵称", 11, "bold", fg=COLORS["sub"], bg=COLORS["card"]).pack(anchor="w", pady=(4, 4))
        UI.entry(left, username_var, 30).pack(fill=tk.X, ipady=8)

        UI.label(left, "天气城市", 11, "bold", fg=COLORS["sub"], bg=COLORS["card"]).pack(anchor="w", pady=(14, 4))
        UI.entry(left, city_var, 30).pack(fill=tk.X, ipady=8)

        UI.label(right, "修改头像", 11, "bold", fg=COLORS["sub"], bg=COLORS["card"]).pack(anchor="w", pady=(4, 8))

        avatar_grid = tk.Frame(right, bg=COLORS["card"])
        avatar_grid.pack(anchor="w")

        avatar_options = [
            "👩‍🎓", "🧑‍💻", "👩‍💻", "🌸", "🌙", "⭐",
            "🐱", "🐰", "🐼", "🦊", "🍀", "💎",
            "🦋", "☁️", "🌈", "📚", "🎧", "🍓",
        ]

        bg_options = [
            COLORS["pink_light"], COLORS["blue_light"], COLORS["green_light"],
            COLORS["orange_light"], COLORS["purple_light"], COLORS["card2"]
        ]

        def set_avatar(icon):
            avatar_var.set(icon)

        for i, icon in enumerate(avatar_options):
            btn = tk.Button(
                avatar_grid,
                text=icon,
                bg=bg_options[i % len(bg_options)],
                fg=COLORS["text"],
                activebackground=COLORS["blue_light"],
                bd=0,
                width=4,
                height=2,
                cursor="hand2",
                font=("Microsoft YaHei", 16),
                command=lambda x=icon: set_avatar(x),
            )
            btn.grid(row=i // 6, column=i % 6, padx=5, pady=5)

        action = tk.Frame(card, bg=COLORS["card"])
        action.pack(anchor="w", padx=24, pady=22)

        def save_settings():
            username = username_var.get().strip()
            avatar = avatar_var.get().strip() or "👤"
            city = city_var.get().strip()

            if not username:
                messagebox.showwarning("输入错误", "昵称不能为空。")
                return
            if not city:
                messagebox.showwarning("输入错误", "城市不能为空。")
                return

            self.data.settings["username"] = username
            self.data.settings["avatar"] = avatar
            self.data.settings["city"] = city
            self.data.save()

            self.refresh_user_profile()
            self.fetch_weather_async()
            messagebox.showinfo("成功", "设置已保存。")

        UI.button(action, "保存设置", save_settings, COLORS["blue"]).pack(side=tk.LEFT)
        UI.button(action, "单独修改头像", self.open_avatar_picker_dialog, COLORS["pink"]).pack(side=tk.LEFT, padx=10)
        UI.button(action, "单独修改昵称", self.open_nickname_dialog, COLORS["green"]).pack(side=tk.LEFT)

        missing = []
        if requests is None:
            missing.append("requests")
        if notification is None:
            missing.append("plyer")
        if Image is None:
            missing.append("pillow")

        dep_text = "依赖库状态：完整" if not missing else "缺少依赖：" + "、".join(missing) + "，请执行 pip install requests plyer pillow"
        UI.label(card, dep_text, 10, fg=COLORS["sub"], bg=COLORS["card"]).pack(anchor="w", padx=24, pady=8)
        UI.label(card, f"数据文件：{DATA_FILE}", 10, fg=COLORS["sub"], bg=COLORS["card"]).pack(anchor="w", padx=24, pady=8)

    # ==================== 定时提醒 ====================

    def reminder_worker(self):
        while self.running:
            current_time = datetime.now()
            changed = False

            for task in self.data.tasks:
                if task.completed or task.reminded or not task.reminder_enabled:
                    continue

                dt = task.dt
                if not dt:
                    continue

                remind_at = dt - timedelta(minutes=task.remind_minutes)
                if remind_at <= current_time <= dt + timedelta(minutes=1):
                    task.reminded = True
                    changed = True
                    self.reminder_queue.put(task)

            if changed:
                self.data.save()

            time.sleep(5)

    def poll_reminders(self):
        try:
            while True:
                task = self.reminder_queue.get_nowait()
                self.show_notification(task)
        except queue.Empty:
            pass

        if self.running:
            self.root.after(1000, self.poll_reminders)

    def show_notification(self, task):
        title = "日程提醒"
        message = f"{task.title}\n时间：{task.task_date} {task.task_time}\n提前：{task.remind_minutes}分钟"

        try:
            if notification:
                notification.notify(title=title, message=message, timeout=8, app_name=APP_NAME)
        except Exception:
            pass

        try:
            if platform.system() == "Windows":
                import winsound
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            else:
                print("\a", end="")
        except Exception:
            pass

        messagebox.showinfo(title, message)

    # ==================== 公共定时更新 ====================

    def update_clock(self):
        now = datetime.now()

        try:
            if hasattr(self, "clock_label") and self.clock_label.winfo_exists():
                self.clock_label.config(text=now.strftime("%H:%M:%S"))

            if hasattr(self, "date_label") and self.date_label.winfo_exists():
                self.date_label.config(text=format_cn_date(now.date()))

            if hasattr(self, "lunar_label") and self.lunar_label.winfo_exists():
                self.lunar_label.config(text=simple_lunar_text(now.date()))

            if hasattr(self, "timeline_canvas") and self.timeline_canvas.winfo_exists() and self.current_page == "日程计划":
                self.draw_timeline()

        except tk.TclError:
            pass

        if self.running:
            self.root.after(1000, self.update_clock)

    def on_close(self):
        self.running = False
        self.data.save()
        self.root.destroy()


def main():
    root = tk.Tk()
    SmartScheduleApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
