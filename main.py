import sys
import os
import json
import objc
# noinspection PyUnresolvedReferences
from Foundation import NSObject
# noinspection PyUnresolvedReferences
from AppKit import NSStatusBar, NSVariableStatusItemLength
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QPushButton, QListWidget, QListWidgetItem,
                             QLineEdit, QAbstractItemView, QInputDialog, QSpinBox)
from PyQt6.QtCore import Qt, QTimer


# ==========================================
# 1. Mac 原生点击事件代理 (PyObjC)
# ==========================================
class MenuBarClickHandler(NSObject):
    def initWithWindow_(self, window):
        self = objc.super(MenuBarClickHandler, self).init()
        if self is None:
            return None
        self.window = window
        return self

    @objc.IBAction
    def iconClicked_(self, sender):
        self.window.showNormal()
        self.window.raise_()
        self.window.activateWindow()


# ==========================================
# 2. 待办事项单行 UI (带 DDL 和真实交互)
# ==========================================
class TaskItemWidget(QWidget):
    def __init__(self, task_name, task_ddl, parent_list, item_ref):
        super().__init__()
        self.parent_list = parent_list
        self.item_ref = item_ref
        self.task_name = task_name
        self.task_ddl = task_ddl

        layout = QHBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)

        self.label = QLabel(f"{self.task_name} (DDL: {self.task_ddl})")
        layout.addWidget(self.label, stretch=1)

        self.btn_complete = QPushButton("完成")
        self.btn_complete.clicked.connect(self.complete_task)
        layout.addWidget(self.btn_complete)

        self.btn_postpone = QPushButton("延期")
        self.btn_postpone.clicked.connect(self.postpone_task)
        layout.addWidget(self.btn_postpone)

        self.setLayout(layout)

    def complete_task(self):
        row = self.parent_list.row(self.item_ref)
        self.parent_list.takeItem(row)

    def postpone_task(self):
        new_ddl, ok = QInputDialog.getText(
            self, "修改 DDL", f"重新设置 [{self.task_name}] 的 DDL:",
            text=self.task_ddl
        )
        if ok and new_ddl:
            self.task_ddl = new_ddl
            self.label.setText(f"{self.task_name} (DDL: {self.task_ddl})")

    # 用于将数据提取出来保存到 JSON
    def to_dict(self):
        return {"name": self.task_name, "ddl": self.task_ddl}


