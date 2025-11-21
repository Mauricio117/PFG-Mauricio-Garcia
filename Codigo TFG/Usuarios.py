import os
import json
import glob
from datetime import datetime

from Encriptacion import ensure_dirs, write_encrypted, read_encrypted


# ======================= Constantes =======================

USERS_FILE = os.path.join(ensure_dirs(), "usuarios.json")


# ======================= Manejo de base de usuarios =======================

def _load_users():
    """Carga la base de datos de usuarios cifrada."""
    if not os.path.exists(USERS_FILE):
        return {}
    try:
        raw = read_encrypted(USERS_FILE)
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return {}

def _save_users(db: dict):
    """Guarda la base de datos de usuarios encriptada."""
    data = json.dumps(db, indent=2, ensure_ascii=False).encode("utf-8")
    write_encrypted(USERS_FILE, data)


# ======================= Creación de usuarios =======================

def add_user(data: dict):
    """
    Registra un nuevo usuario con validaciones de unicidad y tipo.
    data = {
        "id_app": str,
        "password": str,
        "tipo": "administrador" | "terapeuta" | "paciente",
        "nombre": str,
        "id": str,              # cédula
        "terapeuta": str        # opcional (solo paciente)
    }
    """
    db = _load_users()

    if data["tipo"] == "administrador":
        for u in db.values():
            if u.get("tipo") == "administrador":
                return False, "Ya existe un administrador. No se puede crear otro."

    if data["id_app"] in db:
        return False, "El ID de aplicación ya existe."

    db[data["id_app"]] = {
        "password": data["password"],
        "tipo": data["tipo"],
        "nombre": data["nombre"],
        "id": data["id"],
        "fecha_registro": datetime.now().strftime("%Y-%m-%d"),
        "terapeuta": data.get("terapeuta", ""),
        "planes": []
    }
    _save_users(db)
    return True, "Usuario creado correctamente."


def verify_login(id_app: str, password: str):
    """Verifica credenciales. Devuelve (bool, datos|mensaje)."""
    db = _load_users()
    u = db.get(id_app)
    if not u:
        return False, "Usuario no encontrado."
    if u.get("password") != password:
        return False, "Contraseña incorrecta."
    return True, u


def get_user(id_app: str):
    """Obtiene los datos de un usuario específico."""
    return _load_users().get(id_app)


def list_users():
    """Devuelve todos los usuarios (dict) y filtra valores no válidos."""
    data = _load_users()

    # Validar que el contenido sea un diccionario
    if not isinstance(data, dict):
        print("[USUARIOS] ⚠️ Base de usuarios corrupta o inválida, reiniciando.")
        return {}

    clean = {}
    for uid, u in data.items():
        # Solo aceptar entradas que sean dict válidos
        if isinstance(u, dict):
            clean[uid] = u
        else:
            print(f"[USUARIOS] ⚠️ Entrada inválida ignorada: {uid} = {type(u).__name__}")
    return clean



# ======================= Manejo de planes =======================

def upsert_planes(id_app: str, planes_list: list):
    """Actualiza o reemplaza los planes de un usuario."""
    db = _load_users()
    if id_app not in db:
        return False, "Usuario no existe."
    db[id_app]["planes"] = planes_list[:]
    _save_users(db)
    return True, "Planes actualizados."


# ======================= Historial de sesiones =======================

def list_session_summaries(uid: str):
    """
    Lee todos los archivos de sesión cifrados (.json.enc) del usuario y devuelve
    una lista de resúmenes simplificados para mostrar en el historial.
    """
    user_dir = os.path.join(ensure_dirs(), uid)
    print(f"[DEBUG] Buscando sesiones en: {user_dir}")
    print("Archivos encontrados:", os.listdir(user_dir) if os.path.exists(user_dir) else "No existe carpeta")

    if not os.path.exists(user_dir):
        return []

    sesiones = []
    for fname in os.listdir(user_dir):
        if fname.endswith(".json.enc") and "_sesion_" in fname:
            try:
                raw = read_encrypted(os.path.join(user_dir, fname))
                data = json.loads(raw.decode("utf-8"))

                # Estructura del nuevo formato
                resumen = {
                    "usuario": data.get("usuario", uid),
                    "fecha": data.get("fecha", "-"),
                    "plan_usado": data.get("plan_usado", "-"),
                    "duracion_s": data.get("duracion_s", 0),
                    "repeticiones": data.get("repeticiones", "0/0"),
                    "correctas": data.get("correctas", 0),
                    "parciales": data.get("parciales", 0),
                    "incorrectas": data.get("incorrectas", 0),
                    "estado": data.get("estado", "-"),
                    "session_id": data.get("session_id", ""),
                }
                sesiones.append(resumen)
            except Exception as e:
                print(f"[Historial] Error leyendo {fname}: {e}")

    # Ordenar del más reciente al más antiguo
    sesiones.sort(key=lambda x: x.get("fecha", ""), reverse=True)
    return sesiones



# ======================= Utilidades adicionales =======================

def list_therapists():
    """Devuelve lista de IDs de usuarios con tipo 'terapeuta'."""
    db = _load_users()
    return [uid for uid, u in db.items() if u.get("tipo") == "terapeuta"]

def list_patients():
    """Devuelve lista de IDs de usuarios con tipo 'paciente'."""
    db = _load_users()
    return [uid for uid, u in db.items() if u.get("tipo") == "paciente"]
