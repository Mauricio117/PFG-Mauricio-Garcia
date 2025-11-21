import os
import json
import requests
import uuid
import threading
import time
from datetime import datetime
from Adafruit_IO import Client, Feed, RequestError
from Encriptacion import ensure_dirs, read_encrypted
from Usuarios import list_users, _save_users




AIO_USER = "Mau117"
AIO_KEY = "aio_Sgnw12Lfpr2kgN3Qgj1bdzmD1QVV"

# Variables globales que debes definir al inicio del archivo:
ADAFRUIT_IO_USERNAME = "Mau117"
ADAFRUIT_IO_KEY = "aio_Sgnw12Lfpr2kgN3Qgj1bdzmD1QVV"

# ==================== CLIENTE ====================

def get_aio_client():
    """Devuelve un cliente de Adafruit IO si la conexión es válida."""
    try:
        aio = Client(AIO_USER, AIO_KEY)
        # Prueba mínima de conexión
        aio.receive("test") if "test" in [f.name for f in aio.feeds()] else None
        #print("[AdafruitIO] Cliente inicializado correctamente.")
        return aio
    except Exception as e:
        #print(f"[AdafruitIO] Error al conectar: {e}")
        return None


# ==================== FEEDS ====================

def ensure_feed(aio, feed_key):
    """Verifica o crea el feed en minúsculas dentro de la raíz principal."""
    feed_key = feed_key.lower().strip()
    try:
        feeds = aio.feeds()
        if any(f.key == feed_key for f in feeds):
            #print(f"[AdafruitIO] Feed existente detectado, reutilizando {feed_key}")
            return
        #print(f"[AdafruitIO] Creando feed: {feed_key}")
        feed = Feed(name=feed_key, key=feed_key)
        aio.create_feed(feed)
    except Exception as e:
        print(f"[AdafruitIO] ⚠️ Error creando feed {feed_key}: {e}")


# ==================== SINCRONIZACIÓN ====================

def try_sync_pending(aio, usuario):
    base_dir = os.path.join(ensure_dirs(), "pendientes", usuario)
    if not os.path.exists(base_dir):
        #print(f"[AdafruitIO] No se encontró carpeta de pendientes para {usuario}.")
        return False

    any_uploaded = False
    feed_key = f"{usuario}-sesion"

    ensure_feed(aio, feed_key)

    for file in os.listdir(base_dir):
        if not file.endswith(".csv.enc"):
            continue
        path = os.path.join(base_dir, file)
        try:
            content = read_encrypted(path).decode("utf-8").strip().splitlines()

            #print(f"[AdafruitIO] Subiendo {len(content)-1} líneas desde {file}...")
            headers = content[0].split(",")
            for line in content[1:]:
                parts = line.split(",")
                if len(parts) != len(headers):
                    continue
                payload = dict(zip(headers, parts))
                aio.send_data(feed_key, json.dumps(payload, ensure_ascii=False))

            os.remove(path)
            #print(f"[AdafruitIO] Sincronizado y eliminado: {file}")
            any_uploaded = True

        except Exception as e:
            print(f"[AdafruitIO] Error al subir {file}: {e}")

    return any_uploaded


def _merge_user_data(local_data: dict, cloud_data: dict):
    """Fusiona usuarios locales con los de la nube."""
    merged = dict(local_data)
    for uid, cloud_u in cloud_data.items():
        if uid not in merged:
            merged[uid] = cloud_u
        else:
            # Unir planes sin duplicar IDs
            local_planes = {p["id"]: p for p in merged[uid].get("planes", [])}
            for p in cloud_u.get("planes", []):
                if p["id"] not in local_planes:
                    merged[uid].setdefault("planes", []).append(p)
    return merged