# ==========================================
# 3. 主窗口与菜单栏滚动逻辑
# ==========================================
class TaskManagerWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MindScroll 设置")
        self.resize(550, 400)
        self.data_file = "mindscroll_data.json"  # 本地保存的文件名

        layout = QVBoxLayout()

        # --- 顶部输入区 (任务 + DDL) ---
        input_layout = QHBoxLayout()
        self.task_input = QLineEdit()
        self.task_input.setPlaceholderText("待办事项 (例如: 完善论文)")

        self.ddl_input = QLineEdit()
        self.ddl_input.setPlaceholderText("DDL (例如: 周五 23:59)")
        self.ddl_input.setFixedWidth(120)

        self.add_btn = QPushButton("添加")
        self.add_btn.clicked.connect(self.add_task)

        input_layout.addWidget(self.task_input)
        input_layout.addWidget(self.ddl_input)
        input_layout.addWidget(self.add_btn)
        layout.addLayout(input_layout)

        # --- 设置区 (长度与速度) ---
        settings_layout = QHBoxLayout()

        self.length_spinbox = QSpinBox()
        self.length_spinbox.setRange(10, 150)  # 允许最大长度到 150 个字符
        self.length_spinbox.setPrefix("菜单栏显示长度: ")

        self.speed_spinbox = QSpinBox()
        self.speed_spinbox.setRange(50, 2000)
        self.speed_spinbox.setSingleStep(50)
        self.speed_spinbox.setPrefix("滚动速度(毫秒/字, 越小越快): ")

        settings_layout.addWidget(self.length_spinbox)
        settings_layout.addWidget(self.speed_spinbox)
        layout.addLayout(settings_layout)

        # --- 列表区 ---
        self.list_widget = QListWidget()
        self.list_widget.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        layout.addWidget(self.list_widget)

        # --- 底部控制区 ---
        self.save_btn = QPushButton("保存配置并开始滚动")
        self.save_btn.clicked.connect(self.save_and_hide)
        layout.addWidget(self.save_btn)
        self.setLayout(layout)

        # --- Mac 菜单栏初始化 ---
        self.status_bar = NSStatusBar.systemStatusBar()
        self.status_item = self.status_bar.statusItemWithLength_(NSVariableStatusItemLength)
        self.status_item.button().setTitle_("📌 点击添加待办")

        self.click_handler = MenuBarClickHandler.alloc().initWithWindow_(self)
        self.status_item.button().setTarget_(self.click_handler)
        self.status_item.button().setAction_(objc.selector(self.click_handler.iconClicked_, signature=b'v@:@'))

        # --- 滚动逻辑属性 ---
        self.scroll_timer = QTimer()
        self.scroll_timer.timeout.connect(self.scroll_text)
        self.full_text = ""
        self.scroll_position = 0

        # 初始化加载本地数据
        self.load_data()

    # 封装添加列表项的逻辑
    def add_task_to_list(self, name, ddl):
        item = QListWidgetItem(self.list_widget)
        task_widget = TaskItemWidget(name, ddl, self.list_widget, item)
        item.setSizeHint(task_widget.sizeHint())
        self.list_widget.addItem(item)
        self.list_widget.setItemWidget(item, task_widget)

    def add_task(self):
        task_text = self.task_input.text().strip()
        ddl_text = self.ddl_input.text().strip()

        if task_text and ddl_text:
            self.add_task_to_list(task_text, ddl_text)
            self.task_input.clear()
            self.ddl_input.clear()

    def load_data(self):
        # 如果存在本地存档，则读取
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                    # 恢复设置
                    settings = data.get("settings", {})
                    self.length_spinbox.setValue(settings.get("display_length", 30))
                    self.speed_spinbox.setValue(settings.get("scroll_speed", 400))

                    # 恢复待办列表
                    tasks = data.get("tasks", [])
                    for task in tasks:
                        self.add_task_to_list(task.get("name", ""), task.get("ddl", ""))
            except Exception as e:
                print(f"读取存档失败: {e}")
        else:
            # 默认设置
            self.length_spinbox.setValue(30)
            self.speed_spinbox.setValue(400)

    def save_and_hide(self):
        tasks_data = []
        display_texts = []

        # 遍历列表获取最新数据
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            widget = self.list_widget.itemWidget(item)
            tasks_data.append(widget.to_dict())
            display_texts.append(widget.label.text())

        # 整理要保存的数据结构
        data_to_save = {
            "settings": {
                "display_length": self.length_spinbox.value(),
                "scroll_speed": self.speed_spinbox.value()
            },
            "tasks": tasks_data
        }

        # 写入 JSON 文件
        try:
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"保存存档失败: {e}")

        # 更新滚动逻辑
        if not display_texts:
            self.full_text = "📌 暂无待办事项"
            self.scroll_timer.stop()
            self.status_item.button().setTitle_(self.full_text)
        else:
            self.full_text = "   🚀 " + " | ".join(display_texts) + "   "
            self.scroll_position = 0
            # 按照用户设定的速度启动定时器
            self.scroll_timer.start(self.speed_spinbox.value())

        self.hide()

    def scroll_text(self):
        display_length = self.length_spinbox.value()

        if len(self.full_text) <= display_length:
            self.status_item.button().setTitle_(self.full_text)
            return

        display_text = self.full_text[self.scroll_position: self.scroll_position + display_length]

        # 如果切片到了末尾，补全开头的字符实现循环效果
        if len(display_text) < display_length:
            display_text += self.full_text[:display_length - len(display_text)]

        self.status_item.button().setTitle_(display_text)

        self.scroll_position += 1
        if self.scroll_position >= len(self.full_text):
            self.scroll_position = 0


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    window = TaskManagerWindow()
    # 如果加载了数据有内容，可以直接让它跑起来并隐藏窗口，这里为了方便修改我们还是先展示窗口
    window.show()
    sys.exit(app.exec())