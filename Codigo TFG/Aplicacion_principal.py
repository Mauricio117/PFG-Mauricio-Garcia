import threading
import os
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
import json
from datetime import datetime
from Encriptacion import load_or_create_key, ensure_dirs, read_encrypted
from Usuarios import (    add_user, verify_login, get_user, list_users,
    upsert_planes, list_session_summaries, list_therapists, list_patients)
from Conexion_Adafruit import threaded_upload_user, sync_users_with_cloud, send_data_http
from Juego import KneeRehabilitationGame


# ==========================================================
# Utilidades gráficas
# ==========================================================

def set_background(root, image_path="imagenes/Costa_Rica.jpg"):
    """Fondo escalado al tamaño de la ventana, sin tapar la barra de estado."""
    for w in root.winfo_children():
        if isinstance(w, tk.Canvas) and getattr(w, "_is_bg", False):
            w.destroy()
    try:
        img = Image.open(image_path).resize((1280, 720), Image.LANCZOS)
        tkimg = ImageTk.PhotoImage(img)
        canvas = tk.Canvas(root, width=1280, height=720, highlightthickness=0, bd=0)
        canvas._is_bg = True
        canvas.place(x=0, y=0, relwidth=1, relheight=1)
        canvas.background = tkimg
        canvas.create_image(0, 0, image=tkimg, anchor="nw")

        root.after_idle(lambda: canvas.lower("all"))

    except Exception as e:
        print("[Background] Error:", e)
        root.configure(bg="#f5f5f5")


    except Exception as e:
        print("[Background] Error:", e)
        root.configure(bg="#f5f5f5")



def make_card(root, title_text):
    """Tarjeta central blanca con título y separador."""
    card = tk.Frame(root, bg="#ffffff", bd=0, highlightthickness=0)
    card.place(relx=0.5, rely=0.5, anchor="center")
    card.configure(highlightbackground="#e0e0e0", highlightcolor="#e0e0e0")

    title = tk.Label(card, text=title_text, font=("Arial", 18, "bold"), fg="#2e7d32", bg="#ffffff")
    title.grid(row=0, column=0, sticky="w", padx=16, pady=(16, 4))

    sep = ttk.Separator(card, orient="horizontal")
    sep.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 12))

    inner = tk.Frame(card, bg="#ffffff")
    inner.grid(row=2, column=0, sticky="nsew", padx=16, pady=12)

    card.grid_columnconfigure(0, weight=1)
    card.grid_rowconfigure(2, weight=1)
    return card, inner

def green_button(parent, text, cmd):
    return tk.Button(parent, text=text, command=cmd, bg="#2e7d32", fg="white",
                     activebackground="#1b5e20", activeforeground="white",
                     bd=0, padx=14, pady=6, cursor="hand2")

def grey_button(parent, text, cmd):
    return tk.Button(parent, text=text, command=cmd, bg="#757575", fg="white",
                     activebackground="#616161", activeforeground="white",
                     bd=0, padx=14, pady=6, cursor="hand2")

def upload_button(parent, text, cmd):
    return tk.Button(parent, text=text, command=cmd, bg="#0277bd", fg="white",
                     activebackground="#01579b", activeforeground="white",
                     bd=0, padx=14, pady=6, cursor="hand2")


# ==========================================================
# Clase principal de la aplicación
# ==========================================================