def download_large_json(feed_key="usuarios"):
    """
    Descarga y reconstruye un JSON grande enviado por partes desde Adafruit IO.
    Cada fragmento debe tener formato {"part": n, "total": N, "data": "..."}.
    """
    try:
        aio = get_aio_client()
        data_points = aio.data(feed_key, max_results=50)

        # Filtrar fragmentos válidos
        parts = []
        for d in data_points:
            try:
                val = json.loads(d.value)
                if isinstance(val, dict) and "part" in val and "data" in val:
                    parts.append((val["part"], val["total"], val["data"]))
            except Exception:
                continue

        if not parts:
            #print("[SYNC] ⚠️ No se detectaron fragmentos válidos en el feed.")
            return {}

        # Ordenar por número de parte
        parts.sort(key=lambda x: x[0])
        total = parts[0][1]
        if len(parts) < total:
            #print(f"[SYNC] ⚠️ Faltan fragmentos ({len(parts)}/{total}). No se reconstruirá.")
            return {}

        # Unir fragmentos
        combined = "".join(p[2] for p in parts)
        #print(f"[SYNC] 🔧 JSON reconstruido de {len(parts)} fragmentos ({len(combined)} bytes)")
        data = json.loads(combined)
        if not isinstance(data, dict):
            #print("[SYNC] ⚠️ JSON reconstruido no es un diccionario válido.")
            return {}
        return data

    except Exception as e:
        #print(f"[SYNC] ❌ Error al reconstruir JSON: {e}")
        return {}


def _download_cloud_users(aio):
    """
    Descarga el feed 'usuarios' desde Adafruit IO, detectando si está fragmentado.
    """
    try:
        data = aio.receive("usuarios").value
        try:
            result = json.loads(data)
            if isinstance(result, dict) and "part" not in result:
                return result
        except Exception:
            pass
        #print("[SYNC] 🧩 Detectado feed fragmentado. Reconstruyendo...")
        return download_large_json("usuarios")
    except Exception as e:
        #print(f"[SYNC] ⚠️ No se pudo descargar feed 'usuarios': {e}")
        return {}


def sync_users_with_cloud():
    """
    Sincroniza usuarios.json local con el feed 'usuarios' en Adafruit IO.
    Si el JSON es mayor a 1KB, se divide automáticamente en fragmentos válidos.
    """
    aio = get_aio_client()
    if not aio:
        #print("[SYNC] ❌ No se pudo conectar con Adafruit IO.")
        return False

    cloud_users = _download_cloud_users(aio)
    local_users = list_users()
    #print(f"[SYNC] Usuarios locales: {len(local_users)}, en la nube: {len(cloud_users)}")

    merged = dict(local_users)
    cambios_local = False
    cambios_cloud = False

    for uid, cloud_u in cloud_users.items():
        if uid not in merged:
            merged[uid] = cloud_u
            cambios_local = True
        else:
            try:
                fecha_cloud = cloud_u.get("fecha_registro", "")
                fecha_local = merged[uid].get("fecha_registro", "")
                if fecha_cloud > fecha_local:
                    merged[uid] = cloud_u
                    cambios_local = True
                elif fecha_local > fecha_cloud:
                    cambios_cloud = True
            except Exception as e:
                print(f"[SYNC] Error comparando fechas de {uid}: {e}")

    for uid in local_users.keys():
        if uid not in cloud_users:
            cambios_cloud = True

    if cambios_local:
        #print("[SYNC] 💾 Actualizando archivo local...")
        _save_users(merged)

    if cambios_cloud:
        try:
            payload = json.dumps(merged, ensure_ascii=False)
            size_bytes = len(payload.encode("utf-8"))
            #print(f"[SYNC] ☁️ JSON total = {size_bytes} bytes")

            # Asegurar existencia del feed con historial
            feeds = aio.feeds()
            if not any(f.key == "usuarios" for f in feeds):
                feed = Feed(name="usuarios", key="usuarios", history=True)
                aio.create_feed(feed)
                #print("[SYNC] 🧩 Feed 'usuarios' creado con historial activado.")

            # 🔧 Fragmentación dinámica antes de subir
            if size_bytes > 1024:
                #print("[SYNC] 🧩 JSON > 1KB → fragmentando dinámicamente...")
                base_chunk_size = 800
                chunks = []
                i = 0
                while i < len(payload):
                    sub = payload[i:i + base_chunk_size]
                    test_json = json.dumps(
                        {"part": 0, "total": 0, "data": sub},
                        ensure_ascii=False
                    )
                    # Reducir tamaño si el JSON completo pasa de 1024 B
                    while len(test_json.encode("utf-8")) > 1024 and base_chunk_size > 100:
                        base_chunk_size -= 50
                        sub = payload[i:i + base_chunk_size]
                        test_json = json.dumps(
                            {"part": 0, "total": 0, "data": sub},
                            ensure_ascii=False
                        )
                    chunks.append(sub)
                    i += base_chunk_size

                total = len(chunks)
                #print(f"[SYNC] 📦 Enviando {total} fragmentos (~{base_chunk_size} B c/u)...")
                for idx, chunk in enumerate(chunks, start=1):
                    part_json = json.dumps({
                        "part": idx,
                        "total": total,
                        "data": chunk
                    }, ensure_ascii=False)
                    size_final = len(part_json.encode("utf-8"))
                    safe_send(aio, "usuarios", part_json)
                    #print(f"[SYNC] 🧩 Fragmento {idx}/{total} ({size_final} B) enviado.")
                    time.sleep(1.2)
                #print(f"[SYNC] ✅ Subida fragmentada completada ({total} partes).")

            else:
                safe_send(aio, "usuarios", payload)
                #print("[SYNC] ✅ Subida directa completada (<1KB).")

        except Exception as e:
            print(f"[SYNC] ❌ Error subiendo a Adafruit IO: {e}")

    #print("[SYNC] 🔁 Sincronización completada.")
    return True




