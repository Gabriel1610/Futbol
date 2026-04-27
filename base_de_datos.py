import mysql.connector
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv
import sys
import os # IMPORTANTE: Para encontrar el certificado
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from datetime import datetime, timedelta, timezone

PUNTOS = 3
MÁXIMA_CANTIDAD_DE_PUNTOS = 9
LIMITE_MAYORES_ERRORES = 10
MAYOR_ENTERO = 999999999

# Configuración del Logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BaseDeDatos:
    def __init__(self):
        self.ph = PasswordHasher()

        # --- SOLUCIÓN DEL ERROR EN EL EXE ---
        # Detectamos si estamos corriendo en el ejecutable (frozen) o en el script normal
        if getattr(sys, 'frozen', False):
            # Si es EXE, PyInstaller guarda los archivos en sys._MEIPASS
            carpeta_actual = sys._MEIPASS
        else:
            # Si es script .py, usamos la ruta normal
            carpeta_actual = os.path.dirname(os.path.abspath(__file__))
            
        # 1. Cargamos el certificado de seguridad
        ruta_certificado = os.path.join(carpeta_actual, "isrgrootx1.pem")
        
        if not os.path.exists(ruta_certificado):
            logger.error(f"NO SE ENCUENTRA EL CERTIFICADO EN: {ruta_certificado}")

        # 2. Cargamos las variables de entorno desde el archivo .env oculto (si existe)
        ruta_env = os.path.join(carpeta_actual, ".env")
        if os.path.exists(ruta_env):
            load_dotenv(override=True)

        # 3. Leemos las variables (ahora buscará primero en el .env, y si no, en el sistema)
        db_user = os.getenv("DB_USER")
        db_password = os.getenv("DB_PASSWORD")
        db_host = os.getenv("DB_HOST", "gateway01.us-east-1.prod.aws.tidbcloud.com") 
        db_name = os.getenv("DB_NAME", "independiente") 
        
        self.config = {
            'user': db_user,       
            'password': db_password, 
            'host': db_host, 
            'port': 4000,                                         
            'database': db_name,          
            'raise_on_warnings': True,
            'ssl_ca': ruta_certificado,           
            'ssl_verify_cert': True,
            'use_pure': True
        }
        
    def obtener_hora_argentina(self):
        """Retorna la hora exacta de Argentina (UTC-3) sin importar dónde esté el servidor."""
        # Tomamos la hora UTC real, le restamos 3 horas, y le quitamos la 'etiqueta' de zona horaria 
        # para que TiDB lo guarde como un DATETIME normal sin quejarse.
        return (datetime.now(timezone.utc) - timedelta(hours=3)).replace(tzinfo=None)

    def abrir(self):
        """Abre la conexión a la base de datos de forma segura."""
        try:
            conexion = mysql.connector.connect(**self.config)
            return conexion
        except mysql.connector.Error as err:
            # --- MODIFICACIÓN: Mostrar el error técnico completo en el EXE ---
            msg = str(err)
            if "SSL" in msg:
                # Intenta mostrar dónde está buscando el certificado para depurar
                raise Exception(f"Error SSL: {msg}\nRuta buscada: {self.config.get('ssl_ca')}")
            else:
                raise Exception(f"Error de Conexión: {msg}")

    def obtener_rivales_completo(self):
        """Obtiene ID y Nombre de todos los rivales (Sin 'otro_nombre')."""
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()
            sql = "SELECT id, nombre FROM rivales ORDER BY nombre ASC"
            cursor.execute(sql)
            return cursor.fetchall()
        except Exception as e:
            return []
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def buscar_usuario_para_asociar(self, identificador):
        """Busca un usuario por username o email y retorna sus datos."""
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            # dictionary=True nos permite acceder a los datos por el nombre de la columna
            cursor = conexion.cursor(dictionary=True)
            sql = "SELECT id, username, email FROM usuarios WHERE username = %s OR email = %s"
            cursor.execute(sql, (identificador, identificador))
            return cursor.fetchone()
        except Exception as e:
            logger.error(f"Error buscando usuario para asociar: {e}")
            return None
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()
    
    def obtener_usuario_por_telegram(self, id_telegram):
        """Busca el username de un usuario usando su ID de Telegram."""
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            # Usamos dictionary=True para que devuelva los nombres de columnas
            cursor = conexion.cursor(dictionary=True)
            sql = "SELECT username FROM usuarios WHERE id_telegram = %s"
            cursor.execute(sql, (id_telegram,))
            res = cursor.fetchone()
            
            if res:
                return res['username']
            return None
        except Exception as e:
            logger.error(f"Error buscando por Telegram ID: {e}")
            return None
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def actualizar_id_telegram(self, username, id_telegram):
        """Vincula el ID de Telegram a la cuenta del usuario en TiDB."""
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()
            
            # 1. Por extrema seguridad, si este ID de Telegram estaba vinculado a otra cuenta, lo limpiamos
            sql_clean = "UPDATE usuarios SET id_telegram = NULL WHERE id_telegram = %s"
            cursor.execute(sql_clean, (id_telegram,))
            
            # 2. Asociamos el ID al usuario correcto
            sql_update = "UPDATE usuarios SET id_telegram = %s WHERE username = %s"
            cursor.execute(sql_update, (id_telegram, username))
            
            conexion.commit()
            return True
        except Exception as e:
            logger.error(f"Error actualizando ID de Telegram: {e}")
            raise e
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()
    
    def obtener_id_telegram_por_username(self, username):
        """Busca el ID de Telegram asociado a un nombre de usuario específico."""
        conexion = None
        cursor = None
        try:
            # Usamos el método abrir() ya definido en tu clase
            conexion = self.abrir()
            cursor = conexion.cursor()
            
            # Consultamos la columna id_telegram filtrando por username
            sql = "SELECT id_telegram FROM usuarios WHERE username = %s"
            cursor.execute(sql, (username,))
            resultado = cursor.fetchone()
            
            # Si se encuentra el usuario, retornamos el ID (índice 0), sino None
            return resultado[0] if resultado else None
            
        except Exception as e:
            logger.error(f"Error al obtener ID de Telegram para {username}: {e}")
            return None
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()
            
    def actualizar_rival(self, id_rival, nuevo_nombre):
        """Actualiza el nombre de un rival usando su ID."""
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()
            
            sql = "UPDATE rivales SET nombre = %s WHERE id = %s"
            cursor.execute(sql, (nuevo_nombre, id_rival))
            conexion.commit()
            return True
            
        except mysql.connector.Error as e:
            if e.errno == 1062:
                raise Exception("Ya existe un equipo con ese nombre en la base de datos.")
            elif e.errno == 3819:
                if 'chk_rival_nombre_no_vacio' in str(e).lower():
                    raise Exception("El nombre principal del equipo no puede estar compuesto solo por espacios en blanco.")
            raise e
        except Exception as e:
            raise e
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def insertar_usuario(self, username, password, email):
        """Inserta un nuevo usuario capturando múltiples restricciones CHECK."""
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()

            password_hash = self.ph.hash(password)
            fecha_actual = self.obtener_hora_argentina()

            # Insertamos. El 'tipo' se completa solo por defecto a 'comun' en TiDB.
            sql = "INSERT INTO usuarios (username, password, email, fecha_registro) VALUES (%s, %s, %s, %s)"
            valores = (username, password_hash, email, fecha_actual)

            cursor.execute(sql, valores)
            conexion.commit()
            
            logger.info(f"Usuario '{username}' registrado exitosamente.")
            return True

        except mysql.connector.Error as e:
            if e.errno == 1062: 
                raise Exception("El nombre de usuario o el correo ya están registrados.")
            elif e.errno == 3819:
                msg = str(e).lower()
                if 'chk_username_no_vacio' in msg:
                    raise Exception("El nombre de usuario no puede estar vacío.")
                elif 'chk_email_formato' in msg:
                    raise Exception("El formato del correo electrónico es inválido.")
                elif 'chk_tipo_usuario' in msg:
                    raise Exception("Intento de asignar un rol no permitido por el sistema.")
                else:
                    raise Exception("Los datos no cumplen con las reglas de seguridad.")
            raise e
        except Exception as e:
            raise e
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    # --- AGREGAR ESTAS FUNCIONES NUEVAS AL FINAL DE LA CLASE ---

    def verificar_disponibilidad(self, username, email):
        """Verifica si el usuario o el email ya existen antes de enviar el código."""
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()
            
            sql = "SELECT username, email FROM usuarios WHERE username = %s OR email = %s"
            cursor.execute(sql, (username, email))
            resultado = cursor.fetchone()
            
            if resultado:
                # Si encontró algo, devolvemos qué fue lo que encontró para dar un error preciso
                encontrado_user = resultado[0]
                encontrado_email = resultado[1]
                if encontrado_user == username:
                    raise Exception("El nombre de usuario ya está en uso.")
                if encontrado_email == email:
                    raise Exception("El correo electrónico ya está registrado.")
            return True # Está disponible
            
        except Exception as e:
            raise e
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def obtener_email_usuario(self, username):
        """Obtiene el email de un usuario para la recuperación."""
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()
            sql = "SELECT email FROM usuarios WHERE username = %s"
            cursor.execute(sql, (username,))
            res = cursor.fetchone()
            if res:
                return res[0]
            return None
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def guardar_token_recuperacion(self, username, token):
        """Guarda el código de recuperación en la BD con 15 min de validez."""
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()
            
            # Calculamos expiración (Ahora + 15 minutos)
            expiracion = self.obtener_hora_argentina() + timedelta(minutes=15)
            
            sql = "UPDATE usuarios SET token_recuperacion = %s, token_expiracion = %s WHERE username = %s"
            cursor.execute(sql, (token, expiracion, username))
            conexion.commit()
            return True
        except Exception as e:
            logger.error(f"Error guardando token: {e}")
            return False
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def validar_token_recuperacion(self, username, token):
        """Verifica si el token coincide y no ha expirado."""
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()
            
            sql = "SELECT token_expiracion FROM usuarios WHERE username = %s AND token_recuperacion = %s"
            cursor.execute(sql, (username, token))
            res = cursor.fetchone()
            
            if res:
                expiracion = res[0]
                if expiracion and expiracion > self.obtener_hora_argentina():
                    return True # Válido
                else:
                    raise Exception("El código ha expirado.")
            else:
                raise Exception("Código incorrecto.")
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def cambiar_contrasena(self, username, nueva_password):
        """Actualiza la contraseña y limpia el token."""
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()
            
            password_hash = self.ph.hash(nueva_password)
            
            # Actualizamos pass y borramos el token usado
            sql = "UPDATE usuarios SET password = %s, token_recuperacion = NULL, token_expiracion = NULL WHERE username = %s"
            cursor.execute(sql, (password_hash, username))
            conexion.commit()
            return True
        except Exception as e:
            raise e
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def obtener_rivales(self):
        """
        Obtiene la lista de todos los rivales (ID, Nombre) ordenados alfabéticamente.
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()
            
            sql = "SELECT id, nombre FROM rivales ORDER BY nombre ASC"
            cursor.execute(sql)
            return cursor.fetchall()
        except Exception as e:
            logger.error(f"Error obteniendo rivales: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def insertar_pronostico(self, usuario, id_partido, goles_cai, goles_rival, fecha_hora):
        # CAMBIAR ESTA LÍNEA:
        conexion = self.abrir()
        cursor = conexion.cursor()
        
        try:
            consulta = """
                INSERT INTO pronosticos (usuario_id, partido_id, pred_goles_independiente, pred_goles_rival, fecha_prediccion)
                VALUES (
                    (SELECT id FROM usuarios WHERE username = %s), 
                    %s, %s, %s, %s
                )
            """
            
            cursor.execute(consulta, (usuario, id_partido, goles_cai, goles_rival, fecha_hora))
            conexion.commit()
            
        except Exception as e:
            print(f"Error al insertar pronóstico: {e}")
            raise e
        finally:
            cursor.close()
            conexion.close()

    def actualizar_resultados_pendientes(self, lista_jugados):
        """Actualiza resultados usando directamente el ID de FotMob. Adiós a las búsquedas complejas."""
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()
            count = 0

            for datos in lista_jugados:
                if datos['goles_cai'] is not None:
                    try:
                        sql = """
                            UPDATE partidos 
                            SET goles_independiente = %s, goles_rival = %s, fecha_hora = %s, condicion = %s
                            WHERE id = %s AND goles_independiente IS NULL
                        """
                        cursor.execute(sql, (
                            datos['goles_cai'], 
                            datos['goles_rival'], 
                            datos['fecha'],
                            datos['condicion'],
                            datos['fotmob_id']
                        ))
                        
                        if cursor.rowcount > 0:
                            count += 1
                            
                    except mysql.connector.Error as err:
                        if err.errno == 3819:
                            logger.warning(f"⚠️ ALERTA API: FotMob envió goles negativos para el partido vs {datos['rival']}.")

            conexion.commit()
            return count > 0

        except Exception as e:
            return False
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def obtener_campeonatos_completo(self):
        """Obtiene ID y Nombre de todos los campeonatos."""
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()
            sql = "SELECT id, nombre FROM campeonatos ORDER BY nombre ASC"
            cursor.execute(sql)
            return cursor.fetchall()
        except Exception as e:
            return []
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def actualizar_campeonato(self, id_camp, nuevo_nombre):
        """Actualiza el nombre de un campeonato usando su ID."""
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()
            sql = "UPDATE campeonatos SET nombre = %s WHERE id = %s"
            cursor.execute(sql, (nuevo_nombre, id_camp))
            conexion.commit()
            return True
        except mysql.connector.Error as e:
            if e.errno == 1062:
                raise Exception("Ya existe un torneo con ese nombre en la base de datos.")
            raise e
        except Exception as e:
            raise e
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def obtener_partidos(self, usuario, filtro_tiempo='futuros', edicion_id=None, rival_id=None, solo_sin_pronosticar=False):
        """
        Obtiene la lista de partidos aplicando filtros acumulativos.
        - filtro_tiempo: 'todos', 'futuros', 'jugados'
        - edicion_id: ID del torneo (opcional)
        - rival_id: ID del equipo (opcional)
        - solo_sin_pronosticar: Booleano
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()

            # Parametros base para las subconsultas de usuario
            params = [usuario, usuario]
            
            # Lista de condiciones WHERE. Arrancamos con 1=1 para concatenar con AND
            condiciones = ["1=1"]

            # 1. Filtro de Tiempo (Excluyente entre sí)
            if filtro_tiempo == 'futuros':
                condiciones.append("p.fecha_hora > DATE_SUB(NOW(), INTERVAL 3 HOUR)")
                orden_sql = "ASC"
            elif filtro_tiempo == 'jugados':
                condiciones.append("p.fecha_hora <= DATE_SUB(NOW(), INTERVAL 3 HOUR)")
                orden_sql = "DESC"
            else: # 'todos'
                orden_sql = "ASC" if filtro_tiempo == 'futuros' else "DESC"

            # 2. Filtro Torneo (Acumulativo)
            if edicion_id is not None:
                condiciones.append("p.edicion_id = %s")
                params.append(edicion_id)

            # 3. Filtro Equipo (Acumulativo)
            if rival_id is not None:
                condiciones.append("p.rival_id = %s")
                params.append(rival_id)

            # 4. Filtro Sin Pronosticar (Acumulativo)
            if solo_sin_pronosticar:
                condiciones.append("p.fecha_hora > DATE_SUB(NOW(), INTERVAL 3 HOUR)") # Redundancia de seguridad
                condiciones.append("pr.pred_goles_independiente IS NULL")

            # Unir condiciones
            where_clause = " WHERE " + " AND ".join(condiciones)

            sql = f"""
            SELECT 
                p.id,
                r.nombre,
                p.fecha_hora,
                CONCAT(c.nombre, ' ', a.numero) as torneo_completo,
                p.goles_independiente,
                p.goles_rival,
                p.edicion_id,
                CASE 
                    WHEN TIME(p.fecha_hora) = '00:00:00' THEN DATE_FORMAT(p.fecha_hora, '%d/%m/%Y s. h.')
                    ELSE DATE_FORMAT(p.fecha_hora, '%d/%m/%Y %H:%i')
                END as fecha_display,
                pr.pred_goles_independiente, 
                pr.pred_goles_rival,
                -- PUNTOS
                CASE 
                    WHEN p.goles_independiente IS NULL THEN NULL 
                    WHEN pr.pred_goles_independiente IS NULL THEN 0 
                    ELSE
                        (CASE WHEN p.goles_independiente = pr.pred_goles_independiente THEN {PUNTOS} ELSE 0 END) +
                        (CASE WHEN p.goles_rival = pr.pred_goles_rival THEN {PUNTOS} ELSE 0 END) +
                        (CASE WHEN SIGN(p.goles_independiente - p.goles_rival) = SIGN(pr.pred_goles_independiente - pr.pred_goles_rival) THEN {PUNTOS} ELSE 0 END)
                END as tus_puntos,
                
                -- ERROR ABSOLUTO
                CASE 
                    WHEN p.goles_independiente IS NULL OR pr.pred_goles_independiente IS NULL THEN NULL
                    ELSE
                        ABS(CAST(p.goles_independiente AS SIGNED) - CAST(pr.pred_goles_independiente AS SIGNED)) + 
                        ABS(CAST(p.goles_rival AS SIGNED) - CAST(pr.pred_goles_rival AS SIGNED))
                END as error_absoluto,
                
                -- CONDICIÓN (Índice 12)
                p.condicion

            FROM partidos p
            JOIN rivales r ON p.rival_id = r.id
            JOIN ediciones e ON p.edicion_id = e.id
            JOIN campeonatos c ON e.campeonato_id = c.id
            JOIN anios a ON e.anio_id = a.id
            
            LEFT JOIN (
                SELECT 
                    p1.partido_id, 
                    p1.pred_goles_independiente, 
                    p1.pred_goles_rival
                FROM pronosticos p1
                INNER JOIN (
                    SELECT partido_id, MAX(fecha_prediccion) as max_fecha
                    FROM pronosticos
                    WHERE usuario_id = (SELECT id FROM usuarios WHERE username = %s)
                    GROUP BY partido_id
                ) p2 ON p1.partido_id = p2.partido_id AND p1.fecha_prediccion = p2.max_fecha
                WHERE p1.usuario_id = (SELECT id FROM usuarios WHERE username = %s)
            ) pr ON p.id = pr.partido_id
            
            {where_clause}
            ORDER BY p.fecha_hora {orden_sql}
            """
            
            cursor.execute(sql, tuple(params))
            resultados = cursor.fetchall()
            return resultados

        except Exception as e:
            logger.error(f"Error obteniendo partidos: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close() 

    def obtener_datos_evolucion_puestos(self, edicion_id, usuarios_seleccionados):
        """
        Calcula la evolución del ranking aplicando los NUEVOS CRITERIOS.
        Corrección: Se elimina el filtro defectuoso de NOW().
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()

            # 1. Contar total de usuarios
            cursor.execute("SELECT COUNT(*) FROM usuarios")
            total_usuarios = cursor.fetchone()[0]

            # 2. Obtener partidos TERMINADOS ordenados por fecha
            # FILTRO CORREGIDO: Eliminamos "AND fecha_hora < NOW()"
            sql_partidos = """
                SELECT id 
                FROM partidos 
                WHERE edicion_id = %s 
                  AND goles_independiente IS NOT NULL 
                  AND goles_rival IS NOT NULL
                ORDER BY fecha_hora ASC
            """
            cursor.execute(sql_partidos, (edicion_id,))
            partidos = [row[0] for row in cursor.fetchall()]

            if not partidos:
                return 0, total_usuarios, {}

            # 3. Obtener usuarios
            cursor.execute("SELECT id, username FROM usuarios")
            usuarios_bd = cursor.fetchall()
            
            ids_usuarios = [u[0] for u in usuarios_bd]
            mapa_nombres = {u[0]: u[1] for u in usuarios_bd}
            
            # Acumuladores
            puntos_acumulados = {uid: 0 for uid in ids_usuarios} 
            cant_partidos_jugados = {uid: 0 for uid in ids_usuarios} 
            suma_error_absoluto = {uid: 0.0 for uid in ids_usuarios} 
            suma_anticipacion = {uid: 0.0 for uid in ids_usuarios}   
            
            historial_grafico = {user: [] for user in usuarios_seleccionados}

            # 4. Iterar partido a partido
            for partido_id in partidos:
                sql_datos_partido = f"""
                    SELECT 
                        pr.usuario_id,
                        -- Puntos
                        (
                            (CASE WHEN SIGN(CAST(p.goles_independiente AS SIGNED) - CAST(p.goles_rival AS SIGNED)) = 
                                       SIGN(CAST(pr.pred_goles_independiente AS SIGNED) - CAST(pr.pred_goles_rival AS SIGNED)) 
                                  THEN {PUNTOS} ELSE 0 END) +
                            (CASE WHEN p.goles_independiente = pr.pred_goles_independiente THEN {PUNTOS} ELSE 0 END) +
                            (CASE WHEN p.goles_rival = pr.pred_goles_rival THEN {PUNTOS} ELSE 0 END)
                        ) as puntos,
                        -- Error Absoluto del partido
                        (ABS(p.goles_independiente - pr.pred_goles_independiente) + 
                         ABS(p.goles_rival - pr.pred_goles_rival)) as error_match,
                        -- Anticipación (Segundos)
                        TIMESTAMPDIFF(SECOND, pr.fecha_prediccion, p.fecha_hora) as segundos_anticipacion
                    
                    FROM pronosticos pr
                    JOIN (
                        SELECT usuario_id, MAX(id) as max_id
                        FROM pronosticos
                        WHERE partido_id = %s
                        GROUP BY usuario_id
                    ) last_pred ON pr.id = last_pred.max_id
                    JOIN partidos p ON pr.partido_id = p.id
                    WHERE p.id = %s
                """
                cursor.execute(sql_datos_partido, (partido_id, partido_id))
                resultados = cursor.fetchall()

                # Actualizar acumulados
                for uid, pts, err, segs in resultados:
                    if uid in puntos_acumulados:
                        puntos_acumulados[uid] += pts
                        cant_partidos_jugados[uid] += 1
                        
                        val_error = float(err) if err is not None else 0.0
                        suma_error_absoluto[uid] += val_error
                        
                        val_sec = float(segs) if segs is not None else 0.0
                        suma_anticipacion[uid] += val_sec

                # --- CÁLCULO DE RANKING DEL MOMENTO ---
                def get_sort_key(uid):
                    pts = puntos_acumulados[uid]
                    partidos_jug = cant_partidos_jugados[uid]
                    
                    if partidos_jug > 0:
                        avg_error = suma_error_absoluto[uid] / partidos_jug
                        avg_ant = suma_anticipacion[uid] / partidos_jug
                    else:
                        avg_error = 999.0 # Castigo por no jugar
                        avg_ant = 0.0

                    return (-pts, -partidos_jug, avg_error, -avg_ant)

                # Ordenar
                ranking_ordenado = sorted(ids_usuarios, key=get_sort_key)
                
                # Asignar puestos
                mapa_puestos = {}
                prev_key = None
                puesto_actual = 0
                
                for i, uid in enumerate(ranking_ordenado):
                    current_key = get_sort_key(uid)
                    if current_key != prev_key:
                        puesto_actual = i + 1
                        prev_key = current_key
                    mapa_puestos[uid] = puesto_actual

                # Guardar historial
                for usuario_target in usuarios_seleccionados:
                    target_id = next((k for k, v in mapa_nombres.items() if v == usuario_target), None)
                    if target_id:
                        puesto = mapa_puestos.get(target_id, total_usuarios)
                        historial_grafico[usuario_target].append(puesto)

            return len(partidos), total_usuarios, historial_grafico

        except Exception as e:
            print(f"Error evolución: {e}")
            return 0, 0, {}
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def obtener_datos_evolucion_puntos(self, edicion_id, usuarios_seleccionados):
        """
        Obtiene el historial de puntos acumulados partido a partido para graficar.
        Corrección: Se elimina el filtro defectuoso de NOW() para mostrar todos los partidos finalizados.
        """
        if not usuarios_seleccionados:
            return 0, 0, {}
            
        conexion = self.abrir()
        if not conexion:
            return 0, 0, {}
            
        cursor = conexion.cursor()
        
        try:
            # 1. Obtener la lista de partidos finalizados de esta edición
            # FILTRO CORREGIDO: Eliminamos "AND fecha_hora < NOW()"
            sql_partidos = """
                SELECT id FROM partidos 
                WHERE goles_independiente IS NOT NULL 
                  AND goles_rival IS NOT NULL 
                  AND edicion_id = %s
                ORDER BY fecha_hora ASC
            """
            cursor.execute(sql_partidos, (edicion_id,))
            lista_partidos = [row[0] for row in cursor.fetchall()]
            
            if not lista_partidos:
                return 0, len(usuarios_seleccionados), {u: [] for u in usuarios_seleccionados}
                
            # Diccionario base para los puntos de cada partido (Esto ya asegura los 0 puntos a los que faltan)
            historial_por_partido = {p_id: {u: 0 for u in usuarios_seleccionados} for p_id in lista_partidos}
            
            # 2. Consultar los puntos calculados de cada usuario
            placeholders = ', '.join(['%s'] * len(usuarios_seleccionados))
            params_puntos = [edicion_id] + usuarios_seleccionados
            
            # FILTRO CORREGIDO: Eliminamos "AND p.fecha_hora < NOW()"
            sql_puntos = f"""
                SELECT 
                    pr.partido_id,
                    u.username,
                    (CASE WHEN SIGN(CAST(p.goles_independiente AS SIGNED) - CAST(p.goles_rival AS SIGNED)) = 
                               SIGN(CAST(pr.pred_goles_independiente AS SIGNED) - CAST(pr.pred_goles_rival AS SIGNED)) 
                          THEN {PUNTOS} ELSE 0 END) +
                    (CASE WHEN p.goles_independiente = pr.pred_goles_independiente THEN {PUNTOS} ELSE 0 END) +
                    (CASE WHEN p.goles_rival = pr.pred_goles_rival THEN {PUNTOS} ELSE 0 END) as puntos_partido
                FROM pronosticos pr
                
                INNER JOIN (
                    SELECT MAX(id) as max_id
                    FROM pronosticos
                    GROUP BY usuario_id, partido_id
                ) ultimos ON pr.id = ultimos.max_id
                
                JOIN partidos p ON pr.partido_id = p.id
                JOIN usuarios u ON pr.usuario_id = u.id
                
                WHERE p.goles_independiente IS NOT NULL 
                  AND p.goles_rival IS NOT NULL 
                  AND p.edicion_id = %s
                  AND u.username IN ({placeholders})
            """
            cursor.execute(sql_puntos, tuple(params_puntos))
            
            for row in cursor.fetchall():
                p_id = row[0]
                usr = row[1]
                pts = row[2]
                if p_id in historial_por_partido and usr in usuarios_seleccionados:
                    # Guardamos el puntaje (si el usuario no pronosticó, queda en 0 por defecto)
                    historial_por_partido[p_id][usr] = pts
                    
            # 3. Acumular los puntos cronológicamente
            historial_final = {u: [] for u in usuarios_seleccionados}
            acumulados = {u: 0 for u in usuarios_seleccionados}
            
            for p_id in lista_partidos:
                for u in usuarios_seleccionados:
                    acumulados[u] += historial_por_partido[p_id][u]
                    historial_final[u].append(acumulados[u])
                    
            return len(lista_partidos), len(usuarios_seleccionados), historial_final
            
        except Exception as e:
            print(f"Error en datos de evolución de puntos: {e}")
            return 0, 0, {}
            
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def obtener_historial_puntos_usuario(self, edicion_id, usuario):
        """
        Obtiene una lista ordenada de puntos obtenidos por un usuario.
        Filtra solo el ÚLTIMO pronóstico realizado por partido para evitar duplicados en el gráfico.
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()

            sql = f"""
            SELECT 
                CASE 
                    WHEN p.goles_independiente IS NULL THEN 0
                    WHEN pr.pred_goles_independiente IS NULL THEN 0
                    ELSE
                        (CASE WHEN p.goles_independiente = pr.pred_goles_independiente THEN {PUNTOS} ELSE 0 END) +
                        (CASE WHEN p.goles_rival = pr.pred_goles_rival THEN {PUNTOS} ELSE 0 END) +
                        (CASE WHEN SIGN(p.goles_independiente - p.goles_rival) = SIGN(pr.pred_goles_independiente - pr.pred_goles_rival) THEN {PUNTOS} ELSE 0 END)
                END as puntos
            FROM partidos p
            -- Subconsulta para obtener SOLO el último pronóstico del usuario para cada partido
            LEFT JOIN (
                SELECT p1.partido_id, p1.pred_goles_independiente, p1.pred_goles_rival
                FROM pronosticos p1
                INNER JOIN (
                    SELECT partido_id, MAX(fecha_prediccion) as max_fecha
                    FROM pronosticos
                    WHERE usuario_id = (SELECT id FROM usuarios WHERE username = %s)
                    GROUP BY partido_id
                ) p2 ON p1.partido_id = p2.partido_id AND p1.fecha_prediccion = p2.max_fecha
                WHERE p1.usuario_id = (SELECT id FROM usuarios WHERE username = %s)
            ) pr ON p.id = pr.partido_id
            WHERE p.edicion_id = %s 
              AND p.goles_independiente IS NOT NULL
            ORDER BY p.fecha_hora ASC
            """
            
            # Pasamos 'usuario' dos veces (para las subconsultas) y luego 'edicion_id'
            cursor.execute(sql, (usuario, usuario, edicion_id))
            resultados = cursor.fetchall()
            
            return [row[0] for row in resultados]

        except Exception as e:
            logger.error(f"Error obteniendo historial puntos: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()  

    def obtener_torneos_ganados(self, anio=None):
        """
        Calcula cuántos torneos ha ganado cada usuario aplicando los 4 criterios de desempate:
        1. Puntos (Mayor). 
        2. Cantidad Partidos Pronosticados (Mayor). 
        3. Anticipación Promedio (Mayor). 
        4. Eficiencia / Promedio Intentos (Menor).
        
        Solo cuenta torneos finalizados (e.finalizado = TRUE).
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()

            params = []
            filtro_anio = ""
            
            if anio is not None:
                filtro_anio = " AND a.numero = %s "
                params.append(anio)

            sql = f"""
            WITH LatestPredictions AS (
                -- CTE 1: Calcula Puntos, Cantidad de Partidos y Anticipación (usando el ÚLTIMO pronóstico)
                SELECT 
                    pr.usuario_id,
                    p.edicion_id,
                    SUM(
                        (CASE WHEN p.goles_independiente = pr.pred_goles_independiente THEN {PUNTOS} ELSE 0 END) +
                        (CASE WHEN p.goles_rival = pr.pred_goles_rival THEN {PUNTOS} ELSE 0 END) +
                        (CASE WHEN SIGN(p.goles_independiente - p.goles_rival) = SIGN(pr.pred_goles_independiente - pr.pred_goles_rival) THEN {PUNTOS} ELSE 0 END)
                    ) as total_puntos,
                    COUNT(p.id) as cant_partidos,
                    AVG(TIMESTAMPDIFF(SECOND, pr.fecha_prediccion, p.fecha_hora)) as avg_anticipacion
                FROM pronosticos pr
                INNER JOIN (
                    -- Filtro para obtener solo el último pronóstico por partido/usuario
                    SELECT usuario_id, partido_id, MAX(fecha_prediccion) as max_fecha
                    FROM pronosticos
                    GROUP BY usuario_id, partido_id
                ) last_pr ON pr.usuario_id = last_pr.usuario_id 
                         AND pr.partido_id = last_pr.partido_id 
                         AND pr.fecha_prediccion = last_pr.max_fecha
                JOIN partidos p ON pr.partido_id = p.id
                JOIN ediciones e ON p.edicion_id = e.id
                JOIN anios a ON e.anio_id = a.id
                WHERE p.goles_independiente IS NOT NULL 
                  AND e.finalizado = TRUE
                  {filtro_anio}
                GROUP BY pr.usuario_id, p.edicion_id
            ),
            TotalAttempts AS (
                -- CTE 2: Calcula el total de intentos (historial) para el desempate de eficiencia
                SELECT 
                    pr.usuario_id,
                    p.edicion_id,
                    COUNT(*) as total_intentos
                FROM pronosticos pr
                JOIN partidos p ON pr.partido_id = p.id
                JOIN ediciones e ON p.edicion_id = e.id
                JOIN anios a ON e.anio_id = a.id
                WHERE e.finalizado = TRUE
                  {filtro_anio}
                GROUP BY pr.usuario_id, p.edicion_id
            ),
            RankedUsers AS (
                -- CTE 3: Aplica el RANK() con los 4 criterios
                SELECT 
                    lp.usuario_id,
                    lp.edicion_id,
                    RANK() OVER (
                        PARTITION BY lp.edicion_id 
                        ORDER BY 
                            lp.total_puntos DESC,           -- 1. Más Puntos
                            lp.cant_partidos DESC,          -- 2. Más Partidos Jugados
                            lp.avg_anticipacion DESC,       -- 3. Mayor Anticipación
                            (COALESCE(ta.total_intentos, 0) / NULLIF(lp.cant_partidos, 0)) ASC -- 4. Menor Promedio Intentos
                    ) as ranking
                FROM LatestPredictions lp
                JOIN TotalAttempts ta ON lp.usuario_id = ta.usuario_id AND lp.edicion_id = ta.edicion_id
            )
            -- Consulta Final: Cuenta cuántas veces quedó 1º cada usuario
            SELECT 
                u.username,
                COUNT(r.edicion_id) as copas
            FROM usuarios u
            LEFT JOIN RankedUsers r ON u.id = r.usuario_id AND r.ranking = 1
            GROUP BY u.id, u.username
            ORDER BY copas DESC, u.username ASC
            """
            
            # Duplicamos params porque filtro_anio se usa 2 veces (en LatestPredictions y TotalAttempts)
            cursor.execute(sql, tuple(params * 2))
            return cursor.fetchall()
        except Exception as e:
            logger.error(f"Error obteniendo historial de campeones: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()
            
    def obtener_usuarios(self):
        """Obtiene la lista de nombres de usuario registrados."""
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()
            # Ordenamos alfabéticamente
            cursor.execute("SELECT username FROM usuarios ORDER BY username ASC")
            # Retornamos una lista simple de strings
            return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error obteniendo usuarios: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()
    
    def obtener_racha_actual(self, edicion_id=None, anio=None):
        """
        Calcula la racha actual (partidos consecutivos sumando puntos).
        Si el torneo finalizó, calcula la racha con la que el usuario terminó el torneo.
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()

            params = []
            filtro_sql = ""

            if edicion_id is not None:
                filtro_sql = " AND p.edicion_id = %s "
                params.append(edicion_id)
            elif anio is not None:
                filtro_sql = " AND a.numero = %s "
                params.append(anio)

            # Lógica:
            # 1. Obtenemos TODOS los partidos jugados (goles no nulos) del filtro.
            # 2. Cruzamos con Usuarios para evaluar partido a partido.
            # 3. Ordenamos por Fecha DESC (Del último partido jugado hacia atrás).
            sql = f"""
            SELECT 
                u.username,
                p.fecha_hora,
                CASE 
                    WHEN pr.pred_goles_independiente IS NULL THEN 0 -- Si no pronosticó, rompe racha
                    ELSE
                        (CASE WHEN p.goles_independiente = pr.pred_goles_independiente THEN {PUNTOS} ELSE 0 END) +
                        (CASE WHEN p.goles_rival = pr.pred_goles_rival THEN {PUNTOS} ELSE 0 END) +
                        (CASE WHEN SIGN(p.goles_independiente - p.goles_rival) = SIGN(pr.pred_goles_independiente - pr.pred_goles_rival) THEN {PUNTOS} ELSE 0 END)
                END as puntos
            FROM usuarios u
            CROSS JOIN partidos p 
            JOIN ediciones e ON p.edicion_id = e.id
            JOIN anios a ON e.anio_id = a.id
            LEFT JOIN (
                SELECT p1.usuario_id, p1.partido_id, p1.pred_goles_independiente, p1.pred_goles_rival
                FROM pronosticos p1
                INNER JOIN (
                    SELECT usuario_id, partido_id, MAX(fecha_prediccion) as max_fecha
                    FROM pronosticos
                    GROUP BY usuario_id, partido_id
                ) p2 ON p1.usuario_id = p2.usuario_id 
                    AND p1.partido_id = p2.partido_id 
                    AND p1.fecha_prediccion = p2.max_fecha
            ) pr ON u.id = pr.usuario_id AND p.id = pr.partido_id
            WHERE 
                p.goles_independiente IS NOT NULL -- Solo partidos que ya se jugaron
                {filtro_sql}
            ORDER BY u.username ASC, p.fecha_hora DESC
            """
            
            cursor.execute(sql, tuple(params))
            resultados = cursor.fetchall()
            
            # --- Cálculo de Racha ---
            rachas = []
            
            if resultados:
                usuario_actual = None
                racha_actual = 0
                racha_activa = True 
                
                for row in resultados:
                    user = row[0]
                    puntos = row[2]
                    
                    if user != usuario_actual:
                        # Guardar racha del usuario anterior
                        if usuario_actual is not None:
                            rachas.append((usuario_actual, racha_actual))
                        
                        # Iniciar nuevo usuario
                        usuario_actual = user
                        racha_actual = 0
                        racha_activa = True
                        
                        # Evaluamos el partido MÁS RECIENTE del filtro
                        if puntos > 0:
                            racha_actual += 1
                        else:
                            racha_activa = False # Si falló el último, racha actual es 0
                    else:
                        # Partidos anteriores (hacia atrás en el tiempo)
                        if racha_activa:
                            if puntos > 0:
                                racha_actual += 1
                            else:
                                racha_activa = False # Se cortó la racha aquí
                
                # Guardar el último usuario del loop
                if usuario_actual is not None:
                    rachas.append((usuario_actual, racha_actual))

            # Ordenar por quien tiene la racha activa más larga
            return sorted(rachas, key=lambda x: x[1], reverse=True)

        except Exception as e:
            logger.error(f"Error calculando racha actual: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()
    
    def insertar_partido_manual(self, edicion_id, rival_id, condicion, fecha_str, goles_cai, goles_rival):
        """
        Inserta un nuevo partido calculando automáticamente el siguiente ID disponible.
        """
        conexion = self.abrir()
        if not conexion:
            raise Exception("Error de conexión a la base de datos.")
            
        try:
            cursor = conexion.cursor()
            
            # 1. Calculamos el nuevo ID manualmente ya que la tabla no tiene AUTO_INCREMENT
            cursor.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM partidos")
            nuevo_id = cursor.fetchone()[0]
            
            # 2. Insertamos usando los nombres exactos de tus columnas
            query = """
                INSERT INTO partidos (id, edicion_id, rival_id, condicion, fecha_hora, goles_independiente, goles_rival) 
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            valores = (nuevo_id, edicion_id, rival_id, condicion, fecha_str, goles_cai, goles_rival)
            
            cursor.execute(query, valores)
            conexion.commit()
            
        except Exception as e:
            conexion.rollback()
            raise Exception(f"Error insertando partido: {e}")
            
        finally:
            if 'cursor' in locals() and cursor: cursor.close()
            if conexion: conexion.close()

    # ---------------- RIVALES ----------------
    def insertar_rival_manual(self, nombre):
        conexion = self.abrir()
        try:
            cursor = conexion.cursor()
            cursor.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM rivales")
            nuevo_id = cursor.fetchone()[0]
            cursor.execute("INSERT INTO rivales (id, nombre) VALUES (%s, %s)", (nuevo_id, nombre))
            conexion.commit()
        finally:
            if 'cursor' in locals() and cursor: cursor.close()
            if conexion: conexion.close()

    def actualizar_rival_manual(self, rival_id, nombre):
        conexion = self.abrir()
        try:
            cursor = conexion.cursor()
            cursor.execute("UPDATE rivales SET nombre = %s WHERE id = %s", (nombre, rival_id))
            conexion.commit()
        finally:
            if 'cursor' in locals() and cursor: cursor.close()
            if conexion: conexion.close()

    def eliminar_rival_manual(self, rival_id):
        conexion = self.abrir()
        try:
            cursor = conexion.cursor()
            cursor.execute("DELETE FROM rivales WHERE id = %s", (rival_id,))
            conexion.commit()
        finally:
            if 'cursor' in locals() and cursor: cursor.close()
            if conexion: conexion.close()

    # ---------------- TORNEOS (CAMPEONATOS) ----------------
    def insertar_torneo_manual(self, nombre):
        conexion = self.abrir()
        try:
            cursor = conexion.cursor()
            cursor.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM campeonatos")
            nuevo_id = cursor.fetchone()[0]
            cursor.execute("INSERT INTO campeonatos (id, nombre) VALUES (%s, %s)", (nuevo_id, nombre))
            conexion.commit()
        finally:
            if 'cursor' in locals() and cursor: cursor.close()
            if conexion: conexion.close()

    def actualizar_torneo_manual(self, torneo_id, nombre):
        conexion = self.abrir()
        try:
            cursor = conexion.cursor()
            cursor.execute("UPDATE campeonatos SET nombre = %s WHERE id = %s", (nombre, torneo_id))
            conexion.commit()
        finally:
            if 'cursor' in locals() and cursor: cursor.close()
            if conexion: conexion.close()

    def eliminar_torneo_manual(self, torneo_id):
        conexion = self.abrir()
        try:
            cursor = conexion.cursor()
            cursor.execute("DELETE FROM campeonatos WHERE id = %s", (torneo_id,))
            conexion.commit()
        finally:
            if 'cursor' in locals() and cursor: cursor.close()
            if conexion: conexion.close()
            
    def actualizar_partido_manual(self, partido_id, edicion_id, rival_id, condicion, fecha_str, goles_cai, goles_rival):
        """
        Actualiza los datos de un partido usando la estructura de la base de datos 'independiente'.
        """
        conexion = self.abrir()
        if not conexion:
            raise Exception("Error de conexión a la base de datos.")
            
        try:
            cursor = conexion.cursor()
            
            query = """
                UPDATE partidos 
                SET edicion_id = %s, 
                    rival_id = %s, 
                    condicion = %s, 
                    fecha_hora = %s, 
                    goles_independiente = %s, 
                    goles_rival = %s
                WHERE id = %s
            """
            valores = (edicion_id, rival_id, condicion, fecha_str, goles_cai, goles_rival, partido_id)
            
            cursor.execute(query, valores)
            conexion.commit()
            
        except Exception as e:
            conexion.rollback()
            raise Exception(f"Error actualizando partido: {e}")
            
        finally:
            if 'cursor' in locals() and cursor: cursor.close()
            if conexion: conexion.close()

    def eliminar_partido_manual(self, partido_id):
        """
        Elimina un partido. Gracias a ON DELETE CASCADE en la tabla pronosticos, 
        el motor de la base de datos limpiará automáticamente los pronósticos huérfanos.
        """
        conexion = self.abrir()
        if not conexion:
            raise Exception("Error de conexión a la base de datos.")
            
        try:
            cursor = conexion.cursor()
            
            # Solo necesitamos borrar el partido, la base de datos hace el resto
            cursor.execute("DELETE FROM partidos WHERE id = %s", (partido_id,))
            conexion.commit()
            
        except Exception as e:
            conexion.rollback()
            raise Exception(f"Error eliminando partido: {e}")
            
        finally:
            if 'cursor' in locals() and cursor: cursor.close()
            if conexion: conexion.close()
                   
    def obtener_racha_record(self, edicion_id=None, anio=None):
        """
        Calcula la MEJOR racha (récord) de partidos consecutivos sumando puntos en la historia (o filtro).
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()

            params = []
            filtro_sql = ""

            if edicion_id is not None:
                filtro_sql = " AND p.edicion_id = %s "
                params.append(edicion_id)
            elif anio is not None:
                filtro_sql = " AND a.numero = %s "
                params.append(anio)

            # Query: Misma estructura que racha actual, pero ordenado por Fecha ASCENDENTE
            # para poder calcular la continuidad desde el principio.
            sql = f"""
            SELECT 
                u.username,
                p.fecha_hora,
                CASE 
                    WHEN pr.pred_goles_independiente IS NULL THEN 0
                    ELSE
                        (CASE WHEN p.goles_independiente = pr.pred_goles_independiente THEN {PUNTOS} ELSE 0 END) +
                        (CASE WHEN p.goles_rival = pr.pred_goles_rival THEN {PUNTOS} ELSE 0 END) +
                        (CASE WHEN SIGN(p.goles_independiente - p.goles_rival) = SIGN(pr.pred_goles_independiente - pr.pred_goles_rival) THEN {PUNTOS} ELSE 0 END)
                END as puntos
            FROM usuarios u
            CROSS JOIN partidos p 
            JOIN ediciones e ON p.edicion_id = e.id
            JOIN anios a ON e.anio_id = a.id
            LEFT JOIN (
                SELECT p1.usuario_id, p1.partido_id, p1.pred_goles_independiente, p1.pred_goles_rival
                FROM pronosticos p1
                INNER JOIN (
                    SELECT usuario_id, partido_id, MAX(fecha_prediccion) as max_fecha
                    FROM pronosticos
                    GROUP BY usuario_id, partido_id
                ) p2 ON p1.usuario_id = p2.usuario_id 
                    AND p1.partido_id = p2.partido_id 
                    AND p1.fecha_prediccion = p2.max_fecha
            ) pr ON u.id = pr.usuario_id AND p.id = pr.partido_id
            WHERE 
                p.goles_independiente IS NOT NULL
                {filtro_sql}
            ORDER BY u.username ASC, p.fecha_hora ASC
            """
            
            cursor.execute(sql, tuple(params))
            resultados = cursor.fetchall()
            
            # --- Algoritmo para encontrar el MAX streak por usuario ---
            mapa_maximos = {} # {username: max_racha}
            
            if resultados:
                usuario_actual = None
                racha_temporal = 0
                
                for row in resultados:
                    user = row[0]
                    puntos = row[2]
                    
                    if user != usuario_actual:
                        # Cambio de usuario, reseteamos contadores
                        usuario_actual = user
                        racha_temporal = 0
                        if user not in mapa_maximos:
                            mapa_maximos[user] = 0
                    
                    if puntos > 0:
                        racha_temporal += 1
                        # Si la racha actual supera al máximo guardado, actualizamos
                        if racha_temporal > mapa_maximos[user]:
                            mapa_maximos[user] = racha_temporal
                    else:
                        # Cortó racha
                        racha_temporal = 0
            
            # Convertir diccionario a lista de tuplas para ordenar
            lista_final = [(k, v) for k, v in mapa_maximos.items()]
            
            # Ordenar por racha récord descendente
            return sorted(lista_final, key=lambda x: x[1], reverse=True)

        except Exception as e:
            logger.error(f"Error calculando racha récord: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def obtener_todos_pronosticos(self, filtro_tiempo='todos', filtro_torneo=None, filtro_equipo=None, filtro_usuario=None):
        """
        Obtiene el listado de pronósticos.
        Ahora filtra directamente desde la base de datos y ordena ascendentemente si es 'futuros'.
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()

            condiciones = ["1=1"]
            params = []

            # 1. Filtro de tiempo y Ordenamiento
            if filtro_tiempo == 'futuros':
                condiciones.append("p.fecha_hora > DATE_SUB(NOW(), INTERVAL 3 HOUR)")
                orden = "ASC"  # <--- ORDEN ASCENDENTE PARA LOS QUE FALTAN JUGAR
            elif filtro_tiempo == 'jugados':
                condiciones.append("p.fecha_hora <= DATE_SUB(NOW(), INTERVAL 3 HOUR)")
                orden = "DESC" # <--- ORDEN DESCENDENTE PARA EL HISTORIAL
            else:
                orden = "DESC"

            # 2. Filtro de Torneo
            if filtro_torneo:
                condiciones.append("CONCAT(c.nombre, ' ', a.numero) = %s")
                params.append(filtro_torneo)

            # 3. Filtro de Equipo
            if filtro_equipo:
                condiciones.append("r.nombre = %s")
                params.append(filtro_equipo)

            # 4. Filtro de Usuario
            if filtro_usuario:
                condiciones.append("u.username = %s")
                params.append(filtro_usuario)

            where_clause = " AND ".join(condiciones)

            sql = f"""
            SELECT 
                r.nombre,
                p.fecha_hora,
                CONCAT(c.nombre, ' ', a.numero) as torneo,
                p.goles_independiente,
                p.goles_rival,
                u.username,
                pr.pred_goles_independiente,
                pr.pred_goles_rival,
                
                -- CÁLCULO DE PUNTOS
                CASE 
                    WHEN p.goles_independiente IS NULL THEN NULL
                    WHEN pr.fecha_prediccion < latest.max_fecha THEN NULL
                    ELSE
                        (CASE WHEN p.goles_independiente = pr.pred_goles_independiente THEN {PUNTOS} ELSE 0 END) +
                        (CASE WHEN p.goles_rival = pr.pred_goles_rival THEN {PUNTOS} ELSE 0 END) +
                        (CASE WHEN SIGN(p.goles_independiente - p.goles_rival) = SIGN(pr.pred_goles_independiente - pr.pred_goles_rival) THEN {PUNTOS} ELSE 0 END)
                END as puntos,
                
                pr.fecha_prediccion,
                
                -- ERROR ABSOLUTO
                CASE 
                    WHEN p.goles_independiente IS NULL OR pr.pred_goles_independiente IS NULL THEN NULL
                    WHEN pr.fecha_prediccion < latest.max_fecha THEN NULL
                    ELSE
                        ABS(CAST(p.goles_independiente AS SIGNED) - CAST(pr.pred_goles_independiente AS SIGNED)) + 
                        ABS(CAST(p.goles_rival AS SIGNED) - CAST(pr.pred_goles_rival AS SIGNED))
                END as error_absoluto

            FROM pronosticos pr  
            JOIN partidos p ON pr.partido_id = p.id
            JOIN usuarios u ON pr.usuario_id = u.id
            JOIN rivales r ON p.rival_id = r.id
            JOIN ediciones e ON p.edicion_id = e.id
            JOIN campeonatos c ON e.campeonato_id = c.id
            JOIN anios a ON e.anio_id = a.id
            
            INNER JOIN (
                SELECT usuario_id, partido_id, MAX(fecha_prediccion) as max_fecha
                FROM pronosticos
                GROUP BY usuario_id, partido_id
            ) latest ON pr.usuario_id = latest.usuario_id AND pr.partido_id = latest.partido_id
            
            WHERE {where_clause}
            ORDER BY p.fecha_hora {orden}, pr.fecha_prediccion DESC
            """
            
            cursor.execute(sql, tuple(params))
            return cursor.fetchall()
        except Exception as e:
            logger.error(f"Error obteniendo pronósticos: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def obtener_estadisticas_estilo_pronostico(self, usuario, edicion_id=None, anio=None):
        """
        Obtiene estadísticas para el gráfico de torta de 'Estilo de Pronóstico'.
        Considera partidos PASADOS para determinar si hubo pronóstico o no.
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()

            params = [usuario, usuario] # Para las subconsultas de pronósticos
            filtro_sql = ""

            # Filtros dinámicos
            if edicion_id is not None:
                filtro_sql += " AND p.edicion_id = %s "
                params.append(edicion_id)
            elif anio is not None:
                filtro_sql += " AND a.numero = %s "
                params.append(anio)

            sql = f"""
            SELECT 
                -- Total partidos jugados en el periodo
                COUNT(p.id) as total_partidos,
                
                -- Cantidad sin pronóstico (partidos pasados donde no hay predicción)
                SUM(CASE WHEN pr.pred_goles_independiente IS NULL THEN 1 ELSE 0 END) as sin_pronostico,
                
                -- Cantidad Victorias pronosticadas
                SUM(CASE WHEN pr.pred_goles_independiente > pr.pred_goles_rival THEN 1 ELSE 0 END) as pred_victoria,
                
                -- Cantidad Empates pronosticados
                SUM(CASE WHEN pr.pred_goles_independiente = pr.pred_goles_rival THEN 1 ELSE 0 END) as pred_empate,
                
                -- Cantidad Derrotas pronosticadas
                SUM(CASE WHEN pr.pred_goles_independiente < pr.pred_goles_rival THEN 1 ELSE 0 END) as pred_derrota

            FROM partidos p
            JOIN ediciones e ON p.edicion_id = e.id
            JOIN anios a ON e.anio_id = a.id
            
            -- Left Join para ver si el usuario pronosticó (solo el último pronóstico)
            LEFT JOIN (
                SELECT p1.partido_id, p1.pred_goles_independiente, p1.pred_goles_rival
                FROM pronosticos p1
                INNER JOIN (
                    SELECT partido_id, MAX(fecha_prediccion) as max_fecha
                    FROM pronosticos
                    WHERE usuario_id = (SELECT id FROM usuarios WHERE username = %s)
                    GROUP BY partido_id
                ) p2 ON p1.partido_id = p2.partido_id AND p1.fecha_prediccion = p2.max_fecha
                WHERE p1.usuario_id = (SELECT id FROM usuarios WHERE username = %s)
            ) pr ON p.id = pr.partido_id
            
            WHERE 
                p.goles_independiente IS NOT NULL -- Solo partidos que ya se jugaron (historia)
                {filtro_sql}
            """
            
            cursor.execute(sql, tuple(params))
            return cursor.fetchone()

        except Exception as e:
            logger.error(f"Error obteniendo estadísticas estilo pronóstico: {e}")
            return None
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()
    
    def obtener_estadisticas_tendencia_pronostico(self, usuario, edicion_id=None, anio=None):
        """
        Calcula la cantidad de partidos en cada categoría de tendencia (Optimismo/Pesimismo)
        para un usuario, basado en la diferencia de goles pronosticada vs real.
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()

            params = [usuario, usuario]
            filtro_sql = ""

            if edicion_id is not None:
                filtro_sql += " AND p.edicion_id = %s "
                params.append(edicion_id)
            elif anio is not None:
                filtro_sql += " AND a.numero = %s "
                params.append(anio)

            # Fórmula del índice: (Pred_CAI - Pred_Rival) - (Real_CAI - Real_Rival)
            # >= 1.5: Muy Optimista
            # 0.5 a 1.5: Optimista
            # -0.5 a 0.5: Realista
            # -1.5 a -0.5: Pesimista
            # <= -1.5: Muy Pesimista
            
            sql = f"""
            SELECT 
                COUNT(p.id) as total_partidos,
                
                -- 1. Sin Pronóstico
                SUM(CASE WHEN pr.pred_goles_independiente IS NULL THEN 1 ELSE 0 END) as sin_pronostico,
                
                -- 2. Muy Optimista (>= 1.5)
                SUM(CASE 
                    WHEN pr.pred_goles_independiente IS NOT NULL AND 
                         ((CAST(pr.pred_goles_independiente AS SIGNED) - CAST(pr.pred_goles_rival AS SIGNED)) - 
                          (CAST(p.goles_independiente AS SIGNED) - CAST(p.goles_rival AS SIGNED))) >= 1.5 
                    THEN 1 ELSE 0 END) as muy_optimista,
                    
                -- 3. Optimista (0.5 <= x < 1.5)
                SUM(CASE 
                    WHEN pr.pred_goles_independiente IS NOT NULL AND 
                         ((CAST(pr.pred_goles_independiente AS SIGNED) - CAST(pr.pred_goles_rival AS SIGNED)) - 
                          (CAST(p.goles_independiente AS SIGNED) - CAST(p.goles_rival AS SIGNED))) >= 0.5 AND
                         ((CAST(pr.pred_goles_independiente AS SIGNED) - CAST(pr.pred_goles_rival AS SIGNED)) - 
                          (CAST(p.goles_independiente AS SIGNED) - CAST(p.goles_rival AS SIGNED))) < 1.5
                    THEN 1 ELSE 0 END) as optimista,
                    
                -- 4. Realista (-0.5 < x < 0.5)
                SUM(CASE 
                    WHEN pr.pred_goles_independiente IS NOT NULL AND 
                         ((CAST(pr.pred_goles_independiente AS SIGNED) - CAST(pr.pred_goles_rival AS SIGNED)) - 
                          (CAST(p.goles_independiente AS SIGNED) - CAST(p.goles_rival AS SIGNED))) > -0.5 AND
                         ((CAST(pr.pred_goles_independiente AS SIGNED) - CAST(pr.pred_goles_rival AS SIGNED)) - 
                          (CAST(p.goles_independiente AS SIGNED) - CAST(p.goles_rival AS SIGNED))) < 0.5
                    THEN 1 ELSE 0 END) as realista,
                    
                -- 5. Pesimista (-1.5 < x <= -0.5)
                SUM(CASE 
                    WHEN pr.pred_goles_independiente IS NOT NULL AND 
                         ((CAST(pr.pred_goles_independiente AS SIGNED) - CAST(pr.pred_goles_rival AS SIGNED)) - 
                          (CAST(p.goles_independiente AS SIGNED) - CAST(p.goles_rival AS SIGNED))) > -1.5 AND
                         ((CAST(pr.pred_goles_independiente AS SIGNED) - CAST(pr.pred_goles_rival AS SIGNED)) - 
                          (CAST(p.goles_independiente AS SIGNED) - CAST(p.goles_rival AS SIGNED))) <= -0.5
                    THEN 1 ELSE 0 END) as pesimista,

                -- 6. Muy Pesimista (<= -1.5)
                SUM(CASE 
                    WHEN pr.pred_goles_independiente IS NOT NULL AND 
                         ((CAST(pr.pred_goles_independiente AS SIGNED) - CAST(pr.pred_goles_rival AS SIGNED)) - 
                          (CAST(p.goles_independiente AS SIGNED) - CAST(p.goles_rival AS SIGNED))) <= -1.5 
                    THEN 1 ELSE 0 END) as muy_pesimista

            FROM partidos p
            JOIN ediciones e ON p.edicion_id = e.id
            JOIN anios a ON e.anio_id = a.id
            
            LEFT JOIN (
                SELECT p1.partido_id, p1.pred_goles_independiente, p1.pred_goles_rival
                FROM pronosticos p1
                INNER JOIN (
                    SELECT partido_id, MAX(fecha_prediccion) as max_fecha
                    FROM pronosticos
                    WHERE usuario_id = (SELECT id FROM usuarios WHERE username = %s)
                    GROUP BY partido_id
                ) p2 ON p1.partido_id = p2.partido_id AND p1.fecha_prediccion = p2.max_fecha
                WHERE p1.usuario_id = (SELECT id FROM usuarios WHERE username = %s)
            ) pr ON p.id = pr.partido_id
            
            WHERE 
                p.goles_independiente IS NOT NULL
                {filtro_sql}
            """
            
            cursor.execute(sql, tuple(params))
            return cursor.fetchone()

        except Exception as e:
            logger.error(f"Error obteniendo estadísticas tendencia: {e}")
            return None
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()
    
    def obtener_administradores(self):
        """
        Devuelve una lista con los usernames de los usuarios con tipo 'administrador'.
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()
            
            sql = "SELECT username, email FROM usuarios WHERE tipo = 'administrador'"
            cursor.execute(sql)
            
            # fetchall devuelve una lista de tuplas [(user1, email1), (user2, email2), ...]
            # Usamos comprensión de listas para sacar el string limpio
            return [fila[0] for fila in cursor.fetchall()]
            
        except Exception as e:
            logger.error(f"Error obteniendo administradores: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def obtener_ranking_mayores_errores(self, usuario=None, edicion_id=None, anio=None):
        """
        Devuelve el TOP 10 de pronósticos con mayor error absoluto (incluyendo empates).
        Adaptado al esquema: JOIN con rivales, fecha_hora, etc.
        Filtro agregado: Solo el ÚLTIMO pronóstico de cada usuario por partido.
        """
        conexion = self.abrir()
        if not conexion: return []
        cursor = conexion.cursor()

        # Condición para partidos terminados
        filtros = ["p.goles_independiente IS NOT NULL"] 
        params = []

        if edicion_id:
            filtros.append("p.edicion_id = %s")
            params.append(edicion_id)
        if anio:
            filtros.append("YEAR(p.fecha_hora) = %s")
            params.append(anio)
        if usuario:
            filtros.append("u.username = %s")
            params.append(usuario)

        where_clause = " AND ".join(filtros)

        # SQL Modificado usando RANK() para manejar los empates por fila real
        sql = f"""
            WITH ErroresClasificados AS (
                SELECT 
                    u.username, 
                    r.nombre as rival,          
                    p.fecha_hora,               
                    pr.fecha_prediccion,        
                    pr.pred_goles_independiente,
                    pr.pred_goles_rival,        
                    p.goles_independiente,      
                    p.goles_rival,              
                    (ABS(p.goles_independiente - pr.pred_goles_independiente) + ABS(p.goles_rival - pr.pred_goles_rival)) as error_abs,
                    RANK() OVER (
                        ORDER BY (ABS(p.goles_independiente - pr.pred_goles_independiente) + ABS(p.goles_rival - pr.pred_goles_rival)) DESC
                    ) as puesto_ranking
                FROM pronosticos pr
                
                -- FILTRO CLAVE: Solo el último pronóstico de cada usuario para cada partido
                INNER JOIN (
                    SELECT MAX(id) as max_id
                    FROM pronosticos
                    GROUP BY usuario_id, partido_id
                ) ultimos ON pr.id = ultimos.max_id
                
                JOIN partidos p ON pr.partido_id = p.id
                JOIN rivales r ON p.rival_id = r.id  
                JOIN usuarios u ON pr.usuario_id = u.id
                WHERE {where_clause}
            )
            SELECT 
                username, 
                rival, 
                fecha_hora, 
                fecha_prediccion, 
                pred_goles_independiente, 
                pred_goles_rival, 
                goles_independiente, 
                goles_rival, 
                error_abs
            FROM ErroresClasificados
            WHERE puesto_ranking <= {LIMITE_MAYORES_ERRORES}
            ORDER BY error_abs DESC, fecha_hora DESC
        """
        
        cursor.execute(sql, tuple(params))
        datos = cursor.fetchall()
        cursor.close()
        conexion.close()
        return datos
           
    def obtener_estadisticas_firmeza_pronostico(self, usuario, edicion_id=None, anio=None):
        """
        Calcula estadísticas sobre la cantidad de veces que el usuario cambió su pronóstico
        para partidos del PASADO.
        Categorías:
        - 1 intento: Firme
        - 2 intentos: Dudoso
        - 3+ intentos: Cambiante
        - 0 intentos (o NULL): No participativo
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()

            # --- CORRECCIÓN AQUÍ: Solo un usuario en la lista ---
            params = [usuario] 
            filtro_sql = ""

            if edicion_id is not None:
                filtro_sql += " AND p.edicion_id = %s "
                params.append(edicion_id)
            elif anio is not None:
                filtro_sql += " AND a.numero = %s "
                params.append(anio)

            sql = f"""
            SELECT 
                COUNT(p.id) as total_partidos,
                
                -- 0. Sin Pronóstico (No participativo)
                SUM(CASE WHEN stats.cant_intentos IS NULL OR stats.cant_intentos = 0 THEN 1 ELSE 0 END) as sin_pronostico,
                
                -- 1. Firme (Exactamente 1 intento)
                SUM(CASE WHEN stats.cant_intentos = 1 THEN 1 ELSE 0 END) as firme,
                
                -- 2. Dudoso (Exactamente 2 intentos)
                SUM(CASE WHEN stats.cant_intentos = 2 THEN 1 ELSE 0 END) as dudoso,
                
                -- 3. Cambiante (3 o más intentos)
                SUM(CASE WHEN stats.cant_intentos >= 3 THEN 1 ELSE 0 END) as cambiante

            FROM partidos p
            JOIN ediciones e ON p.edicion_id = e.id
            JOIN anios a ON e.anio_id = a.id
            
            -- Subconsulta: Contar cuántos registros tiene el usuario por partido
            LEFT JOIN (
                SELECT partido_id, COUNT(*) as cant_intentos
                FROM pronosticos
                WHERE usuario_id = (SELECT id FROM usuarios WHERE username = %s)
                GROUP BY partido_id
            ) stats ON p.id = stats.partido_id
            
            WHERE 
                p.goles_independiente IS NOT NULL -- Solo partidos jugados (historial)
                {filtro_sql}
            """
            
            cursor.execute(sql, tuple(params))
            return cursor.fetchone()

        except Exception as e:
            logger.error(f"Error obteniendo estadísticas firmeza: {e}")
            return None
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def obtener_ediciones(self, solo_finalizados=False):
        """
        Obtiene las ediciones de torneos (ID, Nombre, Año, Finalizado).
        Si solo_finalizados es True, filtra para mostrar SOLO aquellas que tienen partidos jugados.
        Ordenado por ID descendente para mostrar lo más reciente arriba de todo.
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()
            
            if solo_finalizados:
                sql = """
                SELECT e.id, c.nombre, a.numero, e.finalizado
                FROM ediciones e
                JOIN campeonatos c ON e.campeonato_id = c.id
                JOIN anios a ON e.anio_id = a.id
                WHERE EXISTS (
                    SELECT 1 
                    FROM partidos p 
                    WHERE p.edicion_id = e.id 
                      AND p.goles_independiente IS NOT NULL
                )
                ORDER BY e.id DESC
                """
            else:
                sql = """
                SELECT e.id, c.nombre, a.numero, e.finalizado
                FROM ediciones e
                JOIN campeonatos c ON e.campeonato_id = c.id
                JOIN anios a ON e.anio_id = a.id
                ORDER BY e.id DESC
                """
                
            cursor.execute(sql)
            return cursor.fetchall()
        except Exception as e:
            print(f"Error obteniendo ediciones: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def obtener_anios(self):
        """Obtiene la lista de años disponibles en la base de datos."""
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()
            cursor.execute("SELECT id, numero FROM anios ORDER BY numero DESC")
            return cursor.fetchall()
        except Exception as e:
            logger.error(f"Error obteniendo años: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def marcar_edicion_finalizada(self, nombre_torneo, numero_anio):
        """
        Marca una edición como finalizada (finalizado = TRUE) en la base de datos.
        Se llama cuando la API detecta que ya no hay partidos futuros para este torneo.
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()

            # 1. Buscar ID del Campeonato
            cursor.execute("SELECT id FROM campeonatos WHERE nombre = %s", (nombre_torneo,))
            res_camp = cursor.fetchone()
            
            # 2. Buscar ID del Año (Manejo de string/int)
            anio_str = str(numero_anio).split("-")[0]
            cursor.execute("SELECT id FROM anios WHERE numero = %s", (anio_str,))
            res_anio = cursor.fetchone()

            if res_camp and res_anio:
                camp_id = res_camp[0]
                anio_id = res_anio[0]
                
                # 3. Actualizar a FINALIZADO solo si aún no lo está
                sql = """
                    UPDATE ediciones 
                    SET finalizado = TRUE 
                    WHERE campeonato_id = %s AND anio_id = %s AND finalizado = FALSE
                """
                cursor.execute(sql, (camp_id, anio_id))
                
                if cursor.rowcount > 0:
                    logger.info(f"Torneo marcado como FINALIZADO: {nombre_torneo} {anio_str}")
                    return True
            return False

        except Exception as e:
            logger.error(f"Error finalizando edición en BD: {e}")
            return False
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def obtener_ranking_mufa(self, edicion_id=None, anio=None):
        """
        Calcula el porcentaje de MUFA.
        Mufa = Usuario que pronostica derrota y el equipo PIERDE.
        Fórmula: (Derrotas Acertadas / Total Predicciones de Derrota) * 100
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()

            params = []
            filtro_sql = ""

            if edicion_id is not None:
                filtro_sql = " AND p.edicion_id = %s "
                params.append(edicion_id)
            elif anio is not None:
                filtro_sql = " AND a.numero = %s "
                params.append(anio)

            sql = f"""
            SELECT 
                u.username,
                stats.predicciones_derrota,
                stats.derrotas_acertadas,
                stats.porcentaje_mufa
            FROM usuarios u
            INNER JOIN (
                SELECT 
                    pr.usuario_id,
                    COUNT(*) as predicciones_derrota,
                    -- CAMBIO CLAVE: Contamos cuando REALMENTE PERDIÓ (Goles CAI < Goles Rival)
                    SUM(CASE WHEN p.goles_independiente < p.goles_rival THEN 1 ELSE 0 END) as derrotas_acertadas,
                    -- Cálculo de porcentaje
                    (SUM(CASE WHEN p.goles_independiente < p.goles_rival THEN 1 ELSE 0 END) / COUNT(*)) * 100 as porcentaje_mufa
                FROM pronosticos pr
                INNER JOIN (
                    SELECT usuario_id, partido_id, MAX(fecha_prediccion) as max_fecha
                    FROM pronosticos
                    GROUP BY usuario_id, partido_id
                ) p2 ON pr.usuario_id = p2.usuario_id 
                    AND pr.partido_id = p2.partido_id 
                    AND pr.fecha_prediccion = p2.max_fecha
                JOIN partidos p ON pr.partido_id = p.id
                JOIN ediciones e ON p.edicion_id = e.id
                JOIN anios a ON e.anio_id = a.id
                WHERE 
                    p.goles_independiente IS NOT NULL
                    AND pr.pred_goles_independiente < pr.pred_goles_rival -- FILTRO: Solo cuando pronosticó derrota
                    {filtro_sql}
                GROUP BY pr.usuario_id
            ) stats ON u.id = stats.usuario_id
            
            ORDER BY 
                stats.porcentaje_mufa DESC,      -- El mayor % es el MÁS MUFA
                stats.predicciones_derrota DESC, -- Desempate por cantidad
                u.username ASC
            """
            
            cursor.execute(sql, tuple(params))
            return cursor.fetchall()

        except Exception as e:
            logger.error(f"Error calculando ranking mufa: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()
            
    def obtener_ranking_falso_profeta(self, edicion_id=None, anio=None):
        """
        Ranking de Falso Profeta.
        CAMBIO: Se usa INNER JOIN para excluir usuarios que nunca pronosticaron victoria.
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()

            params = []
            filtro_sql = ""

            if edicion_id is not None:
                filtro_sql = " AND p.edicion_id = %s "
                params.append(edicion_id)
            elif anio is not None:
                filtro_sql = " AND a.numero = %s "
                params.append(anio)

            sql = f"""
            SELECT 
                u.username,
                stats.victorias_pronosticadas,
                stats.porcentaje_acierto
            FROM usuarios u
            INNER JOIN ( -- CAMBIO: INNER JOIN excluye a los que no están en esta subconsulta
                SELECT 
                    pr.usuario_id,
                    COUNT(*) as victorias_pronosticadas,
                    (SUM(CASE WHEN p.goles_independiente > p.goles_rival THEN 1 ELSE 0 END) / COUNT(*)) * 100 as porcentaje_acierto
                FROM pronosticos pr
                INNER JOIN (
                    SELECT usuario_id, partido_id, MAX(fecha_prediccion) as max_fecha
                    FROM pronosticos
                    GROUP BY usuario_id, partido_id
                ) p2 ON pr.usuario_id = p2.usuario_id 
                    AND pr.partido_id = p2.partido_id 
                    AND pr.fecha_prediccion = p2.max_fecha
                JOIN partidos p ON pr.partido_id = p.id
                JOIN ediciones e ON p.edicion_id = e.id
                JOIN anios a ON e.anio_id = a.id
                WHERE 
                    p.goles_independiente IS NOT NULL
                    AND pr.pred_goles_independiente > pr.pred_goles_rival -- FILTRO: Solo victorias pronosticadas
                    {filtro_sql}
                GROUP BY pr.usuario_id
            ) stats ON u.id = stats.usuario_id
            
            ORDER BY 
                stats.porcentaje_acierto ASC, 
                stats.victorias_pronosticadas DESC,
                u.username ASC
            """
            
            cursor.execute(sql, tuple(params))
            return cursor.fetchall()

        except Exception as e:
            logger.error(f"Error calculando ranking falso profeta: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()  

    def obtener_ranking(self, edicion_id=None, anio=None):
        """
        Ranking Definitivo:
        Corrección: Eliminado el filtro fecha_hora < NOW()
        """
        conexion = self.abrir()
        if not conexion:
            return []
        
        cursor = conexion.cursor()
        
        filtro_sql = ""
        params = []
        
        if edicion_id:
            filtro_sql += " AND p.edicion_id = %s"
            params.append(edicion_id)
        if anio:
            filtro_sql += " AND YEAR(p.fecha_hora) = %s"
            params.append(anio)

        sql = f"""
            SELECT 
                u.username,                                                     
                
                -- 1. TOTAL PUNTOS
                COALESCE(SUM(
                    (CASE WHEN SIGN(CAST(p.goles_independiente AS SIGNED) - CAST(p.goles_rival AS SIGNED)) = 
                               SIGN(CAST(pr.pred_goles_independiente AS SIGNED) - CAST(pr.pred_goles_rival AS SIGNED)) 
                          THEN {PUNTOS} ELSE 0 END) +
                    (CASE WHEN p.goles_independiente = pr.pred_goles_independiente THEN {PUNTOS} ELSE 0 END) +
                    (CASE WHEN p.goles_rival = pr.pred_goles_rival THEN {PUNTOS} ELSE 0 END)
                ), 0) as total_puntos,

                -- 2. Puntos Resultado
                COALESCE(SUM(
                    CASE WHEN SIGN(CAST(p.goles_independiente AS SIGNED) - CAST(p.goles_rival AS SIGNED)) = 
                              SIGN(CAST(pr.pred_goles_independiente AS SIGNED) - CAST(pr.pred_goles_rival AS SIGNED)) 
                         THEN {PUNTOS} ELSE 0 END
                ), 0) as pts_resultado,

                -- 3. Puntos Goles CAI
                COALESCE(SUM(CASE WHEN p.goles_independiente = pr.pred_goles_independiente THEN {PUNTOS} ELSE 0 END), 0) as pts_cai,

                -- 4. Puntos Goles Rival
                COALESCE(SUM(CASE WHEN p.goles_rival = pr.pred_goles_rival THEN {PUNTOS} ELSE 0 END), 0) as pts_rival,

                -- 5. Partidos Jugados
                COUNT(pr.id) as partidos_jugados,

                -- 6. Anticipación Promedio
                AVG(TIMESTAMPDIFF(SECOND, pr.fecha_prediccion, p.fecha_hora)) as ant_avg,

                -- 7. Error Promedio
                AVG(
                    ABS(p.goles_independiente - pr.pred_goles_independiente) + 
                    ABS(p.goles_rival - pr.pred_goles_rival)
                ) as error_promedio,

                -- 8. EFECTIVIDAD (Porcentaje de resultados exactos)
                COALESCE(ROUND(
                    (SUM(
                        CASE WHEN p.goles_independiente = pr.pred_goles_independiente 
                              AND p.goles_rival = pr.pred_goles_rival
                             THEN 1 ELSE 0 END
                    ) / NULLIF(COUNT(pr.id), 0)) * 100
                , 2), 0) as efectividad

            FROM usuarios u
            JOIN pronosticos pr ON u.id = pr.usuario_id
            
            INNER JOIN (
                SELECT MAX(id) as max_id
                FROM pronosticos
                GROUP BY usuario_id, partido_id
            ) ultimos ON pr.id = ultimos.max_id
            
            JOIN partidos p ON pr.partido_id = p.id
            
            -- FILTRO CORREGIDO: Eliminamos AND p.fecha_hora < NOW()
            WHERE p.goles_independiente IS NOT NULL 
              AND p.goles_rival IS NOT NULL
            {filtro_sql}
            GROUP BY u.id
            ORDER BY 
                total_puntos DESC,
                partidos_jugados DESC,
                error_promedio ASC,
                ant_avg DESC
        """
        
        try:
            cursor.execute(sql, tuple(params))
            ranking = cursor.fetchall()
        except Exception as e:
            print(f"Error SQL Ranking: {e}")
            ranking = []
        
        cursor.close()
        conexion.close()
        return ranking

    def obtener_indice_optimismo_pesimismo(self, edicion_id=None, anio=None):
        """
        Calcula el índice unificado de Optimismo/Pesimismo mostrando a TODOS los usuarios.
        Formula: (Pred_CAI - Pred_Rival) - (Real_CAI - Real_Rival)
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()

            params = []
            filtro_sql = ""

            # Filtros se aplican a la subconsulta de partidos jugados
            if edicion_id is not None:
                filtro_sql = " AND p.edicion_id = %s "
                params.append(edicion_id)
            elif anio is not None:
                filtro_sql = " AND a.numero = %s "
                params.append(anio)

            sql = f"""
            SELECT 
                u.username,
                stats.indice_promedio,
                stats.desvio_estandar    -- NUEVO CAMPO A EXPORTAR
            FROM usuarios u
            LEFT JOIN (
                SELECT 
                    pr.usuario_id,
                    AVG(
                        (CAST(pr.pred_goles_independiente AS SIGNED) - CAST(pr.pred_goles_rival AS SIGNED)) - 
                        (CAST(p.goles_independiente AS SIGNED) - CAST(p.goles_rival AS SIGNED))
                    ) as indice_promedio,
                    
                    -- NUEVO CÁLCULO: Desvío Estándar
                    STDDEV(
                        (CAST(pr.pred_goles_independiente AS SIGNED) - CAST(pr.pred_goles_rival AS SIGNED)) - 
                        (CAST(p.goles_independiente AS SIGNED) - CAST(p.goles_rival AS SIGNED))
                    ) as desvio_estandar
                    
                FROM pronosticos pr
                INNER JOIN (
                    -- Último pronóstico por partido
                    SELECT usuario_id, partido_id, MAX(fecha_prediccion) as max_fecha
                    FROM pronosticos
                    GROUP BY usuario_id, partido_id
                ) p2 ON pr.usuario_id = p2.usuario_id 
                    AND pr.partido_id = p2.partido_id 
                    AND pr.fecha_prediccion = p2.max_fecha
                JOIN partidos p ON pr.partido_id = p.id
                JOIN ediciones e ON p.edicion_id = e.id
                JOIN anios a ON e.anio_id = a.id
                WHERE 
                    p.goles_independiente IS NOT NULL
                    {filtro_sql}
                GROUP BY pr.usuario_id
            ) stats ON u.id = stats.usuario_id
            ORDER BY 
                CASE WHEN stats.indice_promedio IS NULL THEN 1 ELSE 0 END, -- Nulos al final (o principio según preferencia)
                stats.indice_promedio DESC, 
                u.username ASC
            """
            
            cursor.execute(sql, tuple(params))
            return cursor.fetchall()

        except Exception as e:
            logger.error(f"Error calculando indice opt/pes: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()
    
    def obtener_ranking_mejor_predictor(self, edicion_id=None, anio=None):
        """
        Calcula el Ranking de Mejor Predictor basado en el Error Absoluto de Goles.
        Fórmula por partido: |G_Real_CAI - G_Pred_CAI| + |G_Real_Rival - G_Pred_Rival|
        El ranking se ordena por el PROMEDIO de ese error (ASCENDENTE, menor es mejor).
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()

            params = []
            filtro_sql = ""

            if edicion_id is not None:
                filtro_sql = " AND p.edicion_id = %s "
                params.append(edicion_id)
            elif anio is not None:
                filtro_sql = " AND a.numero = %s "
                params.append(anio)

            sql = f"""
            SELECT 
                u.username,
                stats.promedio_error
            FROM usuarios u
            INNER JOIN (
                SELECT 
                    pr.usuario_id,
                    -- Calculamos el promedio del error absoluto sumado de ambos equipos
                    AVG(
                        ABS(CAST(p.goles_independiente AS SIGNED) - CAST(pr.pred_goles_independiente AS SIGNED)) + 
                        ABS(CAST(p.goles_rival AS SIGNED) - CAST(pr.pred_goles_rival AS SIGNED))
                    ) as promedio_error
                FROM pronosticos pr
                INNER JOIN (
                    -- Solo el último pronóstico por partido
                    SELECT usuario_id, partido_id, MAX(fecha_prediccion) as max_fecha
                    FROM pronosticos
                    GROUP BY usuario_id, partido_id
                ) p2 ON pr.usuario_id = p2.usuario_id 
                    AND pr.partido_id = p2.partido_id 
                    AND pr.fecha_prediccion = p2.max_fecha
                JOIN partidos p ON pr.partido_id = p.id
                JOIN ediciones e ON p.edicion_id = e.id
                JOIN anios a ON e.anio_id = a.id
                WHERE 
                    p.goles_independiente IS NOT NULL -- Solo partidos jugados
                    {filtro_sql}
                GROUP BY pr.usuario_id
            ) stats ON u.id = stats.usuario_id
            
            ORDER BY 
                stats.promedio_error ASC, -- Menor error es mejor
                u.username ASC
            """
            
            cursor.execute(sql, tuple(params))
            return cursor.fetchall()

        except Exception as e:
            logger.error(f"Error calculando ranking mejor predictor: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()
        
    def obtener_partidos_futuros_crudo(self):
        """Devuelve ID, rival y fecha exacta de los partidos futuros que aún tienen usuarios pendientes de pronosticar."""
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()
            
            # La subconsulta EXISTS asegura que el partido solo se devuelva si 
            # falta al menos un usuario con Telegram asociado por pronosticar.
            query = """
                SELECT p.id, r.nombre, p.fecha_hora
                FROM partidos p
                JOIN rivales r ON p.rival_id = r.id
                WHERE p.fecha_hora > DATE_SUB(NOW(), INTERVAL 3 HOUR)
                  AND EXISTS (
                      SELECT 1 
                      FROM usuarios u 
                      WHERE u.id_telegram IS NOT NULL 
                        AND u.id NOT IN (
                            SELECT usuario_id 
                            FROM pronosticos pr 
                            WHERE pr.partido_id = p.id
                        )
                  );
            """
            cursor.execute(query)
            return cursor.fetchall()
            
        except Exception as e:
            print(f"Error obteniendo partidos futuros: {e}")
            return []
        finally:
            if 'conexion' in locals() and conexion.is_connected():
                cursor.close()
                conexion.close()

    def obtener_pendientes_notificacion(self, dias=5):
        """
        Obtiene una lista de usuarios que tienen partidos sin pronosticar.
        Si faltan varios días, notifica 1 vez al día.
        Si falta menos de 1 hora, envía una alerta urgente (máximo 1 vez por hora para no hacer spam).
        
        AJUSTE HORARIO: Se resta 3 horas a NOW() para compensar el horario de TiDB.
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()

            sql = f"""
            SELECT 
                DISTINCT u.id, 
                u.username, 
                u.email, 
                r.nombre, 
                p.fecha_hora
            FROM partidos p
            JOIN rivales r ON p.rival_id = r.id
            CROSS JOIN usuarios u
            LEFT JOIN pronosticos pr ON p.id = pr.partido_id AND u.id = pr.usuario_id
            WHERE 
                pr.id IS NULL -- Que NO tenga pronóstico
                AND u.email IS NOT NULL -- Que tenga email
                
                AND (
                    -- =========================================================
                    -- CASO 1: Alerta diaria normal (dentro del rango de días)
                    -- Solo se envía si HOY no se le mandó nada.
                    -- =========================================================
                    (
                        p.fecha_hora >= DATE_SUB(NOW(), INTERVAL 3 HOUR)
                        AND p.fecha_hora <= DATE_ADD(DATE_SUB(NOW(), INTERVAL 3 HOUR), INTERVAL %s DAY)
                        AND (
                            u.fecha_ultima_notificacion IS NULL 
                            OR DATE(u.fecha_ultima_notificacion) < DATE(DATE_SUB(NOW(), INTERVAL 3 HOUR))
                        )
                    )
                    OR 
                    -- =========================================================
                    -- CASO 2: Alerta URGENTE (Falta menos de 1 hora)
                    -- Se envía AUNQUE ya se le haya avisado hoy a la mañana,
                    -- pero verificamos que haya pasado al menos 1 hora desde
                    -- el último aviso para no bombardearle la bandeja de entrada.
                    -- =========================================================
                    (
                        p.fecha_hora >= DATE_SUB(NOW(), INTERVAL 3 HOUR)
                        AND p.fecha_hora <= DATE_ADD(DATE_SUB(NOW(), INTERVAL 3 HOUR), INTERVAL 1 HOUR)
                        AND (
                            u.fecha_ultima_notificacion IS NULL 
                            OR u.fecha_ultima_notificacion <= DATE_SUB(DATE_SUB(NOW(), INTERVAL 3 HOUR), INTERVAL 1 HOUR)
                        )
                    )
                )
            ORDER BY u.id, p.fecha_hora ASC
            """
            
            cursor.execute(sql, (dias,))
            return cursor.fetchall()

        except Exception as e:
            logger.error(f"Error obteniendo pendientes notificación: {e}")
            return []
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def marcar_usuario_notificado(self, usuario_id):
        """Actualiza la fecha de última notificación a 'ahora'."""
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()
            
            sql = "UPDATE usuarios SET fecha_ultima_notificacion = DATE_SUB(NOW(), INTERVAL 3 HOUR) WHERE id = %s"
            cursor.execute(sql, (usuario_id,))
            conexion.commit()
            return True
        except Exception as e:
            logger.error(f"Error marcando notificado: {e}")
            return False
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def validar_usuario(self, input_identificador, password):
        """
        Verifica si el texto ingresado coincide con un Usuario O un Email.
        Retorna el 'username' real si la contraseña es correcta.
        Lanza excepciones con mensajes específicos para la UI.
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor(dictionary=True)
            
            # Búsqueda dual: Nombre de usuario O Correo
            sql = "SELECT username, password FROM usuarios WHERE username = %s OR email = %s"
            cursor.execute(sql, (input_identificador, input_identificador))
            usuario = cursor.fetchone()
            
            # --- VALIDACIÓN 1: EXISTENCIA ---
            if not usuario:
                # Mensaje específico solicitado
                raise ValueError("El texto ingresado no corresponde a ningún nombre de usuario ni correo electrónico registrado.")
            
            # --- VALIDACIÓN 2: CONTRASEÑA ---
            hash_guardado = usuario['password']
            try:
                self.ph.verify(hash_guardado, password)
                # Retornamos el username real para que el sistema cargue los datos correctos
                return usuario['username']
            except VerifyMismatchError:
                raise ValueError("La contraseña es incorrecta.")
            
        except ValueError as ve:
            # Re-lanzamos los errores de validación (usuario no existe / contraseña mal)
            raise ve
        except Exception as e:
            logger.error(f"Error validando usuario: {e}")
            raise Exception(f"Fallo técnico en base de datos: {e}")
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def verificar_username_libre(self, nuevo_username):
        """Verifica que el nuevo nombre de usuario no esté ocupado."""
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()
            sql = "SELECT id FROM usuarios WHERE username = %s"
            cursor.execute(sql, (nuevo_username,))
            if cursor.fetchone():
                raise Exception("El nombre de usuario ya está en uso.")
            return True
        except Exception as e:
            raise e
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def actualizar_username(self, id_usuario, nuevo_username):
        """Actualiza el nombre de usuario capturando restricciones CHECK."""
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()
            sql = "UPDATE usuarios SET username = %s WHERE id = %s"
            cursor.execute(sql, (nuevo_username, id_usuario))
            conexion.commit()
            return True
            
        except mysql.connector.Error as e:
            if e.errno == 1062:
                raise Exception("El nombre de usuario ya está en uso.")
            elif e.errno == 3819:
                if 'chk_username_no_vacio' in str(e).lower():
                    raise Exception("El nombre de usuario no puede estar compuesto solo por espacios en blanco.")
            raise e
        except Exception as e:
            raise e
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def obtener_id_por_username(self, username):
        """Obtiene el ID numérico de un usuario."""
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()
            cursor.execute("SELECT id FROM usuarios WHERE username = %s", (username,))
            res = cursor.fetchone()
            return res[0] if res else None
        except Exception:
            return None
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()
    
    def obtener_ranking_estabilidad(self, edicion_id=None, anio=None):
        """
        Calcula el promedio de pronósticos por partido (Estabilidad)
        considerando ÚNICAMENTE partidos terminados (goles cargados).
        Fórmula: Total de filas en 'pronosticos' para partidos jugados / Cantidad de partidos jugados distintos.
        """
        conexion = self.abrir()
        if not conexion: return []
        cursor = conexion.cursor()

        # Filtro base: Solo partidos que tienen resultado cargado (goles_independiente IS NOT NULL)
        filtros = ["p.goles_independiente IS NOT NULL"] 
        params = []

        if edicion_id:
            filtros.append("p.edicion_id = %s")
            params.append(edicion_id)
        if anio:
            filtros.append("YEAR(p.fecha_hora) = %s")
            params.append(anio)

        where_clause = " AND ".join(filtros)

        sql = f"""
            SELECT 
                u.username, 
                -- Cálculo: Total Versiones / Total Partidos Únicos
                COUNT(pr.id) / NULLIF(COUNT(DISTINCT pr.partido_id), 0) as promedio_cambios
            FROM usuarios u
            JOIN pronosticos pr ON u.id = pr.usuario_id
            JOIN partidos p ON pr.partido_id = p.id
            WHERE {where_clause}
            GROUP BY u.id
            ORDER BY u.username ASC
        """
        
        try:
            cursor.execute(sql, tuple(params))
            datos = cursor.fetchall()
        except Exception as e:
            logger.error(f"Error en ranking estabilidad: {e}")
            datos = []
            
        cursor.close()
        conexion.close()
        return datos
            
    def actualizar_email_usuario(self, username, nuevo_email):
        """Actualiza el correo electrónico del usuario capturando restricciones CHECK."""
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()
            
            # Verificar que el email no lo esté usando otro usuario
            sql_check = "SELECT id FROM usuarios WHERE email = %s AND username != %s"
            cursor.execute(sql_check, (nuevo_email, username))
            if cursor.fetchone():
                raise Exception("El correo ya está en uso por otra cuenta.")

            sql = "UPDATE usuarios SET email = %s WHERE username = %s"
            cursor.execute(sql, (nuevo_email, username))
            conexion.commit()
            return True
            
        except mysql.connector.Error as e:
            if e.errno == 1062:
                raise Exception("El correo electrónico ya está registrado.")
            elif e.errno == 3819:
                if 'chk_email_formato' in str(e).lower():
                    raise Exception("El formato del correo electrónico es inválido según la seguridad de la base de datos.")
            raise e
        except Exception as e:
            raise e
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()
        
    # -------------------------------------------------------------
    # --- MÉTODOS PARA LA ADMINISTRACIÓN DE EDICIONES Y AÑOS ---
    # -------------------------------------------------------------

    def obtener_anios_admin(self):
        """Obtiene la lista de años disponibles para los selectores."""
        conexion = None; cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()
            cursor.execute("SELECT id, numero FROM anios ORDER BY numero DESC")
            return cursor.fetchall()
        except Exception as e:
            raise e
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def obtener_ediciones_admin(self):
        """Obtiene todas las ediciones combinando Torneo, Año y Estado."""
        conexion = None; cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()
            cursor.execute("""
                SELECT e.id, c.nombre, a.numero, e.finalizado, c.id, a.id 
                FROM ediciones e 
                JOIN campeonatos c ON e.campeonato_id = c.id 
                JOIN anios a ON e.anio_id = a.id 
                ORDER BY e.finalizado ASC, a.numero DESC, c.nombre ASC
            """)
            return cursor.fetchall()
        except Exception as e:
            raise e
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def agregar_edicion_admin(self, campeonato_id, anio_id, finalizado):
        """Agrega una nueva edición validando que no esté duplicada."""
        conexion = None; cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()
            cursor.execute("INSERT INTO ediciones (campeonato_id, anio_id, finalizado) VALUES (%s, %s, %s)", (campeonato_id, anio_id, finalizado))
            conexion.commit()
        except mysql.connector.Error as e:
            if e.errno == 1062:
                raise Exception("Esta edición (Torneo + Año) ya existe en la base de datos.")
            raise e
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def editar_edicion_admin(self, edicion_id, campeonato_id, anio_id, finalizado):
        """Edita una edición existente."""
        conexion = None; cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()
            cursor.execute("UPDATE ediciones SET campeonato_id=%s, anio_id=%s, finalizado=%s WHERE id=%s", (campeonato_id, anio_id, finalizado, edicion_id))
            conexion.commit()
        except mysql.connector.Error as e:
            if e.errno == 1062:
                raise Exception("Esta edición (Torneo + Año) ya existe en la base de datos.")
            raise e
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()
    
    def registrar_anio_actual(self):
        """Registra el año actual en la base de datos automáticamente si no existe."""
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()
            
            # Usamos tu función para obtener el año exacto en horario de Argentina
            anio_actual = self.obtener_hora_argentina().year
            
            # Respetamos el CHECK de tu base de datos (2026 - 2100)
            if 2026 <= anio_actual <= 2100:
                sql = "INSERT INTO anios (numero) VALUES (%s)"
                cursor.execute(sql, (anio_actual,))
                conexion.commit()
                logger.info(f"Año {anio_actual} registrado automáticamente en la base de datos.")
                
        except mysql.connector.Error as e:
            if e.errno == 1062:
                # Error 1062 = Duplicate entry. El año ya existe.
                # Lo ignoramos en total silencio porque es lo que esperamos el 99% de las veces.
                pass
            else:
                logger.error(f"Error de BD al registrar el año actual: {e}")
        except Exception as e:
            logger.error(f"Error general al registrar el año actual: {e}")
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def eliminar_edicion_admin(self, edicion_id):
        """Elimina una edición SOLO si no tiene partidos jugados/cargados."""
        conexion = None; cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()
            
            # Control de seguridad restrictivo: ¿Hay partidos en esta edición?
            cursor.execute("SELECT COUNT(*) FROM partidos WHERE edicion_id = %s", (edicion_id,))
            cantidad = cursor.fetchone()[0]
            if cantidad > 0:
                raise Exception("No se puede eliminar la edición porque ya tiene partidos asociados. Debes eliminar los partidos primero.")
                
            cursor.execute("DELETE FROM ediciones WHERE id = %s", (edicion_id,))
            conexion.commit()
        except Exception as e:
            raise e
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()

    def verificar_email_libre(self, nuevo_email, usuario_actual):
        """
        Verifica si un email está disponible para cambio (que no lo tenga OTRO usuario).
        """
        conexion = None
        cursor = None
        try:
            conexion = self.abrir()
            cursor = conexion.cursor()
            
            # Buscamos si existe el email PERO asociado a un usuario DISTINTO al actual
            sql = "SELECT username FROM usuarios WHERE email = %s AND username != %s"
            cursor.execute(sql, (nuevo_email, usuario_actual))
            resultado = cursor.fetchone()
            
            if resultado:
                raise Exception("El correo electrónico ya está registrado por otra cuenta.")
                
            return True 
            
        except Exception as e:
            raise e
        finally:
            if cursor: cursor.close()
            if conexion: conexion.close()
            
