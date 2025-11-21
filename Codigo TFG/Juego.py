import os
import json
import random
import time
import threading
from datetime import datetime
import uuid
import tkinter as tk
from PIL import Image, ImageTk

from Conexion_Teensy import conectar_teensy, leer_teensy_linea, configurar_teensy
from Encriptacion import ensure_dirs, write_encrypted



class KneeRehabilitationGame:
    """
    Juego de rehabilitación: se ejecuta en un hilo separado.
    Solo controla GUI + lectura de Teensy.
    No realiza subidas a Adafruit IO (eso se maneja fuera del juego).
    """

    def __init__(self, parent, plan_config: dict, usuario_actual: str, on_finish_callback=None):
        self.parent = parent
        self.plan = dict(plan_config)
        self.usuario = usuario_actual
        self.on_finish_callback = on_finish_callback

        # Configuración del juego
        self.w, self.h = 1280, 720
        self.ang_min = float(self.plan.get("angulo_min", 0))
        self.ang_max = float(self.plan.get("angulo_max", 90))
        self.obj = int(self.plan.get("repeticiones", 10))

        # Estados
        self.total = self.ok = self.parcial = self.bad = 0
        self._phase = "waiting_min"
        self._max_reached = False
        self._peak = 0.0
        self.mediciones = []
        self.t0 = time.time()
        self._running = True
        self._paused = False
        self._partial_end = False

        # Conexión al Teensy
        self.ser = conectar_teensy()
        if self.ser:
            resorte = self.plan.get("resorte", "0")
            tipo = self.plan.get("tipo", "Extensión")
            tipo_cmd = "E" if tipo.lower().startswith("ext") else "F"
            configurar_teensy(self.ser, resorte, tipo_cmd)
            print(f"[Juego] Conectado y configurado: Resorte {resorte}, Tipo {tipo_cmd}")
        else:
            print("[Juego] No se detectó Teensy. Continuando sin datos en vivo.")

        # GUI
        self._build_gui()
        self._load_images()

        # Elementos del juego
        self.asteroides = []
        self.balas = []
        self.zonas = [1, 2, 3, 4, 3, 2, 1, 2]
        self.zona_index = 0
        self.max_asteroides = 4
        self.velocidad_asteroides = 3.0
        self.intervalo_generacion = 3
        self.last_spawn = 0

        # Contador de puntaje
        self.score = 0
        self.lbl_score = tk.Label(self.parent, text="Score: 0", bg="#111", fg="#FFD700",
                                  font=("Arial", 14, "bold"))
        self.lbl_score.place(x=20, y=20)

        # Hilo lector del Teensy
        self._stop_reader = threading.Event()
        self.reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self.reader_thread.start()

        # Bucle principal del juego (GUI)
        self._tick()

    # ================= GUI =================
    def _build_gui(self):
        for w in self.parent.winfo_children():
            w.destroy()
        self.canvas = tk.Canvas(self.parent, width=self.w, height=self.h, bg="black")
        self.canvas.pack(fill="both", expand=True)

        # Fondo estrellado
        for _ in range(100):
            x, y = random.randint(0, self.w), random.randint(0, self.h)
            self.canvas.create_oval(x - 1, y - 1, x + 1, y + 1, fill="white", outline="")

        # Barra superior
        top = tk.Frame(self.parent, bg="#111")
        top.place(relx=0.5, rely=0.02, anchor="n")

        tk.Button(top, text="Regresar", bg="#757575", fg="white", command=self._go_back).pack(side="left", padx=5)
        self.btn_pause = tk.Button(top, text="Pausar", bg="#2e7d32", fg="white", command=self._toggle_pause)
        self.btn_pause.pack(side="left", padx=5)
        tk.Button(top, text="Finalizar sesión", bg="#d32f2f", fg="white", command=self._finish_partial).pack(side="left", padx=5)

        # Barra inferior
        self.status_bar = tk.Label(self.parent, text="Conectando...", bg="#222", fg="white", font=("Arial", 11))
        self.status_bar.pack(side="bottom", fill="x")

    def _update_status_bar(self, msg, color="white"):
        if not self._running or not hasattr(self, "status_bar"):
            return
        try:
            self.status_bar.config(text=msg, fg=color)
        except tk.TclError:
            pass

    def _load_images(self):
        def load_img(name, size):
            path = os.path.join("imagenes", name)
            try:
                return ImageTk.PhotoImage(Image.open(path).resize(size, Image.LANCZOS))
            except Exception:
                return None

        self.nave_x, self.nave_y = 100, self.h // 2
        self.img_nave = load_img("Nave.png", (80, 80))
        self.img_bala = load_img("Disparo.png", (35, 35))
        self.img_ast = [load_img(f"Asteroide_{i}.png", (65, 65)) for i in range(3)]
        self.nave_id = self.canvas.create_image(self.nave_x, self.nave_y, image=self.img_nave or None)

    # =============== Lectura Teensy (en hilo) ===============
    def _reader_loop(self):
        ser = self.ser
        if not ser:
            self._update_status_bar("Sin conexión con Teensy", "orange")
            return
        try:
            next_t = time.time()
            while not self._stop_reader.is_set() and self._running:
                if self._paused:
                    time.sleep(0.1)
                    continue
                if time.time() < next_t:
                    time.sleep(0.01)
                    continue
                next_t += 0.05  # 20 Hz
                data = leer_teensy_linea(ser)
                if not data:
                    continue
                ang, fuerza = data
                self.parent.after(0, lambda a=ang, f=fuerza: self._on_sample(a, f))
        except Exception as e:
            print(f"[Juego] Error lector Teensy: {e}")
            self._update_status_bar("Error en lectura del Teensy", "red")

    # =============== Lógica principal ===============
    def _on_sample(self, ang, fuerza):
        if not self._running:
            return

        ang_min, ang_max = self.ang_min, self.ang_max
        if ang_max <= ang_min:
            ang_max = ang_min + 1

        # Normalizar
        p = min(1.0, max(0.0, (ang - ang_min) / (ang_max - ang_min)))
        self.nave_y = int((1 - p) * self.h)
        self.canvas.coords(self.nave_id, self.nave_x, self.nave_y)

        t_rel = round(time.time() - self.t0, 3)
        self.mediciones.append((t_rel, ang, fuerza))
        self._auto_shoot_if_aligned()
        self._update_rep_fsm(ang)

    def _update_rep_fsm(self, ang):
        p = (ang - self.ang_min) / (self.ang_max - self.ang_min)
        p = max(0, min(1, p))
        near_min, near_max = p <= 0.1, p >= 0.98
        if self._phase == "waiting_min" and near_min:
            self._phase, self._max_reached, self._peak = "going_up", False, p
        elif self._phase == "going_up":
            self._peak = max(self._peak, p)
            if near_max:
                self._max_reached = True
            if near_min and self._peak > 0.1:
                self.total += 1
                if self._max_reached:
                    self.ok += 1
                elif self._peak >= 0.5:
                    self.parcial += 1
                else:
                    self.bad += 1
                if self.total >= self.obj:
                    self._finish_now()
                    return
                self._phase = "waiting_min"

    # =============== Asteroides y balas ===============
    def _spawn_asteroid(self):
        if len(self.asteroides) >= self.max_asteroides:
            return
        zona = self.zonas[self.zona_index]
        self.zona_index = (self.zona_index + 1) % len(self.zonas)
        seccion = self.h / 4
        y = int((zona - 1) * seccion + seccion / 2 + random.randint(-40, 40))
        img = random.choice(self.img_ast)
        aid = self.canvas.create_image(self.w + 50, y, image=img)
        self.asteroides.append({"id": aid, "x": self.w + 50, "y": y})

    def _auto_shoot_if_aligned(self):
        for a in self.asteroides:
            if a["x"] > self.nave_x and abs(a["y"] - self.nave_y) <= 40:
                self._spawn_bullet(self.nave_x + 40, self.nave_y)
                break

    def _spawn_bullet(self, x, y):
        bid = self.canvas.create_image(x, y, image=self.img_bala)
        self.balas.append({"id": bid, "x": x, "y": y})

    def _move_asteroids(self):
        for a in list(self.asteroides):
            a["x"] -= self.velocidad_asteroides
            self.canvas.coords(a["id"], a["x"], a["y"])
            if a["x"] < -80:
                self.canvas.delete(a["id"])
                self.asteroides.remove(a)

    def _move_bullets(self):
        for b in list(self.balas):
            b["x"] += 10
            self.canvas.coords(b["id"], b["x"], b["y"])

            for a in list(self.asteroides):
                if abs(b["x"] - a["x"]) <= 50 and abs(b["y"] - a["y"]) <= 50:
                    # === NUEVO: asignar puntos según el tipo de asteroide ===
                    if a.get("img") in self.img_ast:
                        idx = self.img_ast.index(a["img"])
                        puntos = [1, 3, 5][idx] if 0 <= idx < 3 else 1
                    else:
                        puntos = 1

                    self.score += puntos
                    self.lbl_score.config(text=f"Score: {self.score}")

                    # Eliminar elementos del canvas
                    self.canvas.delete(a["id"])
                    self.asteroides.remove(a)
                    self.canvas.delete(b["id"])
                    self.balas.remove(b)
                    break

            if b["x"] > self.w + 80:
                self.canvas.delete(b["id"])
                self.balas.remove(b)

    # =============== Bucle principal ===============
    def _tick(self):
        if not self._running:
            return
        if not self._paused:
            now = time.time()
            if now - self.last_spawn >= self.intervalo_generacion:
                self._spawn_asteroid()
                self.last_spawn = now
            self._move_asteroids()
            self._move_bullets()
        self.parent.after(16, self._tick)

    # =============== Finalización ===============
    def _toggle_pause(self):
        self._paused = not self._paused
        self.btn_pause.config(text="Reanudar" if self._paused else "Pausar")

    def _go_back(self):
        self._running = False
        self._stop_reader.set()
        for w in self.parent.winfo_children():
            w.destroy()
        if self.on_finish_callback:
            self.on_finish_callback(None)

    def _finish_partial(self):
        self._partial_end = True
        self._finish_now()

    def _finish_now(self):
        if not self._running:
            return
        self._running = False
        self._stop_reader.set()

        resumen = {
            "usuario": self.usuario,
            "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "plan_usado": self.plan.get("id"),
            "duracion_s": int(time.time() - self.t0),
            "repeticiones": f"{self.total}/{self.obj}",
            "correctas": self.ok,
            "parciales": self.parcial,
            "incorrectas": self.bad,
            "estado": "Completada" if (self.total >= self.obj and not self._partial_end) else "Parcial",
            "score": self.score,  # 🟩 NUEVO campo
            "session_id": uuid.uuid4().hex[:8].upper()
        }

        self._persist_local(resumen)
        self._show_end_screen(resumen)

    def _persist_local(self, resumen):
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        user_dir = os.path.join(ensure_dirs(), self.usuario)
        os.makedirs(user_dir, exist_ok=True)

        session_id = uuid.uuid4().hex[:8].upper()

        # Combinar resumen + mediciones en un solo dict
        resumen_completo = dict(resumen)
        resumen_completo["session_id"] = session_id
        resumen_completo["mediciones"] = self.mediciones

        json_path = os.path.join(user_dir, f"{self.usuario}_sesion_{stamp}.json.enc")
        write_encrypted(json_path, json.dumps(resumen_completo, ensure_ascii=False, indent=2).encode("utf-8"))
        print(f"[Juego] Sesión guardada → {json_path}")

        # (No subimos directamente aquí, se hará en la sincronización posterior)
        self._update_status_bar("Sesión guardada localmente", "orange")

    def _show_end_screen(self, resumen):
        for w in self.parent.winfo_children():
            w.destroy()
        canvas = tk.Canvas(self.parent, width=self.w, height=self.h, bg="black", highlightthickness=0)
        canvas.pack(fill="both", expand=True)

        for _ in range(120):
            x, y = random.randint(0, self.w), random.randint(0, self.h)
            canvas.create_oval(x - 1, y - 1, x + 1, y + 1, fill="white", outline="")

        def texto(y, contenido, size=24, color="white"):
            canvas.create_text(self.w // 2, y, text=contenido, fill=color, font=("Arial", size, "bold"))

        texto(self.h // 2 - 120, "✅ Sesión finalizada", 36, "#00FF99")
        texto(self.h // 2 - 60, f"Usuario: {resumen.get('usuario', '-')}")
        texto(self.h // 2 - 20, f"Plan: {resumen.get('plan_usado', '-')}")
        dur = resumen.get("duracion_s", 0)
        texto(self.h // 2 + 20, f"Duración: {dur // 60:02d}:{dur % 60:02d}")
        texto(self.h // 2 + 60, f"Repeticiones: {resumen.get('repeticiones', '-')}")
        texto(self.h // 2 + 100,
              f"Correctas: {resumen.get('correctas', 0)} • Parciales: {resumen.get('parciales', 0)} • Incorrectas: {resumen.get('incorrectas', 0)}")
        texto(self.h // 2 + 140, f"Estado: {resumen.get('estado', '-')}")
        # === NUEVO: mostrar puntaje ===
        texto(self.h // 2 + 180, f"Puntaje total: {resumen.get('score', 0)}", 26, "#FFD700")

        boton = tk.Button(self.parent, text="Volver", bg="#757575", fg="white",
                          activebackground="#616161", bd=0, padx=14, pady=8,
                          command=lambda: self.on_finish_callback(resumen) if self.on_finish_callback else None)
        canvas.create_window(self.w // 2, int(self.h * 0.85), window=boton)


