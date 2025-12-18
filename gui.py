import tkinter as tk
from tkinter import ttk, messagebox

from parser_flow import parse_pascal_to_flow
from flow_cgen import FlowCGenerator
from flow import FlowNode, StartNode, EndNode, OperationNode, ConditionNode


# ---------- Graph utils ----------

SERVICE_MARKERS = {"/* empty */", "/* join */", "/* after while */", "/* after for */"}

def is_real(node: FlowNode) -> bool:
    if isinstance(node, (StartNode, EndNode, ConditionNode)):
        return True
    if isinstance(node, OperationNode):
        return not any(m in node.code for m in SERVICE_MARKERS)
    return False


def iter_reachable(start: FlowNode):
    visited = set()
    stack = [start]
    while stack:
        n = stack.pop()
        if n.id in visited:
            continue
        visited.add(n.id)
        yield n
        if isinstance(n, ConditionNode):
            if n.true_branch: stack.append(n.true_branch)
            if n.false_branch: stack.append(n.false_branch)
        for nx in n.next:
            stack.append(nx)


def skip_service(node: FlowNode | None) -> FlowNode | None:
    """
    Пропускает цепочки служебных OperationNode (/* empty */ и т.п.)
    по .next[0], пока не найдём реальный узел или не упремся.
    """
    seen = set()
    cur = node
    while cur is not None and cur.id not in seen and not is_real(cur):
        seen.add(cur.id)
        if getattr(cur, "next", None):
            cur = cur.next[0] if cur.next else None
        else:
            return None
    return cur


def is_loop_condition(cond: ConditionNode) -> bool:
    """
    Эвристика: если из true-ветки есть путь обратно в этот cond,
    считаем, что это цикл.
    """
    start = skip_service(cond.true_branch)
    if start is None:
        return False
    visited = set()
    stack = [start]
    while stack:
        n = stack.pop()
        if n.id in visited:
            continue
        visited.add(n.id)
        if n is cond:
            return True
        if isinstance(n, ConditionNode):
            if n.true_branch: stack.append(n.true_branch)
            if n.false_branch: stack.append(n.false_branch)
        for nx in n.next:
            stack.append(nx)
    return False


# ---------- Layout ----------

