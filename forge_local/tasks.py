"""本地任务注册表（内存，保留最近 200 个），带日志与进度。"""

import secrets
import threading
import time
import traceback

MAX_TASKS = 200
MAX_LOG = 1_000_000


class TaskError(Exception):
    """任务内可预期的失败，消息直接展示给用户。"""


class Task:
    def __init__(self, ttype, title):
        self.id = "t_" + time.strftime("%Y%m%d_%H%M%S") + "_" + secrets.token_hex(2)
        self.type = ttype
        self.title = title
        self.status = "running"
        self.progress = 0.0
        self.created = time.time()
        self.finished = None
        self.result = None
        self.error = None
        self._log = []
        self._len = 0
        self._dropped = 0       # 因超长被丢弃的前缀字符数（offset 仍单调）
        self.lock = threading.Lock()

    def log(self, msg):
        line = time.strftime("[%H:%M:%S] ") + str(msg).rstrip("\n") + "\n"
        with self.lock:
            self._log.append(line)
            self._len += len(line)
            while self._len - self._dropped > MAX_LOG and len(self._log) > 1:
                first = self._log.pop(0)
                self._dropped += len(first)

    def set_progress(self, p, title=None):
        with self.lock:
            self.progress = max(0.0, min(1.0, float(p)))
            if title:
                self.title = title

    def text(self):
        with self.lock:
            return "".join(self._log)

    def read_log(self, offset):
        with self.lock:
            full = "".join(self._log)
            base = self._dropped
            total = self._len
            done = self.status != "running"
        offset = max(0, int(offset))
        if offset < base:
            offset = base
        return {"text": full[offset - base:], "offset": total, "done": done}

    def to_dict(self):
        with self.lock:
            tail = "".join(self._log[-40:])[-2000:]
            return {
                "id": self.id, "type": self.type, "title": self.title,
                "status": self.status, "progress": round(self.progress, 4),
                "log_tail": tail, "created": self.created, "finished": self.finished,
                "result": self.result, "error": self.error,
            }


class TaskRegistry:
    def __init__(self):
        self.lock = threading.Lock()
        self.tasks = []         # 旧 → 新

    def create(self, ttype, title, fn, *args):
        """创建任务并在后台线程执行 fn(task, *args)；fn 的返回值作为 result。"""
        t = Task(ttype, title)
        with self.lock:
            self.tasks.append(t)
            if len(self.tasks) > MAX_TASKS:
                # 优先丢弃已结束的最旧任务
                for i, old in enumerate(self.tasks):
                    if old.status != "running":
                        self.tasks.pop(i)
                        break
                else:
                    self.tasks.pop(0)

        def runner():
            try:
                res = fn(t, *args)
                with t.lock:
                    t.result = res if res is not None else t.result
                    t.status = "done"
                    t.progress = 1.0
            except TaskError as e:
                t.log("✗ " + str(e))
                with t.lock:
                    t.status, t.error = "error", str(e)
            except Exception as e:  # noqa: BLE001
                t.log("✗ 内部错误: %r\n%s" % (e, traceback.format_exc()))
                with t.lock:
                    t.status, t.error = "error", "%s: %s" % (type(e).__name__, e)
            finally:
                t.finished = time.time()

        threading.Thread(target=runner, name="task-" + t.id, daemon=True).start()
        return t

    def get(self, tid):
        with self.lock:
            for t in self.tasks:
                if t.id == tid:
                    return t
        return None

    def list(self):
        with self.lock:
            items = list(self.tasks)
        return [t.to_dict() for t in reversed(items)]

    def running(self, ttype=None):
        with self.lock:
            return [t for t in self.tasks
                    if t.status == "running" and (ttype is None or t.type == ttype)]