def safe_send(aio, feed_key, value):
    """
    Envía datos a Adafruit IO asegurando que el feed exista.
    - Convierte la clave a minúsculas.
    - Crea el feed automáticamente si no existe.
    - Soporta feeds con historial activado (history=True).
    - Evita duplicar errores 404 o 422.
    """
    feed_key = feed_key.lower().strip()
    try:
        # Verificar si el feed ya existe
        try:
            all_feeds = aio.feeds()
            match = next((f for f in all_feeds if f.key == feed_key), None)
        except Exception as e:
            #print(f"[SYNC] ⚠️ No se pudo listar feeds: {e}")
            match = None

        if not match:
            #print(f"[SYNC] 🧩 Feed '{feed_key}' no encontrado. Creando...")
            try:
                # Crear con historial activado para permitir fragmentación
                feed = Feed(name=feed_key, key=feed_key, history=True)
                aio.create_feed(feed)
                #print(f"[SYNC] ✅ Feed '{feed_key}' creado exitosamente.")
            except RequestError as re:
                #print(f"[SYNC] ❌ Error creando feed '{feed_key}': {re}")
                return
            except Exception as ce:
                #print(f"[SYNC] ❌ No se pudo crear feed '{feed_key}': {ce}")
                return

        # Intentar enviar el valor
        try:
            aio.send_data(feed_key, value)
            #print(f"[SYNC] ✅ Enviado correctamente a {feed_key}")
            time.sleep(0.25)
        except RequestError as re:
            # Si da error 404 o 422, intentar una vez más creando el feed
            if "404" in str(re) or "not found" in str(re).lower():
                #print(f"[SYNC] ⚠️ Feed '{feed_key}' desapareció, recreando...")
                feed = Feed(name=feed_key, key=feed_key, history=True)
                aio.create_feed(feed)
                aio.send_data(feed_key, value)
                #print(f"[SYNC] ✅ Valor reenviado tras recrear feed '{feed_key}'")
            elif "422" in str(re) or "unprocessable" in str(re).lower():
                print(f"[SYNC] ⚠️ Valor muy grande para {feed_key} (>1KB). Omitido.")
            else:
                print(f"[SYNC] ❌ Error al enviar a {feed_key}: {re}")
        except Exception as e2:
            print(f"[SYNC] ❌ Error general al enviar a {feed_key}: {e2}")

    except Exception as e:
        print(f"[SYNC] ❌ Error inesperado en safe_send({feed_key}): {e}")