class Layout:
    """
    Очень простой layout:
    - основной поток идёт вниз по центру (x=0),
    - для ConditionNode: True уходит вправо, False — влево,
      потом ветки сводятся вниз в общий "join Y".
    - для циклов: back-edge рисуем слева, выход (false) — вправо.
    """
    def __init__(self):
        self.pos = {}          # node.id -> (x, y) в логических координатах
        self.level_y = 0       # текущая высота
        self.visited = set()

        # параметры
        self.step_y = 110
        self.branch_dx = 260   # отступ веток влево/вправо
        self.min_gap_y = 1

    def place_linear(self, node: FlowNode, x: int = 0):
        nid = node.id
        if nid in self.visited:
            return
        self.visited.add(nid)

        self.pos[nid] = (x, self.level_y)
        self.level_y += self.step_y

        if isinstance(node, ConditionNode):
            self.place_condition(node, x)
        else:
            # идти дальше по .next[0], пропуская служебные
            nxt = skip_service(node.next[0]) if getattr(node, "next", None) and node.next else None
            if nxt is not None:
                self.place_linear(nxt, x)

    def place_subchain(self, start: FlowNode, x: int, y_start: int, stop_at: FlowNode | None):
        """
        Размещает цепочку узлов (приближенно) начиная с y_start.
        stop_at — узел, при достижении которого ветку дальше не раскладываем.
        """
        cur = start
        y = y_start
        local_seen = set()
        while cur is not None and cur.id not in local_seen:
            local_seen.add(cur.id)
            if cur is stop_at:
                break
            if not is_real(cur):
                cur = skip_service(cur)
                if cur is None:
                    break
            if cur.id not in self.pos:
                self.pos[cur.id] = (x, y)
                y += self.step_y
            # если внутри встретили ещё condition — не раскладываем глубоко (минимальный вариант)
            if isinstance(cur, ConditionNode):
                # поставили ромб, дальше не углубляемся (иначе начнётся лавина)
                break
            cur = skip_service(cur.next[0]) if cur.next else None
        return y  # y, на котором ветка закончилась

    def place_condition(self, cond: ConditionNode, x_center: int):
        # true/false цели, пропуская служебные узлы
        t = skip_service(cond.true_branch)
        f = skip_service(cond.false_branch)

        loop = is_loop_condition(cond)

        # y текущего ромба
        _, y_cond = self.pos[cond.id]

        # Ветка TRUE вправо, FALSE влево (как ты просил)
        y_t_end = y_cond + self.step_y
        y_f_end = y_cond + self.step_y

        if t is not None:
            y_t_end = self.place_subchain(t, x_center + self.branch_dx, y_cond + self.step_y, stop_at=cond if loop else None)
        if f is not None:
            # для цикла выход (false) будем вести вправо, но саму false-ветку как "после цикла" оставим на центре ниже
            if loop:
                # false — это "выход": разместим на центре ниже
                if f.id not in self.pos:
                    self.pos[f.id] = (x_center, y_cond + self.step_y)
                y_f_end = y_cond + self.step_y + self.step_y
            else:
                y_f_end = self.place_subchain(f, x_center - self.branch_dx, y_cond + self.step_y, stop_at=None)

        # join Y = максимум конца веток
        join_y = max(y_t_end, y_f_end, y_cond + self.step_y) + self.step_y

        # Узел продолжения после условия (cond.next[0] в нашей модели)
        nxt = skip_service(cond.next[0]) if cond.next else None
        if nxt is not None and nxt.id not in self.pos:
            self.pos[nxt.id] = (x_center, join_y)
            # продолжим основную линию уже от nxt
            self.level_y = max(self.level_y, join_y + self.step_y)
            self.place_linear(nxt, x_center)


# ---------- GUI ----------

