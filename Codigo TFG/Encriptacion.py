import os
from cryptography.fernet import Fernet

# ======================= Directorios =======================

def ensure_dirs():
    """Crea estructura 'Datos locales' y 'pendientes' si no existe."""
    base = os.path.join(os.getcwd(), "Datos locales")
    os.makedirs(base, exist_ok=True)
    os.makedirs(os.path.join(base, "pendientes"), exist_ok=True)
    return base

# ======================= Clave de cifrado =======================

def key_path():
    """Ruta al archivo de clave."""
    return os.path.join(ensure_dirs(), "clave.key")

def load_or_create_key():
    """Carga o crea clave Fernet."""
    path = key_path()
    if not os.path.exists(path):
        key = Fernet.generate_key()
        with open(path, "wb") as f:
            f.write(key)
    else:
        with open(path, "rb") as f:
            key = f.read()
    return key

# Inicializa el cifrador global
_F = Fernet(load_or_create_key())

# ======================= Lectura y escritura cifrada =======================

def write_encrypted(path: str, raw_bytes: bytes):
    """Escribe datos cifrados."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(_F.encrypt(raw_bytes))

def read_encrypted(path: str) -> bytes:
    """Lee y descifra un archivo."""
    with open(path, "rb") as f:
        return _F.decrypt(f.read())