def threaded_upload_user(uid):
    """
    Sube archivos de sesión (JSON cifrados) del usuario a Adafruit IO.
    Si los feeds no existen, los crea automáticamente.
    """
    def worker():
        try:
            aio = get_aio_client()
            if not aio:
                #print(f"[UPLOAD] ❌ No se pudo inicializar cliente Adafruit IO.")
                return

            base_dir = ensure_dirs()
            user_dir = os.path.join(base_dir, uid)
            if not os.path.exists(user_dir):
                #print(f"[UPLOAD] No hay datos locales para {uid}")
                return

            # Verificar/crear feeds principales del usuario
            feeds = [f"{uid.lower()}-angulo", f"{uid.lower()}-fuerza", f"{uid.lower()}-info"]
            all_feeds = {f.key for f in aio.feeds()}
            for fk in feeds:
                if fk not in all_feeds:
                    try:
                        feed = Feed(name=fk, key=fk, history=True)
                        aio.create_feed(feed)
                        #print(f"[SYNC] 🧩 Feed '{fk}' creado automáticamente.")
                    except Exception as e:
                        print(f"[SYNC] ⚠️ No se pudo crear feed '{fk}': {e}")

            for fname in os.listdir(user_dir):
                if not fname.endswith(".json.enc"):
                    continue

                path = os.path.join(user_dir, fname)
                try:
                    data = json.loads(read_encrypted(path).decode("utf-8"))
                except Exception as e:
                    #print(f"[UPLOAD] ⚠️ No se pudo leer {fname}: {e}")
                    continue

                session_id = data.get("session_id") or uuid.uuid4().hex[:8].upper()
                fecha_sesion = data.get("fecha", "?")
                plan_id = data.get("plan_usado", "?")
                mediciones = data.get("mediciones", [])

                feed_ang = f"{uid.lower()}-angulo"
                feed_fza = f"{uid.lower()}-fuerza"

                # Enviar marcador de inicio usando safe_send()
                marker = f"Inicio de subida — ID: {session_id} | usuario: {uid} | plan: {plan_id} | fecha: {fecha_sesion}"
                safe_send(aio, feed_ang, marker)
                safe_send(aio, feed_fza, marker)
                #print(f"[UPLOAD] Marcador enviado para {uid}: {marker}")
                time.sleep(2)

                # Enviar datos numéricos
                for row in mediciones:
                    try:
                        _, ang, fuerza = row
                        safe_send(aio, feed_ang, str(round(float(ang), 3)))
                        safe_send(aio, feed_fza, str(round(float(fuerza), 3)))
                        time.sleep(2)
                    except Exception as e:
                        #print(f"[UPLOAD] ⚠️ Error en fila de medición: {e}")
                        continue

                #print(f"[UPLOAD] ✅ Sesión subida correctamente ({session_id})")

                # 🔹 Eliminar tras éxito
                os.remove(path)
                #print(f"[UPLOAD] Archivo eliminado: {fname}")

        except Exception as e:
            print(f"[UPLOAD_THREAD] Error general en subida de {uid}: {e}")

    threading.Thread(target=worker, daemon=True).start()



# ============================================
# Manejo HTTP hacia Adafruit IO con control de tasa
# ============================================

def send_data_http(feed_key, value):
    url = f"https://io.adafruit.com/api/v2/{ADAFRUIT_IO_USERNAME}/feeds/{feed_key}/data"
    headers = {"X-AIO-Key": ADAFRUIT_IO_KEY, "Content-Type": "application/json"}

    try:
        r = requests.post(url, json={"value": value}, headers=headers)
        if r.status_code == 429:
            # Esperar automáticamente si se alcanzó el límite
            #print(f"[SYNC] ⚠️ Límite de tasa alcanzado. Esperando 2 segundos...")
            time.sleep(2)
            return False
        elif r.status_code >= 400:
            #print(f"[SYNC] ❌ Error {r.status_code} al enviar a {feed_key}: {r.text}")
            return False
        else:
            #print(f"[SYNC] ✅ Enviado a {feed_key}")
            # Pausa entre envíos para no exceder 30 por minuto
            time.sleep(0.8)
            return True
    except Exception as e:
        #print(f"[SYNC] Error al enviar {feed_key}: {e}")
        return False




def test_connection():
    aio = get_aio_client()
    #print(f"Usuario autenticado: {aio.username}")
    feeds = aio.feeds()
    #print("Feeds visibles para este usuario:")
    for f in feeds:
        print("-", f.key)