class App:
    SAMPLE1 = """var a, b: integer;
begin
  a := 1;
  b := a + 2;
  writeln(b);
end.
"""

    SAMPLE2 = """var i, s: integer;
begin
  s := 0;
  for i := 1 to 5 do
    s := s + i;
  writeln(s);
end.
"""

    SAMPLE3 = """var n, i, f: integer;
begin
  readln(n);
  f := 1;
  i := 1;
  while i <= n do
  begin
    f := f * i;
    i := i + 1;
  end;
  if f > 1000 then
    writeln(f)
  else
    writeln(0);
end.
"""

    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("Pascal → Блок-схема → C")

        self.current_start: FlowNode | None = None
        self.scale = 1.0

        # grid 3 columns
        root.columnconfigure(0, weight=1)
        root.columnconfigure(1, weight=1)
        root.columnconfigure(2, weight=1)
        root.rowconfigure(1, weight=1)

        tk.Label(root, text="PascalABC.NET").grid(row=0, column=0, sticky="nsew")
        tk.Label(root, text="Блок-схема").grid(row=0, column=1, sticky="nsew")
        tk.Label(root, text="C code").grid(row=0, column=2, sticky="nsew")

        self.txt_pascal = tk.Text(root, wrap="none")
        self.txt_pascal.grid(row=1, column=0, sticky="nsew", padx=2, pady=2)

        # canvas + scroll
        frame = tk.Frame(root)
        frame.grid(row=1, column=1, sticky="nsew", padx=2, pady=2)
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(frame, bg="white")
        self.vsb = tk.Scrollbar(frame, orient="vertical", command=self.canvas.yview)
        self.hsb = tk.Scrollbar(frame, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=self.vsb.set, xscrollcommand=self.hsb.set)

        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vsb.grid(row=0, column=1, sticky="ns")
        self.hsb.grid(row=1, column=0, sticky="ew")

        self.txt_c = tk.Text(root, wrap="none", state="disabled")
        self.txt_c.grid(row=1, column=2, sticky="nsew", padx=2, pady=2)

        # zoom + pan
        self.canvas.bind("<MouseWheel>", self.on_zoom)
        self.canvas.bind("<ButtonPress-1>", self.on_pan_start)
        self.canvas.bind("<B1-Motion>", self.on_pan_move)

        # buttons
        ttk.Button(root, text="Перевести", command=self.on_translate).grid(row=2, column=0, sticky="ew", pady=5)
        ttk.Button(root, text="Тест 1", command=lambda: self.load_sample(self.SAMPLE1)).grid(row=2, column=1, sticky="ew", pady=5)
        ttk.Button(root, text="Тест 2", command=lambda: self.load_sample(self.SAMPLE2)).grid(row=2, column=2, sticky="ew", pady=5)
        ttk.Button(root, text="Тест 3", command=lambda: self.load_sample(self.SAMPLE3)).grid(row=3, column=0, columnspan=3, sticky="ew", pady=5)

        self.load_sample(self.SAMPLE1)

    def load_sample(self, code: str):
        self.txt_pascal.delete("1.0", "end")
        self.txt_pascal.insert("1.0", code)

    def on_translate(self):
        src = self.txt_pascal.get("1.0", "end").strip()
        if not src:
            messagebox.showwarning("Внимание", "Введите код на PascalABC.NET")
            return
        try:
            seg = parse_pascal_to_flow(src)
        except Exception as e:
            messagebox.showerror("Ошибка парсинга", str(e))
            return

        self.current_start = seg.first
        self.scale = 1.0

        gen = FlowCGenerator()
        c_code = gen.generate(self.current_start)

        self.txt_c.config(state="normal")
        self.txt_c.delete("1.0", "end")
        self.txt_c.insert("1.0", c_code)
        self.txt_c.config(state="disabled")

        self.draw_flow()

    def on_zoom(self, event):
        if self.current_start is None:
            return
        self.scale *= 1.1 if event.delta > 0 else 1 / 1.1
        self.scale = max(0.35, min(3.0, self.scale))
        self.draw_flow()

    def on_pan_start(self, event):
        self.canvas.scan_mark(event.x, event.y)

    def on_pan_move(self, event):
        self.canvas.scan_dragto(event.x, event.y, gain=1)

    # -------- drawing primitives --------

    def draw_flow(self):
        self.canvas.delete("all")
        if self.current_start is None:
            return

        # layout
        lay = Layout()
        start = skip_service(self.current_start) or self.current_start
        lay.place_linear(start, x=0)
        pos = lay.pos

        # bounds (logical)
        xs = [x for x, _ in pos.values()]
        ys = [y for _, y in pos.values()]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        # transform
        def to_screen(lx, ly):
            sx = (lx - min_x) * self.scale + 140
            sy = (ly - min_y) * self.scale + 30
            return sx, sy

        # node sizes
        op_w = 180 * self.scale
        op_h = 55 * self.scale
        dia_w = 200 * self.scale
        dia_h = 70 * self.scale
        oval_w = 90 * self.scale
        oval_h = 45 * self.scale

        # helper: connection points on diamond
        def diamond_points(x, y):
            # returns (top, right, bottom, left)
            return (x, y - dia_h/2), (x + dia_w/2, y), (x, y + dia_h/2), (x - dia_w/2, y)

        # draw nodes
        nodes = [n for n in iter_reachable(start) if is_real(n)]
        for n in nodes:
            if n.id not in pos:
                continue
            lx, ly = pos[n.id]
            x, y = to_screen(lx, ly)

            if isinstance(n, StartNode) or isinstance(n, EndNode):
                color = "lightgreen" if isinstance(n, StartNode) else "lightcoral"
                self.canvas.create_oval(x - oval_w/2, y - oval_h/2, x + oval_w/2, y + oval_h/2,
                                        fill=color, outline="black")
                self.canvas.create_text(x, y, text=n.label)
            elif isinstance(n, ConditionNode):
                top, right, bottom, left = diamond_points(x, y)
                self.canvas.create_polygon(top[0], top[1], right[0], right[1], bottom[0], bottom[1], left[0], left[1],
                                           fill="lightyellow", outline="black")
                self.canvas.create_text(x, y, text=n.cond_code, width=dia_w - 14)
            elif isinstance(n, OperationNode):
                self.canvas.create_rectangle(x - op_w/2, y - op_h/2, x + op_w/2, y + op_h/2,
                                             fill="lightblue", outline="black")
                self.canvas.create_text(x, y, text=n.code, width=op_w - 14)

        # draw edges with requested style
        for n in nodes:
            if n.id not in pos:
                continue
            lx1, ly1 = pos[n.id]
            x1, y1 = to_screen(lx1, ly1)

            if isinstance(n, ConditionNode):
                loop = is_loop_condition(n)

                # targets
                t = skip_service(n.true_branch)
                f = skip_service(n.false_branch)

                # diamond side points
                top, right, bottom, left = diamond_points(x1, y1)

                # True: вправо
                if t is not None and t.id in pos:
                    x2, y2 = to_screen(*pos[t.id])
                    # из правого угла ромба -> к верху target
                    self.canvas.create_line(right[0], right[1], x2, y2 - op_h/2,
                                            arrow="last")
                    self.canvas.create_text((right[0] + x2) / 2, (right[1] + y2) / 2, text="T", fill="red")

                # False:
                if f is not None and f.id in pos:
                    x2, y2 = to_screen(*pos[f.id])

                    if loop:
                        # В цикле выход ведём вправо (как просил): из правого угла к выходу
                        self.canvas.create_line(right[0], right[1], x2 + 30*self.scale, y1,
                                                x2 + 30*self.scale, y2 - op_h/2,
                                                x2, y2 - op_h/2,
                                                arrow="last", smooth=False)
                        self.canvas.create_text((right[0] + x2) / 2, y1 - 14*self.scale, text="F", fill="red")
                    else:
                        # В if-else: else влево
                        self.canvas.create_line(left[0], left[1], x2, y2 - op_h/2,
                                                arrow="last")
                        self.canvas.create_text((left[0] + x2) / 2, (left[1] + y2) / 2, text="F", fill="red")

                # back-edge для циклов рисуем слева
                if loop and t is not None:
                    # ищем узел в true-ветке, у которого есть прямой next назад к n
                    # (обычно это последний узел тела)
                    back_from = None
                    visited2 = set()
                    stack2 = [t]
                    while stack2:
                        u = stack2.pop()
                        if u.id in visited2:
                            continue
                        visited2.add(u.id)
                        if u is n:
                            continue
                        if getattr(u, "next", None):
                            for nx in u.next:
                                if nx is n:
                                    back_from = u
                                    break
                        if back_from:
                            break
                        if isinstance(u, ConditionNode):
                            if u.true_branch: stack2.append(u.true_branch)
                            if u.false_branch: stack2.append(u.false_branch)
                        for nx in getattr(u, "next", []):
                            stack2.append(nx)

                    if back_from is not None and back_from.id in pos:
                        xb, yb = to_screen(*pos[back_from.id])
                        # ломаная слева: из низа back_from -> влево -> вверх -> влево к левому углу ромба
                        x_left_lane = min_x * self.scale + 40  # "левая шина"
                        self.canvas.create_line(
                            xb, yb + op_h/2,
                            x_left_lane, yb + op_h/2,
                            x_left_lane, y1,
                            left[0], left[1],
                            arrow="last"
                        )

                # обычный next (переход вниз) — из нижнего угла ромба
                if n.next:
                    nx = skip_service(n.next[0])
                    if nx is not None and nx.id in pos:
                        x2, y2 = to_screen(*pos[nx.id])
                        self.canvas.create_line(bottom[0], bottom[1], x2, y2 - op_h/2, arrow="last")

            else:
                # обычные операции: вниз по центру
                if getattr(n, "next", None) and n.next:
                    nx = skip_service(n.next[0])
                    if nx is not None and nx.id in pos:
                        x2, y2 = to_screen(*pos[nx.id])
                        self.canvas.create_line(x1, y1 + op_h/2, x2, y2 - op_h/2, arrow="last")

        # scrollregion
        self.canvas.config(scrollregion=self.canvas.bbox("all"))


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