class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Sistema de Rehabilitación de Rodilla")
        self.root.geometry("1280x720")
        self.root.resizable(False, False)

        # Crear barra de estado persistente
        self.status_bar = tk.Label(self.root, text="", bg="#222", fg="white", font=("Arial", 10))
        self.status_bar.pack(side="bottom", fill="x")

        self.current_user = None
        self.id_app = None

        self._ensure_status_bar()

        self._screen_login()

    # ===================== Adafruit IO =====================

    def _start_initial_sync(self, current_uid: str):
        """
        Sincroniza automáticamente todos los pacientes al iniciar la app.
        Usa hilos para no bloquear la interfaz.
        """

        def sync_thread():
            try:
                self._safe_status_update("🔄 Sincronizando datos con Adafruit IO...", "#c7a500")

                sync_users_with_cloud()

                users = list_users()
                pacientes = {uid: u for uid, u in users.items() if u.get("tipo") == "paciente"}

                for uid in pacientes.keys():
                    self._safe_status_update(f"⬆️ Subiendo datos pendientes de {uid}...", "#0277bd")
                    threaded_upload_user(uid)

                self._safe_status_update("✅ Sincronización en segundo plano iniciada", "#2e7d32")

            except Exception as e:
                print(f"[SYNC ERROR] {e}")
                self._safe_status_update("⚠️ Error durante sincronización", "#b71c1c")

        threading.Thread(target=sync_thread, daemon=True).start()

    # ==================== Barra de estado segura ====================

    def _ensure_status_bar(self):
        # Crea una sola barra de estado persistente (si no existe)
        if getattr(self, "status_bar", None) and self.status_bar.winfo_exists():
            return
        self.status_bar = tk.Label(self.root, text="", bg="#222222", fg="white", font=("Arial", 11))
        self.status_bar.place(relx=0, rely=1.0, anchor="sw", relwidth=1.0)

    def _safe_status_update(self, text, color=None):
        def _update():
            if not hasattr(self, "status_bar") or not self.status_bar.winfo_exists():
                return
            if color:
                self.status_bar.config(text=text, bg=color)
            else:
                self.status_bar.config(text=text)

        self.root.after(0, _update)

    # ==================== Utilidades ====================

    def _clear(self):
        """Elimina todos los widgets menos la barra de estado persistente."""
        for w in self.root.winfo_children():
            if w is getattr(self, "status_bar", None):
                continue  # mantener barra viva
            w.destroy()

    def _back_to_login(self):
        self._screen_login()


    # ==================== Pantalla de inicio de sesión ====================

    def _screen_login(self):
        self._clear()
        set_background(self.root, "imagenes/Costa_Rica.jpg")
        card, inner = make_card(self.root, "Sistema de rehabilitación de rodilla")

        # Configurar columnas para centrado
        inner.grid_columnconfigure(0, weight=1)
        inner.grid_columnconfigure(1, weight=1)

        # Campos centrados
        tk.Label(inner, text="Usuario (ID_app):", bg="#ffffff").grid(row=0, column=0, sticky="e", padx=6, pady=6)
        self.e_user = ttk.Entry(inner, width=26, justify="center")
        self.e_user.grid(row=0, column=1, padx=6, pady=6, sticky="ew")

        tk.Label(inner, text="Contraseña:", bg="#ffffff").grid(row=1, column=0, sticky="e", padx=6, pady=6)
        self.e_pass = ttk.Entry(inner, width=26, show="*", justify="center")
        self.e_pass.grid(row=1, column=1, padx=6, pady=6, sticky="ew")

        # Botones centrados
        btns = tk.Frame(inner, bg="#ffffff")
        btns.grid(row=2, column=0, columnspan=2, pady=(14, 0))
        btns.grid_columnconfigure(0, weight=1)
        btns.grid_columnconfigure(1, weight=1)

        green_button(btns, "Iniciar sesión", self._action_login).grid(row=0, column=0, padx=10)
        grey_button(btns, "Registrar nuevo usuario", self._screen_register).grid(row=0, column=1, padx=10)

        # Centrar todo verticalmente en el recuadro
        for r in range(3):
            inner.grid_rowconfigure(r, weight=1)


    # ==================== Pantalla de registro ====================

    def _screen_register(self):
        self._clear()
        set_background(self.root, "imagenes/Costa_Rica.jpg")
        card, inner = make_card(self.root, "Crear cuenta en el sistema de rehabilitación")

        # Centrado de columnas
        inner.grid_columnconfigure(1, weight=1)

        campos = [
            ("Nombre completo:", "r_nombre"),
            ("Cédula (ID):", "r_id"),
            ("ID de aplicación (ID_app):", "r_idapp"),
            ("Contraseña:", "r_pw", "*"),
            ("Confirmar contraseña:", "r_pw2", "*"),
        ]

        # Crear etiquetas y campos centrados
        for i, campo in enumerate(campos):
            label_text = campo[0]
            attr = campo[1]
            show_char = campo[2] if len(campo) > 2 else None
            tk.Label(inner, text=label_text, bg="#ffffff").grid(row=i, column=0, sticky="e", padx=6, pady=6)
            entry = ttk.Entry(inner, width=28, show=show_char, justify="center") if show_char else ttk.Entry(inner,
                                                                                                             width=28,
                                                                                                             justify="center")
            entry.grid(row=i, column=1, padx=6, pady=6, sticky="ew")
            setattr(self, attr, entry)

        # Tipo de usuario
        tk.Label(inner, text="Tipo de usuario:", bg="#ffffff").grid(row=5, column=0, sticky="e", padx=6, pady=6)
        self.r_tipo = ttk.Combobox(inner, values=["Administrador", "Terapeuta", "Paciente"], state="readonly", width=26,
                                   justify="center")
        self.r_tipo.grid(row=5, column=1, padx=6, pady=6, sticky="ew")
        self.r_tipo.bind("<<ComboboxSelected>>", self._on_tipo_change)

        # Terapeuta asignado dinámico
        tk.Label(inner, text="Terapeuta asignado (solo paciente):", bg="#ffffff").grid(row=6, column=0, sticky="e",
                                                                                       padx=6, pady=6)
        terapeutas = [
            u_id for u_id, u_data in list_users().items()
            if u_data.get("tipo") == "terapeuta"
        ]
        self.r_ter = ttk.Combobox(inner, values=terapeutas, state="disabled", width=26, justify="center")
        self.r_ter.grid(row=6, column=1, padx=6, pady=6, sticky="ew")

        # Botones centrados
        btns = tk.Frame(inner, bg="#ffffff")
        btns.grid(row=7, column=0, columnspan=2, pady=(14, 0))
        btns.grid_columnconfigure(0, weight=1)
        btns.grid_columnconfigure(1, weight=1)

        green_button(btns, "Registrar", self._do_register).grid(row=0, column=0, padx=10)
        grey_button(btns, "Volver al inicio", self._back_to_login).grid(row=0, column=1, padx=10)

        # Centrar filas verticalmente
        for r in range(8):
            inner.grid_rowconfigure(r, weight=1)

    def _on_tipo_change(self, evt=None):
        """Actualiza el combobox de terapeutas si el tipo seleccionado es 'Paciente'."""
        t = self.r_tipo.get().strip().lower()

        if t == "paciente":
            usuarios = list_users()
            terapeutas = [
                uid for uid, data in usuarios.items()
                if data.get("tipo", "").lower() == "terapeuta"
            ]

            if not terapeutas:
                self.r_ter["values"] = ["(No hay terapeutas registrados)"]
                self.r_ter.set("(No hay terapeutas registrados)")
                self.r_ter.configure(state="disabled")
            else:
                self.r_ter["values"] = terapeutas
                self.r_ter.configure(state="readonly")
                self.r_ter.set(terapeutas[0])
        else:
            self.r_ter.set("")
            self.r_ter.configure(state="disabled")

    # ==================== Login y redirección ====================

    def _action_login(self):
        uid = self.e_user.get().strip()
        pw = self.e_pass.get().strip()

        ok, data_or_msg = verify_login(uid, pw)
        if not ok:
            messagebox.showerror("Error", data_or_msg)
            return

        self.current_user = data_or_msg
        self.id_app = uid

        t = self.current_user.get("tipo")
        if t == "administrador":
            self._screen_admin()
        elif t == "terapeuta":
            self._screen_therapist()
        else:
            self._screen_patient()

        # ====== Iniciar sincronización con Adafruit IO ======
        self._start_initial_sync(uid)

    def _do_register(self):
        """Procesa el registro de un nuevo usuario y lo guarda en usuarios.json."""
        nombre = self.r_nombre.get().strip()
        cedula = self.r_id.get().strip()
        id_app = self.r_idapp.get().strip()
        pw1 = self.r_pw.get().strip()
        pw2 = self.r_pw2.get().strip()
        tipo = self.r_tipo.get().strip().lower()
        terapeuta_asig = self.r_ter.get().strip() if tipo == "paciente" else ""

        # ==== Validaciones básicas ====
        if not all([nombre, cedula, id_app, pw1, pw2, tipo]):
            messagebox.showwarning("Campos vacíos", "Debe completar todos los campos.")
            return

        if pw1 != pw2:
            messagebox.showwarning("Contraseña", "Las contraseñas no coinciden.")
            return

        # ==== Crear usuario con el formato esperado ====
        nuevo = {
            "id_app": id_app,  # 👈 NECESARIO para que add_user() funcione
            "password": pw1,
            "tipo": tipo,
            "nombre": nombre,
            "id": cedula,
            "terapeuta": terapeuta_asig
        }

        ok, msg = add_user(nuevo)
        if ok:
            messagebox.showinfo("Registro exitoso", f"Usuario '{id_app}' creado correctamente.")
            self._screen_login()
        else:
            messagebox.showerror("Error", msg)

    # ==================== Panel de administrador ====================

    def _screen_admin(self):
        self._clear()
        set_background(self.root, "imagenes/Costa_Rica.jpg")
        card, inner = make_card(self.root, "Panel de administración")

        cols = ("Usuario (ID_app)","Tipo","Nombre","Cédula (ID)","Terapeuta","Contraseña")
        tv = ttk.Treeview(inner, columns=cols, show="headings", height=10)
        for c in cols:
            tv.heading(c, text=c)
            tv.column(c, width=170 if c != "password" else 220)
        tv.grid(row=0, column=0, columnspan=3, padx=6, pady=6, sticky="nsew")

        vs = ttk.Scrollbar(inner, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=vs.set)
        vs.grid(row=0, column=3, sticky="ns")

        db = list_users()
        for uid, data in db.items():
            tv.insert("", "end", values=(uid, data.get("tipo",""), data.get("nombre",""),
                                         data.get("id",""), data.get("terapeuta",""),
                                         data.get("password","")))

        key = load_or_create_key().decode("utf-8")
        tk.Label(inner, text="Clave de cifrado (guardar con cuidado):", fg="red", bg="#ffffff").grid(row=1, column=0, sticky="w", padx=6, pady=(10,4))
        e = ttk.Entry(inner, width=64)
        e.grid(row=1, column=1, padx=6, pady=(10,4), sticky="w")
        e.insert(0, key)

        grey_button(inner, "Cerrar sesión", self._back_to_login).grid(row=2, column=0, padx=6, pady=10, sticky="w")


    # ==================== Panel del terapeuta ====================

    def _screen_therapist(self):
        self._clear()
        set_background(self.root, "imagenes/Costa_Rica.jpg")
        card, inner = make_card(self.root, "Panel del terapeuta")

        top = tk.Frame(inner, bg="#ffffff")
        top.grid(row=0, column=0, sticky="ew", padx=4, pady=(0, 8))

        tk.Label(top, text="Paciente:", bg="#ffffff").pack(side="left", padx=(0,6))

        self.cb_pacientes = ttk.Combobox(top, state="readonly", width=28)
        all_users = list_users()
        pacientes_ids = sorted([uid for uid, d in all_users.items() if d.get("tipo") == "paciente"])
        self.cb_pacientes["values"] = pacientes_ids
        self.cb_pacientes.pack(side="left", padx=(0,8))
        self.cb_pacientes.bind("<<ComboboxSelected>>", self._on_patient_selected)  # carga planes al seleccionar

        upload_button(top, "Subir a Adafruit IO", self._ther_push_user).pack(side="right", padx=(8,0))
        grey_button(top, "Ver historial", self._ther_history_screen).pack(side="right", padx=(8,0))
        grey_button(top, "Cerrar sesión", self._back_to_login).pack(side="right")

        # ---- Formulario de plan
        form = tk.LabelFrame(inner, text="Nuevo plan", bg="#ffffff", fg="#2e7d32")
        form.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)

        tk.Label(form, text="Modo:", bg="#ffffff").grid(row=0, column=0, sticky="e", padx=6, pady=6)
        self.f_modo = ttk.Combobox(form, values=["Activo","Pasivo"], state="readonly", width=18)
        self.f_modo.grid(row=0, column=1, padx=6, pady=6)

        tk.Label(form, text="Pierna:", bg="#ffffff").grid(row=1, column=0, sticky="e", padx=6, pady=6)
        self.f_pierna = ttk.Combobox(form, values=["Derecha","Izquierda"], state="readonly", width=18)
        self.f_pierna.grid(row=1, column=1, padx=6, pady=6)

        tk.Label(form, text="Tipo:", bg="#ffffff").grid(row=2, column=0, sticky="e", padx=6, pady=6)
        self.f_tipo = ttk.Combobox(form, values=["Flexión","Extensión"], state="readonly", width=18)
        self.f_tipo.grid(row=2, column=1, padx=6, pady=6)

        tk.Label(form, text="Resorte:", bg="#ffffff").grid(row=3, column=0, sticky="e", padx=6, pady=6)
        self.f_resorte = ttk.Combobox(form, values=["1","2","3"], state="readonly", width=18)
        self.f_resorte.grid(row=3, column=1, padx=6, pady=6)

        tk.Label(form, text="Ángulo mín.:", bg="#ffffff").grid(row=4, column=0, sticky="e", padx=6, pady=6)
        self.f_angmin = ttk.Entry(form, width=20)
        self.f_angmin.grid(row=4, column=1, padx=6, pady=6)

        tk.Label(form, text="Ángulo máx.:", bg="#ffffff").grid(row=5, column=0, sticky="e", padx=6, pady=6)
        self.f_angmax = ttk.Entry(form, width=20)
        self.f_angmax.grid(row=5, column=1, padx=6, pady=6)

        tk.Label(form, text="Repeticiones:", bg="#ffffff").grid(row=6, column=0, sticky="e", padx=6, pady=6)
        self.f_reps = ttk.Entry(form, width=20)
        self.f_reps.grid(row=6, column=1, padx=6, pady=6)

        tk.Label(form, text="ID del plan:", bg="#ffffff").grid(row=7, column=0, sticky="e", padx=6, pady=6)
        self.f_id = ttk.Entry(form, width=20)
        self.f_id.grid(row=7, column=1, padx=6, pady=6)

        green_button(form, "Guardar plan", self._ther_add_plan).grid(row=8, column=0, columnspan=2, pady=(8,4))

        # ---- Tabla de planes del paciente
        table_frame = tk.LabelFrame(inner, text="Planes del paciente", bg="#ffffff", fg="#2e7d32")
        table_frame.grid(row=2, column=0, sticky="nsew", padx=4, pady=4)

        cols = ("ID","Modo","Pierna","Tipo","Resorte","Ang_min","Ang_max","Reps")
        self.tv_planes = ttk.Treeview(table_frame, columns=cols, show="headings", height=8)
        for c in cols:
            self.tv_planes.heading(c, text=c)
            self.tv_planes.column(c, width=120)
        self.tv_planes.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)

        vs = ttk.Scrollbar(table_frame, orient="vertical", command=self.tv_planes.yview)
        self.tv_planes.configure(yscrollcommand=vs.set)
        vs.grid(row=0, column=1, sticky="ns")

        inner.grid_columnconfigure(0, weight=1)
        inner.grid_rowconfigure(2, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)
        table_frame.grid_rowconfigure(0, weight=1)

    def _on_patient_selected(self, event=None):
        uid = self.cb_pacientes.get().strip()
        if not uid:
            return

        # --- Cargar planes actuales del paciente
        self._reload_patient_plans_table(uid)

        # --- Obtener lista de planes
        u = get_user(uid)
        planes = u.get("planes", [])

        # --- Calcular siguiente ID disponible
        if planes:
            max_id = max((p.get("id", 0) for p in planes), default=0)
            next_id = max_id + 1
        else:
            next_id = 1

        # --- Mostrar ID en el campo (solo lectura)
        self.f_id.config(state="normal")
        self.f_id.delete(0, tk.END)
        self.f_id.insert(0, str(next_id))
        self.f_id.config(state="readonly")

    def _reload_patient_plans_table(self, uid):
        """Rellena la tabla de planes existentes del paciente seleccionado."""
        for i in self.tv_planes.get_children():
            self.tv_planes.delete(i)

        u = get_user(uid)
        if not u:
            return

        for p in u.get("planes", []):
            self.tv_planes.insert("", "end", values=(
                p.get("id"),
                p.get("modo"),
                p.get("pierna"),
                p.get("tipo"),
                p.get("resorte"),
                p.get("angulo_min"),
                p.get("angulo_max"),
                p.get("repeticiones")
            ))

    def _ther_add_plan(self):
        uid = self.cb_pacientes.get().strip()
        if not uid:
            messagebox.showwarning("Atención", "Seleccione un paciente.")
            return

        modo = self.f_modo.get().strip()
        pierna = self.f_pierna.get().strip()
        tipo = self.f_tipo.get().strip()
        resorte = self.f_resorte.get().strip()
        angmin = self.f_angmin.get().strip()
        angmax = self.f_angmax.get().strip()
        reps = self.f_reps.get().strip()

        # Validar campos requeridos
        if not (modo and pierna and tipo and resorte and angmin and angmax and reps):
            messagebox.showwarning("Atención", "Complete todos los campos del plan.")
            return

        # Obtener usuario y lista actual de planes
        u = get_user(uid)
        if not u:
            messagebox.showerror("Error", "Usuario no encontrado.")
            return

        planes = u.get("planes", [])

        # ==============================
        #   ASIGNACIÓN AUTOMÁTICA DE ID
        # ==============================
        if planes:
            max_id = max((p.get("id", 0) for p in planes), default=0)
            nuevo_id = max_id + 1
        else:
            nuevo_id = 1

        try:
            plan = {
                "modo": modo,
                "pierna": pierna,
                "tipo": tipo,
                "resorte": resorte,
                "angulo_min": float(angmin),
                "angulo_max": float(angmax),
                "repeticiones": int(reps),
                "id": nuevo_id
            }
        except Exception:
            messagebox.showerror("Error", "Revise los valores numéricos (ángulos, repeticiones).")
            return

        planes.append(plan)
        ok, msg = upsert_planes(uid, planes)

        if ok:
            self._reload_patient_plans_table(uid)
            messagebox.showinfo("Plan", f"Plan guardado correctamente (ID: {nuevo_id}).")
        else:
            messagebox.showerror("Error", msg)

    def _ther_history_screen(self):
        """Pantalla de historial (más reciente primero) con columna Estado."""
        uid = self.cb_pacientes.get().strip()
        if not uid:
            messagebox.showwarning("Historial", "Seleccione un paciente primero.")
            return

        self._clear()
        set_background(self.root, "imagenes/Costa_Rica.jpg")
        card, inner = make_card(self.root, f"Historial de {uid}")

        cols = ("Fecha","Plan","Duración","Repeticiones","Correctas","Parciales","Incorrectas","Estado")
        tv = ttk.Treeview(inner, columns=cols, show="headings", height=12)
        for c in cols:
            tv.heading(c, text=c)
            tv.column(c, width=130 if c!="repeticiones" else 120)
        tv.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)

        vs = ttk.Scrollbar(inner, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=vs.set)
        vs.grid(row=0, column=1, sticky="ns")

        data = list_session_summaries(uid)
        for s in data:
            mm, ss = divmod(int(s.get("duracion_s",0)), 60)
            tv.insert("", "end", values=(
                s.get("fecha",""),
                s.get("plan_usado",""),
                f"{mm:02d}:{ss:02d}",
                s.get("repeticiones",""),
                s.get("correctas",0),
                s.get("parciales",0),
                s.get("incorrectas",0),
                s.get("estado","-")
            ))

        btns = tk.Frame(inner, bg="#ffffff")
        btns.grid(row=1, column=0, sticky="w", padx=6, pady=8)
        grey_button(btns, "Volver", self._screen_therapist).pack(side="left", padx=6)

        inner.grid_columnconfigure(0, weight=1)
        inner.grid_rowconfigure(0, weight=1)

    def _ther_push_user(self):
        """
        Envía los datos del paciente (nombre, ID, terapeuta, planes)
        al feed <uid>-info en Adafruit IO, usando requests.post() directo.
        """

        uid = self.cb_pacientes.get().strip()
        if not uid:
            messagebox.showwarning("Atención", "Seleccione un paciente.")
            return

        u = get_user(uid)
        if not u:
            messagebox.showerror("Error", "Usuario no encontrado.")
            return

        # Solo pacientes crean/usan feeds
        if u.get("tipo") != "paciente":
            messagebox.showinfo("Info", "Solo los usuarios tipo 'Paciente' poseen feeds en Adafruit IO.")
            return

        # Payload con info de usuario y planes
        payload = {
            "nombre": u.get("nombre", ""),
            "id_app": uid,
            "id": u.get("id", ""),
            "fecha_registro": u.get("fecha_registro", ""),
            "terapeuta": u.get("terapeuta", ""),
            "planes": u.get("planes", [])
        }

        # Feed clave correcta (en minúscula, como en tu cuenta)
        feed_key = f"{uid.lower()}-info"

        try:
            ok = send_data_http(feed_key, json.dumps(payload, ensure_ascii=False))
            if ok:
                messagebox.showinfo("Subida", f"Datos de usuario/planes enviados a Adafruit IO ({feed_key}).")
            else:
                messagebox.showwarning("Subida", f"No se pudo enviar datos al feed {feed_key}.")
        except Exception as e:
            messagebox.showwarning("Subida", f"Error al subir a Adafruit IO:\n{e}")

    # ==================== Panel del paciente ====================

    def _screen_patient(self):
        self._clear()
        set_background(self.root, "imagenes/Costa_Rica.jpg")
        card, inner = make_card(self.root, f"Paciente: {self.id_app}")

        u = get_user(self.id_app)
        planes = u.get("planes", [])
        activos = planes[-4:] if len(planes) >= 4 else planes[:]

        cols = ("ID", "Modo", "Pierna", "Tipo", "Resorte", "Ang_min", "Ang_max", "Reps")
        tv = ttk.Treeview(inner, columns=cols, show="headings", height=6)
        for c in cols:
            tv.heading(c, text=c)
            tv.column(c, width=130)
        tv.grid(row=0, column=0, columnspan=3, sticky="ew", padx=6, pady=6)

        for p in activos:
            tv.insert("", "end", values=(
                p.get("id"),
                p.get("modo"),
                p.get("pierna"),
                p.get("tipo"),
                p.get("resorte"),
                p.get("angulo_min"),
                p.get("angulo_max"),
                p.get("repeticiones")
            ))

        tk.Label(inner, text="ID del plan a ejecutar:", bg="#ffffff").grid(row=1, column=0, sticky="e", padx=6, pady=6)
        self.e_plan_id = ttk.Entry(inner, width=10)
        self.e_plan_id.grid(row=1, column=1, padx=6, pady=6)

        btns = tk.Frame(inner, bg="#ffffff")
        btns.grid(row=2, column=0, columnspan=2, pady=8, sticky="w")
        green_button(btns, "Iniciar", self._patient_start).pack(side="left", padx=6)
        grey_button(btns, "Ver historial", self._patient_history_screen).pack(side="left", padx=6)
        grey_button(btns, "Cerrar sesión", self._back_to_login).pack(side="left", padx=6)

    def _patient_start(self):
        pid = self.e_plan_id.get().strip()
        if not pid:
            messagebox.showwarning("Atención", "Indique el ID de plan a ejecutar.")
            return

        try:
            pid = int(pid)
        except Exception:
            messagebox.showerror("Error", "ID de plan inválido.")
            return

        u = get_user(self.id_app)
        if not u:
            messagebox.showerror("Error", "Usuario no encontrado.")
            return

        plan = None
        for p in u.get("planes", []):
            if p.get("id") == pid:
                plan = p
                break

        if not plan:
            messagebox.showerror("Error", "Ese plan no existe para este usuario.")
            return

        def _finish(_resumen):
            # Al volver del juego, recargamos la pantalla del paciente
            self._screen_patient()

        threading.Thread(
            target=lambda: KneeRehabilitationGame(self.root, plan, self.id_app, _finish),
            daemon=True
        ).start()

    # ==================== Historial ====================

    def _patient_history_screen(self):
        """Historial del propio paciente con columna Estado (más reciente primero)."""
        self._clear()
        set_background(self.root, "imagenes/Costa_Rica.jpg")
        card, inner = make_card(self.root, f"Mi historial ({self.id_app})")

        cols = ("Fecha", "Plan", "Duración", "Repeticiones", "Correctas", "Parciales", "Incorrectas", "Estado")
        tv = ttk.Treeview(inner, columns=cols, show="headings", height=12)
        for c in cols:
            tv.heading(c, text=c)
            tv.column(c, width=130 if c != "repeticiones" else 120)
        tv.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)

        vs = ttk.Scrollbar(inner, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=vs.set)
        vs.grid(row=0, column=1, sticky="ns")

        data = list_session_summaries(self.id_app)
        for s in data:
            mm, ss = divmod(int(s.get("duracion_s", 0)), 60)
            tv.insert("", "end", values=(
                s.get("fecha", ""),
                s.get("plan_usado", ""),
                f"{mm:02d}:{ss:02d}",
                s.get("repeticiones", ""),
                s.get("correctas", 0),
                s.get("parciales", 0),
                s.get("incorrectas", 0),
                s.get("estado", "-")
            ))

        btns = tk.Frame(inner, bg="#ffffff")
        btns.grid(row=1, column=0, sticky="w", padx=6, pady=8)
        grey_button(btns, "Volver", self._screen_patient).pack(side="left", padx=6)

        inner.grid_columnconfigure(0, weight=1)
        inner.grid_rowconfigure(0, weight=1)


# ==========================================================
# Ejecución principal
# ==========================================================

if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)

    # Iniciar sincronización de usuarios automáticamente al abrir la aplicación
    threading.Thread(target=sync_users_with_cloud, daemon=True).start()

    root.mainloop()
