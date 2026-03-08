# Python 3.11.9
import flet as ft
import os
import sys
import time
import threading
import requests
import smtplib
import random
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from tarjeta_acceso import TarjetaAcceso
from estilos import Estilos
from base_de_datos import BaseDeDatos
from datetime import datetime, timedelta, timezone
from ventana_mensaje import GestorMensajes
import gc
from ventana_carga import VentanaCarga

# Constantes
NOMBRE_ICONO = "favicon.ico"
NOMBRE_ICONO_UI = "Escudo.png"
MAXIMA_CANTIDAD_DE_PUNTOS = 9
ID_INDEPENDIENTE = 10078  # ID real de Independiente en FotMob
URL_API = "https://www.fotmob.com/api/teams"
CANT_PARTIDOS_A_SINCRONIZAR = 10
DÍAS_NOTIFICACIÓN = 3  # Días antes del partido para notificar
ADMINISTRADOR = 'Gabriel'
CANT_USUARIOS_EN_LISTA = 4
ALTURA_POR_USUARIO_LISTA = 52
ALTURA_LISTAS_DIALOGO = CANT_USUARIOS_EN_LISTA * ALTURA_POR_USUARIO_LISTA
ANCHO_COLUMNA_USUARIO = 100
NOTIFICACIONES_LANZADAS = False
ANCHO_RIVALES_NOMBRE = 225
ANCHO_TORNEOS_NOMBRE = 225
ANCHO_PRONÓSTICO_USUARIO = 65

# --- CREDENCIALES SEGURAS ---
# Lee el correo desde el sistema, si no lo encuentra usa el tuyo por defecto
REMITENTE = os.getenv("EMAIL_REMITENTE")

# Lee la contraseña invisible que guardamos en Windows
PASSWORD = os.getenv("EMAIL_PASSWORD")

if PASSWORD is None:
    print("¡ADVERTENCIA!: No se encontró la contraseña del correo en el sistema.")

class SistemaIndependiente:
    def __init__(self, page: ft.Page):
        self.page = page
        self._configurar_ventana()

        try:
            bd = BaseDeDatos()
            self.lista_administradores = bd.obtener_administradores()
        except:
            self.lista_administradores = []

        self._construir_interfaz_login()
        global NOTIFICACIONES_LANZADAS
        if not NOTIFICACIONES_LANZADAS:
            NOTIFICACIONES_LANZADAS = True
            threading.Thread(target=self._servicio_notificaciones_background, daemon=True).start()

    def _servicio_notificaciones_background(self):
        """
        Revisa si hay usuarios sin pronosticar partidos próximos y les envía un correo.
        Se ejecuta una sola vez al iniciar la app.
        """
        time.sleep(5) 
        
        # Aseguramos que timedelta y datetime estén disponibles localmente para los cálculos
        from datetime import datetime, timedelta
        
        try:
            print("🔔 Verificando notificaciones pendientes...")
            bd = BaseDeDatos()
            pendientes = bd.obtener_pendientes_notificacion(dias=DÍAS_NOTIFICACIÓN)
            
            if not pendientes:
                print("   -> No hay notificaciones para enviar hoy.")
                return

            usuarios_a_notificar = {}
            
            # 1. Agrupamos todos los datos (incluyendo el objeto fecha original)
            for fila in pendientes:
                uid, uname, email, rival, fecha = fila
                
                if uid not in usuarios_a_notificar:
                    usuarios_a_notificar[uid] = {
                        'username': uname,
                        'email': email,
                        'partidos': []
                    }
                
                usuarios_a_notificar[uid]['partidos'].append({
                    'rival': rival,
                    'fecha': fecha
                })

            cantidad_enviados = 0
            ahora = self.obtener_hora_argentina()
            
            # 2. Armamos el correo analizando partido por partido
            for uid, datos in usuarios_a_notificar.items():
                destinatario = datos['email']
                username = datos['username']
                
                mensajes_hoy = []
                mensajes_alarma = []
                lineas_partidos = []
                
                for p in datos['partidos']:
                    rival = p['rival']
                    fecha = p['fecha']
                    fecha_str = fecha.strftime('%d/%m %H:%M')
                    
                    diferencia = fecha - ahora
                    segundos_restantes = diferencia.total_seconds()
                    
                    # Verificaciones lógicas exactas por calendario
                    es_hoy = fecha.date() == ahora.date()
                    es_manana = fecha.date() == (ahora + timedelta(days=1)).date()
                    dias_faltantes = (fecha.date() - ahora.date()).days
                    
                    # Construcción de los bloques de alerta
                    if es_hoy:
                        mensajes_hoy.append(f"📌 ¡ATENCIÓN! Hoy es el partido contra {rival.upper()}.")
                        
                        # Mensaje alarmante si falta menos de 1 hora y el partido no empezó
                        if 0 < segundos_restantes <= 3600:
                            horas = int(segundos_restantes // 3600)
                            minutos = int((segundos_restantes % 3600) // 60)
                            mensajes_alarma.append(f"🚨 ¡URGENTE! Falta {horas:02d}:{minutos:02d} horas para el partido contra {rival}.")
                            
                        detalle_tiempo = "¡Es HOY!"
                    elif es_manana:
                        detalle_tiempo = "Falta 1 día (Mañana)"
                    elif dias_faltantes > 1:
                        detalle_tiempo = f"Faltan {dias_faltantes} días"
                    else:
                        detalle_tiempo = "Partido en curso o finalizado"
                        
                    # Lista con el nuevo formato detallado
                    lineas_partidos.append(f"- {rival} ({fecha_str}) -> {detalle_tiempo}")

                # 3. Ensamblamos el cuerpo del correo dinámicamente
                cuerpo = f"Hola {username},\n\n"
                
                if mensajes_hoy:
                    cuerpo += "\n".join(mensajes_hoy) + "\n\n"
                    
                if mensajes_alarma:
                    cuerpo += "\n".join(mensajes_alarma) + "\n\n"
                    
                cuerpo += "Aún no has cargado tu pronóstico para los siguientes encuentros:\n\n"
                cuerpo += "\n".join(lineas_partidos) + "\n\n"
                
                # --- AQUÍ SE AGREGA EL ENLACE A RENDER ---
                cuerpo += "¡No te olvides de sumar puntos!\nIngresa a la aplicación para dejar tu resultado: https://independiente.onrender.com\n\nSaludos,\nEl Sistema."

                asunto = "⚠️ Recordatorio: Partidos sin pronosticar - CAI"
                
                try:
                    msg = MIMEMultipart()
                    msg['From'] = REMITENTE
                    msg['To'] = destinatario
                    msg['Subject'] = asunto
                    msg.attach(MIMEText(cuerpo, 'plain'))
                    
                    server = smtplib.SMTP('smtp.gmail.com', 587)
                    server.starttls()
                    server.login(REMITENTE, PASSWORD)
                    server.send_message(msg)
                    server.quit()
                    
                    bd.marcar_usuario_notificado(uid)
                    cantidad_enviados += 1
                    
                except Exception as e_mail:
                    mensaje_log = f"Error enviando a {username}: {e_mail}"
                    print(f"   [!] {mensaje_log}")
                    self._mostrar_mensaje_admin("Error SMTP", mensaje_log, "error", nombre_función="SistemaIndependiente._servicio_notificaciones_background")

            if cantidad_enviados > 0:
                print(f"🔔 Se enviaron {cantidad_enviados} notificaciones exitosamente.")

        except Exception as e:
            mensaje_log = f"Error en servicio de notificaciones: {e}"
            print(mensaje_log)
            self._mostrar_mensaje_admin("Error de Sistema", mensaje_log, "error", nombre_función="SistemaIndependiente._servicio_notificaciones_background")

    def _mostrar_mensaje_admin(self, titulo, mensaje, tipo="error", nombre_función=None):
        """
        Verifica si el usuario es admin y muestra un mensaje. 
        Si no es admin, envía un correo de alerta silencioso a los administradores.
        """
        # 1. Extraemos solo los nombres de usuario de nuestra nueva lista de diccionarios
        nombres_admins = [admin["username"] for admin in self.lista_administradores]
        
        # 2. Verificamos si el usuario actual está logueado y es administrador
        es_admin = hasattr(self, 'usuario_actual') and self.usuario_actual in nombres_admins
        
        if es_admin:
            # Es administrador: le mostramos el cartel en pantalla
            GestorMensajes.mostrar(self.page, titulo, mensaje, tipo)
            self.page.update()
        else:
            # No es administrador: lanzamos el envío de correo en segundo plano para no congelar la app
            threading.Thread(
                target=self._enviar_alerta_correo_admins, 
                args=(titulo, mensaje, tipo, nombre_función), 
                daemon=True
            ).start()
    
    def _enviar_alerta_correo_admins(self, titulo, mensaje, tipo, nombre_función=None):
        """
        Envía un correo electrónico a todos los administradores registrados.
        """
        # 1. Creamos una lista rápida solo con los nombres (ignorando los emails)
        nombres_admins = [admin["username"] for admin in self.lista_administradores]

        # 2. Corroboramos que el usuario no sea un administrador para evitar enviarle un correo a alguien que es quien debería recibirlo
        if usuario_implicado not in nombres_admins:
            # Variables de entorno de tu correo del sistema (Render)
            remitente = os.getenv("EMAIL_USER")
            password = os.getenv("EMAIL_PASSWORD")
            
            if not remitente or not password:
                print("No se enviará la alerta: Credenciales de correo no configuradas.")
                return

            # Extraemos solo los correos que no sean nulos o vacíos
            correos_destino = [admin["email"] for admin in self.lista_administradores if admin.get("email")]
            
            if not correos_destino:
                print("No hay administradores con correo configurado para recibir la alerta.")
                return
                
            try:
                msg = MIMEMultipart()
                msg['From'] = remitente
                # Unimos todos los correos separados por coma
                msg['To'] = ", ".join(correos_destino) 
                msg['Subject'] = f"🚨 ALERTA DEL SISTEMA: {titulo}"
                
                usuario_implicado = getattr(self, 'usuario_actual', 'Usuario no logueado')
                
                cuerpo_mensaje = f"""
                Se ha registrado una alerta oculta en el sistema de Pronósticos CAI.
                
                • Usuario implicado: {usuario_implicado}
                • Gravedad: {tipo.upper()}
                • Título del error: {titulo}
                • Función donde ocurrió el error: {nombre_función if nombre_función else "Desconocida"}
                
                Detalle técnico:
                {mensaje}
                
                -----------------------------------------
                Este es un mensaje automático del servidor.
                """
                
                msg.attach(MIMEText(cuerpo_mensaje, 'plain'))
                
                # Conexión al servidor SMTP (Asumiendo que usas Gmail o Google Workspace)
                server = smtplib.SMTP('smtp.gmail.com', 587)
                server.starttls()
                server.login(remitente, password)
                server.send_message(msg)
                server.quit()
                
                print(f"Alerta enviada exitosamente a los administradores.")
                
            except Exception as e:
                print(f"Fallo crítico al intentar enviar correo a administradores: {e}")

    def _sincronizar_fixture_api(self):
        """
        Sincronización Inteligente:
        1. Pasado: Actualiza resultados de los partidos jugados.
        2. General: Sincroniza torneos y fechas de los últimos 5 y próximos 5 partidos.
        3. Finalización: Si un torneo tiene partidos jugados pero ya no tiene futuros, se marca como finalizado.
        """
        print("Iniciando sincronización (Lógica Estricta)...")

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json"
        }
        
        params = {
            "id": ID_INDEPENDIENTE,
            "timezone": "America/Argentina/Buenos_Aires",
            "ccode3": "ARG"
        }
        
        bd = BaseDeDatos()
        
        try:
            response = requests.get(URL_API, headers=headers, params=params, timeout=15)
            if response.status_code != 200:
                print(f"Error API: Status {response.status_code}")
                return

            data = response.json()
            fixtures_obj = data.get("fixtures", {})
            partidos_unicos = {}

            # Recolección de datos
            def agregar_partidos(lista_origen):
                if not lista_origen: return
                for m in lista_origen:
                    if isinstance(m, dict):
                        m_id = m.get("id")
                        if m_id: partidos_unicos[m_id] = m

            agregar_partidos(fixtures_obj.get("results", []))
            agregar_partidos(fixtures_obj.get("fixtures", []))
            raw_all = fixtures_obj.get("allFixtures")
            if isinstance(raw_all, list): agregar_partidos(raw_all)
            elif isinstance(raw_all, dict):
                for val in raw_all.values():
                    if isinstance(val, list): agregar_partidos(val)

            if not partidos_unicos: return

            # Clasificación
            jugados = []
            por_jugar = []
            
            for match in partidos_unicos.values():
                datos = self._procesar_partido_fotmob(match)
                if not datos: continue
                
                status = match.get("status", {})
                finished = status.get("finished", False)
                cancelled = status.get("cancelled", False)
                
                if cancelled: continue 

                if finished:
                    jugados.append(datos)
                else:
                    por_jugar.append(datos)
            
            # Ordenamiento
            jugados.sort(key=lambda x: x['fecha'], reverse=True)
            por_jugar.sort(key=lambda x: x['fecha'], reverse=False)
            
            # --- LÓGICA DE REGLA DE 21:00 H (PLACEHOLDER) ---
            ahora = self.obtener_hora_argentina()
            for i, p in enumerate(por_jugar):
                fecha = p['fecha']
                
                if fecha.hour == 21 and fecha.minute == 0 and fecha.second == 0:
                    no_es_proximo = (i >= 3)
                    dias_faltantes = (fecha - ahora).days
                    es_lejano = (dias_faltantes > 7)
                    
                    if no_es_proximo or es_lejano:
                        p['fecha'] = fecha.replace(hour=0, minute=0, second=0, microsecond=0)

            # --- 1. ACTUALIZACIÓN DE GOLES Y RESULTADOS ---
            if jugados:
                print(f"Procesando resultados de {len(jugados)} partidos jugados...")
                bd.actualizar_resultados_pendientes(jugados)

            # --- 2. SINCRONIZACIÓN DE TORNEOS Y FECHAS (Pasado del año actual + Próximos 5) ---
            anio_actual = ahora.year
            
            # 1. Filtramos TODOS los partidos jugados que pertenezcan exclusivamente a este año
            jugados_este_anio = [p for p in jugados if p['fecha'].year == anio_actual]
            
            # 2. Tomamos estrictamente los próximos 5 partidos a jugar (sean de este año o del próximo)
            proximos_5 = por_jugar[:5]
            
            partidos_a_sincronizar = jugados_este_anio + proximos_5
            
            if partidos_a_sincronizar:
                print(f"Sincronizando {len(jugados_este_anio)} jugados este año y los próximos {len(proximos_5)} a jugar...")
                bd.sincronizar_partidos(partidos_a_sincronizar)
            
            # --- 3. LÓGICA DE FINALIZACIÓN DE TORNEOS ---
            torneos_con_futuro = set()
            for p in por_jugar:
                torneos_con_futuro.add((p['torneo'], p['anio']))
            
            torneos_con_pasado = set()
            for p in jugados:
                torneos_con_pasado.add((p['torneo'], p['anio']))
            
            posibles_finalizados = torneos_con_pasado - torneos_con_futuro
            
            if posibles_finalizados:
                print(f"Verificando finalización de {len(posibles_finalizados)} torneos...")
                for nombre, anio in posibles_finalizados:
                    bd.marcar_edicion_finalizada(nombre, anio)

            print("Sincronización completada.")
            
        except Exception as e:
            self._mostrar_mensaje_admin("Error Sincronización", f"Error crítico sincronizando FotMob: {e}", "error", nombre_función="SistemaIndependiente._sincronizar_fixture_api")
        
        finally:
            if hasattr(self, 'dlg_cargando_inicio') and self.dlg_cargando_inicio.open:
                self._limpiar_memoria_dialogo(self.dlg_cargando_inicio)
            
            print("Cargando interfaz...")
            self._recargar_datos(
                actualizar_partidos=True, 
                actualizar_pronosticos=True, 
                actualizar_ranking=True,
                actualizar_copas=True, 
                actualizar_admin=True 
            )

    def _configurar_ventana(self):
        self.page.title = "Pronósticos CAI"
        # ELIMINADO: self.page.favicon = NOMBRE_ICONO (Ya sabemos que en la web esto no va)
        
        if not self.page.web:
            # Aquí está el truco de Windows: Forzamos estrictamente el formato .ico
            self.page.window.icon = NOMBRE_ICONO
            self.page.window.maximized = True
        
        self.page.theme_mode = ft.ThemeMode.DARK 
        self.page.bgcolor = "#121212" 
        self.page.padding = 0
        self.page.update()
        
        self.page.vertical_alignment = ft.MainAxisAlignment.CENTER
        self.page.horizontal_alignment = ft.CrossAxisAlignment.CENTER

    # --- PANTALLA 1: LOGIN ---
    def _construir_interfaz_login(self):
        self.page.appbar = None
        
        self.tarjeta = TarjetaAcceso(
            self.page, 
            on_login_success=self._ir_a_menu_principal,
            on_error_fatal=self._enviar_alerta_correo_admins
        )

        self.btn_salir = ft.IconButton(
            icon="close",
            icon_color="white",
            bgcolor="#333333", 
            on_click=lambda e: self.page.window.close() if not self.page.web else None,
            visible=not self.page.web  # Desaparece inteligentemente en navegadores
        )

        layout = ft.Stack(
            controls=[
                self.tarjeta, 
                ft.Container(content=self.btn_salir, right=10, top=10)
            ],
            expand=True
        )

        self.page.add(layout)

    def _toggle_sin_pronosticar(self, e):
        """Activa o desactiva el filtro 'Sin Pronosticar' sumándose a los demás."""
        self.filtro_sin_pronosticar = not self.filtro_sin_pronosticar
        self._actualizar_botones_partidos_visual()
        self._actualizar_titulo_partidos()
        self._recargar_datos(actualizar_partidos=True, actualizar_copas=False)

    def _gestionar_accion_boton_filtro(self, tipo):
        """
        Gestiona la lógica 'toggle' de los botones específicos (Torneo, Equipo, Usuario).
        - Si el filtro ya está activo -> Lo desactiva.
        - Si no está activo -> Abre el modal para seleccionar.
        """
        if tipo == 'torneo':
            if self.filtro_pron_torneo is not None:
                # Desactivar
                self.filtro_pron_torneo = None
                self._actualizar_botones_pronosticos_visual() # Pinta de nuevo los colores correctos
                self._actualizar_titulo_pronosticos()
                self._recargar_datos(actualizar_pronosticos=True)
            else:
                # Abrir Modal
                self._abrir_selector_torneo_pronosticos(None)
                
        elif tipo == 'equipo':
            if self.filtro_pron_equipo is not None:
                # Desactivar
                self.filtro_pron_equipo = None
                self._actualizar_botones_pronosticos_visual()
                self._actualizar_titulo_pronosticos()
                self._recargar_datos(actualizar_pronosticos=True)
            else:
                # Abrir Modal
                self._abrir_selector_equipo_pronosticos(None)
                
        elif tipo == 'usuario':
            if self.filtro_pron_usuario is not None:
                # Desactivar
                self.filtro_pron_usuario = None
                self._actualizar_botones_pronosticos_visual()
                self._actualizar_titulo_pronosticos()
                self._recargar_datos(actualizar_pronosticos=True)
            else:
                # Abrir Modal
                self._abrir_selector_usuario_pronosticos(None)

    def _actualizar_titulo_pronosticos(self):
        """Construye el título dinámico basado en TODOS los filtros activos."""
        partes = []
        
        # Parte Tiempo
        if self.filtro_pron_tiempo == 'todos': partes.append("Todos")
        elif self.filtro_pron_tiempo == 'futuros': partes.append("Por Jugar")
        elif self.filtro_pron_tiempo == 'jugados': partes.append("Finalizados")
        
        # Partes Específicas
        detalles = []
        if self.filtro_pron_torneo: detalles.append(self.filtro_pron_torneo)
        if self.filtro_pron_equipo: detalles.append(f"vs {self.filtro_pron_equipo}")
        if self.filtro_pron_usuario: detalles.append(f"de {self.filtro_pron_usuario}")
        
        titulo = "Pronósticos: " + " - ".join(partes)
        if detalles:
            titulo += " (" + ", ".join(detalles) + ")"
            
        self.txt_titulo_pronosticos.value = titulo
        self.txt_titulo_pronosticos.update()

    def _abrir_modal_falso_profeta(self, e):
        """Muestra el ranking de 'Falso Profeta' con animación de carga y scroll horizontal."""
        
        self.loading_modal = ft.ProgressBar(width=200, color="amber", bgcolor="#222222")
        
        # Ancho dinámico para que no se salga del celular
        ancho_pantalla = self.page.width if self.page.width else 600
        ancho_modal = min(650, ancho_pantalla - 20)
        
        columna_content = ft.Column(
            controls=[
                ft.Text("Ranking Falso Profeta 🤡", size=18, weight="bold", color="white"),
                ft.Text("Usuarios que más le erran cuando dicen que el Rojo va a ganar.", size=12, color="white70"),
                ft.Container(height=10),
                self.loading_modal,
                ft.Container(height=50)
            ],
            height=150,
            width=ancho_modal, # <--- AHORA ES DINÁMICO
            scroll=ft.ScrollMode.ALWAYS
        )
        
        self.dlg_fp = ft.AlertDialog(content=columna_content, modal=True)
        self.page.open(self.dlg_fp)

        def _cargar():
            time.sleep(0.3)
            
            try:
                bd = BaseDeDatos()
                datos = bd.obtener_ranking_falso_profeta(self.filtro_ranking_edicion_id, self.filtro_ranking_anio)
                
                filas = []
                for i, fila in enumerate(datos, start=1):
                    user = fila[0]
                    victorias_pred = fila[1]
                    porcentaje_acierto = float(fila[2])
                    
                    porcentaje_falso = 100 - porcentaje_acierto
                    txt_porcentaje = f"{porcentaje_falso:.1f}%".replace('.', ',')
                    
                    if porcentaje_falso >= 80: color_txt = "red"
                    elif porcentaje_falso >= 50: color_txt = "orange"
                    else: color_txt = "green"
                    
                    filas.append(ft.DataRow(cells=[
                        ft.DataCell(ft.Container(content=ft.Text(f"{i}º", color="white", weight=ft.FontWeight.BOLD), width=50, alignment=ft.alignment.center)),
                        ft.DataCell(ft.Container(content=ft.Text(user, color="white"), width=ANCHO_COLUMNA_USUARIO, alignment=ft.alignment.center_left)),
                        ft.DataCell(ft.Container(content=ft.Text(str(victorias_pred), color="cyan"), width=120, alignment=ft.alignment.center)),
                        ft.DataCell(ft.Container(content=ft.Text(txt_porcentaje, color=color_txt, weight=ft.FontWeight.BOLD), width=120, alignment=ft.alignment.center)),
                    ]))

                tabla = ft.DataTable(
                    columns=[
                        ft.DataColumn(ft.Container(content=ft.Text("Pos", weight="bold", color="white"), width=50, alignment=ft.alignment.center)),
                        ft.DataColumn(ft.Container(content=ft.Text("Usuario", weight="bold", color="white"), width=ANCHO_COLUMNA_USUARIO, alignment=ft.alignment.center_left)),
                        ft.DataColumn(ft.Container(content=ft.Text("Pred. Victoria", tooltip="Veces que dijo que ganábamos", weight="bold", color="white"), width=120, alignment=ft.alignment.center), numeric=True),
                        ft.DataColumn(ft.Container(content=ft.Text("% Falso Profeta", tooltip="Porcentaje de veces que falló al predecir victoria", weight="bold", color="white"), width=120, alignment=ft.alignment.center), numeric=True),
                    ],
                    rows=filas,
                    heading_row_color="black",
                    data_row_color={"hoverED": "#1A1A1A"},
                    border=ft.border.all(1, "white10"),
                    column_spacing=10,
                    heading_row_height=60,
                    data_row_max_height=50,
                    data_row_min_height=50
                )
                
                # Altura matemática perfecta: 60px de cabecera + 50px por cada usuario
                altura_tabla = 60 + (len(filas) * 50) + 30
                altura_contenedor = min(270, altura_tabla)

                contenedor_tabla_nativa = ft.Row(
                    scroll=ft.ScrollMode.ALWAYS,
                    controls=[
                        ft.Container(
                            height=altura_contenedor,
                            content=ft.Column(
                                controls=[tabla],
                                scroll=ft.ScrollMode.ALWAYS
                            )
                        )
                    ]
                )
                
                # Ajuste dinámico del modal sin dejar espacios vacíos
                alto_pantalla = self.page.height if self.page.height else 600
                columna_content.height = min(alto_pantalla - 50, altura_contenedor + 150) 
                
                columna_content.controls = [
                    ft.Text("Ranking Falso Profeta 🤡", size=18, weight="bold", color="white"),
                    ft.Text("Usuarios que más le erran cuando dicen que el Rojo va a ganar.", size=12, color="white70"),
                    ft.Container(height=10),
                    contenedor_tabla_nativa,
                    ft.Container(height=10),
                    ft.Row([ft.ElevatedButton("Cerrar", on_click=lambda e: self._limpiar_memoria_dialogo(self.dlg_fp))], alignment=ft.MainAxisAlignment.END)
                ]
                self.dlg_fp.update()

            except Exception as ex:
                self._limpiar_memoria_dialogo(self.dlg_fp)
                GestorMensajes.mostrar(self.page, "Error", f"No se pudo cargar falso profeta: {ex}", "error")
                self._enviar_alerta_correo_admins("Error Falso Profeta", f"Error al cargar ranking de falso profeta: {ex}", "error", nombre_función="SistemaIndependiente._abrir_modal_falso_profeta._cargar")

        threading.Thread(target=_cargar, daemon=True).start()

    def _seleccionar_fila_ranking(self, usuario):
        """Marca visualmente la fila sin recargar datos ni activar selección nativa."""
        # 1. Actualizar estado
        if self.usuario_seleccionado_ranking == usuario:
            self.usuario_seleccionado_ranking = None
        else:
            self.usuario_seleccionado_ranking = usuario
            
        # 2. Actualizar color manualmente
        for row in self.tabla_estadisticas.rows:
            if row.data == self.usuario_seleccionado_ranking:
                row.color = "#8B0000"
                # row.selected = True  <--- ¡ESTO NO LO PONGAS!
            else:
                row.color = None
                # row.selected = False <--- ESTO TAMPOCO
        
        self.tabla_estadisticas.update()

    def _seleccionar_fila_pronostico(self, row_key):
        """Marca visualmente la fila sin recargar datos ni activar selección nativa."""
        # 1. Actualizar estado
        if self.pronostico_seleccionado_key == row_key:
            self.pronostico_seleccionado_key = None
        else:
            self.pronostico_seleccionado_key = row_key
            
        # 2. Actualizar color manualmente
        for row in self.tabla_pronosticos.rows:
            if row.data == self.pronostico_seleccionado_key:
                row.color = "#8B0000"
            else:
                row.color = None
                
        self.tabla_pronosticos.update()

    def _seleccionar_fila_pronostico(self, row_key):
        """Marca visualmente la fila sin recargar datos ni activar selección nativa."""
        # 1. Actualizar estado
        if self.pronostico_seleccionado_key == row_key:
            self.pronostico_seleccionado_key = None
        else:
            self.pronostico_seleccionado_key = row_key
            
        # 2. Actualizar color manualmente
        for row in self.tabla_pronosticos.rows:
            if row.data == self.pronostico_seleccionado_key:
                row.color = "#8B0000"
            else:
                row.color = None
                
        self.tabla_pronosticos.update()

    def _click_grafico_barras(self, e):
        """Intercepta el clic del gráfico de barras para avisar si falta el torneo."""
        if self.filtro_ranking_edicion_id is None:
            self.page.snack_bar = ft.SnackBar(ft.Text("Debe seleccionar un torneo para ver este gráfico.", color="white"), bgcolor="#8B0000", duration=2000)
            self.page.snack_bar.open = True
            self.page.update()
            return
            
        self._abrir_selector_usuarios_generico("Puntos por partidos", False, "Ver Gráfico", ft.Icons.BAR_CHART, self._generar_grafico_barras)

    # --- PANTALLA 2: MENÚ PRINCIPAL ---

    def _ir_a_menu_principal(self, usuario):
        self.page.controls.clear()
        self.page.bgcolor = Estilos.COLOR_ROJO_CAI
        self.usuario_actual = usuario
        
        # --- BANDERAS Y ESTADOS ---
        self.cargando_partidos = False
        self.cargando_torneos = False
        self.procesando_partidos = False 
        self.procesando_torneos = False
        self.editando_torneo = False 
        self.pronosticos_sort_col_index = None
        self.pronosticos_sort_asc = True
        self.filtro_partidos = 'futuros'
        self.filtro_edicion_id = None 
        self.filtro_rival_id = None 
        self.filtro_pron_tiempo = 'todos' 
        self.filtro_pron_torneo = None 
        self.filtro_pron_equipo = None 
        self.filtro_pron_usuario = None 
        self.torneo_seleccionado_id = None
        self.filtro_ranking_edicion_id = None
        self.filtro_ranking_nombre = None
        self.filtro_ranking_anio = None
        self.cache_ediciones_modal = [] 
        self.cache_rivales_modal = [] 
        self.temp_campeonato_sel = None 
        self.temp_anio_sel = None
        self.temp_rival_sel_id = None 
        self.temp_rival_sel_nombre = None
        self.temp_usuario_sel = None
        self.edicion_seleccionada_id = None
        self.fila_seleccionada_ref = None
        self.partido_seleccionado_id = None
        self.fila_partido_ref = None
        self.partido_a_pronosticar_id = None
        self.fila_pronostico_ref = None
        self.rival_seleccionado_id = None
        self.chk_usuarios_grafico = [] 
        self.chk_usuarios_grafico_lp = [] 
        self.usuario_grafico_barra_sel = None 
        self.usuario_seleccionado_ranking = None
        self.pronostico_seleccionado_key = None

        # NUEVAS VARIABLES DE ESTADO PARA FILTROS CONJUNTOS
        self.filtro_temporal = 'futuros'      # 'todos', 'jugados', 'futuros'
        self.filtro_edicion_id = None         # ID o None
        self.filtro_rival_id = None           # ID o None
        self.filtro_sin_pronosticar = False   # True o False

        # --- SELECTORES ---
        self.page.appbar = ft.AppBar(
            # Flet buscará la imagen directamente en la carpeta assets
            leading=ft.Container(content=ft.Image(src=NOMBRE_ICONO_UI, fit=ft.ImageFit.CONTAIN), padding=5),
            leading_width=50,
            title=ft.Text(f"Bienvenido, {usuario}", weight=ft.FontWeight.BOLD, color=Estilos.COLOR_ROJO_CAI),
            center_title=False, bgcolor="white", 
            actions=[ft.IconButton(icon=ft.Icons.LOGOUT, tooltip="Cerrar Sesión", icon_color=Estilos.COLOR_ROJO_CAI, on_click=self._cerrar_sesion), ft.Container(width=10)]
        )

        # --- BARRAS DE CARGA ---
        self.loading = ft.ProgressBar(width=400, color="amber", bgcolor="#222222", visible=True)
        self.loading_partidos = ft.ProgressBar(width=400, color="amber", bgcolor="#222222", visible=False) 
        self.loading_pronosticos = ft.ProgressBar(width=400, color="amber", bgcolor="#222222", visible=False) 
        self.loading_admin = ft.ProgressBar(width=400, color="amber", bgcolor="#222222", visible=False)
        self.loading_torneos_admin = ft.ProgressBar(width=400, color="amber", bgcolor="#222222", visible=False)
        self.loading_copas = ft.ProgressBar(width=400, color="amber", bgcolor="#222222", visible=False)
        
        # --- CONTENEDOR 1: FILTROS ---
        self.btn_ranking_torneo = ft.ElevatedButton("Por torneo", icon=ft.Icons.EMOJI_EVENTS, bgcolor="#333333", color="white", width=140, height=30, style=ft.ButtonStyle(padding=5, text_style=ft.TextStyle(size=12)), on_click=self._abrir_selector_torneo_ranking)
        self.btn_ranking_anio = ft.ElevatedButton("Por año", icon=ft.Icons.CALENDAR_MONTH, bgcolor="#333333", color="white", width=140, height=30, style=ft.ButtonStyle(padding=5, text_style=ft.TextStyle(size=12)), on_click=self._abrir_selector_anio_ranking)

        self.contenedor_filtro_torneo = ft.Container(
            padding=ft.padding.all(10), border=ft.border.all(1, "white24"), border_radius=8, bgcolor="#1E1E1E", 
            content=ft.Column(
                spacing=10, horizontal_alignment=ft.CrossAxisAlignment.START, 
                controls=[
                    ft.Text("Filtros", size=11, weight=ft.FontWeight.BOLD, color="white54"), 
                    ft.Row(controls=[self.btn_ranking_torneo, self.btn_ranking_anio], alignment=ft.MainAxisAlignment.START, wrap=True, spacing=10, run_spacing=10) 
                ]
            )
        )

        # --- CONTENEDOR 2: GRÁFICOS DE LÍNEA ---
        self.btn_grafico_puestos = ft.ElevatedButton("Por puestos", icon=ft.Icons.SHOW_CHART, bgcolor="#222222", color="white30", width=140, height=30, tooltip="Visualiza la evolución del ranking (subidas y bajadas) fecha a fecha.", style=ft.ButtonStyle(padding=5, text_style=ft.TextStyle(size=12)), on_click=self._abrir_selector_grafico_puestos)
        self.btn_grafico_linea_puntos = ft.ElevatedButton("Por puntos", icon=ft.Icons.SHOW_CHART, bgcolor="#222222", color="white30", width=140, height=30, tooltip="Visualiza la acumulación de puntos a lo largo del tiempo comparando usuarios.", style=ft.ButtonStyle(padding=5, text_style=ft.TextStyle(size=12)), on_click=self._abrir_selector_grafico_linea_puntos)

        self.contenedor_graficos = ft.Container(
            padding=ft.padding.all(10), border=ft.border.all(1, "white24"), border_radius=8, bgcolor="#1E1E1E", 
            content=ft.Column(
                spacing=10, horizontal_alignment=ft.CrossAxisAlignment.START, 
                controls=[
                    ft.Text("Gráficos de línea", size=11, weight=ft.FontWeight.BOLD, color="white54"), 
                    ft.Row(controls=[self.btn_grafico_puestos, self.btn_grafico_linea_puntos], alignment=ft.MainAxisAlignment.START, wrap=True, spacing=10, run_spacing=10)
                ]
            )
        )

        # --- CONTENEDOR 3: GRÁFICOS DE BARRA ---
        self.btn_grafico_barras_puntos = ft.ElevatedButton("Puntos por partidos", icon=ft.Icons.BAR_CHART, bgcolor="#222222", color="white30", width=140, height=45, tooltip="Muestra cuántos puntos sumó un usuario en cada partido individual (9, 6, 3 o 0).", style=ft.ButtonStyle(padding=5, text_style=ft.TextStyle(size=12)), on_click=self._click_grafico_barras)

        self.contenedor_graficos_barra = ft.Container(
            padding=ft.padding.all(10), border=ft.border.all(1, "white24"), border_radius=8, bgcolor="#1E1E1E", 
            content=ft.Column(
                spacing=10, horizontal_alignment=ft.CrossAxisAlignment.START, 
                controls=[
                    ft.Text("Gráficos de barra", size=11, weight=ft.FontWeight.BOLD, color="white54"), 
                    ft.Row(controls=[self.btn_grafico_barras_puntos], alignment=ft.MainAxisAlignment.START, wrap=True, spacing=10, run_spacing=10)
                ]
            )
        )

        # --- CONTENEDOR 4: RANKINGS ---
        self.btn_indice_opt_pes = ft.ElevatedButton(
            "Optimismo/Pesimismo", icon="assessment", bgcolor="#333333", color="white", width=180, height=45, 
            style=ft.ButtonStyle(padding=5, text_style=ft.TextStyle(size=12)), 
            tooltip="Mide tu tendencia a pronosticar resultados a favor (Optimista) o en contra (Pesimista) del Rojo.",
            on_click=self._abrir_modal_opt_pes
        )
        self.btn_ranking_fp = ft.ElevatedButton(
            "Falso profeta", icon="new_releases", bgcolor="#333333", color="white", width=140, height=45, 
            style=ft.ButtonStyle(padding=5, text_style=ft.TextStyle(size=12)), 
            tooltip="Usuarios que más se equivocan cuando dicen que Independiente va a ganar.",
            on_click=self._abrir_modal_falso_profeta
        )
        self.btn_estilo_decision = ft.ElevatedButton(
            "Estilo de decisión", icon=ft.Icons.PSYCHOLOGY, bgcolor="#333333", color="white", width=180, height=45, 
            style=ft.ButtonStyle(padding=5, text_style=ft.TextStyle(size=12)), 
            tooltip="Clasifica tu estilo según el tiempo de anticipación con el que guardas tus pronósticos.",
            on_click=self._abrir_modal_estilo_decision
        )
        self.btn_mufa = ft.ElevatedButton(
            "Mufa", icon="flash_on", bgcolor="#333333", color="white", width=140, height=45, 
            style=ft.ButtonStyle(padding=5, text_style=ft.TextStyle(size=12)), 
            tooltip="Usuarios que más aciertan el resultado cuando pronostican que el Rojo pierde.",
            on_click=self._abrir_modal_mufa
        )
        self.btn_mejor_predictor = ft.ElevatedButton(
            "Mejor predictor", icon="precision_manufacturing", bgcolor="#333333", color="white", width=140, height=45, 
            style=ft.ButtonStyle(padding=5, text_style=ft.TextStyle(size=12)), 
            tooltip="Premia a quienes tienen el menor margen de error en la cantidad de goles pronosticados.",
            on_click=self._abrir_modal_mejor_predictor
        )
        self.btn_cambios_pronostico = ft.ElevatedButton(
            "Cambios de pronóstico", icon=ft.Icons.EDIT_NOTE, bgcolor="#333333", color="white", width=180, height=45, 
            style=ft.ButtonStyle(padding=5, text_style=ft.TextStyle(size=12)), 
            tooltip="Muestra quiénes dudan más y cambian su resultado constantemente antes del partido.",
            on_click=self._abrir_modal_cambios_pronostico
        )
        self.btn_racha_actual = ft.ElevatedButton(
            "Racha actual", icon="trending_up", bgcolor="#333333", color="white", width=140, height=45, 
            style=ft.ButtonStyle(padding=5, text_style=ft.TextStyle(size=12)), 
            tooltip="Cantidad de partidos consecutivos actuales en los que sumaste al menos 3 puntos.",
            on_click=self._abrir_modal_racha_actual
        )
        self.btn_racha_record = ft.ElevatedButton(
            "Racha récord", icon="military_tech", bgcolor="#333333", color="white", width=140, height=45, 
            style=ft.ButtonStyle(padding=5, text_style=ft.TextStyle(size=12)), 
            tooltip="La mejor racha histórica de partidos consecutivos sumando puntos por jugador.",
            on_click=self._abrir_modal_racha_record
        )
        self.btn_mayores_errores = ft.ElevatedButton(
            "Mayores errores", icon=ft.Icons.ERROR_OUTLINE, bgcolor="#333333", color="white", width=140, height=45, 
            style=ft.ButtonStyle(padding=5, text_style=ft.TextStyle(size=12)), 
            tooltip="El top 10 histórico de los peores pronósticos (mayor diferencia absoluta de goles).",
            on_click=self._generar_tabla_mayores_errores
        )

        # --- CONTENEDOR 5: GRÁFICOS DE TORTA ---
        self.btn_grafico_torta_estilo = ft.ElevatedButton("Resultados pronosticados", icon=ft.Icons.PIE_CHART, bgcolor="#333333", color="white", width=215, height=30, style=ft.ButtonStyle(padding=5, text_style=ft.TextStyle(size=12)), on_click=lambda e: self._abrir_selector_usuarios_generico("Resultados pronosticados", False, "Ver Gráfico", ft.Icons.PIE_CHART, self._generar_grafico_torta_estilo_pronostico))
        self.btn_grafico_torta_tendencia = ft.ElevatedButton("Tendencia de pronóstico", icon=ft.Icons.PIE_CHART_OUTLINE, bgcolor="#333333", color="white", width=215, height=30, style=ft.ButtonStyle(padding=5, text_style=ft.TextStyle(size=12)), on_click=lambda e: self._abrir_selector_usuarios_generico("Tendencia de pronóstico", False, "Ver Gráfico", ft.Icons.PIE_CHART_OUTLINE, self._generar_grafico_torta_tendencia))
        self.btn_grafico_torta_firmeza = ft.ElevatedButton("Grado de firmeza", icon=ft.Icons.SHIELD, bgcolor="#333333", color="white", width=215, height=30, style=ft.ButtonStyle(padding=5, text_style=ft.TextStyle(size=12)), on_click=lambda e: self._abrir_selector_usuarios_generico("Grado de firmeza", False, "Ver Gráfico", ft.Icons.SHIELD, self._generar_grafico_torta_firmeza))
        
        self.contenedor_graficos_torta = ft.Container(
            padding=ft.padding.all(10), border=ft.border.all(1, "white24"), border_radius=8, bgcolor="#1E1E1E", 
            content=ft.Column(
                spacing=10, horizontal_alignment=ft.CrossAxisAlignment.START, 
                controls=[
                    ft.Text("Gráficos de torta", size=11, weight=ft.FontWeight.BOLD, color="white54"), 
                    ft.Row(controls=[self.btn_grafico_torta_estilo, self.btn_grafico_torta_tendencia, self.btn_grafico_torta_firmeza], alignment=ft.MainAxisAlignment.START, wrap=True, spacing=10, run_spacing=10)
                ]
            )
        )

        self.btn_grafico_torta_tendencia = ft.ElevatedButton(
            "Tendencia de pronóstico", 
            icon=ft.Icons.PIE_CHART_OUTLINE, 
            bgcolor="#333333", color="white", width=215, height=30, 
            tooltip="Analiza si tus pronósticos suelen ser optimistas, neutrales o pesimistas respecto al resultado final.", 
            style=ft.ButtonStyle(padding=5, text_style=ft.TextStyle(size=12)), 
            on_click=lambda e: self._abrir_selector_usuarios_generico("Tendencia de pronóstico", False, "Ver Gráfico", ft.Icons.PIE_CHART_OUTLINE, self._generar_grafico_torta_tendencia)
        )
        
        self.btn_grafico_torta_firmeza = ft.ElevatedButton(
            "Grado de firmeza", 
            icon=ft.Icons.SHIELD, 
            bgcolor="#333333", color="white", width=215, height=30, 
            tooltip="Analiza la cantidad de veces que cambiaste de opinión antes del partido.\n🧱 1 vez | 🤔 2 veces | 🔄 3+ veces", 
            style=ft.ButtonStyle(padding=5, text_style=ft.TextStyle(size=12)), 
            on_click=lambda e: self._abrir_selector_usuarios_generico("Grado de firmeza", False, "Ver Gráfico", ft.Icons.SHIELD, self._generar_grafico_torta_firmeza)
        )

        # --- BOTÓN DE GRÁFICO DE BARRAS ---
        # (Ajusta el nombre de la variable si en tu código se llama distinto, ej: self.btn_grafico_barras)
        self.btn_grafico_barras = ft.ElevatedButton(
            "Puntos por partidos", 
            icon=ft.Icons.BAR_CHART, 
            bgcolor="#333333", color="white", width=215, height=30, 
            tooltip="Muestra el rendimiento de puntos por partido.", 
            style=ft.ButtonStyle(padding=5, text_style=ft.TextStyle(size=12)), 
            on_click=lambda e: self._abrir_selector_usuarios_generico("Puntos por partidos", False, "Ver Gráfico", ft.Icons.BAR_CHART, self._generar_grafico_barras)
        )

        self.contenedor_graficos_torta = ft.Container(
            padding=ft.padding.all(10), border=ft.border.all(1, "white24"), border_radius=8, bgcolor="#1E1E1E", 
            content=ft.Column(
                spacing=10, horizontal_alignment=ft.CrossAxisAlignment.START, 
                controls=[
                    ft.Text("Gráficos de torta", size=11, weight=ft.FontWeight.BOLD, color="white54"), 
                    ft.Row(controls=[self.btn_grafico_torta_estilo, self.btn_grafico_torta_tendencia, self.btn_grafico_torta_firmeza], alignment=ft.MainAxisAlignment.START, wrap=True, spacing=10, run_spacing=10)
                ]
            )
        )

        self.contenedor_indices = ft.Container(
            padding=ft.padding.all(10), border=ft.border.all(1, "white24"), border_radius=8, bgcolor="#1E1E1E", 
            content=ft.Column(
                spacing=10, horizontal_alignment=ft.CrossAxisAlignment.START, 
                controls=[
                    ft.Text("Rankings", size=11, weight=ft.FontWeight.BOLD, color="white54"), 
                    # ¡AQUÍ ESTÁ LA CLAVE! Todos los botones en un solo Row.
                    ft.Row(
                        controls=[
                            self.btn_indice_opt_pes, self.btn_ranking_fp, 
                            self.btn_estilo_decision, self.btn_mufa, 
                            self.btn_mejor_predictor, self.btn_cambios_pronostico, 
                            self.btn_racha_actual, self.btn_racha_record, self.btn_mayores_errores
                        ], 
                        alignment=ft.MainAxisAlignment.START, 
                        wrap=True, spacing=10, run_spacing=10
                    )
                ]
            )
        )

        # --- CONTROLES FORMULARIO PRONÓSTICOS ---
        self.input_pred_cai = ft.TextField(label="Goles CAI", width=80, text_align=ft.TextAlign.CENTER, keyboard_type=ft.KeyboardType.NUMBER, max_length=2, bgcolor="#2D2D2D", border_color="white24", color="white", on_change=self._validar_solo_numeros)
        self.input_pred_rival = ft.TextField(label="Goles Rival", width=110, text_align=ft.TextAlign.CENTER, keyboard_type=ft.KeyboardType.NUMBER, max_length=2, bgcolor="#2D2D2D", border_color="white24", color="white", on_change=self._validar_solo_numeros)
        self.btn_pronosticar = ft.ElevatedButton("Pronosticar", icon=ft.Icons.SPORTS_SOCCER, bgcolor="green", color="white", on_click=self._guardar_pronostico)

        # --- TÍTULOS ---
        self.txt_titulo_ranking = ft.Text("Tabla de posiciones histórica", size=28, weight=ft.FontWeight.BOLD, color="white")
        self.txt_titulo_copas = ft.Text("Torneos ganados en la historia", size=24, weight=ft.FontWeight.BOLD, color="white")
        self.txt_titulo_partidos = ft.Text("Partidos por jugar", size=28, weight=ft.FontWeight.BOLD, color="white")
        self.txt_titulo_pronosticos = ft.Text("Todos los pronósticos", size=28, weight=ft.FontWeight.BOLD, color="white") 

        # --- BOTONES FILTROS (PESTAÑA PARTIDOS) ---
        self.btn_todos = ft.ElevatedButton("Todos", icon=ft.Icons.LIST, bgcolor="#333333", color="white", on_click=lambda _: self._cambiar_filtro_tiempo_partidos('todos'))
        self.btn_jugados = ft.ElevatedButton("Jugados", icon=ft.Icons.HISTORY, bgcolor="#333333", color="white", on_click=lambda _: self._cambiar_filtro_tiempo_partidos('jugados'))
        self.btn_por_jugar = ft.ElevatedButton("Por jugar", icon=ft.Icons.UPCOMING, bgcolor="blue", color="white", on_click=lambda _: self._cambiar_filtro_tiempo_partidos('futuros'))
        self.btn_por_torneo = ft.ElevatedButton("Por torneo", icon=ft.Icons.EMOJI_EVENTS, bgcolor="#333333", color="white", on_click=self._abrir_selector_torneo)
        self.btn_sin_pronosticar = ft.ElevatedButton("Sin pronosticar", icon=ft.Icons.EVENT_BUSY, bgcolor="#333333", color="white", on_click=self._toggle_sin_pronosticar)
        self.btn_por_equipo = ft.ElevatedButton("Por equipo", icon=ft.Icons.GROUPS, bgcolor="#333333", color="white", on_click=self._abrir_selector_equipo)

        # --- BOTONES FILTROS (PESTAÑA PRONÓSTICOS) ---
        self.btn_pron_todos = ft.ElevatedButton("Todos", icon=ft.Icons.LIST, bgcolor="blue", color="white", on_click=lambda _: self._cambiar_filtro_tiempo_pronosticos('todos'))
        self.btn_pron_por_jugar = ft.ElevatedButton("Por jugar", icon=ft.Icons.UPCOMING, bgcolor="#333333", color="white", on_click=lambda _: self._cambiar_filtro_tiempo_pronosticos('futuros'))
        self.btn_pron_jugados = ft.ElevatedButton("Jugados", icon=ft.Icons.HISTORY, bgcolor="#333333", color="white", on_click=lambda _: self._cambiar_filtro_tiempo_pronosticos('jugados'))
        self.btn_pron_por_torneo = ft.ElevatedButton("Por torneo", icon=ft.Icons.EMOJI_EVENTS, bgcolor="#333333", color="white", on_click=lambda _: self._gestionar_accion_boton_filtro('torneo'))
        self.btn_pron_por_equipo = ft.ElevatedButton("Por equipo", icon=ft.Icons.GROUPS, bgcolor="#333333", color="white", on_click=lambda _: self._gestionar_accion_boton_filtro('equipo'))
        self.btn_pron_por_usuario = ft.ElevatedButton("Por usuario", icon=ft.Icons.PERSON, bgcolor="#333333", color="white", on_click=lambda _: self._gestionar_accion_boton_filtro('usuario'))

        # --- COLUMNAS TABLAS ---
        columnas_partidos = [
            ft.DataColumn(ft.Container(content=ft.Text("Vs (rival)", color="white", weight=ft.FontWeight.BOLD), width=190, alignment=ft.alignment.center)),
            ft.DataColumn(ft.Container(content=ft.Text("Resultado", color="white", weight=ft.FontWeight.BOLD), width=80, alignment=ft.alignment.center)), 
            ft.DataColumn(ft.Container(content=ft.Text("Fecha y hora", color="white", weight=ft.FontWeight.BOLD), width=140, alignment=ft.alignment.center)), 
            ft.DataColumn(ft.Container(content=ft.Text("Condición", color="white", weight=ft.FontWeight.BOLD), width=90, alignment=ft.alignment.center)),
            ft.DataColumn(ft.Container(content=ft.Text("Torneo", color="yellow", weight=ft.FontWeight.BOLD), width=150, alignment=ft.alignment.center)), 
            ft.DataColumn(ft.Container(content=ft.Text("Tu pronóstico", color="cyan", weight=ft.FontWeight.BOLD), width=100, alignment=ft.alignment.center)), 
            ft.DataColumn(ft.Container(content=ft.Text("Tus puntos", color="green", weight=ft.FontWeight.BOLD), width=80, alignment=ft.alignment.center)),
            ft.DataColumn(ft.Container(content=ft.Text("Error\nabsoluto", color="red", weight=ft.FontWeight.BOLD, text_align="center"), width=80, alignment=ft.alignment.center), numeric=True)
        ]
        columnas_pronosticos = [
            ft.DataColumn(ft.Container(content=ft.Text("Vs (rival)", color="white", weight=ft.FontWeight.BOLD), width=190, alignment=ft.alignment.center), on_sort=self._ordenar_tabla_pronosticos),
            ft.DataColumn(ft.Container(content=ft.Text("Fecha y hora", color="white", weight=ft.FontWeight.BOLD), width=140, alignment=ft.alignment.center), on_sort=self._ordenar_tabla_pronosticos), 
            ft.DataColumn(ft.Container(content=ft.Text("Torneo", color="yellow", weight=ft.FontWeight.BOLD), width=150, alignment=ft.alignment.center), on_sort=self._ordenar_tabla_pronosticos), 
            ft.DataColumn(ft.Container(content=ft.Text("Resultado", color="white", weight=ft.FontWeight.BOLD), width=80, alignment=ft.alignment.center), on_sort=self._ordenar_tabla_pronosticos), 
            ft.DataColumn(ft.Container(content=ft.Text("Usuario", color="white", weight=ft.FontWeight.BOLD), width=ANCHO_PRONÓSTICO_USUARIO, alignment=ft.alignment.center), on_sort=self._ordenar_tabla_pronosticos), 
            ft.DataColumn(ft.Container(content=ft.Text("Pronóstico", color="cyan", weight=ft.FontWeight.BOLD), width=80, alignment=ft.alignment.center), on_sort=self._ordenar_tabla_pronosticos), 
            ft.DataColumn(ft.Container(content=ft.Text("Fecha predicción", color="white70", weight=ft.FontWeight.BOLD), width=160, alignment=ft.alignment.center), on_sort=self._ordenar_tabla_pronosticos),
            ft.DataColumn(ft.Container(content=ft.Text("Puntos", color="green", weight=ft.FontWeight.BOLD), width=60, alignment=ft.alignment.center), numeric=True, on_sort=self._ordenar_tabla_pronosticos),
            ft.DataColumn(ft.Container(content=ft.Text("Error\nabsoluto", color="red", weight=ft.FontWeight.BOLD, text_align="center"), width=80, alignment=ft.alignment.center), numeric=True, on_sort=self._ordenar_tabla_pronosticos)
        ]
        ancho_usuario = ANCHO_COLUMNA_USUARIO
        columnas_estadisticas = [
            ft.DataColumn(ft.Container(content=ft.Text("Puesto", color="white", weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER), width=50, alignment=ft.alignment.center)), 
            ft.DataColumn(ft.Container(content=ft.Text("Usuario", color="white", weight=ft.FontWeight.BOLD), width=ancho_usuario, alignment=ft.alignment.center)), 
            ft.DataColumn(ft.Container(content=ft.Text("Puntos\ntotales", color="yellow", weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER), width=75, alignment=ft.alignment.center)), 
            ft.DataColumn(ft.Container(content=ft.Text("Pts.\ngoles CAI", color="white", text_align=ft.TextAlign.CENTER), width=75, alignment=ft.alignment.center)), 
            ft.DataColumn(ft.Container(content=ft.Text("Pts.\ngoles rival", color="white", text_align=ft.TextAlign.CENTER), width=75, alignment=ft.alignment.center)), 
            ft.DataColumn(ft.Container(content=ft.Text("Pts.\nresultado", color="white", text_align=ft.TextAlign.CENTER, tooltip="Puntos por acertar Gana/Empata/Pierde"), width=75, alignment=ft.alignment.center)), 
            ft.DataColumn(ft.Container(content=ft.Text("Partidos\njugados", color="cyan", text_align=ft.TextAlign.CENTER), width=70, alignment=ft.alignment.center)), 
            ft.DataColumn(ft.Container(content=ft.Text("Error\npromedio", color="red", text_align=ft.TextAlign.CENTER, tooltip="Promedio de error absoluto de goles"), width=80, alignment=ft.alignment.center)),
            ft.DataColumn(ft.Container(content=ft.Text("Anticipación\npromedio", color="cyan", text_align=ft.TextAlign.CENTER), width=190, alignment=ft.alignment.center)), 
            ft.DataColumn(ft.Container(content=ft.Text("Efectividad", text_align="center", weight="bold"), width=80, alignment=ft.alignment.center)),
        ]
        columnas_copas = [
            ft.DataColumn(ft.Container(content=ft.Text("Puesto", color="white", weight=ft.FontWeight.BOLD), width=60, alignment=ft.alignment.center)), 
            ft.DataColumn(ft.Container(content=ft.Text("Usuario", color="white", weight=ft.FontWeight.BOLD), width=ancho_usuario, alignment=ft.alignment.center)), 
            ft.DataColumn(ft.Container(content=ft.Text("Torneos ganados", color="yellow", weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER), width=120, alignment=ft.alignment.center))
        ]

        columnas_rivales = [
            ft.DataColumn(ft.Container(content=ft.Text("Nombre", color="white", weight=ft.FontWeight.BOLD), width=ANCHO_RIVALES_NOMBRE, alignment=ft.alignment.center))
        ]
        
        # --- DEFINICIÓN DE TABLAS ---
        self.tabla_estadisticas_header = ft.DataTable(width=1050, horizontal_margin=0, bgcolor="#2D2D2D", border=ft.border.all(1, "white10"), border_radius=ft.border_radius.only(top_left=8, top_right=8), vertical_lines=ft.border.BorderSide(1, "white10"), horizontal_lines=ft.border.BorderSide(1, "white10"), heading_row_color="black", heading_row_height=70, data_row_max_height=0, column_spacing=10, columns=columnas_estadisticas, rows=[])
        self.tabla_estadisticas = ft.DataTable(width=1050, horizontal_margin=0, bgcolor="#2D2D2D", border=ft.border.all(1, "white10"), border_radius=ft.border_radius.only(bottom_left=8, bottom_right=8), vertical_lines=ft.border.BorderSide(1, "white10"), horizontal_lines=ft.border.BorderSide(1, "white10"), heading_row_height=0, data_row_max_height=60, column_spacing=10, columns=columnas_estadisticas, rows=[])
        
        self.tabla_copas_header = ft.DataTable(width=400, bgcolor="#2D2D2D", border=ft.border.all(1, "white10"), border_radius=ft.border_radius.only(top_left=8, top_right=8), vertical_lines=ft.border.BorderSide(1, "white10"), horizontal_lines=ft.border.BorderSide(1, "white10"), heading_row_color="black", heading_row_height=70, data_row_max_height=0, column_spacing=20, columns=columnas_copas, rows=[])
        self.tabla_copas = ft.DataTable(width=400, bgcolor="#2D2D2D", border=ft.border.all(1, "white10"), border_radius=ft.border_radius.only(bottom_left=8, bottom_right=8), vertical_lines=ft.border.BorderSide(1, "white10"), horizontal_lines=ft.border.BorderSide(1, "white10"), heading_row_height=0, data_row_max_height=60, column_spacing=20, columns=columnas_copas, rows=[])
        
        self.tabla_partidos_header = ft.DataTable(bgcolor="#2D2D2D", border=ft.border.all(1, "white10"), border_radius=ft.border_radius.only(top_left=8, top_right=8), vertical_lines=ft.border.BorderSide(1, "white10"), horizontal_lines=ft.border.BorderSide(1, "white10"), heading_row_color="black", heading_row_height=70, data_row_max_height=0, column_spacing=20, columns=columnas_partidos, rows=[])
        self.tabla_partidos = ft.DataTable(bgcolor="#2D2D2D", border=ft.border.all(1, "white10"), border_radius=ft.border_radius.only(bottom_left=8, bottom_right=8), vertical_lines=ft.border.BorderSide(1, "white10"), horizontal_lines=ft.border.BorderSide(1, "white10"), heading_row_height=0, data_row_min_height=20, data_row_max_height=60, column_spacing=20, columns=columnas_partidos, rows=[])

        self.tabla_pronosticos_header = ft.DataTable(bgcolor="#2D2D2D", border=ft.border.all(1, "white10"), border_radius=ft.border_radius.only(top_left=8, top_right=8), vertical_lines=ft.border.BorderSide(1, "white10"), horizontal_lines=ft.border.BorderSide(1, "white10"), heading_row_color="black", heading_row_height=70, data_row_max_height=0, column_spacing=20, columns=columnas_pronosticos, rows=[])
        self.tabla_pronosticos = ft.DataTable(bgcolor="#2D2D2D", border=ft.border.all(1, "white10"), border_radius=ft.border_radius.only(bottom_left=8, bottom_right=8), vertical_lines=ft.border.BorderSide(1, "white10"), horizontal_lines=ft.border.BorderSide(1, "white10"), heading_row_height=0, data_row_min_height=20, data_row_max_height=60, column_spacing=20, columns=columnas_pronosticos, sort_column_index=self.pronosticos_sort_col_index, sort_ascending=self.pronosticos_sort_asc, rows=[])

        self.tabla_rivales_header = ft.DataTable(bgcolor="#2D2D2D", border=ft.border.all(1, "white10"), border_radius=ft.border_radius.only(top_left=8, top_right=8), vertical_lines=ft.border.BorderSide(1, "white10"), horizontal_lines=ft.border.BorderSide(1, "white10"), heading_row_color="black", heading_row_height=60, data_row_max_height=0, column_spacing=20, columns=columnas_rivales, rows=[])
        self.tabla_rivales = ft.DataTable(bgcolor="#2D2D2D", border=ft.border.all(1, "white10"), border_radius=ft.border_radius.only(bottom_left=8, bottom_right=8), vertical_lines=ft.border.BorderSide(1, "white10"), horizontal_lines=ft.border.BorderSide(1, "white10"), heading_row_height=0, data_row_min_height=20, data_row_max_height=60, column_spacing=20, columns=columnas_rivales, rows=[])

        self.input_admin_nombre = ft.TextField(label="Nombre", width=250, bgcolor="#2D2D2D", color="white", border_color="white24")
        self.btn_guardar_rival = ft.ElevatedButton("Guardar", icon=ft.Icons.SAVE, bgcolor="green", color="white", on_click=self._guardar_rival_admin)

        self.contenedor_admin_rivales = ft.Container(content=ft.Column(controls=[self.input_admin_nombre, ft.Container(height=10), self.btn_guardar_rival], horizontal_alignment=ft.CrossAxisAlignment.CENTER), padding=20)

        # Columnas de Torneos
        columnas_torneos = [
            ft.DataColumn(ft.Container(content=ft.Text("Nombre", color="white", weight=ft.FontWeight.BOLD), width=ANCHO_TORNEOS_NOMBRE, alignment=ft.alignment.center))
        ]
        
        # Tablas de Torneos
        self.tabla_torneos_header = ft.DataTable(bgcolor="#2D2D2D", border=ft.border.all(1, "white10"), border_radius=ft.border_radius.only(top_left=8, top_right=8), vertical_lines=ft.border.BorderSide(1, "white10"), horizontal_lines=ft.border.BorderSide(1, "white10"), heading_row_color="black", heading_row_height=60, data_row_max_height=0, column_spacing=20, columns=columnas_torneos, rows=[])
        
        self.tabla_torneos = ft.DataTable(bgcolor="#2D2D2D", border=ft.border.all(1, "white10"), border_radius=ft.border_radius.only(bottom_left=8, bottom_right=8), vertical_lines=ft.border.BorderSide(1, "white10"), horizontal_lines=ft.border.BorderSide(1, "white10"), heading_row_height=0, data_row_min_height=40, data_row_max_height=60, column_spacing=20, columns=columnas_torneos, rows=[])

        # Formulario de Torneos
        self.input_admin_nombre_torneo = ft.TextField(label="Nombre", width=250, bgcolor="#2D2D2D", color="white", border_color="white24")
        self.btn_guardar_torneo = ft.ElevatedButton("Guardar", icon=ft.Icons.SAVE, bgcolor="green", color="white", on_click=self._guardar_torneo_admin)

        self.contenedor_admin_torneos = ft.Container(content=ft.Column(controls=[self.input_admin_nombre_torneo, ft.Container(height=10), self.btn_guardar_torneo], horizontal_alignment=ft.CrossAxisAlignment.CENTER), padding=20)

        # 0. Obtener datos actuales para mostrar en Configuración
        email_actual_display = "Cargando..."
        try:
            bd = BaseDeDatos()
            email_bd = bd.obtener_email_usuario(self.usuario_actual)
            if email_bd: email_actual_display = email_bd
            else: email_actual_display = "No registrado"
        except:
            email_actual_display = "Error de conexión"

        # Textos normales sin alteraciones
        self.txt_info_user_actual = ft.Text(f"Usuario: {self.usuario_actual}", size=14, color="cyan", weight=ft.FontWeight.BOLD)
        self.txt_info_email_actual = ft.Text(f"Email: {email_actual_display}", size=14, color="cyan", weight=ft.FontWeight.BOLD)
        
        bloque_usuario = ft.Row([ft.Icon("info_outline", color="cyan"), self.txt_info_user_actual], spacing=5, vertical_alignment=ft.CrossAxisAlignment.CENTER)
        bloque_email = ft.Row([ft.Icon("email_outlined", color="cyan"), self.txt_info_email_actual], spacing=5, vertical_alignment=ft.CrossAxisAlignment.CENTER)

        contenedor_info_actual = ft.Container(
            content=ft.Row(
                controls=[
                    # LA SOLUCIÓN: Un Container extra que "empuja" el texto hacia arriba
                    ft.Container(
                        content=ft.Column(
                            controls=[
                                bloque_usuario,
                                bloque_email
                            ],
                            spacing=12  
                        ),
                        padding=ft.padding.only(bottom=15) # Espacio hueco reservado exclusivamente para la barra
                    )
                ],
                scroll=ft.ScrollMode.ALWAYS 
            ),
            bgcolor="#2D2D2D", 
            # Achicamos el padding inferior externo para compensar y que la caja no quede muy alta
            padding=ft.padding.only(top=15, left=15, right=15, bottom=5), 
            border_radius=8, 
            border=ft.border.all(1, "white10")
        )

        # 1. PANEL CONTRASEÑA
        self.input_conf_pass_1 = ft.TextField(label="Nueva contraseña", password=True, can_reveal_password=True, width=280, bgcolor="#2D2D2D", color="white", border_color="white24", label_style=ft.TextStyle(color="white70"), text_size=14)
        self.input_conf_pass_2 = ft.TextField(label="Repetir contraseña", password=True, can_reveal_password=True, width=280, bgcolor="#2D2D2D", color="white", border_color="white24", label_style=ft.TextStyle(color="white70"), text_size=14)
        self.btn_conf_guardar_pass = ft.ElevatedButton("Guardar nueva clave", icon="lock_reset", bgcolor="green", color="white", width=280, height=40, on_click=self._guardar_contrasena_config)
        self.frame_cambio_pass = ft.Container(
            content=ft.Column(controls=[
                ft.Row([ft.Icon("security", color="cyan"), ft.Text("Seguridad", size=16, weight=ft.FontWeight.BOLD, color="white")]),
                ft.Divider(color="white24"),
                ft.Text("Cambiar contraseña", size=12, color="white70"),
                self.input_conf_pass_1, self.input_conf_pass_2, ft.Container(height=10), self.btn_conf_guardar_pass
            ], spacing=10),
            padding=25, border=ft.border.all(1, "white24"), border_radius=10, bgcolor="#1E1E1E", width=350
        )

        # 2. PANEL EMAIL
        self.input_conf_email = ft.TextField(label="Nuevo correo", width=280, bgcolor="#2D2D2D", color="white", border_color="white24", label_style=ft.TextStyle(color="white70"), text_size=14, prefix_icon="email")
        self.btn_conf_guardar_email = ft.ElevatedButton("Enviar código", icon="send", bgcolor="blue", color="white", width=280, height=40, on_click=self._iniciar_cambio_email)
        self.frame_cambio_email = ft.Container(
            content=ft.Column(controls=[
                ft.Row([ft.Icon("alternate_email", color="cyan"), ft.Text("Contacto", size=16, weight=ft.FontWeight.BOLD, color="white")]),
                ft.Divider(color="white24"),
                ft.Text("Cambiar email", size=12, color="white70"),
                self.input_conf_email, ft.Container(height=10), self.btn_conf_guardar_email, ft.Container(height=60)
            ], spacing=10),
            padding=25, border=ft.border.all(1, "white24"), border_radius=10, bgcolor="#1E1E1E", width=350
        )

        # 3. PANEL USUARIO
        self.input_conf_usuario = ft.TextField(label="Nuevo nombre de usuario", width=280, bgcolor="#2D2D2D", color="white", border_color="white24", label_style=ft.TextStyle(color="white70"), text_size=14, prefix_icon="person")
        self.btn_conf_guardar_usuario = ft.ElevatedButton("Guardar cambio", icon="save", bgcolor="orange", color="white", width=280, height=40, on_click=self._guardar_nuevo_usuario)
        self.frame_cambio_usuario = ft.Container(
            content=ft.Column(controls=[
                ft.Row([ft.Icon("account_circle", color="cyan"), ft.Text("Identidad", size=16, weight=ft.FontWeight.BOLD, color="white")]),
                ft.Divider(color="white24"),
                ft.Text("Cambiar nombre de usuario", size=12, color="white70"),
                self.input_conf_usuario, ft.Container(height=10), self.btn_conf_guardar_usuario, ft.Container(height=60)
            ], spacing=10),
            padding=25, border=ft.border.all(1, "white24"), border_radius=10, bgcolor="#1E1E1E", width=350
        )

        # ==============================================================
        # --- CREACIÓN DE PESTAÑAS (DISEÑO FLUIDO CON SCROLL NATIVO) ---
        # ==============================================================
        lista_pestanas = [
            ft.Tab(
                text="Estadísticas", icon="bar_chart",
                content=ft.Container(
                    padding=20, alignment=ft.alignment.top_left,
                    content=ft.Column(
                        scroll=ft.ScrollMode.ALWAYS, expand=True,
                        controls=[
                            self.txt_titulo_ranking, self.loading,
                            ft.Row(scroll=ft.ScrollMode.ALWAYS, controls=[
                                ft.Column(spacing=0, controls=[
                                    self.tabla_estadisticas_header, 
                                    ft.Container(height=300, content=ft.Column(scroll=ft.ScrollMode.ALWAYS, controls=[self.tabla_estadisticas]))
                                ])
                            ]),
                            ft.Container(height=20),
                            ft.Row(wrap=True, alignment=ft.MainAxisAlignment.START, vertical_alignment=ft.CrossAxisAlignment.START, spacing=20, run_spacing=20, controls=[self.contenedor_filtro_torneo, self.contenedor_graficos, self.contenedor_graficos_torta, self.contenedor_graficos_barra, self.contenedor_indices]),
                            ft.Container(height=20),
                            ft.Row(wrap=True, alignment=ft.MainAxisAlignment.START, vertical_alignment=ft.CrossAxisAlignment.START, controls=[
                                ft.Column(controls=[
                                    self.txt_titulo_copas, self.loading_copas, 
                                    ft.Row(scroll=ft.ScrollMode.ALWAYS, controls=[
                                        ft.Column(spacing=0, controls=[
                                            self.tabla_copas_header, 
                                            ft.Container(height=240, content=ft.Column(scroll=ft.ScrollMode.ALWAYS, controls=[self.tabla_copas]))
                                        ])
                                    ])
                                ])
                            ]),
                            ft.Container(height=40) 
                        ]
                    )
                )
            ),
            ft.Tab(
                text="Partidos", icon="sports_soccer", 
                content=ft.Container(
                    padding=20, alignment=ft.alignment.top_left,
                    content=ft.Column(
                        scroll=ft.ScrollMode.ALWAYS, expand=True, horizontal_alignment=ft.CrossAxisAlignment.START,
                        controls=[
                            self.txt_titulo_partidos, self.loading_partidos, 
                            ft.Row(wrap=True, vertical_alignment=ft.CrossAxisAlignment.START, spacing=20, run_spacing=20, controls=[
                                ft.Row(scroll=ft.ScrollMode.ALWAYS, controls=[
                                    ft.Column(spacing=0, controls=[
                                        self.tabla_partidos_header, 
                                        ft.Container(height=350, content=ft.Column(scroll=ft.ScrollMode.ALWAYS, controls=[self.tabla_partidos]))
                                    ])
                                ]), 
                                ft.Container(padding=10, border=ft.border.all(1, "white10"), border_radius=8, bgcolor="#1E1E1E", content=ft.Column(horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=15, controls=[ft.Text("Tu Pronóstico", size=16, weight=ft.FontWeight.BOLD), self.input_pred_cai, self.input_pred_rival, self.btn_pronosticar]))
                            ]),
                            ft.Container(height=10), 
                            ft.Row(controls=[self.btn_todos, self.btn_jugados, self.btn_por_jugar, self.btn_por_torneo, self.btn_sin_pronosticar, self.btn_por_equipo], alignment=ft.MainAxisAlignment.START, vertical_alignment=ft.CrossAxisAlignment.CENTER, wrap=True),
                            ft.Container(height=40)
                        ]
                    )
                )
            ),
            ft.Tab(
                text="Pronósticos", icon="list_alt", 
                content=ft.Container(
                    padding=20, alignment=ft.alignment.top_left,
                    content=ft.Column(
                        scroll=ft.ScrollMode.ALWAYS, expand=True, horizontal_alignment=ft.CrossAxisAlignment.START,
                        controls=[
                            self.txt_titulo_pronosticos, self.loading_pronosticos, 
                            ft.Row(scroll=ft.ScrollMode.ALWAYS, controls=[
                                ft.Column(spacing=0, controls=[
                                    self.tabla_pronosticos_header, 
                                    ft.Container(height=350, content=ft.Column(scroll=ft.ScrollMode.ALWAYS, controls=[self.tabla_pronosticos]))
                                ])
                            ]),
                            ft.Container(height=10), 
                            ft.Row(controls=[self.btn_pron_todos, self.btn_pron_por_jugar, self.btn_pron_jugados, self.btn_pron_por_torneo, self.btn_pron_por_equipo, self.btn_pron_por_usuario], alignment=ft.MainAxisAlignment.START, vertical_alignment=ft.CrossAxisAlignment.CENTER, wrap=True),
                            ft.Container(height=40)
                        ]
                    )
                )
            ),
            ft.Tab(
                text="Configuración", icon=ft.Icons.SETTINGS, 
                content=ft.Container(
                    padding=30, alignment=ft.alignment.top_left,
                    content=ft.Column(
                        scroll=ft.ScrollMode.ALWAYS, expand=True,
                        controls=[
                            ft.Text("Opciones de usuario", size=28, weight=ft.FontWeight.BOLD, color="white"),
                            contenedor_info_actual,
                            ft.Container(height=20),
                            ft.Row(wrap=True, spacing=20, run_spacing=20, controls=[self.frame_cambio_pass, self.frame_cambio_email, self.frame_cambio_usuario]),
                            ft.Container(height=40)
                        ]
                    )
                )
            )
        ]

        if usuario == "Gabriel":
            lista_pestanas.append(
                ft.Tab(
                    text="Administración", icon="admin_panel_settings", 
                    content=ft.Container(
                        padding=20, alignment=ft.alignment.top_left, 
                        content=ft.Column(
                            scroll=ft.ScrollMode.ALWAYS, expand=True,
                            controls=[
                                ft.Text("Panel de Administración", size=20, weight=ft.FontWeight.BOLD, color="white"), 
                                self.loading_admin, 
                                ft.Row(
                                    wrap=True, spacing=20, run_spacing=20, alignment=ft.MainAxisAlignment.START, vertical_alignment=ft.CrossAxisAlignment.START, 
                                    controls=[
                                        # 1. MÓDULO EQUIPOS (Tabla)
                                        ft.Column(spacing=5, controls=[
                                            ft.Text("Equipos", weight="bold", color="white", size=16),
                                            ft.Row(scroll=ft.ScrollMode.ALWAYS, controls=[
                                                ft.Column(spacing=0, controls=[
                                                    self.tabla_rivales_header, 
                                                    ft.Container(height=220, content=ft.Column(scroll=ft.ScrollMode.ALWAYS, controls=[self.tabla_rivales]))
                                                ])
                                            ])
                                        ]),
                                        # 2. MÓDULO EQUIPOS (Formulario)
                                        ft.Column(spacing=5, controls=[
                                            ft.Text(" ", size=16), # Truco para alinear a la misma altura de la cabecera
                                            ft.Card(width=320, content=ft.Container(padding=15, content=ft.Column(controls=[ft.Text("Cambiar nombre", weight="bold", size=16), self.contenedor_admin_rivales])))
                                        ]),
                                        
                                        # 3. MÓDULO TORNEOS (Tabla)
                                        ft.Column(spacing=5, controls=[
                                            ft.Text("Torneos", weight="bold", color="white", size=16),
                                            ft.Row(scroll=ft.ScrollMode.ALWAYS, controls=[
                                                ft.Column(spacing=0, controls=[
                                                    self.tabla_torneos_header, 
                                                    ft.Container(height=220, content=ft.Column(scroll=ft.ScrollMode.ALWAYS, controls=[self.tabla_torneos]))
                                                ])
                                            ])
                                        ]),
                                        # 4. MÓDULO TORNEOS (Formulario)
                                        ft.Column(spacing=5, controls=[
                                            ft.Text(" ", size=16), 
                                            ft.Card(width=320, content=ft.Container(padding=15, content=ft.Column(controls=[ft.Text("Cambiar nombre", weight="bold", size=16), self.contenedor_admin_torneos])))
                                        ])
                                    ]
                                ),
                                ft.Container(height=40)
                            ]
                        )
                    )
                )
            )
            
        self.dlg_cargando_inicio = ft.AlertDialog(modal=True, title=ft.Text("Actualizando información..."), content=ft.Column([ft.ProgressBar(width=300, color="amber", bgcolor="#222222"), ft.Container(height=10), ft.Text("Buscando nuevos partidos y resultados. Esto puede demorar unos segundos...")], height=100, alignment=ft.MainAxisAlignment.CENTER), actions=[])

        mis_pestanas = ft.Tabs(selected_index=0, expand=True, tabs=lista_pestanas)
        self.page.add(mis_pestanas)
        self.page.open(self.dlg_cargando_inicio)
        threading.Thread(target=self._sincronizar_fixture_api, daemon=True).start()

    def _seleccionar_torneo_admin(self, id_torneo):
        self.torneo_seleccionado_id = id_torneo
        encontrado = False
        for row in self.tabla_torneos.rows:
            if row.data == id_torneo:
                row.color = "#8B0000"
                try:
                    nombre_ui = row.cells[0].content.content.value
                    self.input_admin_nombre_torneo.value = nombre_ui
                    self.input_admin_nombre_torneo.update()
                except Exception as e:
                    self._mostrar_mensaje_admin("Error", f"No se pudo cargar el nombre del torneo seleccionado: {str(e)}", "error")
                encontrado = True
            else:
                row.color = None
        if encontrado:
            self.tabla_torneos.update()

    def _guardar_torneo_admin(self, e):
        if not self.torneo_seleccionado_id:
            GestorMensajes.mostrar(self.page, "Error", "Seleccione un torneo de la tabla.", "error")
            return
            
        nombre = self.input_admin_nombre_torneo.value.strip()
        
        if not nombre:
            GestorMensajes.mostrar(self.page, "Error", "El nombre es obligatorio.", "error")
            return

        def _guardar():
            self.loading_partidos.visible = True
            self.loading_pronosticos.visible = True
            self.loading_admin.visible = True
            self.page.update()
            try:
                bd = BaseDeDatos()
                bd.actualizar_campeonato(self.torneo_seleccionado_id, nombre)
                
                GestorMensajes.mostrar(self.page, "Éxito", "Torneo actualizado.", "exito")
                self.torneo_seleccionado_id = None
                self.input_admin_nombre_torneo.value = ""
                
                self._recargar_datos(actualizar_partidos=True, actualizar_pronosticos=True, actualizar_ranking=False, actualizar_admin=True, actualizar_copas=False)
            except Exception as ex:
                GestorMensajes.mostrar(self.page, "Error al guardar", str(ex), "error")
                self.loading_partidos.visible = False
                self.loading_pronosticos.visible = False
                self.loading_admin.visible = False
                self.page.update()

        threading.Thread(target=_guardar, daemon=True).start()

    def _guardar_nuevo_usuario(self, e):
        """Cambia el nombre de usuario directamente verificando restricciones."""
        nuevo_user = self.input_conf_usuario.value.strip() if self.input_conf_usuario.value else ""
        
        # --- VALIDACIONES FRONTEND ---
        if not nuevo_user:
            GestorMensajes.mostrar(self.page, "Atención", "El nombre no puede estar vacío ni formado solo por espacios.", "error")
            return
            
        if len(nuevo_user) < 3:
            GestorMensajes.mostrar(self.page, "Error", "El nombre debe tener al menos 3 caracteres.", "error")
            return

        if nuevo_user == self.usuario_actual:
            GestorMensajes.mostrar(self.page, "Atención", "El nombre es igual al actual.", "info")
            return

        def _tarea():
            self.btn_conf_guardar_usuario.disabled = True
            self.btn_conf_guardar_usuario.text = "Verificando..." 
            self.btn_conf_guardar_usuario.update()
            
            try:
                bd = BaseDeDatos()
                bd.verificar_username_libre(nuevo_user)
                id_user = bd.obtener_id_por_username(self.usuario_actual)
                
                if id_user:
                    bd.actualizar_username(id_user, nuevo_user)
                    
                    old_name = self.usuario_actual
                    self.usuario_actual = nuevo_user
                    
                    self.page.appbar.title.value = f"Bienvenido, {self.usuario_actual}"
                    self.txt_info_user_actual.value = f"Usuario: {self.usuario_actual}"
                    self.page.appbar.update()
                    self.txt_info_user_actual.update()
                    
                    GestorMensajes.mostrar(self.page, "Éxito", f"Nombre cambiado de {old_name} a {self.usuario_actual}", "exito")
                    self.input_conf_usuario.value = ""
                    self.input_conf_usuario.update()
                else:
                    raise Exception("No se pudo identificar al usuario actual.")
                    
            except Exception as ex:
                GestorMensajes.mostrar(self.page, "Error", str(ex), "error")
                self._enviar_alerta_correo_admins("Error al cambiar nombre de usuario", f"Error al cambiar nombre de usuario", tipo=str(ex), nombre_función="SistemaIndependiente._guardar_nuevo_usuario._tarea")
            
            finally:
                self.btn_conf_guardar_usuario.disabled = False
                self.btn_conf_guardar_usuario.text = "Guardar cambio"
                self.btn_conf_guardar_usuario.update()

        threading.Thread(target=_tarea, daemon=True).start()

    def _cambiar_filtro_tiempo_partidos(self, nuevo_tiempo):
        """
        Gestiona el grupo de filtros de Tiempo para PARTIDOS (Todos, Futuros, Jugados).
        Estos son EXCLUYENTES entre sí y modifican self.filtro_temporal.
        """
        self.filtro_temporal = nuevo_tiempo
        
        # Actualizamos visualmente los botones de Partidos
        self._actualizar_botones_partidos_visual()
        
        # Actualizamos título y recargamos la tabla Partidos
        self._actualizar_titulo_partidos()
        self._recargar_datos(actualizar_partidos=True, actualizar_copas=False)

    def _cambiar_filtro_tiempo_pronosticos(self, nuevo_filtro):
        """
        Gestiona el grupo de filtros de Tiempo para PRONÓSTICOS.
        Modifica self.filtro_pron_tiempo.
        """
        self.filtro_pron_tiempo = nuevo_filtro
        
        # --- SOLUCIÓN AL BUG DE FLET ---
        # En lugar de usar 'None' (que causa el colapso de la tabla),
        # forzamos la flecha visual a la columna 1 ("Fecha y hora").
        self.pronosticos_sort_col_index = 1
        
        # Si es "Por jugar", la flecha indica Ascendente. Caso contrario, Descendente.
        if nuevo_filtro == 'futuros':
            self.pronosticos_sort_asc = True
        else:
            self.pronosticos_sort_asc = False
        
        # Actualizamos visualmente los botones de Pronósticos
        self._actualizar_botones_pronosticos_visual()
        
        # Actualizamos título y recargamos la tabla Pronósticos
        self._actualizar_titulo_pronosticos()
        self._recargar_datos(actualizar_pronosticos=True)

    def _abrir_modal_opt_pes(self, e):
        """Abre la ventana modal con la tabla de Optimismo/Pesimismo (con flechas horizontales)."""
        
        titulo = "Índice de Optimismo/Pesimismo histórico"
        if self.filtro_ranking_nombre: 
             titulo = f"Optimismo/Pesimismo ({self.filtro_ranking_nombre})"
        elif self.filtro_ranking_anio:
             titulo = f"Optimismo/Pesimismo ({self.filtro_ranking_anio})"
             
        self.loading_modal = ft.ProgressBar(width=200, color="amber", bgcolor="#222222")
        
        # Ancho dinámico para que no se salga del celular
        ancho_pantalla = self.page.width if self.page.width else 600
        ancho_modal = min(650, ancho_pantalla - 20)
        
        columna_content = ft.Column(
            controls=[
                ft.Text(titulo, size=18, weight="bold", color="white"),
                ft.Container(height=10),
                self.loading_modal,
                ft.Container(height=50)
            ],
            height=150,
            width=ancho_modal, 
            scroll=ft.ScrollMode.ALWAYS 
        )
        
        self.dlg_opt_pes = ft.AlertDialog(content=columna_content, modal=True)
        self.page.open(self.dlg_opt_pes)

        def _cargar():
            bd = BaseDeDatos()
            datos = bd.obtener_indice_optimismo_pesimismo(self.filtro_ranking_edicion_id, self.filtro_ranking_anio)
            
            filas = []
            for i, row in enumerate(datos, start=1):
                user = row[0]
                val = row[1]
                
                if val is None:
                    txt_val = "-"
                    clasificacion = "-"
                    color_val = "white"
                else:
                    indice = float(val)
                    txt_val = f"{indice:+.2f}".replace('.', ',')
                    
                    if indice >= 1.5:
                        clasificacion = "🔴 Muy optimista"
                        color_val = "red"
                    elif 0.5 <= indice < 1.5: 
                        clasificacion = "🙂 Optimista"
                        color_val = "orange"
                    elif -0.5 < indice < 0.5: 
                        clasificacion = "⚖️ Neutral"
                        color_val = "cyan"
                    elif -1.5 < indice <= -0.5: 
                        clasificacion = "😐 Pesimista"
                        color_val = "indigo"
                    else: 
                        clasificacion = "🔵 Muy pesimista"
                        color_val = "blue"

                filas.append(ft.DataRow(cells=[
                    ft.DataCell(ft.Container(content=ft.Text(f"{i}º", weight="bold", color="white"), width=50, alignment=ft.alignment.center)),
                    ft.DataCell(ft.Container(content=ft.Text(user, weight="bold", color="white"), width=ANCHO_COLUMNA_USUARIO, alignment=ft.alignment.center_left)),
                    ft.DataCell(ft.Container(content=ft.Text(txt_val, weight="bold", color=color_val), width=150, alignment=ft.alignment.center)),
                    ft.DataCell(ft.Container(content=ft.Text(clasificacion, weight="bold", color="white"), width=150, alignment=ft.alignment.center_left)),
                ]))
            
            tabla = ft.DataTable(
                columns=[
                    ft.DataColumn(ft.Container(content=ft.Text("Puesto", weight="bold", color="white"), width=50, alignment=ft.alignment.center)),
                    ft.DataColumn(ft.Container(content=ft.Text("Usuario", weight="bold", color="white"), width=ANCHO_COLUMNA_USUARIO, alignment=ft.alignment.center_left)),
                    ft.DataColumn(ft.Container(content=ft.Text("Optimismo/\nPesimismo", text_align="center", weight="bold", color="white"), width=150, alignment=ft.alignment.center), numeric=True),
                    ft.DataColumn(ft.Container(content=ft.Text("Clasificación", weight="bold", color="white"), width=150, alignment=ft.alignment.center_left)),
                ],
                rows=filas,
                heading_row_color="black",
                border=ft.border.all(1, "white10"),
                column_spacing=10,
                heading_row_height=60,
                data_row_max_height=50,
                data_row_min_height=50
            )

            # Altura matemática perfecta
            altura_tabla = 60 + (len(filas) * 50) + 30
            altura_contenedor = min(270, altura_tabla)

            contenedor_tabla_nativa = ft.Row(
                scroll=ft.ScrollMode.ALWAYS,
                controls=[
                    ft.Container(
                        height=altura_contenedor,
                        content=ft.Column(
                            controls=[tabla],
                            scroll=ft.ScrollMode.ALWAYS
                        )
                    )
                ]
            )
            
            # Ajuste dinámico del modal sin dejar espacios vacíos
            alto_pantalla = self.page.height if self.page.height else 600
            columna_content.height = min(alto_pantalla - 50, altura_contenedor + 130) 
            
            columna_content.controls = [
                ft.Text(titulo, size=18, weight="bold", color="white"),
                ft.Container(height=10),
                contenedor_tabla_nativa,
                ft.Container(height=10),
                ft.Row([ft.ElevatedButton("Cerrar", on_click=lambda e: self._limpiar_memoria_dialogo(self.dlg_opt_pes))], alignment=ft.MainAxisAlignment.END)
            ]
            self.dlg_opt_pes.update()
            
        threading.Thread(target=_cargar, daemon=True).start()

    def _actualizar_botones_partidos_visual(self):
        """Actualiza colores. Ahora soporta combinaciones."""
        # Grupo Tiempo (Excluyentes)
        f_temp = self.filtro_temporal
        self.btn_todos.bgcolor = "blue" if f_temp == 'todos' else "#333333"
        self.btn_jugados.bgcolor = "blue" if f_temp == 'jugados' else "#333333"
        self.btn_por_jugar.bgcolor = "blue" if f_temp == 'futuros' else "#333333"
        
        # Grupo Filtros (Independientes)
        self.btn_por_torneo.bgcolor = "blue" if self.filtro_edicion_id is not None else "#333333"
        self.btn_sin_pronosticar.bgcolor = "blue" if self.filtro_sin_pronosticar else "#333333"
        self.btn_por_equipo.bgcolor = "blue" if self.filtro_rival_id is not None else "#333333"
        
        # Update individual
        self.btn_todos.update()
        self.btn_jugados.update()
        self.btn_por_jugar.update()
        self.btn_por_torneo.update()
        self.btn_sin_pronosticar.update()
        self.btn_por_equipo.update()

    def _procesar_partido_fotmob(self, match):
        """
        Extrae datos limpios de un objeto partido de FotMob con validaciones.
        CORREGIDO: Convierte UTC a Hora Argentina (UTC-3).
        """
        try:
            # Validación inicial de tipo
            if not isinstance(match, dict): return None

            # 1. FECHA Y STATUS
            status = match.get("status", {})
            if not isinstance(status, dict): return None 
            
            fecha_str = status.get("utcTime")
            if not fecha_str: return None
            
            # Limpieza fecha ISO
            fecha_str = fecha_str.replace("Z", "+00:00")
            try:
                # Importamos timedelta aquí para realizar la resta de horas
                from datetime import timedelta

                # 1. Convertimos string a datetime
                fecha_utc = datetime.fromisoformat(fecha_str)
                
                # 2. Restamos 3 horas para ajustar a Argentina y quitamos la zona horaria
                fecha_dt = fecha_utc.replace(tzinfo=None) - timedelta(hours=3)
                
            except ValueError:
                return None

            # --- DETECCIÓN DE HORARIO NO DEFINIDO (TEXTUAL) ---
            status_short = str(status.get("short", "")).lower()
            status_long = str(status.get("long", "")).lower()
            reason_short = str(status.get("reason", {}).get("short", "")).lower()
            reason_long = str(status.get("reason", {}).get("long", "")).lower()
            
            senales_tbd = [
                "tbd", "tbc", "to be defined", "time to be defined", 
                "postponed", "time tbd", "time tbc", "pending", 
                "awarded"
            ]
            
            is_time_defined = match.get("isTimeDefined", True)

            es_horario_tbd = (
                not is_time_defined or 
                status_short in senales_tbd or 
                reason_short in senales_tbd or
                any(senal in status_long for senal in senales_tbd) or
                any(senal in reason_long for senal in senales_tbd)
            )

            if es_horario_tbd:
                # Si es explícitamente TBD, forzamos las 00:00:00
                fecha_dt = fecha_dt.replace(hour=0, minute=0, second=0, microsecond=0)
            
            # 2. EQUIPOS
            home = match.get("home", {})
            away = match.get("away", {})
            
            # Asegurar IDs numéricos
            try:
                id_home = int(home.get("id") or 0)
            except: id_home = 0
            
            # Si Independiente no juega, ignorar
            if id_home != ID_INDEPENDIENTE and int(away.get("id") or 0) != ID_INDEPENDIENTE:
                return None

            score_str = status.get("scoreStr", "")
            finished = status.get("finished", False)
            goles_cai = None
            goles_rival = None
            
            # --- NUEVA EXTRACCIÓN DE ID DE RIVAL Y CONDICIÓN ---
            id_rival_fotmob = 0
            
            # Detección de estadio neutral (Buscamos la bandera en posibles nodos del JSON)
            es_neutral = match.get("neutralGround", False) or match.get("status", {}).get("neutralGround", False) or match.get("general", {}).get("neutralGround", False)

            if es_neutral:
                condicion = 0
            elif id_home == ID_INDEPENDIENTE:
                condicion = 1
            else:
                condicion = -1

            if id_home == ID_INDEPENDIENTE:
                nombre_rival = away.get("name", "Rival Desconocido")
                id_rival_fotmob = int(away.get("id") or 0) 
                if finished and score_str and " - " in score_str:
                    try:
                        partes = score_str.split(" - ")
                        goles_cai = int(partes[0])
                        goles_rival = int(partes[1])
                    except: pass
            else:
                nombre_rival = home.get("name", "Rival Desconocido")
                id_rival_fotmob = int(home.get("id") or 0) 
                if finished and score_str and " - " in score_str:
                    try:
                        partes = score_str.split(" - ")
                        goles_cai = int(partes[1]) 
                        goles_rival = int(partes[0])
                    except: pass

            # 3. TORNEO
            tourney_dict = match.get("tournament", {})
            league_dict = match.get("league", {})
            
            nombre_torneo = tourney_dict.get("name") or league_dict.get("name", "Liga Profesional")
            id_torneo = tourney_dict.get("leagueId") or league_dict.get("id", 0)
                
            anio_temporada = str(fecha_dt.year)

            match_id = match.get("id")

            # Preparamos el diccionario de retorno
            datos_finales = {
                'fotmob_id': match_id,
                'rival_id': id_rival_fotmob,
                'rival': nombre_rival,
                'torneo_id': int(id_torneo),
                'torneo': nombre_torneo,
                'anio': anio_temporada,
                'fecha': fecha_dt,
                'goles_cai': goles_cai,
                'goles_rival': goles_rival,
                'condicion': condicion
            }
            return datos_finales

        except Exception as e:
            print(f"Error procesando item individual: {e}")
            self._mostrar_mensaje_admin("Error procesando item individual", f"{e}", "error", nombre_función="SistemaIndependiente._procesar_partido_fotmob")
            return None

    def _ordenar_tabla_pronosticos(self, e):
        """Maneja el evento de ordenar columnas en la tabla de pronósticos"""
        # Si clica la misma columna, invierte el orden. Si es nueva, resetea a Ascendente.
        if self.pronosticos_sort_col_index == e.column_index:
            self.pronosticos_sort_asc = not self.pronosticos_sort_asc
        else:
            self.pronosticos_sort_col_index = e.column_index
            self.pronosticos_sort_asc = True
            
        # 1. Actualizamos la tabla de ENCABEZADO (Header) para que muestre la flecha
        self.tabla_pronosticos_header.sort_column_index = self.pronosticos_sort_col_index
        self.tabla_pronosticos_header.sort_ascending = self.pronosticos_sort_asc
        
        # 2. Reseteamos la tabla de DATOS (Cuerpo) para que NO muestre flecha
        self.tabla_pronosticos.sort_column_index = None
        self.tabla_pronosticos.sort_ascending = None
        
        # 3. Renderizamos cambios visuales en ambas tablas
        self.tabla_pronosticos_header.update()
        self.tabla_pronosticos.update()
        
        # 4. Recargamos datos aplicando el orden lógico
        self._recargar_datos(actualizar_pronosticos=True)

    def _abrir_selector_grafico_torta_generico(self, titulo_dialogo, funcion_generar):
        """Base estructural compartida para los 3 gráficos de torta."""
        loading_content = ft.Column(
            controls=[
                ft.Text("Cargando filtros...", size=16, weight="bold", color="white"),
                ft.Container(height=10),
                ft.ProgressBar(width=200, color="amber", bgcolor="#222222"),
                ft.Text("Obteniendo torneos y usuarios...", size=12, color="white70")
            ],
            height=100, width=300, alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER
        )
        self.dlg_carga_filtros = ft.AlertDialog(content=loading_content, modal=True)
        self.page.open(self.dlg_carga_filtros)

        def _cargar_datos_torta():
            time.sleep(0.5)
            self.txt_titulo_torneo_torta = ft.Text("1. Torneo (Opcional)", weight="bold", size=12, color="white")
            self.txt_titulo_anio_torta = ft.Text("2. Año (Opcional)", weight="bold", size=12, color="white")
            
            self.lv_torneos_torta = ft.ListView(expand=True, spacing=5, height=ALTURA_LISTAS_DIALOGO)
            self.lv_anios_torta = ft.ListView(expand=True, spacing=5, height=ALTURA_LISTAS_DIALOGO)
            self.lv_usuarios_torta = ft.ListView(expand=True, spacing=5, height=ALTURA_LISTAS_DIALOGO)
            
            self.temp_camp_torta = None
            self.temp_anio_torta = None
            self.temp_usuario_torta = None 
            
            # --- Aquí se inyecta la función generadora específica ---
            self.btn_generar_grafico_torta = ft.ElevatedButton(
                "Generar Gráfico", 
                icon=ft.Icons.PIE_CHART, 
                disabled=True, 
                on_click=funcion_generar 
            )

            bd = BaseDeDatos()
            ediciones = bd.obtener_ediciones()
            self.cache_ediciones_modal = ediciones
            nombres_unicos = sorted(list(set(e[1] for e in ediciones)))
            
            controles_tor = []
            for nombre in nombres_unicos:
                controles_tor.append(ft.ListTile(title=ft.Text(nombre, size=14), data=nombre, on_click=self._sel_torneo_torta_modal, bgcolor="#2D2D2D"))
            self.lv_torneos_torta.controls = controles_tor
            self.lv_anios_torta.controls = []

            usuarios = bd.obtener_usuarios()
            controles_usu = []
            for usu in usuarios:
                controles_usu.append(ft.ListTile(title=ft.Text(usu, size=14), data=usu, on_click=self._sel_usuario_torta_modal, bgcolor="#2D2D2D"))
            self.lv_usuarios_torta.controls = controles_usu
            
            col_tor = ft.Container(width=200, content=ft.Column(controls=[self.txt_titulo_torneo_torta, ft.Container(content=self.lv_torneos_torta, border=ft.border.all(1, "white24"), border_radius=5)]))
            col_anio = ft.Container(width=200, content=ft.Column(controls=[self.txt_titulo_anio_torta, ft.Container(content=self.lv_anios_torta, border=ft.border.all(1, "white24"), border_radius=5)]))
            col_usu = ft.Container(width=200, content=ft.Column(controls=[ft.Text("3. Usuario (Obligatorio)", weight="bold", size=12, color="cyan"), ft.Container(content=self.lv_usuarios_torta, border=ft.border.all(1, "white24"), border_radius=5)]))

            es_celular = self.page.width < 750 if self.page.width else False
            
            flecha_arriba = ft.Container(content=ft.Icon(ft.Icons.KEYBOARD_DOUBLE_ARROW_UP, color="amber", size=35), top=0, right=10, visible=False, ignore_interactions=True, data=False)
            flecha_abajo = ft.Container(content=ft.Icon(ft.Icons.KEYBOARD_DOUBLE_ARROW_DOWN, color="amber", size=35), bottom=0, right=10, visible=es_celular, ignore_interactions=True, data=False)

            def _on_scroll_modal(e):
                try:
                    pos, max_pos = float(e.pixels), float(e.max_scroll_extent)
                    if max_pos <= 0:
                        if not flecha_arriba.data or not flecha_abajo.data:
                            flecha_arriba.visible, flecha_arriba.data = False, True
                            flecha_abajo.visible, flecha_abajo.data = False, True
                            flecha_arriba.update()
                            flecha_abajo.update()
                        return

                    if not flecha_arriba.data:
                        if pos <= 10 and flecha_arriba.visible:
                            flecha_arriba.visible, flecha_arriba.data = False, True
                            flecha_arriba.update()
                        elif pos > 10 and not flecha_arriba.visible:
                            flecha_arriba.visible = True
                            flecha_arriba.update()
                            
                    if not flecha_abajo.data:
                        if pos >= (max_pos - 10) and flecha_abajo.visible:
                            flecha_abajo.visible, flecha_abajo.data = False, True
                            flecha_abajo.update()
                        elif pos < (max_pos - 10) and not flecha_abajo.visible:
                            flecha_abajo.visible = True
                            flecha_abajo.update()
                except: pass

            contenido = ft.Container(
                width=750, height=350, 
                content=ft.Column(
                    scroll=ft.ScrollMode.ALWAYS,
                    controls=[
                        ft.Row(controls=[col_tor, col_anio, col_usu], wrap=True, alignment=ft.MainAxisAlignment.CENTER, spacing=20, run_spacing=20),
                        ft.Container(height=40) 
                    ]
                )
            )

            self.dlg_grafico_torta = ft.AlertDialog(
                modal=True, 
                title=ft.Text(titulo_dialogo),  # --- Inyectado ---
                content=contenido, 
                actions=[
                    ft.TextButton("Cancelar", on_click=lambda e: self._limpiar_memoria_dialogo(self.dlg_grafico_torta)), 
                    self.btn_generar_grafico_torta
                ]
            )
            
            self._limpiar_memoria_dialogo(self.dlg_carga_filtros)
            self.page.open(self.dlg_grafico_torta)

        threading.Thread(target=_cargar_datos_torta, daemon=True).start()

    def _generar_grafico_linea_puntos(self, e):
        """Genera y muestra el gráfico de líneas de puntos acumulados (VERSIÓN RESPONSIVA)."""
        usuarios_sel = self.temp_usuarios_seleccionados
        edicion_id = self.filtro_ranking_edicion_id
        
        # 1. CERRAR EL SELECTOR INMEDIATAMENTE
        self._limpiar_memoria_dialogo(self.dlg_gen_usuarios)

        # 2. ABRIR UN NUEVO DIÁLOGO EXCLUSIVO PARA LA CARGA
        loading_content = ft.Column(
            controls=[
                ft.Text("Calculando puntos...", size=16, weight="bold", color="white"),
                ft.Container(height=10),
                ft.ProgressBar(width=200, color="red", bgcolor="#222222")
            ],
            height=100, width=300, alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER
        )
        self.dlg_carga_grafico = ft.AlertDialog(content=loading_content, modal=True)
        self.page.open(self.dlg_carga_grafico)

        def _tarea():
            bd = BaseDeDatos()
            cant_partidos, _, historial = bd.obtener_datos_evolucion_puntos(edicion_id, usuarios_sel)
            
            # 3. CERRAR EL DIÁLOGO DE CARGA
            self._limpiar_memoria_dialogo(self.dlg_carga_grafico)

            if cant_partidos == 0:
                GestorMensajes.mostrar(self.page, "Info", "No hay partidos jugados.", "info")
                return

            max_puntos_alcanzado = 0
            for puntos in historial.values():
                if puntos: max_puntos_alcanzado = max(max_puntos_alcanzado, max(puntos))
            
            altura_eje = max_puntos_alcanzado + 2 
            colores = [ft.Colors.CYAN, ft.Colors.AMBER, ft.Colors.PINK, ft.Colors.GREEN]
            data_series = []
            
            for i, user in enumerate(usuarios_sel):
                puntos_acum = historial.get(user, [])
                puntos_grafico = [ft.LineChartDataPoint(0, 0, tooltip=f"{user}: Inicio")]
                
                for idx_partido, pts in enumerate(puntos_acum):
                    puntos_grafico.append(ft.LineChartDataPoint(x=idx_partido + 1, y=pts, tooltip=f"{user}: {pts} pts"))
                
                data_series.append(ft.LineChartData(data_points=puntos_grafico, stroke_width=4, color=colores[i % len(colores)], curved=False, stroke_cap_round=True, point=True))

            labels_y = [ft.ChartAxisLabel(value=0, label=ft.Text("0", size=10, weight="bold"))]
            intervalo_y = 5 if altura_eje > 20 else 3
            for p in range(intervalo_y, int(altura_eje), intervalo_y):
                labels_y.append(ft.ChartAxisLabel(value=p, label=ft.Text(str(p), size=12)))

            ancho = self.page.width - 50 if self.page.width else 900
            alto = self.page.height - 50 if self.page.height else 600
            es_pc = (self.page.width >= 750) if self.page.width else True
            
            alto_grafico = 450 if es_pc else 525          
            alto_requerido_base = 580 if es_pc else 600
            ancho_punto = 60 if es_pc else 90
            ancho_grafico_dinamico = max((ancho - 100), cant_partidos * ancho_punto)
            necesita_scroll_h = (cant_partidos * ancho_punto) > (ancho - 100)

            chart = ft.LineChart(
                data_series=data_series, border=ft.border.all(1, ft.Colors.WHITE10),
                left_axis=ft.ChartAxis(labels=labels_y, labels_size=40, title=ft.Text("Puntos Acumulados", size=14, italic=True), title_size=30),
                bottom_axis=ft.ChartAxis(labels_interval=1, title=ft.Text("Partido Nro", size=14, italic=True), labels_size=40),
                tooltip_bgcolor=ft.Colors.with_opacity(0.9, "#1E1E1E"), min_y=0, max_y=altura_eje + 5, min_x=-0.5, max_x=cant_partidos + 0.5,
                horizontal_grid_lines=ft.ChartGridLines(interval=intervalo_y, color=ft.Colors.WHITE10, width=1), vertical_grid_lines=ft.ChartGridLines(interval=1, color=ft.Colors.WHITE10, width=1),
            )
            
            items_leyenda = [ft.Row([ft.Container(width=15, height=15, bgcolor=colores[i % len(colores)], border_radius=3), ft.Text(user, weight="bold", size=14, color="white")], spacing=5) for i, user in enumerate(usuarios_sel)]

            espacio_util_interno = alto - 40
            alto_requerido = alto_requerido_base + (len(usuarios_sel) * 25)
            necesita_scroll_v = alto_requerido > espacio_util_interno
            
            flecha_arriba = ft.Container(content=ft.Icon(ft.Icons.KEYBOARD_DOUBLE_ARROW_UP, color="amber", size=35), top=60, right=10, visible=False, ignore_interactions=True, data=False)
            flecha_abajo = ft.Container(content=ft.Icon(ft.Icons.KEYBOARD_DOUBLE_ARROW_DOWN, color="amber", size=35), bottom=10, right=10, visible=necesita_scroll_v, ignore_interactions=True, data=False)

            def _on_scroll_vertical(e):
                try:
                    pos = float(e.pixels); max_pos = float(e.max_scroll_extent)
                    if not flecha_arriba.data:
                        if pos <= 10 and flecha_arriba.visible: flecha_arriba.visible = False; flecha_arriba.data = True; flecha_arriba.update()
                        elif pos > 10 and not flecha_arriba.visible: flecha_arriba.visible = True; flecha_arriba.update()
                    if not flecha_abajo.data:
                        if pos >= (max_pos - 10) and flecha_abajo.visible: flecha_abajo.visible = False; flecha_abajo.data = True; flecha_abajo.update()
                        elif pos < (max_pos - 10) and not flecha_abajo.visible: flecha_abajo.visible = True; flecha_abajo.update()
                except: pass

            flecha_izq = ft.Container(content=ft.Icon(ft.Icons.KEYBOARD_DOUBLE_ARROW_LEFT, color="amber", size=35), left=0, top=150, visible=False, ignore_interactions=True, data=False)
            flecha_der = ft.Container(content=ft.Icon(ft.Icons.KEYBOARD_DOUBLE_ARROW_RIGHT, color="amber", size=35), right=0, top=150, visible=necesita_scroll_h, ignore_interactions=True, data=False)

            def _on_scroll_horizontal(e):
                try:
                    pos = float(e.pixels); max_pos = float(e.max_scroll_extent)
                    if not flecha_izq.data:
                        if pos <= 10 and flecha_izq.visible: flecha_izq.visible = False; flecha_izq.data = True; flecha_izq.update()
                        elif pos > 10 and not flecha_izq.visible: flecha_izq.visible = True; flecha_izq.update()
                    if not flecha_der.data:
                        if pos >= (max_pos - 10) and flecha_der.visible: flecha_der.visible = False; flecha_der.data = True; flecha_der.update()
                        elif pos < (max_pos - 10) and not flecha_der.visible: flecha_der.visible = True; flecha_der.update()
                except: pass

            fila_grafico = ft.Row(
                controls=[ft.Container(content=chart, width=ancho_grafico_dinamico, height=alto_grafico, padding=ft.padding.only(top=40, right=60, bottom=20, left=50))],
                scroll=ft.ScrollMode.ALWAYS
            )

            columna_principal = ft.Column([
                ft.Row(
                    controls=[
                        ft.Container(content=ft.Text(f"Evolución Puntos: {self.filtro_ranking_nombre}", size=20, weight="bold"), expand=True),
                        ft.IconButton(icon=ft.Icons.CLOSE, on_click=lambda e: self._limpiar_memoria_dialogo(self.dlg_grafico_lp_full)) 
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                ),
                ft.Text("Historial partido a partido...", size=12, color="white54"),
                ft.Divider(), fila_grafico, ft.Container(height=20), ft.Divider(), ft.Row(items_leyenda, alignment="center", wrap=True), ft.Container(height=30)
            ], scroll=ft.ScrollMode.ALWAYS, expand=True)
            
            contenido_final = ft.Container(width=ancho, height=alto, padding=20, bgcolor="#1E1E1E", border_radius=10, content=columna_principal)
            
            if hasattr(self, 'dlg_grafico_full') and self.dlg_grafico_full:
                    self.dlg_grafico_full = None

            self.dlg_grafico_lp_full = ft.AlertDialog(content=contenido_final, modal=True, content_padding=0, bgcolor=ft.Colors.TRANSPARENT)
            self.page.open(self.dlg_grafico_lp_full)

        threading.Thread(target=_tarea, daemon=True).start()

    def _generar_grafico_barras(self, e):
        """Genera y muestra el gráfico de barras por puntos (Soporta historial global o por torneo)."""
        
        loading_content = ft.Column(
            controls=[
                ft.Text("Calculando barras...", size=16, weight="bold", color="white"),
                ft.Container(height=10),
                ft.ProgressBar(width=200, color="red", bgcolor="#222222"),
            ],
            height=100, width=300, alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER
        )
        self.dlg_carga_grafico = ft.AlertDialog(content=loading_content, modal=True)
        self.page.open(self.dlg_carga_grafico)

        # 1. Obtenemos el usuario del nuevo modal genérico y los filtros globales
        usuario_sel = self.temp_usuarios_seleccionados[0]
        edicion_id = self.filtro_ranking_edicion_id

        def _tarea():
            bd = BaseDeDatos()
            
            try:
                # Obtenemos los puntos. Tu backend debe soportar edicion_id=None para traer toda la historia
                puntos_lista = bd.obtener_historial_puntos_usuario(edicion_id, usuario_sel)
                
                # --- SOLUCIÓN: MANEJAR HISTORIAL GLOBAL VS TORNEO ESPECÍFICO ---
                if edicion_id is not None:
                    # Si hay torneo, usamos la función de evolución para recortar partidos futuros
                    cant_partidos_reales, _, _ = bd.obtener_datos_evolucion_puntos(edicion_id, [usuario_sel])
                    if cant_partidos_reales > 0:
                        puntos_lista = puntos_lista[:cant_partidos_reales] 
                    elif cant_partidos_reales == 0:
                        puntos_lista = [] 
                else:
                    # Si es toda la historia, filtramos valores nulos (partidos por jugar que no tienen puntos aún)
                    if puntos_lista:
                        puntos_lista = [p for p in puntos_lista if p is not None]

            except Exception as ex:
                self._limpiar_memoria_dialogo(self.dlg_carga_grafico)
                GestorMensajes.mostrar(self.page, "Error de BD", f"Asegúrate de que obtener_historial_puntos_usuario soporte edicion_id=None. Error: {ex}", "error")
                self._enviar_alerta_correo_admins("Error al generar gráfico de barras", f"Error al generar gráfico de barras", tipo=str(ex), nombre_función="SistemaIndependiente._generar_grafico_barras._tarea")
                return

            if not puntos_lista:
                self._limpiar_memoria_dialogo(self.dlg_carga_grafico)
                GestorMensajes.mostrar(self.page, "Info", "No hay partidos finalizados para este usuario en este filtro.", "info")
                return

            cant_partidos = len(puntos_lista)

            # 1. Crear datos para el gráfico de barras
            bar_groups = []
            for i, puntos in enumerate(puntos_lista):
                n_partido = i + 1
                
                if puntos == 9: color_barra = "#0B8616"
                elif puntos == 6: color_barra = "#FFFF00"
                elif puntos == 3: color_barra = "#FF5100"
                else: color_barra = "#FF0000"
                
                # Truco: Le damos una "mini altura" al 0 para que el dedo/ratón pueda detectarlo
                altura_barra = 0.15 if puntos == 0 else puntos
                
                bar_groups.append(
                    ft.BarChartGroup(
                        x=n_partido,
                        bar_rods=[
                            ft.BarChartRod(
                                from_y=0,
                                to_y=altura_barra,
                                width=20,
                                color=color_barra,
                                tooltip=f"Partido {n_partido}: {puntos} pts",
                                border_radius=3
                            )
                        ]
                    )
                )

            # --- PANTALLA COMPLETA ---
            ancho = self.page.width - 50 if self.page.width else 900
            alto = self.page.height - 50 if self.page.height else 600

            # --- EL SECRETO DEL ESPACIADO ---
            # Si hay muchos partidos (ej: historial de 100 partidos), reducimos el grosor de la separación 
            # para que el gráfico no sea excesivamente kilométrico de deslizar.
            espacio_por_barra = 50 if cant_partidos < 40 else 30
            ancho_grafico_dinamico = max((ancho - 100), cant_partidos * espacio_por_barra)
            necesita_scroll_h = (cant_partidos * espacio_por_barra) > (ancho - 100)

            # 2. Configurar Gráfico
            chart = ft.BarChart(
                bar_groups=bar_groups,
                border=ft.border.all(1, ft.Colors.WHITE10),
                left_axis=ft.ChartAxis(
                    labels_size=40,
                    title=ft.Text("Puntos", size=14, italic=True),
                    title_size=40
                ),
                bottom_axis=ft.ChartAxis(
                    labels=[
                        ft.ChartAxisLabel(value=i+1, label=ft.Text(str(i+1), size=12)) for i in range(cant_partidos)
                    ],
                    labels_size=40,
                    title=ft.Text("Partido Nro", size=14, italic=True),
                    title_size=40
                ),
                horizontal_grid_lines=ft.ChartGridLines(interval=1, color=ft.Colors.WHITE10, width=1),
                min_y=0,
                max_y=MAXIMA_CANTIDAD_DE_PUNTOS + 1,
            )

            # --- CONTENEDOR GRÁFICO ---
            es_pc = (self.page.width >= 750) if self.page.width else True
            fila_grafico = ft.Row(
                controls=[
                    ft.Container(
                        content=chart, 
                        width=ancho_grafico_dinamico, 
                        height=350, 
                        padding=ft.padding.only(top=20 if es_pc else 35, right=20 if es_pc else 50)
                    )
                ],
                scroll=ft.ScrollMode.ALWAYS
            )

            titulo_txt = f"Puntos de {usuario_sel}"
            subtitulo_txt = self.filtro_ranking_nombre if self.filtro_ranking_nombre else (f"Año {self.filtro_ranking_anio}" if self.filtro_ranking_anio else "Toda la historia")

            # --- ENSAMBLE GENERAL ---
            columna_principal = ft.Column([
                ft.Row(
                    controls=[
                        ft.Column([ft.Text(titulo_txt, size=20, weight="bold"), ft.Text(subtitulo_txt, size=14, color="white54")], expand=True),
                        ft.IconButton(icon=ft.Icons.CLOSE, on_click=lambda e: self._limpiar_memoria_dialogo(self.dlg_grafico_barras_full))
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                ),
                ft.Divider(),
                
                fila_grafico,
                
                ft.Divider(),
                ft.Container(height=30)
            ], scroll=ft.ScrollMode.ALWAYS, expand=True)

            contenido_final = ft.Container(
                width=ancho, height=alto,
                padding=20, bgcolor="#1E1E1E", border_radius=10,
                content=columna_principal
            )
            
            self._limpiar_memoria_dialogo(self.dlg_carga_grafico)
            self._limpiar_memoria_dialogo(self.dlg_gen_usuarios) # Cierra el modal de selección de usuarios

            if hasattr(self, 'dlg_grafico_full') and self.dlg_grafico_full:
                    self.dlg_grafico_full = None

            self.dlg_grafico_barras_full = ft.AlertDialog(content=contenido_final, modal=True, content_padding=0, bgcolor=ft.Colors.TRANSPARENT)
            self.page.open(self.dlg_grafico_barras_full)

        threading.Thread(target=_tarea, daemon=True).start()

    def _abrir_modal_mejor_predictor(self, e):
        """Abre la ventana modal con la tabla de Mejor Predictor (Error Absoluto)."""
        
        titulo = "Ranking Mejor Predictor (Histórico)"
        if self.filtro_ranking_nombre: 
             titulo = f"Ranking Mejor Predictor ({self.filtro_ranking_nombre})"
        elif self.filtro_ranking_anio:
             titulo = f"Ranking Mejor Predictor ({self.filtro_ranking_anio})"
             
        self.loading_modal = ft.ProgressBar(width=200, color="amber", bgcolor="#222222")
        
        # Ancho dinámico para que no se salga del celular
        ancho_pantalla = self.page.width if self.page.width else 600
        ancho_modal = min(700, ancho_pantalla - 20)
        
        columna_content = ft.Column(
            controls=[
                ft.Text(titulo, size=18, weight="bold", color="white"),
                ft.Container(height=10),
                self.loading_modal,
                ft.Container(height=50)
            ],
            height=150,
            width=ancho_modal, 
            scroll=ft.ScrollMode.ALWAYS # Barra vertical nativa siempre activa
        )
        
        self.dlg_mejor_predictor = ft.AlertDialog(content=columna_content, modal=True)
        self.page.open(self.dlg_mejor_predictor)

        def _cargar():
            bd = BaseDeDatos()
            datos = bd.obtener_ranking_mejor_predictor(self.filtro_ranking_edicion_id, self.filtro_ranking_anio)
            
            filas = []
            for i, row in enumerate(datos, start=1):
                user = row[0]
                val = float(row[1])
                
                txt_val = f"{val:.2f}".replace('.', ',')
                color_val = self._obtener_color_error(val)
                if val == 0:
                    clasificacion = "🎯 Predictor perfecto"
                elif val <= 1.0:
                    clasificacion = "👌 Muy preciso"
                elif val <= 2.0:
                    clasificacion = "👍 Aceptable"
                else: 
                    clasificacion = "🎲 Poco realista / arriesgado"

                filas.append(ft.DataRow(cells=[
                    ft.DataCell(ft.Container(content=ft.Text(f"{i}º", weight="bold", color="white"), width=50, alignment=ft.alignment.center)),
                    ft.DataCell(ft.Container(content=ft.Text(user, weight="bold", color="white"), width=ANCHO_COLUMNA_USUARIO, alignment=ft.alignment.center_left)),
                    ft.DataCell(ft.Container(content=ft.Text(txt_val, weight="bold", color=color_val), width=180, alignment=ft.alignment.center)),
                    ft.DataCell(ft.Container(content=ft.Text(clasificacion, weight="bold", color="white"), width=200, alignment=ft.alignment.center_left)),
                ]))
            
            tabla = ft.DataTable(
                columns=[
                    ft.DataColumn(ft.Container(content=ft.Text("Puesto", weight="bold", color="white"), width=50, alignment=ft.alignment.center)),
                    ft.DataColumn(ft.Container(content=ft.Text("Usuario", weight="bold", color="white"), width=ANCHO_COLUMNA_USUARIO, alignment=ft.alignment.center_left)),
                    ft.DataColumn(ft.Container(content=ft.Text("Promedio error\nabsoluto de goles", text_align="center", weight="bold", color="white"), width=180, alignment=ft.alignment.center), numeric=True),
                    ft.DataColumn(ft.Container(content=ft.Text("Clasificación", weight="bold", color="white"), width=200, alignment=ft.alignment.center_left)),
                ],
                rows=filas,
                heading_row_color="black",
                border=ft.border.all(1, "white10"),
                column_spacing=10,
                heading_row_height=60,
                data_row_max_height=50,
                data_row_min_height=50
            )

            # Altura matemática perfecta
            altura_tabla = 60 + (len(filas) * 50) + 30
            altura_contenedor = min(270, altura_tabla)

            # Contenedor limpio con scroll nativo visible
            contenedor_tabla_nativa = ft.Row(
                scroll=ft.ScrollMode.ALWAYS,
                controls=[
                    ft.Container(
                        height=altura_contenedor,
                        content=ft.Column(
                            controls=[tabla],
                            scroll=ft.ScrollMode.ALWAYS
                        )
                    )
                ]
            )
            
            # Ajuste dinámico del modal sin dejar espacios vacíos
            alto_pantalla = self.page.height if self.page.height else 600
            columna_content.height = min(alto_pantalla - 50, altura_contenedor + 150) 
            
            columna_content.controls = [
                ft.Text(titulo, size=18, weight="bold", color="white"),
                ft.Container(height=10),
                contenedor_tabla_nativa,
                ft.Container(height=10),
                ft.Row([ft.ElevatedButton("Cerrar", on_click=lambda e: self._limpiar_memoria_dialogo(self.dlg_mejor_predictor))], alignment=ft.MainAxisAlignment.END)
            ]
            self.dlg_mejor_predictor.update()
            
        threading.Thread(target=_cargar, daemon=True).start()

    def _guardar_pronostico(self, e):
        """Valida y guarda el pronóstico ingresado con protección anti-doble clic."""
        
        # --- 1. ESCUDO ANTI-DOBLE CLIC SÚPER RÁPIDO ---
        # Si el botón ya está inhabilitado en la memoria de Python, abortamos inmediatamente.
        if self.btn_pronosticar.disabled:
            return 
            
        # 2. INHABILITAR EL BOTÓN INMEDIATAMENTE
        self.btn_pronosticar.disabled = True
        self.btn_pronosticar.update()
        
        def _tarea():
            # 3. MOSTRAR MENSAJE DE CARGA
            self.loading_partidos.visible = False 
            VentanaCarga.mostrar(self.page, "Guardando pronóstico...")
            
            try:
                # Validaciones
                if not self.partido_a_pronosticar_id:
                    VentanaCarga.cerrar(self.page)
                    GestorMensajes.mostrar(self.page, "Atención", "Seleccione un partido de la tabla.", "error")
                    return
                
                gc_str = self.input_pred_cai.value.strip()
                gr_str = self.input_pred_rival.value.strip()
                
                if not gc_str or not gr_str:
                    VentanaCarga.cerrar(self.page)
                    GestorMensajes.mostrar(self.page, "Atención", "Ingrese ambos resultados.", "error")
                    return
                
                # Capturar la hora de Argentina
                hora_celular = self.obtener_hora_argentina().strftime('%Y-%m-%d %H:%M:%S')
                
                # Insertar en BD
                bd = BaseDeDatos()
                bd.insertar_pronostico(self.usuario_actual, self.partido_a_pronosticar_id, int(gc_str), int(gr_str), hora_celular)
                
                # 4. VACIAR EL FORMULARIO
                self.input_pred_cai.value = ""
                self.input_pred_rival.value = ""
                
                # Recargar las tablas silenciosamente de fondo
                self._recargar_datos(
                    actualizar_partidos=True, 
                    actualizar_pronosticos=True, 
                    actualizar_ranking=False,  
                    actualizar_copas=False
                )
                
                # 5. MOSTRAR LA RESPUESTA (Éxito)
                VentanaCarga.cerrar(self.page)
                GestorMensajes.mostrar(self.page, "Éxito", "Pronóstico guardado.", "exito")
                
            except Exception as ex:
                # 5. MOSTRAR LA RESPUESTA (Error)
                VentanaCarga.cerrar(self.page)
                GestorMensajes.mostrar(self.page, "Error", f"No se pudo guardar: {ex}", "error")
                self._enviar_alerta_correo_admins("Error al guardar pronóstico", f"Error al guardar pronóstico", tipo=str(ex), nombre_función="SistemaIndependiente._guardar_pronostico._tarea")
                
            finally:
                # 6. HABILITAR EL BOTÓN NUEVAMENTE (Pase lo que pase)
                VentanaCarga.cerrar(self.page) # Por seguridad
                self.btn_pronosticar.disabled = False
                self.page.update()

        threading.Thread(target=_tarea, daemon=True).start()

    def _abrir_modal_racha_actual(self, e):
        """Abre la ventana modal con la Racha Actual."""
        
        if self.filtro_ranking_nombre: 
             titulo = f"Racha actual ({self.filtro_ranking_nombre})"
        elif self.filtro_ranking_anio:
             titulo = f"Racha actual ({self.filtro_ranking_anio})"
        else:
             titulo = "Racha actual en la historia"
             
        self.loading_modal = ft.ProgressBar(width=200, color="amber", bgcolor="#222222")
        
        # Ancho dinámico para que no se salga del celular
        ancho_pantalla = self.page.width if self.page.width else 600
        ancho_modal = min(500, ancho_pantalla - 20)
        
        columna_content = ft.Column(
            controls=[
                ft.Text(titulo, size=18, weight="bold", color="white"),
                ft.Container(height=10),
                self.loading_modal,
                ft.Container(height=20)
            ],
            height=150,
            width=ancho_modal,
            scroll=ft.ScrollMode.ALWAYS # Barra vertical nativa siempre activa
        )
        
        self.dlg_racha = ft.AlertDialog(content=columna_content, modal=True)
        self.page.open(self.dlg_racha)

        def _cargar():
            bd = BaseDeDatos()
            datos = bd.obtener_racha_actual(self.filtro_ranking_edicion_id, self.filtro_ranking_anio)
            
            filas = []
            for i, row in enumerate(datos, start=1):
                user = row[0]
                racha = row[1]
                
                color_racha = "white"
                if racha >= 5: color_racha = "cyan"
                elif racha >= 3: color_racha = "green"
                elif racha == 0: color_racha = "red"

                filas.append(ft.DataRow(cells=[
                    ft.DataCell(ft.Container(content=ft.Text(f"{i}º", weight="bold", color="white"), width=50, alignment=ft.alignment.center)),
                    ft.DataCell(ft.Container(content=ft.Text(user, weight="bold", color="white"), width=ANCHO_COLUMNA_USUARIO, alignment=ft.alignment.center_left)),
                    ft.DataCell(ft.Container(content=ft.Text(str(racha), weight="bold", color=color_racha), width=100, alignment=ft.alignment.center)),
                ]))
            
            tabla = ft.DataTable(
                columns=[
                    ft.DataColumn(ft.Container(content=ft.Text("Puesto", weight="bold", color="white"), width=50, alignment=ft.alignment.center)),
                    ft.DataColumn(ft.Container(content=ft.Text("Usuario", weight="bold", color="white"), width=ANCHO_COLUMNA_USUARIO, alignment=ft.alignment.center_left)),
                    ft.DataColumn(ft.Container(content=ft.Text("Racha actual", text_align="center", weight="bold", color="white"), width=100, alignment=ft.alignment.center), numeric=True),
                ],
                rows=filas,
                heading_row_color="black",
                border=ft.border.all(1, "white10"),
                column_spacing=10,
                heading_row_height=60,
                data_row_max_height=50,
                data_row_min_height=50
            )

            # Altura matemática + 30px de respiro para los bordes
            altura_tabla = 60 + (len(filas) * 50) + 30 
            altura_contenedor = min(400, altura_tabla) 

            # Contenedor limpio con scroll nativo visible
            contenedor_tabla_nativa = ft.Row(
                scroll=ft.ScrollMode.ALWAYS,
                controls=[
                    ft.Container(
                        height=altura_contenedor,
                        content=ft.Column(
                            controls=[tabla],
                            scroll=ft.ScrollMode.ALWAYS
                        )
                    )
                ]
            )
            
            # Ajuste dinámico del modal sin dejar espacios vacíos
            alto_pantalla = self.page.height if self.page.height else 600
            columna_content.height = min(alto_pantalla - 50, altura_contenedor + 150) 
            
            columna_content.controls = [
                ft.Text(titulo, size=18, weight="bold", color="white"),
                ft.Container(height=10),
                contenedor_tabla_nativa,
                ft.Container(height=10),
                ft.Row([ft.ElevatedButton("Cerrar", on_click=lambda e: self._limpiar_memoria_dialogo(self.dlg_racha))], alignment=ft.MainAxisAlignment.END)
            ]
            self.dlg_racha.update()
            
        threading.Thread(target=_cargar, daemon=True).start()

    def obtener_hora_argentina(self):
        """Retorna la hora exacta de Argentina (UTC-3) sin importar dónde esté el servidor."""
        # Tomamos la hora UTC real, le restamos 3 horas, y le quitamos la 'etiqueta' de zona horaria 
        # para que TiDB lo guarde como un DATETIME normal sin quejarse.
        return (datetime.now(timezone.utc) - timedelta(hours=3)).replace(tzinfo=None)

    def _validar_solo_numeros(self, e):
        """
        Valida que el input solo contenga números.
        Permite borrar el contenido sin bloquearse.
        """
        if e.control.value:
            # Filtramos solo dígitos
            valor_limpio = "".join(filter(str.isdigit, e.control.value))
            # Si hubo cambios (había letras o símbolos), actualizamos
            if valor_limpio != e.control.value:
                e.control.value = valor_limpio
                e.control.update()

    def _abrir_selector_usuario_pronosticos(self, e):
        self.lv_usuarios = ft.ListView(expand=True, spacing=5, height=300)
        self.btn_ver_usuario = ft.ElevatedButton("Ver", icon=ft.Icons.VISIBILITY, disabled=True, on_click=self._confirmar_filtro_usuario_pronosticos)
        
        def _cargar_usuarios_modal():
            try:
                bd = BaseDeDatos()
                usuarios = bd.obtener_usuarios() 
                controles = []
                for usuario in usuarios:
                    controles.append(ft.ListTile(title=ft.Text(usuario, size=14), data=usuario, on_click=self._seleccionar_usuario_modal, bgcolor="#2D2D2D", shape=ft.RoundedRectangleBorder(radius=5)))
                self.lv_usuarios.controls = controles
                self.lv_usuarios.update()
            except Exception as ex:
                self._mostrar_mensaje_admin("Error cargando modal usuarios", f"{e}", "error", nombre_función="SistemaIndependiente._abrir_selector_usuario_pronosticos._cargar_usuarios_modal")

        contenido_modal = ft.Container(width=400, height=400, content=ft.Column(controls=[ft.Text("Seleccione un Usuario", weight=ft.FontWeight.BOLD), ft.Container(content=self.lv_usuarios, border=ft.border.all(1, "white24"), border_radius=5, padding=5, expand=True)]))

        self.dlg_modal_usuario = ft.AlertDialog(modal=True, title=ft.Text("Filtrar por Usuario"), content=contenido_modal, actions=[ft.TextButton("Cancelar", on_click=lambda e: self._limpiar_memoria_dialogo(self.dlg_modal_usuario)), self.btn_ver_usuario], actions_alignment=ft.MainAxisAlignment.END)
        self.page.open(self.dlg_modal_usuario)
        threading.Thread(target=_cargar_usuarios_modal, daemon=True).start()

    def _seleccionar_usuario_modal(self, e):
        """Al clickear un usuario, se habilita el botón ver."""
        usuario_sel = e.control.data
        self.temp_usuario_sel = usuario_sel
        
        # Resaltar selección
        for c in self.lv_usuarios.controls:
            c.bgcolor = "blue" if c.data == usuario_sel else "#2D2D2D"
        self.lv_usuarios.update()
        
        self.btn_ver_usuario.disabled = False
        self.btn_ver_usuario.update()

    def _confirmar_filtro_torneo_pronosticos(self, e):
        if self.temp_campeonato_sel and self.temp_anio_sel:
            nombre_completo = f"{self.temp_campeonato_sel} {self.temp_anio_sel}"
            self.filtro_pron_torneo = nombre_completo
            
            self._actualizar_botones_pronosticos_visual()
            self._actualizar_titulo_pronosticos()
            self._limpiar_memoria_dialogo(self.dlg_modal)
            self._recargar_datos(actualizar_pronosticos=True)

    def _confirmar_filtro_torneo(self, e):
        """Confirma la selección del torneo y lo aplica (sumándose a otros filtros)."""
        if self.temp_campeonato_sel and self.temp_anio_sel:
            edicion_encontrada = None
            for ed in self.cache_ediciones_modal:
                if ed[1] == self.temp_campeonato_sel and ed[2] == self.temp_anio_sel:
                    edicion_encontrada = ed[0] 
                    break
            
            if edicion_encontrada:
                self.filtro_edicion_id = edicion_encontrada
                
                self._actualizar_titulo_partidos()
                self._actualizar_botones_partidos_visual()
                self._limpiar_memoria_dialogo(self.dlg_modal)
                self._recargar_datos(actualizar_partidos=True, actualizar_copas=False)

    def _confirmar_filtro_torneo_ranking(self, e):
        """Busca el ID de la edición seleccionada y aplica el filtro al ranking"""
        if self.temp_campeonato_sel and self.temp_anio_sel:
            edicion_encontrada = None
            for ed in self.cache_ediciones_modal:
                if ed[1] == self.temp_campeonato_sel and ed[2] == self.temp_anio_sel:
                    edicion_encontrada = ed[0] 
                    break
            
            if edicion_encontrada:
                self.filtro_ranking_edicion_id = edicion_encontrada
                self.filtro_ranking_nombre = f"{self.temp_campeonato_sel} {self.temp_anio_sel}"
                self.filtro_ranking_anio = None
                
                self.txt_titulo_ranking.value = f"Tabla de posiciones {self.filtro_ranking_nombre}"
                self.txt_titulo_ranking.update()
                
                self.btn_ranking_torneo.bgcolor = "blue"
                self.btn_ranking_anio.bgcolor = "#333333" 
                self.btn_ranking_torneo.update()
                self.btn_ranking_anio.update()
                
                # --- HABILITAR BOTONES DE GRÁFICOS (Modo visual) ---
                self.btn_grafico_puestos.bgcolor = "#333333"
                self.btn_grafico_puestos.color = "white"
                
                self.btn_grafico_linea_puntos.bgcolor = "#333333"
                self.btn_grafico_linea_puntos.color = "white"
                
                self.btn_grafico_barras_puntos.bgcolor = "#333333"
                self.btn_grafico_barras_puntos.color = "white"
                
                self.btn_grafico_puestos.update()
                self.btn_grafico_linea_puntos.update()
                self.btn_grafico_barras_puntos.update()
                
                self._limpiar_memoria_dialogo(self.dlg_modal)
                self._recargar_datos(actualizar_ranking=True, actualizar_copas=False)
                
    def _abrir_selector_torneo_pronosticos(self, e):
        loading_content = ft.Column(
            controls=[
                ft.Text("Cargando filtros...", size=16, weight="bold", color="white"),
                ft.ProgressBar(width=200, color="amber", bgcolor="#222222")
            ],
            height=80, width=300, alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER
        )
        self.dlg_carga_filtros = ft.AlertDialog(content=loading_content, modal=True)
        self.page.open(self.dlg_carga_filtros)

        def _cargar_datos_modal():
            time.sleep(0.5)
            
            self.temp_campeonato_sel = None
            self.modal_torneo_es_opcional = False
            self.txt_titulo_torneo_modal = ft.Text("1. Torneo (Obligatorio)", weight=ft.FontWeight.BOLD, color="white")
            self.txt_titulo_anio_modal = ft.Text("2. Año (Obligatorio)", weight=ft.FontWeight.BOLD, color="white")
            
            self.lv_torneos = ft.Column(scroll=ft.ScrollMode.ALWAYS, spacing=5)
            self.lv_anios = ft.Column(scroll=ft.ScrollMode.ALWAYS, spacing=5)
            
            self.btn_ver_torneo = ft.ElevatedButton("Ver", icon=ft.Icons.VISIBILITY, disabled=True, on_click=self._confirmar_filtro_torneo_pronosticos)
            
            try:
                bd = BaseDeDatos()
                # --- CAMBIO APLICADO: TODOS LOS TORNEOS ---
                ediciones = bd.obtener_ediciones(solo_finalizados=False)
                self.cache_ediciones_modal = ediciones
                nombres_unicos = sorted(list(set(e[1] for e in ediciones)))
                
                controles = []
                for nombre in nombres_unicos:
                    controles.append(ft.ListTile(title=ft.Text(nombre, size=14), data=nombre, on_click=self._seleccionar_campeonato_modal, bgcolor="#2D2D2D", shape=ft.RoundedRectangleBorder(radius=5)))
                self.lv_torneos.controls = controles
            except Exception as ex:
                self._mostrar_mensaje_admin("Error cargando modal", f"{ex}", "error", nombre_función="SistemaIndependiente._abrir_selector_torneo_pronosticos._cargar_datos_modal")

            es_pc = (self.page.width >= 600) if self.page.width else True
            ancho_pantalla = self.page.width if self.page.width else 600
            ancho_modal = min(500, ancho_pantalla - 20)
            ancho_caja = 200 if es_pc else (ancho_modal - 40)

            col_torneo = ft.Column(
                controls=[
                    self.txt_titulo_torneo_modal, 
                    ft.Container(content=self.lv_torneos, height=180, width=ancho_caja, border=ft.border.all(1, "white24"), border_radius=5, padding=5)
                ]
            )
            col_anio = ft.Column(
                controls=[
                    self.txt_titulo_anio_modal, 
                    ft.Container(content=self.lv_anios, height=180, width=ancho_caja, border=ft.border.all(1, "white24"), border_radius=5, padding=5)
                ]
            )

            if es_pc:
                layout_filtros = ft.Row(controls=[col_torneo, col_anio], spacing=20, alignment=ft.MainAxisAlignment.CENTER)
                alto_contenedor = 250
            else:
                layout_filtros = ft.Column(controls=[col_torneo, col_anio], spacing=20, scroll=ft.ScrollMode.ALWAYS, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
                alto_contenedor = 450

            contenido_modal = ft.Container(width=ancho_modal, height=alto_contenedor, content=layout_filtros)

            self.dlg_modal = ft.AlertDialog(
                modal=True, title=ft.Text("Filtrar por Torneo"), content=contenido_modal, 
                actions=[ft.TextButton("Cancelar", on_click=lambda e: self._limpiar_memoria_dialogo(self.dlg_modal)), self.btn_ver_torneo], 
                actions_alignment=ft.MainAxisAlignment.END
            )
            self._limpiar_memoria_dialogo(self.dlg_carga_filtros)
            self.page.open(self.dlg_modal)

        threading.Thread(target=_cargar_datos_modal, daemon=True).start()

    def _confirmar_filtro_equipo_pronosticos(self, e):
        if self.temp_rival_sel_nombre:
            self.filtro_pron_equipo = self.temp_rival_sel_nombre
            
            self._actualizar_botones_pronosticos_visual()
            
            self._actualizar_titulo_pronosticos()
            self._limpiar_memoria_dialogo(self.dlg_modal_equipo)
            self._recargar_datos(actualizar_pronosticos=True)

    def _confirmar_filtro_usuario_pronosticos(self, e):
        """Confirma selección usuario (COMBINABLE)"""
        if self.temp_usuario_sel:
            self.filtro_pron_usuario = self.temp_usuario_sel
            
            self._actualizar_botones_pronosticos_visual()
            
            self._actualizar_titulo_pronosticos()
            self._limpiar_memoria_dialogo(self.dlg_modal_usuario)
            self._recargar_datos(actualizar_pronosticos=True)

    def _abrir_selector_equipo_pronosticos(self, e):
        # 1. Animación de carga inicial
        loading_content = ft.Column(
            controls=[
                ft.Text("Cargando equipos...", size=16, weight="bold", color="white"),
                ft.ProgressBar(width=200, color="amber", bgcolor="#222222")
            ],
            height=80, width=300, alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER
        )
        self.dlg_carga_filtros = ft.AlertDialog(content=loading_content, modal=True)
        self.page.open(self.dlg_carga_filtros)

        def _cargar_rivales_modal():
            time.sleep(0.5)
            
            # Barra vertical nativa siempre visible
            self.lv_equipos = ft.Column(scroll=ft.ScrollMode.ALWAYS, spacing=5)
            self.btn_ver_equipo = ft.ElevatedButton("Ver", icon=ft.Icons.VISIBILITY, disabled=True, on_click=self._confirmar_filtro_equipo_pronosticos)
            
            try:
                bd = BaseDeDatos()
                rivales = bd.obtener_rivales() 
                controles = []
                for id_rival, nombre in rivales:
                    # CLAVE: no_wrap=False permite que los nombres largos bajen a una segunda línea en lugar de cortarse
                    controles.append(ft.ListTile(title=ft.Text(nombre, size=14, no_wrap=False), data=id_rival, on_click=self._seleccionar_rival_modal, bgcolor="#2D2D2D", shape=ft.RoundedRectangleBorder(radius=5)))
                self.lv_equipos.controls = controles
            except Exception as ex:
                self._mostrar_mensaje_admin("Error cargando modal equipos", f"{ex}", "error", nombre_función="SistemaIndependiente._abrir_selector_equipo_pronosticos._cargar_rivales_modal")

            ancho_pantalla = self.page.width if self.page.width else 600
            ancho_modal = min(400, ancho_pantalla - 20)

            contenido_modal = ft.Container(
                width=ancho_modal, height=400, 
                content=ft.Column(
                    controls=[
                        ft.Text("Seleccione un Equipo", weight=ft.FontWeight.BOLD), 
                        ft.Container(
                            content=self.lv_equipos, # Contenido directo, sin fila horizontal externa
                            border=ft.border.all(1, "white24"), 
                            border_radius=5, 
                            padding=5, 
                            expand=True
                        )
                    ]
                )
            )

            self.dlg_modal_equipo = ft.AlertDialog(
                modal=True, 
                title=ft.Text("Filtrar por Equipo"), 
                content=contenido_modal, 
                actions=[ft.TextButton("Cancelar", on_click=lambda e: self._limpiar_memoria_dialogo(self.dlg_modal_equipo)), self.btn_ver_equipo], 
                actions_alignment=ft.MainAxisAlignment.END
            )
            
            self._limpiar_memoria_dialogo(self.dlg_carga_filtros)
            self.page.open(self.dlg_modal_equipo)

        threading.Thread(target=_cargar_rivales_modal, daemon=True).start()

    def _seleccionar_anio_ranking_modal(self, e):
        anio_sel = e.control.data
        self.temp_anio_sel = anio_sel # Reutilizamos variable temporal
        
        for c in self.lv_anios_ranking.controls:
            c.bgcolor = "blue" if c.data == anio_sel else "#2D2D2D"
        self.lv_anios_ranking.update()
        
        self.btn_ver_anio.disabled = False
        self.btn_ver_anio.update()

    def _seleccionar_partido_click(self, id_partido):
        """
        Simula la selección de una fila tipo 'Treeview'.
        Recibe el ID del partido desde el evento on_click de la celda.
        """
        # Si toco el mismo que ya estaba seleccionado, lo desmarco
        if self.partido_a_pronosticar_id == id_partido:
            self.partido_a_pronosticar_id = None
            self.input_pred_cai.value = ""
            self.input_pred_rival.value = ""
            
            # Desmarcar todo (quitar color)
            for row in self.tabla_partidos.rows:
                row.color = None
            self.page.update()
            return

        # Nueva selección
        self.partido_a_pronosticar_id = id_partido
        
        # Iteramos filas para pintar la correcta y leer sus datos
        for row in self.tabla_partidos.rows:
            if row.data == id_partido:
                row.color = "#8B0000" # Rojo oscuro
                
                # Intentamos leer el pronóstico visual de la celda 4
                try:
                    # Estructura: DataCell -> Container -> Text -> value
                    texto_celda = row.cells[4].content.content.value
                    if " a " in texto_celda:
                        partes = texto_celda.split(" a ")
                        self.input_pred_cai.value = partes[0]
                        self.input_pred_rival.value = partes[1]
                    else:
                        self.input_pred_cai.value = ""
                        self.input_pred_rival.value = ""
                except:
                    self.input_pred_cai.value = ""
                    self.input_pred_rival.value = ""
            else:
                row.color = None
        
        self.page.update()

    def _guardar_contrasena_config(self, e):
        """Valida y guarda el cambio de contraseña desde Configuración."""
        p1 = self.input_conf_pass_1.value
        p2 = self.input_conf_pass_2.value

        # 1. Validaciones básicas
        if not p1 or not p2:
            GestorMensajes.mostrar(self.page, "Error", "Debe completar ambos campos.", "error")
            return
        
        if p1 != p2:
            GestorMensajes.mostrar(self.page, "Error", "Las contraseñas no coinciden.", "error")
            return

        # Opcional: Validar longitud mínima
        if len(p1) < 4:
            GestorMensajes.mostrar(self.page, "Error", "La contraseña es muy corta.", "error")
            return

        # 2. Proceso en segundo plano
        def _tarea():
            # Deshabilitar botón para evitar doble clic
            self.btn_conf_guardar_pass.disabled = True
            self.btn_conf_guardar_pass.update()
            
            try:
                bd = BaseDeDatos()
                # Reutilizamos la función existente en tu BD
                bd.cambiar_contrasena(self.usuario_actual, p1)
                
                GestorMensajes.mostrar(self.page, "Éxito", "Contraseña actualizada correctamente.", "exito")
                
                # Limpiar campos
                self.input_conf_pass_1.value = ""
                self.input_conf_pass_2.value = ""
                self.input_conf_pass_1.update()
                self.input_conf_pass_2.update()
                
            except Exception as ex:
                GestorMensajes.mostrar(self.page, "Error", f"No se pudo cambiar: {ex}", "error")
            
            finally:
                self.btn_conf_guardar_pass.disabled = False
                self.btn_conf_guardar_pass.update()

        threading.Thread(target=_tarea, daemon=True).start()

    def _abrir_modal_estilo_decision(self, e):
        """
        Calcula y muestra el Estilo de Decisión de cada usuario basado en su anticipación.
        Muestra error si no hay partidos jugados.
        """
        
        # Título dinámico
        titulo = "Estilo de Decisión (Anticipación)"
        if self.filtro_ranking_nombre: 
             titulo = f"Estilo de Decisión ({self.filtro_ranking_nombre})"
        elif self.filtro_ranking_anio:
             titulo = f"Estilo de Decisión ({self.filtro_ranking_anio})"
             
        # Elementos de carga
        self.loading_modal = ft.ProgressBar(width=200, color="amber", bgcolor="#222222")
        self.txt_estado_modal = ft.Text("Analizando tiempos de predicción...", color="white70", size=12)
        
        # Ancho dinámico para que no se salga del celular
        ancho_pantalla = self.page.width if self.page.width else 600
        ancho_modal = min(650, ancho_pantalla - 20)
        
        columna_content = ft.Column(
            controls=[
                ft.Text(titulo, size=18, weight="bold", color="white"),
                ft.Container(height=10),
                self.loading_modal,
                self.txt_estado_modal,
                ft.Container(height=20)
            ],
            height=150,
            width=ancho_modal, # <--- ANCHO DINÁMICO
            scroll=ft.ScrollMode.ALWAYS # <--- BARRA VERTICAL SIEMPRE VISIBLE
        )
        
        self.dlg_estilo = ft.AlertDialog(content=columna_content, modal=True)
        self.page.open(self.dlg_estilo)

        def _cargar():
            time.sleep(0.6) # Pequeña pausa para ver la animación
            bd = BaseDeDatos()
            
            # 1. VALIDACIÓN: ¿Hay partidos jugados en el pasado para este filtro?
            partidos_jugados = bd.obtener_partidos(
                self.usuario_actual, 
                filtro_tiempo='jugados', 
                edicion_id=self.filtro_ranking_edicion_id
            )
            
            datos_ranking = bd.obtener_ranking(self.filtro_ranking_edicion_id, self.filtro_ranking_anio)
            
            datos_validos = False
            if partidos_jugados:
                for row in datos_ranking:
                    if row[6] and float(row[6]) > 0:
                        datos_validos = True
                        break
            
            if not partidos_jugados and not datos_validos:
                self.loading_modal.visible = False
                self.txt_estado_modal.value = ""
                
                columna_content.controls = [
                    ft.Text(titulo, size=18, weight="bold", color="white"),
                    ft.Container(height=20),
                    ft.Column([
                        ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, color="yellow", size=50),
                        ft.Text("No hay datos suficientes", size=16, weight="bold", color="white"),
                        ft.Text("Este análisis requiere partidos pasados para calcular el promedio.", size=14, color="white70"),
                    ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    ft.Container(height=20),
                    ft.Row([ft.ElevatedButton("Cerrar", on_click=lambda e: self._limpiar_memoria_dialogo(self.dlg_estilo))], alignment=ft.MainAxisAlignment.END)
                ]
                self.dlg_estilo.update()
                return

            # 2. PROCESAR DATOS
            filas = []
            # Ordenamos por anticipación (mayor a menor)
            datos_ranking.sort(key=lambda x: float(x[6]) if x[6] else 0, reverse=True)

            for i, row in enumerate(datos_ranking, start=1):
                user = row[0]
                raw_seconds = row[6]
                
                if raw_seconds is not None and float(raw_seconds) > 0:
                    val_sec = float(raw_seconds)
                    
                    # Cálculo de horas totales para la clasificación
                    horas_totales_float = val_sec / 3600
                    
                    # Lógica de Clasificación
                    if horas_totales_float > 72:   # +3 días
                        estilo = "🧠 Convencido temprano"
                        color_estilo = "pink"
                    elif horas_totales_float > 24: # +1 día
                        estilo = "🗓️ Anticipado"
                        color_estilo = "cyan"
                    elif horas_totales_float > 6:  # +6 horas
                        estilo = "⚖️ Balanceado"
                        color_estilo = "orange"
                    elif horas_totales_float > 1:  # +1 hora
                        estilo = "⏳ Último momento"
                        color_estilo = "yellow"
                    else:                    # -1 hora
                        estilo = "🔥 Impulsivo"
                        color_estilo = "red"

                    # --- NUEVO FORMATO VISUAL (HH:MM:SS h) ---
                    # Calculamos horas totales acumulando los días
                    horas_display = int(val_sec // 3600) 
                    segundos_restantes = val_sec % 3600
                    minutos_display = int(segundos_restantes // 60)
                    segundos_display = int(segundos_restantes % 60)
                    
                    txt_tiempo = f"{horas_display:02d}:{minutos_display:02d}:{segundos_display:02d} h"

                else:
                    # Caso: Usuario sin anticipación
                    txt_tiempo = "-"
                    estilo = "-"
                    color_estilo = "white30"

                filas.append(ft.DataRow(cells=[
                    ft.DataCell(ft.Container(content=ft.Text(user, weight="bold", color="white"), width=ANCHO_COLUMNA_USUARIO, alignment=ft.alignment.center_left)),
                    ft.DataCell(ft.Container(content=ft.Text(txt_tiempo, color="cyan", weight="bold"), width=120, alignment=ft.alignment.center)),
                    ft.DataCell(ft.Container(content=ft.Text(estilo, color=color_estilo, weight="bold", size=15), width=180, alignment=ft.alignment.center_left)),
                ]))

            # 3. CONSTRUIR TABLA
            tabla = ft.DataTable(
                columns=[
                    ft.DataColumn(ft.Container(content=ft.Text("Usuario", weight="bold", color="white"), width=ANCHO_COLUMNA_USUARIO, alignment=ft.alignment.center_left)),
                    ft.DataColumn(ft.Container(content=ft.Text("Anticipación\nPromedio", text_align="center", weight="bold", color="white"), width=120, alignment=ft.alignment.center)),
                    ft.DataColumn(ft.Container(content=ft.Text("Estilo", weight="bold", color="white"), width=180, alignment=ft.alignment.center_left)),
                ],
                rows=filas,
                heading_row_color="black",
                border=ft.border.all(1, "white10"),
                column_spacing=10,
                heading_row_height=60,
                data_row_max_height=50,
                data_row_min_height=50
            )

            # Altura matemática perfecta
            altura_tabla = 60 + (len(filas) * 50) + 30
            altura_contenedor = min(270, altura_tabla)

            contenedor_tabla_nativa = ft.Row(
                scroll=ft.ScrollMode.ALWAYS,
                controls=[
                    ft.Container(
                        height=altura_contenedor,
                        content=ft.Column(
                            controls=[tabla],
                            scroll=ft.ScrollMode.ALWAYS
                        )
                    )
                ]
            )

            # Ajuste dinámico del modal sin dejar espacios vacíos
            alto_pantalla = self.page.height if self.page.height else 600
            columna_content.height = min(alto_pantalla - 50, altura_contenedor + 150) 
            
            # ¡IMPORTANTE! Aseguramos el ancho dinámico para que no se salga
            ancho_pantalla = self.page.width if self.page.width else 600
            columna_content.width = min(650, ancho_pantalla - 20)
            
            columna_content.controls = [
                ft.Text(titulo, size=18, weight="bold", color="white"),
                ft.Text("Promedio de tiempo de anticipación de los pronósticos.", size=12, color="white70"),
                ft.Container(height=10),
                contenedor_tabla_nativa, # <--- TABLA LIMPIA
                ft.Container(height=10),
                ft.Row([ft.ElevatedButton("Cerrar", on_click=lambda e: self._limpiar_memoria_dialogo(self.dlg_estilo))], alignment=ft.MainAxisAlignment.END)
            ]
            self.dlg_estilo.update()

        threading.Thread(target=_cargar, daemon=True).start()

    def _abrir_modal_mufa(self, e):
        """Muestra el ranking de 'Mufa' con animación de carga."""
        
        # 1. Configuración inicial del modal (Estado Cargando)
        self.loading_modal = ft.ProgressBar(width=200, color="amber", bgcolor="#222222")
        
        # Ancho dinámico para que no se salga del celular
        ancho_pantalla = self.page.width if self.page.width else 600
        ancho_modal = min(650, ancho_pantalla - 20)
        
        columna_content = ft.Column(
            controls=[
                ft.Text("Ranking Mufa 🌩️", size=18, weight="bold", color="white"),
                ft.Text("Usuarios que más aciertan cuando pronostican que el Rojo pierde.", size=12, color="white70"),
                ft.Container(height=10),
                self.loading_modal,
                ft.Container(height=50)
            ],
            height=150,
            width=ancho_modal, # <--- ANCHO DINÁMICO
            scroll=ft.ScrollMode.ALWAYS # <--- BARRA VERTICAL SIEMPRE VISIBLE
        )
        
        self.dlg_mufa = ft.AlertDialog(content=columna_content, modal=True)
        self.page.open(self.dlg_mufa)

        def _cargar():
            time.sleep(0.3)
            try:
                bd = BaseDeDatos()
                datos = bd.obtener_ranking_mufa(self.filtro_ranking_edicion_id, self.filtro_ranking_anio)
                
                filas = []
                for i, fila in enumerate(datos, start=1):
                    user = fila[0]
                    pred_derrotas = fila[1]
                    aciertos = fila[2]
                    porcentaje = fila[3]
                    
                    txt_porcentaje = f"{porcentaje:.1f}%".replace('.', ',')
                    
                    if porcentaje >= 50: color_txt = "red"
                    elif porcentaje >= 20: color_txt = "orange"
                    else: color_txt = "green" 
                    
                    filas.append(ft.DataRow(cells=[
                        ft.DataCell(ft.Container(content=ft.Text(f"{i}º", color="white", weight=ft.FontWeight.BOLD), width=50, alignment=ft.alignment.center)),
                        ft.DataCell(ft.Container(content=ft.Text(user, color="white"), width=ANCHO_COLUMNA_USUARIO, alignment=ft.alignment.center_left)),
                        ft.DataCell(ft.Container(content=ft.Text(str(pred_derrotas), color="cyan"), width=100, alignment=ft.alignment.center)),
                        ft.DataCell(ft.Container(content=ft.Text(str(aciertos), color="white"), width=100, alignment=ft.alignment.center)),
                        ft.DataCell(ft.Container(content=ft.Text(txt_porcentaje, color=color_txt, weight=ft.FontWeight.BOLD), width=100, alignment=ft.alignment.center)),
                    ]))

                tabla = ft.DataTable(
                    columns=[
                        ft.DataColumn(ft.Container(content=ft.Text("Pos", weight="bold", color="white"), width=50, alignment=ft.alignment.center)),
                        ft.DataColumn(ft.Container(content=ft.Text("Usuario", weight="bold", color="white"), width=ANCHO_COLUMNA_USUARIO, alignment=ft.alignment.center_left)),
                        ft.DataColumn(ft.Container(content=ft.Text("Pred. Derrota", tooltip="Veces que pronosticó que perdíamos", weight="bold", color="white"), width=100, alignment=ft.alignment.center), numeric=True),
                        ft.DataColumn(ft.Container(content=ft.Text("Acertadas", tooltip="Veces que pronosticó derrota y PERDIMOS", weight="bold", color="white"), width=100, alignment=ft.alignment.center), numeric=True),
                        ft.DataColumn(ft.Container(content=ft.Text("% Mufa", tooltip="Porcentaje de derrotas acertadas", weight="bold", color="white"), width=100, alignment=ft.alignment.center), numeric=True),
                    ],
                    rows=filas,
                    heading_row_color="black",
                    data_row_color={"hoverED": "#1A1A1A"},
                    border=ft.border.all(1, "white10"),
                    column_spacing=10,
                    heading_row_height=60,
                    data_row_max_height=50,
                    data_row_min_height=50
                )
                
                # Altura matemática perfecta: 60px de cabecera + 50px por cada usuario
                altura_tabla = 60 + (len(filas) * 50) + 30
                altura_contenedor = min(270, altura_tabla)

                contenedor_tabla_nativa = ft.Row(
                    scroll=ft.ScrollMode.ALWAYS,
                    controls=[
                        ft.Container(
                            height=altura_contenedor,
                            content=ft.Column(
                                controls=[tabla],
                                scroll=ft.ScrollMode.ALWAYS
                            )
                        )
                    ]
                )

                # Ajuste dinámico del modal sin dejar espacios vacíos
                alto_pantalla = self.page.height if self.page.height else 600
                columna_content.height = min(alto_pantalla - 50, altura_contenedor + 150)
                
                columna_content.controls = [
                    ft.Text("Ranking Mufa 🌩️", size=18, weight="bold", color="white"),
                    ft.Text("Usuarios que más aciertan cuando pronostican que el Rojo pierde.", size=12, color="white70"),
                    ft.Container(height=10),
                    contenedor_tabla_nativa, # <--- TABLA LIMPIA
                    ft.Container(height=10),
                    ft.Row([ft.ElevatedButton("Cerrar", on_click=lambda e: self._limpiar_memoria_dialogo(self.dlg_mufa))], alignment=ft.MainAxisAlignment.END)
                ]
                self.dlg_mufa.update()

            except Exception as ex:
                self._limpiar_memoria_dialogo(self.dlg_mufa)
                GestorMensajes.mostrar(self.page, "Error", f"No se pudo cargar mufa: {ex}", "error")
                self._enviar_alerta_correo_admins("Error al cargar mufa", f"Error al cargar mufa", tipo=str(ex), nombre_función="SistemaIndependiente._abrir_modal_mufa._cargar")

        # Ejecutar en hilo secundario
        threading.Thread(target=_cargar, daemon=True).start()

    def _abrir_modal_cambios_pronostico(self, e):
        """ 
        Muestra la tabla de 'Estabilidad de Pronósticos'. 
        Clasificación basada en la cantidad promedio de pronósticos por partido (solo terminados).
        """
        titulo = "Estadísticas de Estabilidad"
        if self.filtro_ranking_nombre: 
             titulo = f"Estabilidad ({self.filtro_ranking_nombre})"
        elif self.filtro_ranking_anio:
             titulo = f"Estabilidad ({self.filtro_ranking_anio})"
             
        self.loading_modal = ft.ProgressBar(width=200, color="amber", bgcolor="#222222")
        self.txt_estado_modal = ft.Text("Analizando historial de cambios...", color="white70", size=12)
        
        # Ancho dinámico para que no se salga del celular
        ancho_pantalla = self.page.width if self.page.width else 600
        ancho_modal = min(600, ancho_pantalla - 20)
        
        columna_content = ft.Column(
            controls=[
                ft.Text(titulo, size=18, weight="bold", color="white"),
                ft.Container(height=10),
                self.loading_modal,
                self.txt_estado_modal,
                ft.Container(height=20)
            ],
            height=150,
            width=ancho_modal,
            scroll=ft.ScrollMode.ALWAYS # Barra vertical nativa siempre activa
        )
        
        self.dlg_cambios = ft.AlertDialog(content=columna_content, modal=True)
        self.page.open(self.dlg_cambios)

        def _cargar():
            time.sleep(0.5)
            bd = BaseDeDatos()
            
            datos_estabilidad = bd.obtener_ranking_estabilidad(self.filtro_ranking_edicion_id, self.filtro_ranking_anio)
            
            if not datos_estabilidad:
                self.loading_modal.visible = False
                self.txt_estado_modal.value = ""
                columna_content.controls = [
                    ft.Text(titulo, size=18, weight="bold", color="white"),
                    ft.Container(height=20),
                    ft.Column([
                        ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, color="yellow", size=50),
                        ft.Text("No hay datos históricos", size=16, weight="bold", color="white"),
                        ft.Text("Se requieren partidos terminados con pronósticos.", size=14, color="white70"),
                    ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    ft.Container(height=20),
                    ft.Row([ft.ElevatedButton("Cerrar", on_click=lambda e: self._limpiar_memoria_dialogo(self.dlg_cambios))], alignment=ft.MainAxisAlignment.END)
                ]
                self.dlg_cambios.update()
                return

            filas = []
            datos_estabilidad.sort(key=lambda x: float(x[1]) if x[1] else 999)

            for row in datos_estabilidad:
                user = row[0]
                promedio_cambios = row[1]
                
                if not promedio_cambios: continue
                
                val_cambios = float(promedio_cambios)
                txt_cambios = f"{val_cambios:.2f}".replace('.', ',')
                
                if val_cambios <= 1.10:
                    estilo = "🧱 Firme"
                    color_estilo = "brown"
                elif val_cambios <= 1.50:
                    estilo = "👍 Estable"
                    color_estilo = "amber"
                elif val_cambios <= 2.50:
                    estilo = "🔄 Cambiante"
                    color_estilo = "blue"
                else: 
                    estilo = "📉 Muy volátil"
                    color_estilo = "red"

                filas.append(ft.DataRow(cells=[
                    ft.DataCell(ft.Container(content=ft.Text(user, weight="bold", color="white"), width=ANCHO_COLUMNA_USUARIO, alignment=ft.alignment.center_left)),
                    ft.DataCell(ft.Container(content=ft.Text(txt_cambios, color="white", weight="bold"), width=120, alignment=ft.alignment.center)),
                    ft.DataCell(ft.Container(content=ft.Text(estilo, color=color_estilo, weight="bold", size=14), width=180, alignment=ft.alignment.center_left)),
                ]))

            tabla = ft.DataTable(
                columns=[
                    ft.DataColumn(ft.Container(content=ft.Text("Usuario", weight="bold", color="white"), width=ANCHO_COLUMNA_USUARIO, alignment=ft.alignment.center_left)),
                    ft.DataColumn(ft.Container(content=ft.Text("Promedio de\npronósticos", text_align="center", weight="bold", color="white", tooltip="Promedio de veces que guardó pronóstico por partido finalizado"), width=120, alignment=ft.alignment.center), numeric=True),
                    ft.DataColumn(ft.Container(content=ft.Text("Perfil", weight="bold", color="white"), width=180, alignment=ft.alignment.center_left)),
                ],
                rows=filas,
                heading_row_color="black",
                border=ft.border.all(1, "white10"),
                column_spacing=10,
                heading_row_height=60,
                data_row_max_height=50,
                data_row_min_height=50
            )

            # Altura matemática + 30px de respiro para los bordes y líneas divisorias
            altura_tabla = 60 + (len(filas) * 50) + 30 
            
            altura_contenedor = min(270, altura_tabla)

            # Contenedor limpio con scroll nativo visible
            contenedor_tabla_nativa = ft.Row(
                scroll=ft.ScrollMode.ALWAYS,
                controls=[
                    ft.Container(
                        height=altura_contenedor,
                        content=ft.Column(
                            controls=[tabla],
                            scroll=ft.ScrollMode.ALWAYS
                        )
                    )
                ]
            )
            
            # Ajuste dinámico del modal sin dejar espacios vacíos
            alto_pantalla = self.page.height if self.page.height else 600
            columna_content.height = min(alto_pantalla - 50, altura_contenedor + 150) 
            
            columna_content.controls = [
                ft.Text(titulo, size=18, weight="bold", color="white"),
                ft.Container(height=10),
                contenedor_tabla_nativa,
                ft.Container(height=10),
                ft.Row([ft.ElevatedButton("Cerrar", on_click=lambda e: self._limpiar_memoria_dialogo(self.dlg_cambios))], alignment=ft.MainAxisAlignment.END)
            ]
            self.dlg_cambios.update()
            
        threading.Thread(target=_cargar, daemon=True).start()

    def _seleccionar_rival_admin(self, id_rival):
        self.rival_seleccionado_id = id_rival
        encontrado = False
        for row in self.tabla_rivales.rows:
            if row.data == id_rival:
                row.color = "#8B0000"
                try:
                    nombre_ui = row.cells[0].content.content.value
                    self.input_admin_nombre.value = nombre_ui
                    self.input_admin_nombre.update()
                except Exception as e:
                    pass
                encontrado = True
            else:
                row.color = None
        if encontrado:
            self.tabla_rivales.update()

    def _guardar_rival_admin(self, e):
        if not self.rival_seleccionado_id:
            GestorMensajes.mostrar(self.page, "Error", "Seleccione un equipo de la tabla.", "error")
            return
            
        nombre = self.input_admin_nombre.value.strip()
        
        if not nombre:
            GestorMensajes.mostrar(self.page, "Error", "El nombre es obligatorio.", "error")
            return

        def _guardar():
            self.loading_partidos.visible = True
            self.loading_pronosticos.visible = True
            self.loading_admin.visible = True
            self.page.update()
            try:
                bd = BaseDeDatos()
                bd.actualizar_rival(self.rival_seleccionado_id, nombre) # <--- Ahora solo enviamos 2 parámetros
                
                GestorMensajes.mostrar(self.page, "Éxito", "Equipo actualizado.", "exito")
                self.rival_seleccionado_id = None
                self.input_admin_nombre.value = ""
                
                self._recargar_datos(actualizar_partidos=True, actualizar_pronosticos=True, actualizar_ranking=False, actualizar_admin=True, actualizar_copas=False)
            except Exception as ex:
                GestorMensajes.mostrar(self.page, "Error al guardar", str(ex), "error")
                self.loading_partidos.visible = False
                self.loading_pronosticos.visible = False
                self.loading_admin.visible = False
                self.page.update()

        threading.Thread(target=_guardar, daemon=True).start()

    def _guardar_contrasena_config(self, e):
        """
        Valida y guarda el cambio de contraseña desde la pestaña Configuración.
        """
        p1 = self.input_conf_pass_1.value
        p2 = self.input_conf_pass_2.value

        # --- 1. Validaciones Visuales ---
        if not p1 or not p2:
            GestorMensajes.mostrar(self.page, "Atención", "Por favor, complete ambos campos.", "error")
            return
        
        if p1 != p2:
            GestorMensajes.mostrar(self.page, "Error", "Las contraseñas no coinciden.", "error")
            # Opcional: Marcar bordes en rojo
            self.input_conf_pass_1.border_color = "red"
            self.input_conf_pass_2.border_color = "red"
            self.input_conf_pass_1.update()
            self.input_conf_pass_2.update()
            return
        else:
            # Restaurar bordes si coinciden
            self.input_conf_pass_1.border_color = "white24"
            self.input_conf_pass_2.border_color = "white24"
            self.input_conf_pass_1.update()
            self.input_conf_pass_2.update()

        if len(p1) < 4:
            GestorMensajes.mostrar(self.page, "Seguridad", "La contraseña es muy corta (mínimo 4 caracteres).", "info")
            return

        # --- 2. Guardado en Segundo Plano ---
        def _tarea():
            # Deshabilitar botón para evitar doble clic
            self.btn_conf_guardar_pass.disabled = True
            self.btn_conf_guardar_pass.text = "Guardando..."
            self.btn_conf_guardar_pass.update()
            
            try:
                bd = BaseDeDatos()
                # Usamos la función cambiar_contrasena que ya tienes en base_de_datos.py
                # (Sirve tanto para recuperar como para cambiar estando logueado)
                bd.cambiar_contrasena(self.usuario_actual, p1)
                
                GestorMensajes.mostrar(self.page, "Éxito", "Contraseña actualizada correctamente.", "exito")
                
                # Limpiar campos
                self.input_conf_pass_1.value = ""
                self.input_conf_pass_2.value = ""
                self.input_conf_pass_1.update()
                self.input_conf_pass_2.update()
                
            except Exception as ex:
                GestorMensajes.mostrar(self.page, "Error", f"No se pudo cambiar: {ex}", "error")
            
            finally:
                # Rehabilitar botón
                self.btn_conf_guardar_pass.disabled = False
                self.btn_conf_guardar_pass.text = "Guardar nueva clave"
                self.btn_conf_guardar_pass.update()

        threading.Thread(target=_tarea, daemon=True).start()

    def _recargar_datos(self, actualizar_partidos=False, actualizar_pronosticos=False, actualizar_ranking=False, actualizar_copas=True, actualizar_admin=False):
        """
        Recarga los datos de las tablas solicitadas en segundo plano.
        """
        if actualizar_partidos: self.cargando_partidos = True
            
        if not any([actualizar_partidos, actualizar_pronosticos, actualizar_ranking, actualizar_admin]):
            return

        # --- SPINNERS ---
        if actualizar_ranking: self.loading.visible = True
        if actualizar_ranking and actualizar_copas and self.filtro_ranking_edicion_id is None: 
            self.loading_copas.visible = True 
        if actualizar_partidos: 
            self.loading_partidos.visible = True
            self._bloquear_botones_filtros(True) 
        if actualizar_pronosticos: 
            self.loading_pronosticos.visible = True
            self.tabla_pronosticos_header.sort_column_index = self.pronosticos_sort_col_index
            self.tabla_pronosticos_header.sort_ascending = self.pronosticos_sort_asc
            self.tabla_pronosticos.sort_column_index = None # Aseguramos que abajo no haya flecha
        if actualizar_admin: self.loading_admin.visible = True
        
        self.page.update()

        # Lanzamos el hilo pasando los argumentos necesarios
        threading.Thread(
            target=self._tarea_en_segundo_plano, 
            args=(actualizar_ranking, actualizar_copas, actualizar_partidos, actualizar_pronosticos, actualizar_admin), 
            daemon=True
        ).start()

    def _limpiar_memoria_dialogo(self, dialogo):
        """
        Cierra el diálogo y destruye el árbol de controles de forma segura
        sin romper las reglas estrictas de renderizado de Flet.
        """
        if not dialogo:
            return
            
        try:
            self.page.close(dialogo) # 1. Oculta la ventana de la pantalla
            
            def _vaciar_ram():
                time.sleep(0.4) # 2. Dar tiempo a que termine la animación
                try:
                    # 3. TRUCO: En lugar de usar None, usamos un contenedor vacío.
                    # Esto evita el AssertionError de Flet y libera la memoria del gráfico.
                    if hasattr(dialogo, 'content'):
                        dialogo.content = ft.Container() 
                    if hasattr(dialogo, 'actions'):
                        dialogo.actions = []
                except:
                    pass
                
                # 4. Obligar a Windows a recuperar la memoria RAM libre
                gc.collect() 
                
            threading.Thread(target=_vaciar_ram, daemon=True).start()
        except Exception as e:
            self._enviar_alerta_correo_admins("Error al limpiar memoria de diálogo", f"Error al limpiar memoria de diálogo: {e}", tipo=str(e), nombre_función="SistemaIndependiente._limpiar_memoria_dialogo")
            pass

    def _tarea_en_segundo_plano(self, actualizar_ranking, actualizar_copas, actualizar_partidos, actualizar_pronosticos, actualizar_admin):
        """
        Esta función se ejecuta en un hilo separado.
        """
        time.sleep(0.5) 
        try:
            bd = BaseDeDatos()
            
            # ------------------------------------------
            # 1. RANKING (TABLA POSICIONES)
            # ------------------------------------------
            if actualizar_ranking:
                datos_ranking = bd.obtener_ranking(self.filtro_ranking_edicion_id, self.filtro_ranking_anio)
                filas_ranking = []
                for i, fila in enumerate(datos_ranking, start=1):
                    # Indices basados en la nueva query SQL:
                    # 0:User, 1:Total, 2:Res, 3:Cai, 4:Riv, 5:PJ, 6:Ant, 7:Error
                    user = fila[0]
                    total = fila[1]
                    pts_res = fila[2]
                    pts_cai = fila[3]
                    pts_rival = fila[4]
                    pj = fila[5]
                    raw_seconds = fila[6] 
                    raw_error = fila[7]
                    efectividad = fila[8]
                    
                    user_display = f"🏆 {user}" if i == 1 else user

                    # --- Procesar Efectividad ---
                    if efectividad is not None:
                        txt_efectividad = f"{float(efectividad):.2f}".replace('.', ',')
                    else:
                        txt_efectividad = "0,00"

                    # --- Procesar Anticipación ---
                    if raw_seconds is not None:
                        val_sec = float(raw_seconds)
                        dias = int(val_sec // 86400)
                        resto = val_sec % 86400
                        horas_disp = int(resto // 3600)
                        resto %= 3600
                        minutos = int(resto // 60)
                        segundos = resto % 60
                        
                        if dias > 0:
                            txt_dias = "1 día" if dias == 1 else f"{dias} días"
                            txt_ant = f"{txt_dias} {horas_disp:02d}:{minutos:02d}:{segundos:05.2f} h"
                        else:
                            txt_ant = f"{horas_disp:02d}:{minutos:02d}:{segundos:05.2f} h"
                    else:
                        txt_ant = "00:00:00.00 h"

                    # --- Procesar Error ---
                    if raw_error is not None:
                        val_error = float(raw_error)
                        txt_error = f"{val_error:.2f}".replace('.', ',')
                        color_error = self._obtener_color_error(val_error)
                    else:
                        txt_error = "-"
                        color_error = "white54"

                    color_fila = "#8B0000" if user == self.usuario_seleccionado_ranking else None
                    evento_click = lambda e, u=user: self._seleccionar_fila_ranking(u)

                    filas_ranking.append(ft.DataRow(
                        cells=[
                            ft.DataCell(ft.Container(content=ft.Text(f"{i}º", weight="bold", color="white", text_align=ft.TextAlign.CENTER), width=50, alignment=ft.alignment.center, padding=0, on_click=evento_click)),
                            ft.DataCell(ft.Container(content=ft.Text(user_display, weight="bold", color="white", text_align=ft.TextAlign.CENTER), width=ANCHO_COLUMNA_USUARIO, alignment=ft.alignment.center, padding=0, on_click=evento_click)),
                            ft.DataCell(ft.Container(content=ft.Text(str(total), weight="bold", color="yellow", size=16, text_align=ft.TextAlign.CENTER), width=75, alignment=ft.alignment.center, padding=0, on_click=evento_click)),
                            ft.DataCell(ft.Container(content=ft.Text(str(pts_cai), color="white", text_align=ft.TextAlign.CENTER), width=75, alignment=ft.alignment.center, padding=0, on_click=evento_click)),
                            ft.DataCell(ft.Container(content=ft.Text(str(pts_rival), color="white", text_align=ft.TextAlign.CENTER), width=75, alignment=ft.alignment.center, padding=0, on_click=evento_click)),
                            ft.DataCell(ft.Container(content=ft.Text(str(pts_res), color="white", text_align=ft.TextAlign.CENTER), width=75, alignment=ft.alignment.center, padding=0, on_click=evento_click)),
                            ft.DataCell(ft.Container(content=ft.Text(str(pj), color="cyan", text_align=ft.TextAlign.CENTER), width=70, alignment=ft.alignment.center, padding=0, on_click=evento_click)),
                            ft.DataCell(ft.Container(content=ft.Text(txt_error, color=color_error, text_align=ft.TextAlign.CENTER), width=80, alignment=ft.alignment.center, padding=0, on_click=evento_click)),
                            ft.DataCell(ft.Container(content=ft.Text(txt_ant, color="cyan", size=12, text_align=ft.TextAlign.CENTER), width=190, alignment=ft.alignment.center, padding=0, on_click=evento_click)),
                            ft.DataCell(ft.Container(content=ft.Text(f"{txt_efectividad} %", color="pink", text_align=ft.TextAlign.CENTER), width=80, alignment=ft.alignment.center, padding=0, on_click=evento_click)),
                        ],
                        color=color_fila,
                        data=user 
                    ))
                self.tabla_estadisticas.rows = filas_ranking
                self.tabla_estadisticas.update()

            # ------------------------------------------
            # 2. COPAS (TORNEOS GANADOS)
            # ------------------------------------------
            if actualizar_copas and self.filtro_ranking_edicion_id is None:
                datos_copas = bd.obtener_torneos_ganados(self.filtro_ranking_anio)
                filas_copas = []
                
                # --- NUEVA LÓGICA DE TROFEOS ---
                max_copas = 0
                if datos_copas:
                    # Encontramos la cantidad máxima de copas que alguien tenga en esta lista
                    max_copas = max([int(fila[1]) for fila in datos_copas])

                for i, fila in enumerate(datos_copas, start=1):
                    user = fila[0]
                    copas = int(fila[1])
                    
                    # Condición de victoria: Tienen el máximo de copas Y es mayor a cero.
                    if copas == max_copas and copas > 0:
                        user_display = f"🏆 {user}"
                    else:
                        user_display = user
                    
                    filas_copas.append(ft.DataRow(cells=[
                        ft.DataCell(ft.Container(content=ft.Text(f"{i}º", weight=ft.FontWeight.BOLD, color="white"), width=60, alignment=ft.alignment.center)),
                        ft.DataCell(ft.Container(content=ft.Text(user_display, weight=ft.FontWeight.BOLD, color="white"), width=ANCHO_COLUMNA_USUARIO, alignment=ft.alignment.center_left)),
                        ft.DataCell(ft.Container(content=ft.Text(str(copas), weight=ft.FontWeight.BOLD, color="yellow", size=16), width=120, alignment=ft.alignment.center)),
                    ]))
                self.tabla_copas.rows = filas_copas

            # ------------------------------------------
            # 3. PARTIDOS
            # ------------------------------------------
            if actualizar_partidos:
                datos_partidos_user = bd.obtener_partidos(
                    self.usuario_actual, 
                    filtro_tiempo=self.filtro_temporal, 
                    edicion_id=self.filtro_edicion_id, 
                    rival_id=self.filtro_rival_id, 
                    solo_sin_pronosticar=self.filtro_sin_pronosticar
                )
                filas_tabla_partidos = []
                for fila in datos_partidos_user:
                    p_id = fila[0]
                    rival = fila[1]
                    torneo = fila[3]
                    gc = fila[4]
                    gr = fila[5]
                    fecha_display_str = fila[7] 
                    pred_cai = fila[8]
                    pred_rival = fila[9]
                    puntos_usuario = fila[10] 
                    error_abs = fila[11]

                    # --- EXTRACCIÓN DE NUEVOS DATOS ---
                    condicion_num = fila[12]

                    if condicion_num == 1: txt_condicion = "Local"
                    elif condicion_num == -1: txt_condicion = "Visitante"
                    elif condicion_num == 0: txt_condicion = "Neutral"
                    else: txt_condicion = "-"

                    if gc is not None and gr is not None: texto_resultado = f"{gc} a {gr}"
                    else: texto_resultado = "-"
                    if pred_cai is not None and pred_rival is not None: texto_pronostico = f"{pred_cai} a {pred_rival}"
                    else: texto_pronostico = "-"
                    if puntos_usuario is None: texto_puntos = "-"
                    else: texto_puntos = f"{puntos_usuario}"

                    # --- LOGICA ERROR ABSOLUTO TABLA PARTIDOS ---
                    if error_abs is None:
                        txt_error = "-"
                        color_error = "white70"
                    else:
                        val_err = float(error_abs)
                        txt_error = str(int(val_err))
                        color_error = self._obtener_color_error(val_err)

                    es_partido_jugado = (gc is not None)

                    if not es_partido_jugado:
                        evt_click = lambda e, id=p_id: self._seleccionar_partido_click(id)
                        color_fila = "#8B0000" if p_id == self.partido_a_pronosticar_id else None
                    else:
                        evt_click = None 
                        color_fila = None 

                    filas_tabla_partidos.append(ft.DataRow(
                        cells=[
                            ft.DataCell(ft.Container(content=ft.Text(str(rival), weight=ft.FontWeight.BOLD, color="white"), width=190, alignment=ft.alignment.center_left, on_click=evt_click)),
                            ft.DataCell(ft.Container(content=ft.Text(texto_resultado, color="white"), width=80, alignment=ft.alignment.center, on_click=evt_click)),
                            ft.DataCell(ft.Container(content=ft.Text(fecha_display_str, color="white70"), width=140, alignment=ft.alignment.center_left, on_click=evt_click)), 
                            
                            ft.DataCell(ft.Container(content=ft.Text(txt_condicion, color="white"), width=90, alignment=ft.alignment.center, on_click=evt_click)),
                            
                            ft.DataCell(ft.Container(content=ft.Text(str(torneo), color="yellow"), width=150, alignment=ft.alignment.center_left, on_click=evt_click)),
                            ft.DataCell(ft.Container(content=ft.Text(texto_pronostico, color="cyan"), width=100, alignment=ft.alignment.center, on_click=evt_click)),
                            ft.DataCell(ft.Container(content=ft.Text(texto_puntos, color="green", size=15), width=80, alignment=ft.alignment.center, on_click=evt_click)),
                            ft.DataCell(ft.Container(content=ft.Text(txt_error, color=color_error, size=14), width=80, alignment=ft.alignment.center, on_click=evt_click))
                        ],
                        data=p_id,
                        color=color_fila 
                    ))
                self.tabla_partidos.rows = filas_tabla_partidos

            # ------------------------------------------
            # 4. PRONÓSTICOS
            # ------------------------------------------
            if actualizar_pronosticos:
                datos_raw = bd.obtener_todos_pronosticos(
                    filtro_tiempo=self.filtro_pron_tiempo,
                    filtro_torneo=self.filtro_pron_torneo,
                    filtro_equipo=self.filtro_pron_equipo,
                    filtro_usuario=self.filtro_pron_usuario
                )
                filas_filtradas = []
                
                for row in datos_raw:
                    fecha_partido = row[1]
                    gc, gr = row[3], row[4]
                    pc, pr = row[6], row[7]
                    pts, err_abs = row[8], row[10]
                    
                    res_txt = f"{gc}-{gr}" if gc is not None else "-"
                    pron_txt = f"{pc}-{pr}"
                    
                    if fecha_partido.time().strftime('%H:%M:%S') == '00:00:00': fecha_disp = fecha_partido.strftime('%d/%m/%Y')
                    else: fecha_disp = fecha_partido.strftime('%d/%m/%Y %H:%M')
                        
                    fecha_pred_disp = row[9].strftime('%d/%m/%Y %H:%M:%S') if row[9] else "-"
                    puntos_disp = str(pts) if pts is not None else "-"
                    
                    if err_abs is not None:
                        val_err = float(err_abs)
                        err_disp = str(int(val_err))
                        color_err = self._obtener_color_error(val_err)
                    else:
                        err_disp = "-"
                        color_err = "white70"

                    row_key = hash(row)
                    color_fila_pron = "#8B0000" if row_key == self.pronostico_seleccionado_key else None
                    evt_click_pron = lambda e, k=row_key: self._seleccionar_fila_pronostico(k)

                    filas_filtradas.append(ft.DataRow(
                        cells=[
                            ft.DataCell(ft.Container(content=ft.Text(row[0], color="white", weight=ft.FontWeight.BOLD), width=190, alignment=ft.alignment.center_left, on_click=evt_click_pron)),
                            ft.DataCell(ft.Container(content=ft.Text(fecha_disp, color="white"), width=140, alignment=ft.alignment.center, on_click=evt_click_pron)),
                            ft.DataCell(ft.Container(content=ft.Text(row[2], color="yellow"), width=150, alignment=ft.alignment.center_left, on_click=evt_click_pron)),
                            ft.DataCell(ft.Container(content=ft.Text(res_txt, color="white"), width=80, alignment=ft.alignment.center, on_click=evt_click_pron)), 
                            ft.DataCell(ft.Container(content=ft.Text(row[5], color="white", weight=ft.FontWeight.BOLD), width=ANCHO_PRONÓSTICO_USUARIO, alignment=ft.alignment.center_left, on_click=evt_click_pron)), 
                            ft.DataCell(ft.Container(content=ft.Text(pron_txt, color="cyan"), width=80, alignment=ft.alignment.center, on_click=evt_click_pron)), 
                            ft.DataCell(ft.Container(content=ft.Text(fecha_pred_disp, color="white70"), width=160, alignment=ft.alignment.center, on_click=evt_click_pron)), 
                            ft.DataCell(ft.Container(content=ft.Text(puntos_disp, color="green"), width=60, alignment=ft.alignment.center, on_click=evt_click_pron)), 
                            ft.DataCell(ft.Container(content=ft.Text(err_disp, color=color_err), width=80, alignment=ft.alignment.center, on_click=evt_click_pron)), 
                        ],
                        color=color_fila_pron,
                        data=row_key 
                    ))
                
                if self.pronosticos_sort_col_index is not None:
                    idx = self.pronosticos_sort_col_index
                    reverse_sort = not self.pronosticos_sort_asc
                    def key_sort(row):
                        try:
                            val = row.cells[idx].content.content.value
                            if idx in [7, 8]: 
                                if val == "-": return -999
                                val_clean = val.replace(',', '.')
                                return float(val_clean)
                            if idx in [1, 6]:
                                try:
                                    if ":" in val:
                                        if val.count(":") == 2: return datetime.strptime(val, "%d/%m/%Y %H:%M:%S")
                                        if val.count("/") == 2: return datetime.strptime(val, "%d/%m/%Y %H:%M")
                                        return datetime.strptime(val, "%d/%m %H:%M")
                                    return datetime.strptime(val, "%d/%m/%Y")
                                except: return val
                            return str(val).lower()
                        except: return ""
                    filas_filtradas.sort(key=key_sort, reverse=reverse_sort)
                
                self.tabla_pronosticos.rows = filas_filtradas

            # ------------------------------------------
            # 5. ADMINISTRACIÓN
            # ------------------------------------------
            if actualizar_admin:
                # --- EQUIPOS ---
                datos_rivales = bd.obtener_rivales_completo()
                filas_admin = []
                for fila in datos_rivales:
                    r_id = fila[0]
                    nombre = fila[1]
                    color_row = "#8B0000" if r_id == self.rival_seleccionado_id else None
                    
                    filas_admin.append(ft.DataRow(
                        cells=[
                            ft.DataCell(ft.Container(
                                # AQUI AGREGAMOS MAX_LINES Y OVERFLOW
                                content=ft.Text(nombre, color="white", max_lines=2, overflow=ft.TextOverflow.ELLIPSIS), 
                                width=ANCHO_RIVALES_NOMBRE, 
                                alignment=ft.alignment.center_left, 
                                on_click=lambda e, id=r_id: self._seleccionar_rival_admin(id)
                            )),
                        ],
                        data=r_id,
                        color=color_row
                    ))
                self.tabla_rivales.rows = filas_admin
                
                # --- TORNEOS ---
                datos_torneos = bd.obtener_campeonatos_completo()
                filas_torneos = []
                for fila in datos_torneos:
                    t_id = fila[0]
                    nombre = fila[1]
                    color_row = "#8B0000" if t_id == self.torneo_seleccionado_id else None
                    
                    filas_torneos.append(ft.DataRow(
                        cells=[
                            ft.DataCell(ft.Container(
                                # AQUI AGREGAMOS MAX_LINES Y OVERFLOW
                                content=ft.Text(nombre, color="white", max_lines=2, overflow=ft.TextOverflow.ELLIPSIS), 
                                width=ANCHO_TORNEOS_NOMBRE, 
                                alignment=ft.alignment.center_left, 
                                on_click=lambda e, id=t_id: self._seleccionar_torneo_admin(id)
                            )),
                        ],
                        data=t_id,
                        color=color_row
                    ))
                self.tabla_torneos.rows = filas_torneos
                
                self.tabla_rivales.update()
                self.tabla_torneos.update()
                self.page.update()

        except Exception as e:
            GestorMensajes.mostrar(self.page, "Error recargando datos", f"{e}", "error")
            self._enviar_alerta_correo_admins("Error al recargar datos", f"Ocurrió un error al recargar los datos", tipo=str(e), nombre_función="SistemaIndependiente._tarea_en_segundo_plano")
        finally:
            self.loading.visible = False
            self.loading_copas.visible = False 
            self.loading_partidos.visible = False
            self.loading_pronosticos.visible = False 
            self.loading_admin.visible = False
            
            if actualizar_partidos: 
                self.cargando_partidos = False
                self._bloquear_botones_filtros(False) 
                self._actualizar_botones_partidos_visual()
            if actualizar_pronosticos:
                self._actualizar_botones_pronosticos_visual()
                
            self.page.update()

    def _abrir_modal_racha_record(self, e):
        """Abre la ventana modal con la Racha Récord."""
        
        if self.filtro_ranking_nombre: 
             titulo = f"Racha récord ({self.filtro_ranking_nombre})"
        elif self.filtro_ranking_anio:
             titulo = f"Racha récord ({self.filtro_ranking_anio})"
        else:
             titulo = "Racha récord en la historia"
             
        self.loading_modal = ft.ProgressBar(width=200, color="amber", bgcolor="#222222")
        
        # Ancho dinámico para que no se salga del celular
        ancho_pantalla = self.page.width if self.page.width else 600
        ancho_modal = min(500, ancho_pantalla - 20)
        
        columna_content = ft.Column(
            controls=[
                ft.Text(titulo, size=18, weight="bold", color="white"),
                ft.Container(height=10),
                self.loading_modal,
                ft.Container(height=20)
            ],
            height=150,
            width=ancho_modal,
            scroll=ft.ScrollMode.ALWAYS # Barra vertical nativa siempre activa
        )
        
        self.dlg_racha_record = ft.AlertDialog(content=columna_content, modal=True)
        self.page.open(self.dlg_racha_record)

        def _cargar():
            bd = BaseDeDatos()
            datos = bd.obtener_racha_record(self.filtro_ranking_edicion_id, self.filtro_ranking_anio)
            
            filas = []
            for i, row in enumerate(datos, start=1):
                user = row[0]
                racha = row[1]
                
                color_racha = "white"
                if racha >= 10: color_racha = "purple"
                elif racha >= 7: color_racha = "cyan"
                elif racha >= 4: color_racha = "green"

                filas.append(ft.DataRow(cells=[
                    ft.DataCell(ft.Container(content=ft.Text(f"{i}º", weight="bold", color="white"), width=50, alignment=ft.alignment.center)),
                    ft.DataCell(ft.Container(content=ft.Text(user, weight="bold", color="white"), width=ANCHO_COLUMNA_USUARIO, alignment=ft.alignment.center_left)),
                    ft.DataCell(ft.Container(content=ft.Text(str(racha), weight="bold", color=color_racha), width=100, alignment=ft.alignment.center)),
                ]))
            
            tabla = ft.DataTable(
                columns=[
                    ft.DataColumn(ft.Container(content=ft.Text("Puesto", weight="bold", color="white"), width=50, alignment=ft.alignment.center)),
                    ft.DataColumn(ft.Container(content=ft.Text("Usuario", weight="bold", color="white"), width=ANCHO_COLUMNA_USUARIO, alignment=ft.alignment.center_left)),
                    ft.DataColumn(ft.Container(content=ft.Text("Racha récord", text_align="center", weight="bold", color="white"), width=100, alignment=ft.alignment.center), numeric=True),
                ],
                rows=filas,
                heading_row_color="black",
                border=ft.border.all(1, "white10"),
                column_spacing=10,
                heading_row_height=60,
                data_row_max_height=50,
                data_row_min_height=50
            )

            # Altura matemática + 30px de respiro para los bordes
            altura_tabla = 60 + (len(filas) * 50) + 30 
            altura_contenedor = min(400, altura_tabla) 

            # Contenedor limpio con scroll nativo visible
            contenedor_tabla_nativa = ft.Row(
                scroll=ft.ScrollMode.ALWAYS,
                controls=[
                    ft.Container(
                        height=altura_contenedor,
                        content=ft.Column(
                            controls=[tabla],
                            scroll=ft.ScrollMode.ALWAYS
                        )
                    )
                ]
            )
            
            # Ajuste dinámico del modal sin dejar espacios vacíos
            alto_pantalla = self.page.height if self.page.height else 600
            columna_content.height = min(alto_pantalla - 50, altura_contenedor + 150) 
            
            columna_content.controls = [
                ft.Text(titulo, size=18, weight="bold", color="white"),
                ft.Container(height=10),
                contenedor_tabla_nativa,
                ft.Container(height=10),
                ft.Row([ft.ElevatedButton("Cerrar", on_click=lambda e: self._limpiar_memoria_dialogo(self.dlg_racha_record))], alignment=ft.MainAxisAlignment.END)
            ]
            self.dlg_racha_record.update()
            
        threading.Thread(target=_cargar, daemon=True).start()

    def _iniciar_cambio_email(self, e):
        """Valida el email replicando los CHECK de SQL, verifica disponibilidad y envía código."""
        nuevo_email = self.input_conf_email.value.strip() if self.input_conf_email.value else ""
        
        # --- 1. VALIDACIONES FRONTEND (REPLICA DE CHECK SQL) ---
        if not nuevo_email:
            GestorMensajes.mostrar(self.page, "Error", "Ingrese un correo válido.", "error")
            return
            
        if " " in nuevo_email:
            GestorMensajes.mostrar(self.page, "Error", "El correo no puede contener espacios en blanco.", "error")
            return
            
        if nuevo_email.count('@') != 1:
            GestorMensajes.mostrar(self.page, "Error", "El correo debe tener exactamente un '@'.", "error")
            return
            
        usuario_correo, dominio = nuevo_email.split('@')
        
        if not usuario_correo or not dominio or '.' not in dominio:
            GestorMensajes.mostrar(self.page, "Error", "Estructura de correo incompleta (falta usuario o dominio).", "error")
            return
            
        if usuario_correo.startswith('.') or usuario_correo.endswith('.'):
            GestorMensajes.mostrar(self.page, "Error", "El nombre del correo no puede empezar ni terminar con un punto.", "error")
            return
            
        if dominio.startswith('-') or dominio.endswith('-'):
            GestorMensajes.mostrar(self.page, "Error", "El dominio no puede empezar ni terminar con un guion.", "error")
            return
            
        if '-.' in dominio or '.-' in dominio:
            GestorMensajes.mostrar(self.page, "Error", "El guion no puede estar pegado al punto en el dominio.", "error")
            return

        def _tarea_envio():
            self.btn_conf_guardar_email.disabled = True
            self.btn_conf_guardar_email.text = "Enviando..."
            self.btn_conf_guardar_email.update()
            
            try:
                bd = BaseDeDatos()
                bd.verificar_email_libre(nuevo_email, self.usuario_actual) 
                
                # Generar código
                self.codigo_verificacion_temp = str(random.randint(100000, 999999))
                self.email_pendiente_cambio = nuevo_email
                
                if REMITENTE == "tu_correo@gmail.com":
                    print(f"--- MODO DEBUG: EL CÓDIGO ES {self.codigo_verificacion_temp} ---")
                else:
                    msg = MIMEMultipart()
                    msg['From'] = REMITENTE
                    msg['To'] = nuevo_email
                    msg['Subject'] = "Código de verificación - Sistema CAI"
                    cuerpo = f"Hola {self.usuario_actual},\n\nTu código para cambiar el correo es: {self.codigo_verificacion_temp}\n\nSi no solicitaste esto, ignora este mensaje."
                    msg.attach(MIMEText(cuerpo, 'plain'))
                    
                    server = smtplib.SMTP('smtp.gmail.com', 587)
                    server.starttls()
                    server.login(REMITENTE, PASSWORD)
                    server.send_message(msg)
                    server.quit()

                # Abrir Modal de validación
                self._abrir_modal_codigo_email()
                
            except Exception as ex:
                GestorMensajes.mostrar(self.page, "Error", str(ex), "error")
                self._enviar_alerta_correo_admins("Error al enviar código de verificación", f"Error al enviar código de verificación para cambio de correo", tipo=str(ex), nombre_función="SistemaIndependiente._iniciar_cambio_email._tarea_envio")
            finally:
                self.btn_conf_guardar_email.disabled = False
                self.btn_conf_guardar_email.text = "Enviar código"
                self.btn_conf_guardar_email.update()

        threading.Thread(target=_tarea_envio, daemon=True).start()

    def _abrir_modal_codigo_email(self):
        """Abre el popup para ingresar el código recibido."""
        self.input_codigo_verif = ft.TextField(
            label="Código de 6 dígitos", 
            text_align=ft.TextAlign.CENTER, 
            max_length=6, 
            width=200,
            bgcolor="#2D2D2D",
            border_color="cyan",
            on_change=self._limpiar_error_codigo  # <--- AGREGADO: Limpia error al escribir
        )
        
        # Guardamos el botón en self para poder modificarlo luego (loading)
        self.btn_confirmar_codigo = ft.ElevatedButton(
            "Confirmar", 
            bgcolor="green", 
            color="white", 
            on_click=self._confirmar_cambio_email
        )
        
        self.dlg_validar_email = ft.AlertDialog(
            modal=True,
            title=ft.Text("Verificar Correo"),
            content=ft.Column(
                [
                    ft.Text(f"Se envió un código a:\n{self.email_pendiente_cambio}", size=12, color="white70", text_align="center"),
                    ft.Container(height=10),
                    self.input_codigo_verif
                ],
                height=120,
                width=300,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: self._limpiar_memoria_dialogo(self.dlg_validar_email)),
                self.btn_confirmar_codigo # <--- Usamos la variable creada arriba
            ],
            actions_alignment=ft.MainAxisAlignment.CENTER
        )
        self.page.open(self.dlg_validar_email)

    def _limpiar_error_codigo(self, e):
        """Limpia el mensaje de error visual cuando el usuario escribe."""
        if self.input_codigo_verif.error_text is not None:
            self.input_codigo_verif.error_text = None
            self.input_codigo_verif.border_color = "cyan"
            self.input_codigo_verif.update()

    def _confirmar_cambio_email(self, e):
        """Verifica el código y actualiza la BD con animación de carga."""
        
        def _tarea_verificacion():
            # 1. Estado de Carga (Animación visual)
            self.btn_confirmar_codigo.disabled = True
            self.btn_confirmar_codigo.text = "Verificando..."
            self.input_codigo_verif.disabled = True # Bloquear input mientras carga
            
            self.btn_confirmar_codigo.update()
            self.input_codigo_verif.update()
            
            # Pequeña pausa artificial para que el usuario alcance a leer "Verificando..."
            # (opcional, pero mejora la UX si la BD es muy rápida)
            time.sleep(0.5) 

            codigo_ingresado = self.input_codigo_verif.value.strip()
            
            if codigo_ingresado == self.codigo_verificacion_temp:
                try:
                    bd = BaseDeDatos()
                    bd.actualizar_email_usuario(self.usuario_actual, self.email_pendiente_cambio)
                    
                    self._limpiar_memoria_dialogo(self.dlg_validar_email)
                    GestorMensajes.mostrar(self.page, "Éxito", "Correo electrónico actualizado correctamente.", "exito")
                    
                    # Limpiar campo original
                    self.input_conf_email.value = ""
                    self.input_conf_email.update()
                    
                except Exception as ex:
                    # Error de base de datos
                    self._limpiar_memoria_dialogo(self.dlg_validar_email)
                    GestorMensajes.mostrar(self.page, "Error", f"Error en base de datos: {ex}", "error")
                    self._enviar_alerta_correo_admins("Error al actualizar correo", f"Error al actualizar correo de usuario {self.usuario_actual}", tipo=str(ex), nombre_función="SistemaIndependiente._confirmar_cambio_email._tarea_verificacion")
            else:
                # Código Incorrecto: Restaurar controles y mostrar error
                self.btn_confirmar_codigo.disabled = False
                self.btn_confirmar_codigo.text = "Confirmar"
                self.input_codigo_verif.disabled = False
                
                self.input_codigo_verif.border_color = "red"
                self.input_codigo_verif.error_text = "Código incorrecto"
                
                self.btn_confirmar_codigo.update()
                self.input_codigo_verif.update()

        # Ejecutar en hilo secundario
        threading.Thread(target=_tarea_verificacion, daemon=True).start()

    def _abrir_selector_torneo(self, e):
        if self.filtro_edicion_id is not None:
            self.filtro_edicion_id = None
            self._actualizar_botones_partidos_visual()
            self._actualizar_titulo_partidos()
            self._recargar_datos(actualizar_partidos=True, actualizar_copas=False)
        else:
            loading_content = ft.Column(
                controls=[
                    ft.Text("Cargando filtros...", size=16, weight="bold", color="white"),
                    ft.ProgressBar(width=200, color="amber", bgcolor="#222222")
                ],
                height=80, width=300, alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER
            )
            self.dlg_carga_filtros = ft.AlertDialog(content=loading_content, modal=True)
            self.page.open(self.dlg_carga_filtros)

            def _cargar_datos_modal():
                time.sleep(0.5)
                
                self.temp_campeonato_sel = None
                self.modal_torneo_es_opcional = False
                self.txt_titulo_torneo_modal = ft.Text("1. Torneo (Obligatorio)", weight=ft.FontWeight.BOLD, color="white")
                self.txt_titulo_anio_modal = ft.Text("2. Año (Obligatorio)", weight=ft.FontWeight.BOLD, color="white")
                
                self.lv_torneos = ft.Column(scroll=ft.ScrollMode.ALWAYS, spacing=5)
                self.lv_anios = ft.Column(scroll=ft.ScrollMode.ALWAYS, spacing=5)
                
                self.btn_ver_torneo = ft.ElevatedButton("Ver", icon=ft.Icons.VISIBILITY, disabled=True, on_click=self._confirmar_filtro_torneo)
                
                try:
                    bd = BaseDeDatos()
                    # --- CAMBIO APLICADO: TODOS LOS TORNEOS ---
                    ediciones = bd.obtener_ediciones(solo_finalizados=False)
                    self.cache_ediciones_modal = ediciones
                    nombres_unicos = sorted(list(set(e[1] for e in ediciones)))
                    
                    controles = []
                    for nombre in nombres_unicos:
                        controles.append(ft.ListTile(title=ft.Text(nombre, size=14), data=nombre, on_click=self._seleccionar_campeonato_modal, bgcolor="#2D2D2D", shape=ft.RoundedRectangleBorder(radius=5)))
                    self.lv_torneos.controls = controles
                except Exception as ex:
                    self._mostrar_mensaje_admin("Error cargando modal", f"No se pudieron cargar los torneos: {ex}", "error", nombre_función="SistemaIndependiente._abrir_selector_torneo._cargar_datos_modal")

                es_pc = (self.page.width >= 600) if self.page.width else True
                ancho_pantalla = self.page.width if self.page.width else 600
                ancho_modal = min(500, ancho_pantalla - 20)
                ancho_caja = 200 if es_pc else (ancho_modal - 40)

                col_torneo = ft.Column(
                    controls=[
                        self.txt_titulo_torneo_modal, 
                        ft.Container(content=self.lv_torneos, height=180, width=ancho_caja, border=ft.border.all(1, "white24"), border_radius=5, padding=5)
                    ]
                )
                col_anio = ft.Column(
                    controls=[
                        self.txt_titulo_anio_modal, 
                        ft.Container(content=self.lv_anios, height=180, width=ancho_caja, border=ft.border.all(1, "white24"), border_radius=5, padding=5)
                    ]
                )

                if es_pc:
                    layout_filtros = ft.Row(controls=[col_torneo, col_anio], spacing=20, alignment=ft.MainAxisAlignment.CENTER)
                    alto_contenedor = 250
                else:
                    layout_filtros = ft.Column(controls=[col_torneo, col_anio], spacing=20, scroll=ft.ScrollMode.ALWAYS, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
                    alto_contenedor = 450

                contenido_modal = ft.Container(
                    width=ancho_modal, 
                    height=alto_contenedor, 
                    content=layout_filtros
                )

                self.dlg_modal = ft.AlertDialog(
                    modal=True, 
                    title=ft.Text("Filtrar Partidos por Torneo"), 
                    content=contenido_modal, 
                    actions=[ft.TextButton("Cancelar", on_click=lambda e: self._limpiar_memoria_dialogo(self.dlg_modal)), self.btn_ver_torneo], 
                    actions_alignment=ft.MainAxisAlignment.END
                )
                
                self._limpiar_memoria_dialogo(self.dlg_carga_filtros)
                self.page.open(self.dlg_modal)

            threading.Thread(target=_cargar_datos_modal, daemon=True).start()

    def _abrir_selector_equipo(self, e):
        """
        Lógica TOGGLE:
        - Si ya hay equipo filtrado, se DESAPLICA.
        - Si no, abre modal.
        """
        if self.filtro_rival_id is not None:
            # Desactivar
            self.filtro_rival_id = None
            self.temp_rival_sel_nombre = None # Limpiar nombre para el título
            self._actualizar_botones_partidos_visual()
            self._actualizar_titulo_partidos()
            self._recargar_datos(actualizar_partidos=True, actualizar_copas=False)
        else:
            # 1. Animación de carga inicial
            loading_content = ft.Column(
                controls=[
                    ft.Text("Cargando equipos...", size=16, weight="bold", color="white"),
                    ft.ProgressBar(width=200, color="amber", bgcolor="#222222")
                ],
                height=80, width=300, alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER
            )
            self.dlg_carga_filtros = ft.AlertDialog(content=loading_content, modal=True)
            self.page.open(self.dlg_carga_filtros)

            def _cargar_rivales_modal():
                time.sleep(0.5)
                
                # Barra vertical nativa siempre visible
                self.lv_equipos = ft.Column(scroll=ft.ScrollMode.ALWAYS, spacing=5)
                self.btn_ver_equipo = ft.ElevatedButton("Ver", icon=ft.Icons.VISIBILITY, disabled=True, on_click=self._confirmar_filtro_equipo)
                
                try:
                    bd = BaseDeDatos()
                    rivales = bd.obtener_rivales() 
                    self.cache_rivales_modal = rivales 
                    controles = []
                    for id_rival, nombre in rivales:
                        # CLAVE: no_wrap=False permite que los nombres largos bajen a una segunda línea en lugar de cortarse
                        controles.append(ft.ListTile(title=ft.Text(nombre, size=14, no_wrap=False), data=id_rival, on_click=self._seleccionar_rival_modal, bgcolor="#2D2D2D", shape=ft.RoundedRectangleBorder(radius=5)))
                    self.lv_equipos.controls = controles
                except Exception as ex:
                    self._mostrar_mensaje_admin("Error cargando modal", f"No se pudieron cargar los equipos: {ex}", "error", nombre_función="SistemaIndependiente._abrir_selector_equipo._cargar_rivales_modal")

                ancho_pantalla = self.page.width if self.page.width else 600
                ancho_modal = min(400, ancho_pantalla - 20)

                contenido_modal = ft.Container(
                    width=ancho_modal, height=400, 
                    content=ft.Column(
                        controls=[
                            ft.Text("Seleccione un Equipo", weight=ft.FontWeight.BOLD), 
                            ft.Container(
                                content=self.lv_equipos, # Contenido directo, sin fila horizontal externa
                                border=ft.border.all(1, "white24"), 
                                border_radius=5, 
                                padding=5, 
                                expand=True
                            )
                        ]
                    )
                )

                self.dlg_modal_equipo = ft.AlertDialog(
                    modal=True, 
                    title=ft.Text("Filtrar por Equipo"), 
                    content=contenido_modal, 
                    actions=[ft.TextButton("Cancelar", on_click=lambda e: self._limpiar_memoria_dialogo(self.dlg_modal_equipo)), self.btn_ver_equipo], 
                    actions_alignment=ft.MainAxisAlignment.END
                )
                
                self._limpiar_memoria_dialogo(self.dlg_carga_filtros)
                self.page.open(self.dlg_modal_equipo)
                
            threading.Thread(target=_cargar_rivales_modal, daemon=True).start()

    def _seleccionar_rival_modal(self, e):
        """Al clickear un equipo, se habilita el botón ver."""
        id_sel = e.control.data
        titulo_control = e.control.title.value
        
        self.temp_rival_sel_id = id_sel
        self.temp_rival_sel_nombre = titulo_control
        
        # Resaltar selección
        for c in self.lv_equipos.controls:
            c.bgcolor = "blue" if c.data == id_sel else "#2D2D2D"
        self.lv_equipos.update()
        
        self.btn_ver_equipo.disabled = False
        self.btn_ver_equipo.update()

    def _actualizar_botones_pronosticos_visual(self):
        """Actualiza el color de todos los botones de la pestaña Pronósticos según el filtro activo."""
        # Grupo Tiempo (Excluyentes)
        ft_tiempo = self.filtro_pron_tiempo
        self.btn_pron_todos.bgcolor = "blue" if ft_tiempo == 'todos' else "#333333"
        self.btn_pron_por_jugar.bgcolor = "blue" if ft_tiempo == 'futuros' else "#333333"
        self.btn_pron_jugados.bgcolor = "blue" if ft_tiempo == 'jugados' else "#333333"
        
        # Grupo Específicos (Independientes)
        # Se pintan si la variable del filtro NO es None (está activa)
        self.btn_pron_por_torneo.bgcolor = "blue" if self.filtro_pron_torneo else "#333333"
        self.btn_pron_por_equipo.bgcolor = "blue" if self.filtro_pron_equipo else "#333333"
        self.btn_pron_por_usuario.bgcolor = "blue" if self.filtro_pron_usuario else "#333333"
        
        # Forzar actualización individual para asegurar el cambio visual
        self.btn_pron_todos.update()
        self.btn_pron_por_jugar.update()
        self.btn_pron_jugados.update()
        self.btn_pron_por_torneo.update()
        self.btn_pron_por_equipo.update()
        self.btn_pron_por_usuario.update()

    def _actualizar_titulo_partidos(self):
        """Genera el título dinámico combinando todos los filtros activos."""
        partes = []
        
        # 1. Tiempo
        if self.filtro_temporal == 'todos': partes.append("Todos los partidos")
        elif self.filtro_temporal == 'futuros': partes.append("Partidos por jugar")
        elif self.filtro_temporal == 'jugados': partes.append("Partidos jugados")
        
        detalles = []
        # 2. Sin Pronosticar
        if self.filtro_sin_pronosticar:
            detalles.append("sin pronosticar")
            
        # 3. Torneo
        if self.filtro_edicion_id:
            # Como no guardamos el nombre del torneo en la variable de filtro ID, 
            # usamos las variables temporales si están frescas, o simplificamos el título.
            if self.temp_campeonato_sel:
                detalles.append(f"{self.temp_campeonato_sel} {self.temp_anio_sel}")
            else:
                detalles.append("torneo seleccionado")

        # 4. Equipo
        if self.filtro_rival_id:
            if self.temp_rival_sel_nombre:
                detalles.append(f"vs {self.temp_rival_sel_nombre}")
            else:
                detalles.append("vs equipo")

        titulo = partes[0]
        if detalles:
            titulo += " (" + ", ".join(detalles) + ")"
            
        self.txt_titulo_partidos.value = titulo
        self.txt_titulo_partidos.update()

    def _confirmar_filtro_equipo(self, e):
        """Confirma selección equipo."""
        if self.temp_rival_sel_id:
            self.filtro_rival_id = self.temp_rival_sel_id
            
            self._actualizar_titulo_partidos()
            self._actualizar_botones_partidos_visual()
            self._limpiar_memoria_dialogo(self.dlg_modal_equipo)
            self._recargar_datos(actualizar_partidos=True, actualizar_copas=False)

    # --- FUNCIONES GRÁFICO DE PUESTOS ---

    def _abrir_selector_grafico_puestos(self, e):
        """Intercepta el clic y abre el modal genérico múltiple."""
        if self.filtro_ranking_edicion_id is None:
            self.page.snack_bar = ft.SnackBar(ft.Text("Debe seleccionar un torneo para ver este gráfico.", color="white"), bgcolor="#8B0000", duration=2000)
            self.page.snack_bar.open = True
            self.page.update()
            return
            
        self._abrir_selector_usuarios_generico("Comparar Puestos", True, "Ver Evolución", ft.Icons.SHOW_CHART, self._generar_grafico_puestos)

    def _abrir_selector_grafico_linea_puntos(self, e):
        """Intercepta el clic y abre el modal genérico múltiple."""
        if self.filtro_ranking_edicion_id is None:
            self.page.snack_bar = ft.SnackBar(ft.Text("Debe seleccionar un torneo para ver este gráfico.", color="white"), bgcolor="#8B0000", duration=2000)
            self.page.snack_bar.open = True
            self.page.update()
            return

        self._abrir_selector_usuarios_generico("Comparar Puntos", True, "Ver Evolución", ft.Icons.SHOW_CHART, self._generar_grafico_linea_puntos)

    def _generar_grafico_puestos(self, e):
        """Genera y muestra el gráfico de líneas con la evolución histórica real."""
        # Tomar usuarios de la lista genérica
        usuarios_sel = self.temp_usuarios_seleccionados
        edicion_id = self.filtro_ranking_edicion_id

        # 1. CERRAR EL SELECTOR INMEDIATAMENTE para evitar fantasmas en la UI
        self._limpiar_memoria_dialogo(self.dlg_gen_usuarios)

        # 2. ABRIR UN NUEVO DIÁLOGO EXCLUSIVO PARA LA CARGA
        loading_content = ft.Column(
            controls=[
                ft.Text("Procesando torneo...", size=16, weight="bold", color="white"),
                ft.Container(height=10),
                ft.ProgressBar(width=200, color="red", bgcolor="#222222")
            ],
            height=100, width=300, alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER
        )
        self.dlg_carga_grafico = ft.AlertDialog(content=loading_content, modal=True)
        self.page.open(self.dlg_carga_grafico)

        def _tarea():
            time.sleep(0.5)
            try:
                bd = BaseDeDatos()
                cant_partidos, total_usuarios, historial = bd.obtener_datos_evolucion_puestos(edicion_id, usuarios_sel)
                
                # 3. CERRAR EL DIÁLOGO DE CARGA
                self._limpiar_memoria_dialogo(self.dlg_carga_grafico)

                if cant_partidos == 0:
                    GestorMensajes.mostrar(self.page, "Info", "No hay partidos finalizados para graficar.", "info")
                    return

                peor_puesto_registrado = 1
                for puestos in historial.values():
                    if puestos: peor_puesto_registrado = max(peor_puesto_registrado, max(puestos))
                
                altura_eje = peor_puesto_registrado 
                colores = [ft.Colors.RED, ft.Colors.WHITE, ft.Colors.CYAN, ft.Colors.AMBER, ft.Colors.GREEN, ft.Colors.PURPLE, ft.Colors.ORANGE, ft.Colors.PINK]
                data_series = []
                
                for i, user in enumerate(usuarios_sel):
                    puestos = historial.get(user, [])
                    puntos_grafico = []
                    for idx_partido, puesto in enumerate(puestos):
                        valor_y = altura_eje - puesto + 1 
                        puntos_grafico.append(ft.LineChartDataPoint(x=idx_partido + 1, y=valor_y, tooltip=f"{user}: Puesto {puesto}"))
                    
                    if puntos_grafico:
                        data_series.append(ft.LineChartData(data_points=puntos_grafico, stroke_width=3, color=colores[i % len(colores)], curved=False, stroke_cap_round=True, point=True))

                labels_y = []
                rango_puestos = range(1, peor_puesto_registrado + 1)
                if len(rango_puestos) > 15: rango_puestos = range(1, peor_puesto_registrado + 1, 2)

                for p in rango_puestos:
                    val_y = altura_eje - p + 1
                    labels_y.append(ft.ChartAxisLabel(value=val_y, label=ft.Text(str(p), size=12, weight="bold" if p==1 else "normal")))

                es_pc = (self.page.width >= 750) if self.page.width else True
                px_fila = 60 if es_pc else 80
                alto_calculado = (peor_puesto_registrado + 2) * px_fila
                alto_grafico = max(300, alto_calculado)
                alto_requerido_base = alto_grafico + 50
                ancho_punto = 60 if es_pc else 90
                
                ancho = self.page.width - 50 if self.page.width else 900
                alto = self.page.height - 50 if self.page.height else 600
                ancho_grafico_dinamico = max((ancho - 100), cant_partidos * ancho_punto)
                necesita_scroll_h = (cant_partidos * ancho_punto) > (ancho - 100)

                chart = ft.LineChart(
                    data_series=data_series, border=ft.border.all(1, ft.Colors.WHITE10),
                    left_axis=ft.ChartAxis(labels=labels_y, title=ft.Text("Puesto", size=14, italic=True), title_size=30),
                    bottom_axis=ft.ChartAxis(labels_interval=1, title=ft.Text("Partidos", size=14, italic=True), labels_size=30),
                    tooltip_bgcolor=ft.Colors.with_opacity(0.9, "#1E1E1E"), min_y=0, max_y=altura_eje + (1.2 if es_pc else 0.5), min_x=0.5, max_x=cant_partidos + 0.5,
                    horizontal_grid_lines=ft.ChartGridLines(interval=1, color=ft.Colors.WHITE10, width=1), vertical_grid_lines=ft.ChartGridLines(interval=1, color=ft.Colors.WHITE10, width=1),
                )
                
                items_leyenda = [ft.Row([ft.Container(width=15, height=15, bgcolor=colores[i % len(colores)], border_radius=3), ft.Text(user, weight="bold", size=14, color="white")], spacing=5) for i, user in enumerate(usuarios_sel)]

                espacio_util_interno = alto - 40
                alto_requerido = alto_requerido_base + (len(usuarios_sel) * 25)
                necesita_scroll_v = alto_requerido > espacio_util_interno
                
                flecha_arriba = ft.Container(content=ft.Icon(ft.Icons.KEYBOARD_DOUBLE_ARROW_UP, color="amber", size=35), top=60, right=10, visible=False, ignore_interactions=True, data=False)
                flecha_abajo = ft.Container(content=ft.Icon(ft.Icons.KEYBOARD_DOUBLE_ARROW_DOWN, color="amber", size=35), bottom=10, right=10, visible=necesita_scroll_v, ignore_interactions=True, data=False)

                def _on_scroll_vertical(e):
                    try:
                        pos = float(e.pixels); max_pos = float(e.max_scroll_extent)
                        if not flecha_arriba.data:
                            if pos <= 10 and flecha_arriba.visible: flecha_arriba.visible = False; flecha_arriba.data = True; flecha_arriba.update()
                            elif pos > 10 and not flecha_arriba.visible: flecha_arriba.visible = True; flecha_arriba.update()
                        if not flecha_abajo.data:
                            if pos >= (max_pos - 10) and flecha_abajo.visible: flecha_abajo.visible = False; flecha_abajo.data = True; flecha_abajo.update()
                            elif pos < (max_pos - 10) and not flecha_abajo.visible: flecha_abajo.visible = True; flecha_abajo.update()
                    except: pass

                flecha_izq = ft.Container(content=ft.Icon(ft.Icons.KEYBOARD_DOUBLE_ARROW_LEFT, color="amber", size=35), left=0, top=150, visible=False, ignore_interactions=True, data=False)
                flecha_der = ft.Container(content=ft.Icon(ft.Icons.KEYBOARD_DOUBLE_ARROW_RIGHT, color="amber", size=35), right=0, top=150, visible=necesita_scroll_h, ignore_interactions=True, data=False)

                def _on_scroll_horizontal(e):
                    try:
                        pos = float(e.pixels); max_pos = float(e.max_scroll_extent)
                        if not flecha_izq.data:
                            if pos <= 10 and flecha_izq.visible: flecha_izq.visible = False; flecha_izq.data = True; flecha_izq.update()
                            elif pos > 10 and not flecha_izq.visible: flecha_izq.visible = True; flecha_izq.update()
                        if not flecha_der.data:
                            if pos >= (max_pos - 10) and flecha_der.visible: flecha_der.visible = False; flecha_der.data = True; flecha_der.update()
                            elif pos < (max_pos - 10) and not flecha_der.visible: flecha_der.visible = True; flecha_der.update()
                    except: pass

                fila_grafico = ft.Row(
                    controls=[ft.Container(content=chart, width=ancho_grafico_dinamico, height=alto_grafico, padding=ft.padding.only(top=80 if es_pc else 120, right=60, bottom=20, left=50))],
                    scroll=ft.ScrollMode.ALWAYS
                )

                columna_principal = ft.Column([
                    ft.Row(
                        controls=[
                            ft.Container(content=ft.Text(f"Evolución Puestos: {self.filtro_ranking_nombre}", size=20, weight="bold"), expand=True),
                            ft.IconButton(icon=ft.Icons.CLOSE, on_click=lambda e: self._limpiar_memoria_dialogo(self.dlg_grafico_full)) 
                        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                    ),
                    ft.Text("Historial partido a partido...", size=12, color="white54"),
                    ft.Divider(), fila_grafico, ft.Container(height=20), ft.Divider(), ft.Row(items_leyenda, alignment="center", wrap=True), ft.Container(height=30)
                ], scroll=ft.ScrollMode.ALWAYS, expand=True)

                contenido_final = ft.Container(width=ancho, height=alto, padding=20, bgcolor="#1E1E1E", border_radius=10, content=columna_principal)
                
                if hasattr(self, 'dlg_grafico_full') and self.dlg_grafico_full:
                    self.dlg_grafico_full = None

                self.dlg_grafico_full = ft.AlertDialog(content=contenido_final, modal=True, content_padding=0, bgcolor=ft.Colors.TRANSPARENT)
                self.page.open(self.dlg_grafico_full)

            except Exception as ex:
                self._limpiar_memoria_dialogo(self.dlg_carga_grafico)
                GestorMensajes.mostrar(self.page, "Error", f"Error generando gráfico: {ex}", "error")
                self._enviar_alerta_correo_admins("Error en gráfico de puestos", f"Ocurrió un error al generar el gráfico de puestos", tipo=str(ex), nombre_función="SistemaIndependiente._generar_grafico_puestos._tarea")

        threading.Thread(target=_tarea, daemon=True).start()

    def _abrir_selector_torneo_ranking(self, e):
        if self.filtro_ranking_edicion_id is not None:
            self.filtro_ranking_edicion_id = None
            self.filtro_ranking_nombre = None
            self.txt_titulo_ranking.value = "Tabla de posiciones histórica"
            self.txt_titulo_ranking.update()
            self.btn_ranking_torneo.bgcolor = "#333333"
            self.btn_ranking_torneo.update()
            
            # --- INHABILITAR BOTONES DE GRÁFICOS (Modo visual) ---
            self.btn_grafico_puestos.bgcolor = "#222222"
            self.btn_grafico_puestos.color = "white30"
            
            self.btn_grafico_linea_puntos.bgcolor = "#222222"
            self.btn_grafico_linea_puntos.color = "white30"
            
            self.btn_grafico_barras_puntos.bgcolor = "#222222"
            self.btn_grafico_barras_puntos.color = "white30"
            
            self.btn_grafico_puestos.update()
            self.btn_grafico_linea_puntos.update()
            self.btn_grafico_barras_puntos.update()
            
            self._recargar_datos(actualizar_ranking=True, actualizar_copas=False)
            return

        loading_content = ft.Column(
            controls=[
                ft.Text("Cargando filtros...", size=16, weight="bold", color="white"),
                ft.ProgressBar(width=200, color="amber", bgcolor="#222222")
            ],
            height=80, width=300, alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER
        )
        self.dlg_carga_filtros = ft.AlertDialog(content=loading_content, modal=True)
        self.page.open(self.dlg_carga_filtros)

        def _cargar_datos_modal():
            time.sleep(0.5)
            
            self.temp_campeonato_sel = None
            self.modal_torneo_es_opcional = False
            self.txt_titulo_torneo_modal = ft.Text("1. Torneo (Obligatorio)", weight=ft.FontWeight.BOLD, color="white")
            self.txt_titulo_anio_modal = ft.Text("2. Año (Obligatorio)", weight=ft.FontWeight.BOLD, color="white")
            
            self.lv_torneos = ft.Column(scroll=ft.ScrollMode.ALWAYS, spacing=5)
            self.lv_anios = ft.Column(scroll=ft.ScrollMode.ALWAYS, spacing=5)
            
            self.btn_ver_torneo = ft.ElevatedButton("Ver", icon=ft.Icons.VISIBILITY, disabled=True, on_click=self._confirmar_filtro_torneo_ranking)
            
            try:
                bd = BaseDeDatos()
                # --- CAMBIO APLICADO: SOLO TORNEOS FINALIZADOS ---
                ediciones = bd.obtener_ediciones(solo_finalizados=True)
                self.cache_ediciones_modal = ediciones
                nombres_unicos = sorted(list(set(e[1] for e in ediciones)))
                
                controles = []
                for nombre in nombres_unicos:
                    controles.append(ft.ListTile(title=ft.Text(nombre, size=14), data=nombre, on_click=self._seleccionar_campeonato_modal, bgcolor="#2D2D2D", shape=ft.RoundedRectangleBorder(radius=5)))
                self.lv_torneos.controls = controles
            except Exception as ex:
                self._mostrar_mensaje_admin("Error cargando modal", f"No se pudieron cargar los torneos: {ex}", "error", nombre_función="SistemaIndependiente._abrir_selector_torneo_ranking._cargar_datos_modal")

            es_pc = (self.page.width >= 600) if self.page.width else True
            ancho_pantalla = self.page.width if self.page.width else 600
            ancho_modal = min(500, ancho_pantalla - 20)
            ancho_caja = 200 if es_pc else (ancho_modal - 40)

            col_torneo = ft.Column(
                controls=[
                    self.txt_titulo_torneo_modal, 
                    ft.Container(content=self.lv_torneos, height=180, width=ancho_caja, border=ft.border.all(1, "white24"), border_radius=5, padding=5)
                ]
            )
            col_anio = ft.Column(
                controls=[
                    self.txt_titulo_anio_modal, 
                    ft.Container(content=self.lv_anios, height=180, width=ancho_caja, border=ft.border.all(1, "white24"), border_radius=5, padding=5)
                ]
            )

            if es_pc:
                layout_filtros = ft.Row(controls=[col_torneo, col_anio], spacing=20, alignment=ft.MainAxisAlignment.CENTER)
                alto_contenedor = 250
            else:
                layout_filtros = ft.Column(controls=[col_torneo, col_anio], spacing=20, scroll=ft.ScrollMode.ALWAYS, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
                alto_contenedor = 450

            contenido_modal = ft.Container(
                width=ancho_modal, 
                height=alto_contenedor, 
                content=layout_filtros
            )

            self.dlg_modal = ft.AlertDialog(
                modal=True, 
                title=ft.Text("Filtrar Ranking por Torneo"), 
                content=contenido_modal, 
                actions=[ft.TextButton("Cancelar", on_click=lambda e: self._limpiar_memoria_dialogo(self.dlg_modal)), self.btn_ver_torneo], 
                actions_alignment=ft.MainAxisAlignment.END
            )
            
            self._limpiar_memoria_dialogo(self.dlg_carga_filtros)
            self.page.open(self.dlg_modal)

        threading.Thread(target=_cargar_datos_modal, daemon=True).start()

    def _abrir_selector_anio_ranking(self, e):
        # --- 1. LÓGICA DE TOGGLE ---
        # Si ya hay un año filtrado, lo quitamos
        if self.filtro_ranking_anio is not None:
            self.filtro_ranking_anio = None
            
            # Restaurar títulos
            self.txt_titulo_ranking.value = "Tabla de posiciones histórica"
            self.txt_titulo_copas.value = "Torneos ganados en la historia"
            self.txt_titulo_ranking.update()
            self.txt_titulo_copas.update()
            
            # Apagar botón visualmente
            self.btn_ranking_anio.bgcolor = "#333333"
            self.btn_ranking_anio.update()
            
            # Recargar datos globales
            self._recargar_datos(actualizar_ranking=True)
            return

        # --- 2. SI NO ESTÁ ACTIVO, ABRIMOS EL MODAL ---
        self.lv_anios_ranking = ft.ListView(expand=True, spacing=5, height=300)
        self.btn_ver_anio = ft.ElevatedButton("Ver", icon=ft.Icons.VISIBILITY, disabled=True, on_click=self._confirmar_filtro_anio_ranking)
        
        def _cargar_anios():
            try:
                bd = BaseDeDatos()
                anios = bd.obtener_anios()
                controles = []
                for id_anio, numero in anios:
                    controles.append(
                        ft.ListTile(
                            title=ft.Text(str(numero), size=14),
                            data=numero, 
                            on_click=self._seleccionar_anio_ranking_modal,
                            bgcolor="#2D2D2D",
                            shape=ft.RoundedRectangleBorder(radius=5)
                        )
                    )
                self.lv_anios_ranking.controls = controles
                self.lv_anios_ranking.update()
            except Exception as ex:
                print(f"Error cargando modal años: {ex}")
                self._mostrar_mensaje_general("Error cargando modal", f"No se pudieron cargar los años: {ex}", "error")
                self._enviar_alerta_correo_admins("Error en modal año ranking", f"Ocurrió un error al cargar los años en el modal de ranking", tipo=str(ex), nombre_función="SistemaIndependiente._abrir_selector_anio_ranking._cargar_anios")

        contenido_modal = ft.Container(
            width=300,
            height=350,
            content=ft.Column(
                controls=[
                    ft.Text("Seleccione un Año", weight=ft.FontWeight.BOLD),
                    ft.Container(
                        content=self.lv_anios_ranking,
                        border=ft.border.all(1, "white24"),
                        border_radius=5,
                        padding=5,
                        expand=True
                    )
                ]
            )
        )

        self.dlg_modal_anio = ft.AlertDialog(
            modal=True,
            title=ft.Text("Filtrar por Año"),
            content=contenido_modal,
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: self._limpiar_memoria_dialogo(self.dlg_modal_anio)),
                self.btn_ver_anio
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        self.page.open(self.dlg_modal_anio)
        threading.Thread(target=_cargar_anios, daemon=True).start()

    def _seleccionar_campeonato_modal(self, e):
        """
        Maneja la selección y deselección de un torneo en las listas.
        Respeta si el modal actual es opcional (Estadísticas) o estricto (Partidos/Pronósticos).
        """
        nombre_campeonato = e.control.data
        es_opcional = getattr(self, 'modal_torneo_es_opcional', False)
        
        # 1. Lógica de DESELECCIÓN (Si toca el torneo que ya estaba seleccionado)
        if hasattr(self, 'temp_campeonato_sel') and self.temp_campeonato_sel == nombre_campeonato:
            self.temp_campeonato_sel = None
            
            # Restaurar colores de la lista de torneos a gris
            for control in self.lv_torneos.controls:
                control.bgcolor = "#2D2D2D"
            self.lv_torneos.update()
            
            # Limpiar la lista de años
            self.lv_anios.controls.clear()
            self.lv_anios.update()
            
            # Deshabilitar el botón "Ver"
            if hasattr(self, 'btn_ver_torneo'):
                self.btn_ver_torneo.disabled = True
                self.btn_ver_torneo.update()
                
            # Restaurar los títulos a color blanco y el texto que corresponda
            if hasattr(self, 'txt_titulo_torneo_modal'):
                self.txt_titulo_torneo_modal.value = "1. Torneo (Opcional)" if es_opcional else "1. Torneo (Obligatorio)"
                self.txt_titulo_torneo_modal.color = "white"
                self.txt_titulo_torneo_modal.update()
                
            if hasattr(self, 'txt_titulo_anio_modal'):
                self.txt_titulo_anio_modal.value = "2. Año (Opcional)" if es_opcional else "2. Año (Obligatorio)"
                self.txt_titulo_anio_modal.color = "white"
                self.txt_titulo_anio_modal.update()
                
            return

        # 2. Lógica de SELECCIÓN NUEVA
        self.temp_campeonato_sel = nombre_campeonato
        
        # SOLUCIÓN WARNING FLET: ft.Colors (con C mayúscula)
        for control in self.lv_torneos.controls:
            if control.data == nombre_campeonato:
                control.bgcolor = ft.Colors.BLUE_700 
            else:
                control.bgcolor = "#2D2D2D"
        self.lv_torneos.update()

        # Cambiar los títulos a color celeste y texto "(Obligatorio)" SIEMPRE al seleccionar
        if hasattr(self, 'txt_titulo_torneo_modal'):
            self.txt_titulo_torneo_modal.value = "1. Torneo (Obligatorio)"
            self.txt_titulo_torneo_modal.color = "cyan"
            self.txt_titulo_torneo_modal.update()
            
        if hasattr(self, 'txt_titulo_anio_modal'):
            self.txt_titulo_anio_modal.value = "2. Año (Obligatorio)"
            self.txt_titulo_anio_modal.color = "cyan"
            self.txt_titulo_anio_modal.update()

        # Cargar los años correspondientes a este torneo
        try:
            anios_disponibles = sorted(list(set(ed[2] for ed in self.cache_ediciones_modal if ed[1] == nombre_campeonato)), reverse=True)
            
            controles_anios = []
            for anio in anios_disponibles:
                controles_anios.append(
                    ft.ListTile(
                        title=ft.Text(str(anio), size=14), 
                        data=anio, 
                        on_click=self._seleccionar_anio_modal, 
                        bgcolor="#2D2D2D", 
                        shape=ft.RoundedRectangleBorder(radius=5)
                    )
                )
            self.lv_anios.controls = controles_anios
            self.lv_anios.update()
            
            if hasattr(self, 'btn_ver_torneo'):
                self.btn_ver_torneo.disabled = True
                self.btn_ver_torneo.update()
                
        except Exception as ex:
            self._mostrar_mensaje_admin("Error", f"Error al cargar años: {ex}", "error", nombre_función="SistemaIndependiente._seleccionar_campeonato_modal")

    def _seleccionar_anio_modal(self, e):
        """Al clickear un año, habilita el botón Ver"""
        anio_sel = e.control.data
        self.temp_anio_sel = anio_sel
        
        # Resaltar selección
        for c in self.lv_anios.controls:
            c.bgcolor = "blue" if c.data == anio_sel else "#2D2D2D"
        self.lv_anios.update()
        
        self.btn_ver_torneo.disabled = False
        self.btn_ver_torneo.update()

    def _confirmar_filtro_anio_ranking(self, e):
        """Confirma el filtro por año y borra el de torneo"""
        if self.temp_anio_sel:
            # 1. Establecer filtro Año
            self.filtro_ranking_anio = self.temp_anio_sel
            
            # 2. BORRAR filtro Torneo (Exclusividad)
            self.filtro_ranking_edicion_id = None 
            self.filtro_ranking_nombre = None
            
            # 3. Actualizar Títulos
            self.txt_titulo_ranking.value = f"Tabla de posiciones {self.filtro_ranking_anio}"
            self.txt_titulo_copas.value = f"Torneos ganados {self.filtro_ranking_anio}"
            self.txt_titulo_ranking.update()
            self.txt_titulo_copas.update()
            
            # 4. Actualizar Botones (Uno azul, el otro negro)
            self.btn_ranking_anio.bgcolor = "blue"
            self.btn_ranking_torneo.bgcolor = "#333333"
            
            self.btn_ranking_anio.update()
            self.btn_ranking_torneo.update()
            
            # --- INHABILITAR BOTONES DE GRÁFICOS PORQUE SE QUITÓ EL TORNEO ---
            self.btn_grafico_puestos.bgcolor = "#222222"
            self.btn_grafico_puestos.color = "white30"
            
            self.btn_grafico_linea_puntos.bgcolor = "#222222"
            self.btn_grafico_linea_puntos.color = "white30"
            
            self.btn_grafico_barras_puntos.bgcolor = "#222222"
            self.btn_grafico_barras_puntos.color = "white30"
            
            self.btn_grafico_puestos.update()
            self.btn_grafico_linea_puntos.update()
            self.btn_grafico_barras_puntos.update()
            
            self._limpiar_memoria_dialogo(self.dlg_modal_anio)
            self._recargar_datos(actualizar_ranking=True)

    def _bloquear_botones_filtros(self, bloquear):
        """Habilita o deshabilita los botones de filtro de partidos."""
        self.btn_todos.disabled = bloquear
        self.btn_jugados.disabled = bloquear
        self.btn_por_jugar.disabled = bloquear
        self.btn_por_torneo.disabled = bloquear
        self.btn_sin_pronosticar.disabled = bloquear
        self.btn_por_equipo.disabled = bloquear

    def _cerrar_sesion(self, e):
        self.page.controls.clear()
        self.page.bgcolor = "#121212" 
        self._construir_interfaz_login()
        self.page.update()
    
    # --- FUNCIONES GRÁFICO DE TORTA (ESTILO DE PRONÓSTICO) ---

    def _generar_grafico_torta_estilo_pronostico(self, e):
        """Genera el PieChart con animación de carga y diseño responsivo infalible."""
        
        loading_content = ft.Column(
            controls=[
                ft.Text("Analizando pronósticos...", size=16, weight="bold", color="white"),
                ft.Container(height=10),
                ft.ProgressBar(width=200, color="amber", bgcolor="#222222"),
                ft.Text("Calculando porcentajes...", size=12, color="white70")
            ],
            height=100, width=300, alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER
        )
        self.dlg_carga_grafico = ft.AlertDialog(content=loading_content, modal=True)
        self.page.open(self.dlg_carga_grafico)

        # 1. Obtenemos el usuario del nuevo modal genérico y los filtros globales
        usuario_sel = self.temp_usuarios_seleccionados[0]
        edicion_id = self.filtro_ranking_edicion_id
        anio_filtro = self.filtro_ranking_anio

        def _tarea():
            time.sleep(0.8)
            bd = BaseDeDatos()
            stats = bd.obtener_estadisticas_estilo_pronostico(usuario_sel, edicion_id, anio_filtro)
            
            if not stats or stats[0] == 0:
                self._limpiar_memoria_dialogo(self.dlg_carga_grafico)
                GestorMensajes.mostrar(self.page, "Info", "No hay datos históricos para generar el gráfico.", "info")
                return

            total_partidos = stats[0]
            sin_pron = stats[1]
            victorias = stats[2]
            empates = stats[3]
            derrotas = stats[4]

            def calc_pct(val): return (val / total_partidos) * 100 if total_partidos > 0 else 0

            secciones = []
            if victorias > 0: secciones.append(ft.PieChartSection(value=victorias, title=f"{calc_pct(victorias):.0f}%", color=ft.Colors.GREEN, radius=100, title_style=ft.TextStyle(size=14, weight=ft.FontWeight.BOLD, color="white")))
            if empates > 0: secciones.append(ft.PieChartSection(value=empates, title=f"{calc_pct(empates):.0f}%", color=ft.Colors.YELLOW, radius=100, title_style=ft.TextStyle(size=14, weight=ft.FontWeight.BOLD, color="black")))
            if derrotas > 0: secciones.append(ft.PieChartSection(value=derrotas, title=f"{calc_pct(derrotas):.0f}%", color=ft.Colors.RED, radius=100, title_style=ft.TextStyle(size=14, weight=ft.FontWeight.BOLD, color="white")))
            if sin_pron > 0: secciones.append(ft.PieChartSection(value=sin_pron, title=f"{calc_pct(sin_pron):.0f}%", color=ft.Colors.TRANSPARENT, radius=98, border_side=ft.BorderSide(2, "white54"), title_style=ft.TextStyle(size=12, color="white70")))

            chart = ft.PieChart(sections=secciones, sections_space=2, center_space_radius=0)

            leyenda = ft.Column(
                controls=[
                    ft.Row([ft.Container(width=15, height=15, bgcolor=ft.Colors.GREEN, shape=ft.BoxShape.CIRCLE), ft.Text("Victorias", weight="bold")], spacing=5),
                    ft.Row([ft.Container(width=15, height=15, bgcolor=ft.Colors.YELLOW, shape=ft.BoxShape.CIRCLE), ft.Text("Empates", weight="bold")], spacing=5),
                    ft.Row([ft.Container(width=15, height=15, bgcolor=ft.Colors.RED, shape=ft.BoxShape.CIRCLE), ft.Text("Derrotas", weight="bold")], spacing=5),
                    ft.Row([ft.Container(width=15, height=15, bgcolor=ft.Colors.TRANSPARENT, border=ft.border.all(2, "white"), shape=ft.BoxShape.CIRCLE), ft.Text("Sin pronóstico", color="white70")], spacing=5),
                ],
                alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.START
            )

            titulo_txt = f"Estilo: {usuario_sel}"
            subtitulo_txt = self.filtro_ranking_nombre if self.filtro_ranking_nombre else (f"Año {self.filtro_ranking_anio}" if self.filtro_ranking_anio else "Histórico completo")

            es_pc = (self.page.width >= 600) if self.page.width else True
            
            if es_pc:
                ancho_dialogo = 650
                contenedor_torta_leyenda = ft.Row(
                    controls=[
                        ft.Container(content=chart, width=280, height=280),
                        ft.Container(content=leyenda, padding=ft.padding.only(left=20))
                    ],
                    alignment=ft.MainAxisAlignment.CENTER, vertical_alignment=ft.CrossAxisAlignment.CENTER
                )
            else:
                ancho_dialogo = self.page.width - 20
                contenedor_torta_leyenda = ft.Column(
                    controls=[
                        ft.Container(content=chart, width=220, height=220),
                        ft.Container(content=leyenda, padding=ft.padding.only(top=10))
                    ],
                    alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER
                )

            columna_principal = ft.Column([
                ft.Row(
                    controls=[
                        ft.Column([ft.Text(titulo_txt, size=22, weight="bold"), ft.Text(subtitulo_txt, size=14, color="white54")], expand=True),
                        ft.IconButton(icon=ft.Icons.CLOSE, on_click=lambda e: self._limpiar_memoria_dialogo(self.dlg_grafico_torta_full))
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                ),
                ft.Divider(),
                contenedor_torta_leyenda,
                ft.Container(height=20),
                ft.Text(f"Total Partidos Jugados: {total_partidos}", size=12, italic=True, text_align=ft.TextAlign.CENTER),
                ft.Container(height=10)
            ], scroll=ft.ScrollMode.ALWAYS, horizontal_alignment=ft.CrossAxisAlignment.CENTER)

            contenido_final = ft.Container(
                width=ancho_dialogo, padding=20, bgcolor="#1E1E1E", border_radius=10,
                content=columna_principal
            )
            
            self._limpiar_memoria_dialogo(self.dlg_carga_grafico)
            self._limpiar_memoria_dialogo(self.dlg_gen_usuarios) # Cierra el modal de selección

            if hasattr(self, 'dlg_grafico_full') and self.dlg_grafico_full:
                    self.dlg_grafico_full = None

            self.dlg_grafico_torta_full = ft.AlertDialog(content=contenido_final, modal=True, content_padding=0, bgcolor=ft.Colors.TRANSPARENT)
            self.page.open(self.dlg_grafico_torta_full)

        threading.Thread(target=_tarea, daemon=True).start()

    def _sel_torneo_torta_modal(self, e):
        """Selecciona o deselecciona torneo. Filtra los años y ajusta los títulos."""
        nombre = e.control.data
        
        # Toggle selection
        if self.temp_camp_torta == nombre:
            self.temp_camp_torta = None # Deseleccionar
            
            # Restaurar título a opcional si se deselecciona
            if hasattr(self, 'txt_titulo_anio_torta'):
                self.txt_titulo_torneo_torta.value = "1. Torneo (Opcional)"
                self.txt_titulo_torneo_torta.color = "white"
                self.txt_titulo_anio_torta.value = "2. Año (Opcional)"
                self.txt_titulo_anio_torta.color = "white"
                self.txt_titulo_torneo_torta.update()
                self.txt_titulo_anio_torta.update()
        else:
            self.temp_camp_torta = nombre
            
            # Cambiar título a obligatorio si se selecciona un torneo
            if hasattr(self, 'txt_titulo_anio_torta'):
                self.txt_titulo_torneo_torta.value = "1. Torneo (Obligatorio)"
                self.txt_titulo_torneo_torta.color = "cyan"
                self.txt_titulo_anio_torta.value = "2. Año (Obligatorio)"
                self.txt_titulo_anio_torta.color = "cyan"
                self.txt_titulo_torneo_torta.update()
                self.txt_titulo_anio_torta.update()
        
        # Visual Update Torneos
        for c in self.lv_torneos_torta.controls: 
            c.bgcolor = "blue" if c.data == self.temp_camp_torta else "#2D2D2D"
        self.lv_torneos_torta.update()
        
        # Actualizar lista de Años
        if self.temp_camp_torta:
            # Mostrar solo años de este torneo
            anios_filtrados = sorted([ed[2] for ed in self.cache_ediciones_modal if ed[1] == self.temp_camp_torta], reverse=True)
            ctls = []
            for a in anios_filtrados:
                ctls.append(ft.ListTile(title=ft.Text(str(a), size=14), data=a, on_click=self._sel_anio_torta_modal, bgcolor="#2D2D2D"))
            self.lv_anios_torta.controls = ctls
        else:
            # ¡EL CAMBIO!: Si no hay torneo seleccionado, la lista de años debe quedar totalmente vacía.
            anios_filtrados = []
            self.lv_anios_torta.controls.clear()
        
        # Si el año seleccionado ya no está en la lista filtrada, deseleccionarlo
        if self.temp_anio_torta not in anios_filtrados:
            self.temp_anio_torta = None
        else:
            # Mantener visualmente seleccionado si aun existe
            for c in self.lv_anios_torta.controls:
                if c.data == self.temp_anio_torta: c.bgcolor = "blue"

        self.lv_anios_torta.update()
        self._validar_btn_grafico_torta()

    def _sel_anio_torta_modal(self, e):
        """Selecciona o deselecciona año."""
        anio = e.control.data
        if self.temp_anio_torta == anio:
            self.temp_anio_torta = None
        else:
            self.temp_anio_torta = anio
            
        for c in self.lv_anios_torta.controls: 
            c.bgcolor = "blue" if c.data == self.temp_anio_torta else "#2D2D2D"
        self.lv_anios_torta.update()
        self._validar_btn_grafico_torta()

    def _sel_usuario_torta_modal(self, e):
        """Selecciona usuario (obligatorio)."""
        usuario = e.control.data
        self.temp_usuario_torta = usuario
        
        for c in self.lv_usuarios_torta.controls: 
            c.bgcolor = "blue" if c.data == self.temp_usuario_torta else "#2D2D2D"
        self.lv_usuarios_torta.update()
        self._validar_btn_grafico_torta()

    def _validar_btn_grafico_torta(self):
        """
        Reglas:
        1. Usuario obligatorio.
        2. Si hay Torneo seleccionado, Año es obligatorio.
        """
        usuario_ok = self.temp_usuario_torta is not None
        
        logica_torneo_anio = True
        if self.temp_camp_torta is not None:
            # Si hay torneo, DEBE haber año
            if self.temp_anio_torta is None:
                logica_torneo_anio = False
        
        habilitar = usuario_ok and logica_torneo_anio
        
        self.btn_generar_grafico_torta.disabled = not habilitar
        self.btn_generar_grafico_torta.update()
    
    def _abrir_selector_usuarios_generico(self, titulo, permite_multiple, texto_boton, icono_boton, funcion_accion):
        """Abre un diálogo centrado para seleccionar usuarios de forma paramétrica."""
        
        # 1. Animación de carga inicial
        loading_content = ft.Column(
            controls=[
                ft.Text("Cargando usuarios...", size=16, weight="bold", color="white"),
                ft.ProgressBar(width=200, color="amber", bgcolor="#222222")
            ],
            height=80, width=300, alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER
        )
        self.dlg_carga_filtros = ft.AlertDialog(content=loading_content, modal=True)
        self.page.open(self.dlg_carga_filtros)

        def _cargar():
            time.sleep(0.3)
            self.temp_usuarios_seleccionados = []
            
            # --- NUEVO: Determinamos el texto del subtítulo según el parámetro ---
            if permite_multiple:
                texto_indicacion = "Puedes seleccionar hasta 4 usuarios a la vez."
            else:
                texto_indicacion = "Puedes seleccionar 1 solo usuario."
                
            # --- NUEVO: Creamos una columna ajustada para reemplazar el título simple ---
            titulo_con_subtitulo = ft.Column(
                controls=[
                    ft.Text(titulo, weight=ft.FontWeight.BOLD),
                    ft.Text(texto_indicacion, size=13, color=ft.Colors.WHITE70, italic=True)
                ],
                spacing=2,
                tight=True # Vital para que la columna no ocupe toda la pantalla
            )
            
            # Usamos Column con scroll ALWAYS para cumplir tu requisito de la barra siempre visible
            self.lv_usuarios_gen = ft.Column(scroll=ft.ScrollMode.ALWAYS, spacing=5)
            
            # Botón inyectado por parámetro
            self.btn_accion_gen = ft.ElevatedButton(
                texto_boton, 
                icon=icono_boton, 
                disabled=True, 
                on_click=funcion_accion
            )

            try:
                bd = BaseDeDatos()
                usuarios = bd.obtener_usuarios()
                controles = []
                for usu in usuarios:
                    controles.append(
                        ft.ListTile(
                            title=ft.Text(usu, size=14),
                            data=usu,
                            # Pasamos el flag múltiple al evento click
                            on_click=lambda e, mult=permite_multiple: self._seleccionar_usuario_gen_modal(e, mult),
                            bgcolor="#2D2D2D",
                            shape=ft.RoundedRectangleBorder(radius=5)
                        )
                    )
                self.lv_usuarios_gen.controls = controles
            except Exception as ex:
                self._mostrar_mensaje_admin("Error", f"Error cargando usuarios: {ex}", "error", nombre_función="SistemaIndependiente._abrir_selector_usuarios_generico._cargar")

            # Altura diseñada para mostrar exactamente 4 usuarios (aprox 220px)
            contenido = ft.Container(
                width=300, height=220, 
                content=ft.Container(
                    content=self.lv_usuarios_gen,
                    border=ft.border.all(1, "white24"),
                    border_radius=5,
                    padding=5,
                    expand=True
                )
            )

            self.dlg_gen_usuarios = ft.AlertDialog(
                modal=True,
                title=titulo_con_subtitulo, # <-- Aquí pasamos nuestro nuevo bloque de título + subtítulo
                content=contenido,
                actions=[
                    ft.TextButton("Cancelar", on_click=lambda e: self._limpiar_memoria_dialogo(self.dlg_gen_usuarios)),
                    self.btn_accion_gen
                ],
                actions_alignment=ft.MainAxisAlignment.SPACE_BETWEEN # Asegura Cancelar a la izquierda y Botón Acción a la derecha
            )
            
            self._limpiar_memoria_dialogo(self.dlg_carga_filtros)
            self.page.open(self.dlg_gen_usuarios)
            
        threading.Thread(target=_cargar, daemon=True).start()

    def _seleccionar_usuario_gen_modal(self, e, permite_multiple):
        """Maneja la lógica de selección de usuarios y la activación del botón."""
        usu = e.control.data
        
        if permite_multiple:
            # Toggle múltiple con LÍMITE DE 4
            if usu in self.temp_usuarios_seleccionados:
                self.temp_usuarios_seleccionados.remove(usu)
            else:
                if len(self.temp_usuarios_seleccionados) >= 4:
                    GestorMensajes.mostrar(self.page, "Límite", "Máximo 4 usuarios permitidos para comparar.", "info")
                    return # Corta la ejecución, no lo agrega
                self.temp_usuarios_seleccionados.append(usu)
        else:
            # Toggle individual
            if usu in self.temp_usuarios_seleccionados:
                self.temp_usuarios_seleccionados = []
            else:
                self.temp_usuarios_seleccionados = [usu]
                
        # Actualización de colores
        for c in self.lv_usuarios_gen.controls:
            c.bgcolor = "blue" if c.data in self.temp_usuarios_seleccionados else "#2D2D2D"
        self.lv_usuarios_gen.update()
        
        # El botón se activa solo si la lista tiene al menos 1 usuario
        self.btn_accion_gen.disabled = len(self.temp_usuarios_seleccionados) == 0
        self.btn_accion_gen.update()

    def _generar_grafico_torta_tendencia(self, e):
        """Genera el gráfico de torta de Tendencia con diseño responsivo infalible."""
        
        loading_content = ft.Column(
            controls=[
                ft.Text("Analizando desviaciones...", size=16, weight="bold", color="white"),
                ft.Container(height=10),
                ft.ProgressBar(width=200, color="amber", bgcolor="#222222"),
                ft.Text("Calculando tendencias...", size=12, color="white70")
            ],
            height=100, width=300, alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER
        )
        self.dlg_carga_grafico = ft.AlertDialog(content=loading_content, modal=True)
        self.page.open(self.dlg_carga_grafico)

        # 1. Obtenemos el usuario del nuevo modal genérico y los filtros globales
        usuario_sel = self.temp_usuarios_seleccionados[0]
        edicion_id = self.filtro_ranking_edicion_id
        anio_filtro = self.filtro_ranking_anio

        def _tarea():
            time.sleep(0.8)
            bd = BaseDeDatos()
            stats = bd.obtener_estadisticas_tendencia_pronostico(usuario_sel, edicion_id, anio_filtro)
            
            if not stats or stats[0] == 0:
                self._limpiar_memoria_dialogo(self.dlg_carga_grafico)
                GestorMensajes.mostrar(self.page, "Info", "No hay datos históricos para generar el gráfico.", "info")
                return

            total = stats[0]
            sin_pron = stats[1] or 0
            muy_opt = stats[2] or 0
            opt = stats[3] or 0
            real = stats[4] or 0
            pes = stats[5] or 0
            muy_pes = stats[6] or 0

            def calc_pct(val): return (val / total) * 100 if total > 0 else 0

            secciones = []
            if muy_opt > 0: secciones.append(ft.PieChartSection(value=muy_opt, title=f"{calc_pct(muy_opt):.0f}%", color=ft.Colors.RED, radius=100, title_style=ft.TextStyle(size=12, weight="bold", color="white")))
            if opt > 0: secciones.append(ft.PieChartSection(value=opt, title=f"{calc_pct(opt):.0f}%", color=ft.Colors.ORANGE, radius=100, title_style=ft.TextStyle(size=12, weight="bold", color="white")))
            if real > 0: secciones.append(ft.PieChartSection(value=real, title=f"{calc_pct(real):.0f}%", color=ft.Colors.GREEN, radius=100, title_style=ft.TextStyle(size=12, weight="bold", color="white")))
            if pes > 0: secciones.append(ft.PieChartSection(value=pes, title=f"{calc_pct(pes):.0f}%", color=ft.Colors.BLUE, radius=100, title_style=ft.TextStyle(size=12, weight="bold", color="white")))
            if muy_pes > 0: secciones.append(ft.PieChartSection(value=muy_pes, title=f"{calc_pct(muy_pes):.0f}%", color=ft.Colors.PURPLE, radius=100, title_style=ft.TextStyle(size=12, weight="bold", color="white")))
            if sin_pron > 0: secciones.append(ft.PieChartSection(value=sin_pron, title=f"{calc_pct(sin_pron):.0f}%", color=ft.Colors.TRANSPARENT, radius=98, border_side=ft.BorderSide(2, "white54"), title_style=ft.TextStyle(size=12, color="white70")))

            chart = ft.PieChart(sections=secciones, sections_space=2, center_space_radius=0)

            items_leyenda = [(ft.Colors.RED, "Muy optimista"), (ft.Colors.ORANGE, "Optimista"), (ft.Colors.GREEN, "Neutral"), (ft.Colors.BLUE, "Pesimista"), (ft.Colors.PURPLE, "Muy pesimista")]
            controles_leyenda = [ft.Row([ft.Container(width=15, height=15, bgcolor=col, shape=ft.BoxShape.CIRCLE), ft.Text(txt, weight="bold", size=12)], spacing=5) for col, txt in items_leyenda]
            controles_leyenda.append(ft.Row([ft.Container(width=15, height=15, bgcolor=ft.Colors.TRANSPARENT, border=ft.border.all(2, "white"), shape=ft.BoxShape.CIRCLE), ft.Text("No pronosticado", color="white70", size=12)], spacing=5))
            
            leyenda = ft.Column(controls=controles_leyenda, alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.START)

            titulo_txt = f"Tendencia: {usuario_sel}"
            subtitulo_txt = self.filtro_ranking_nombre if self.filtro_ranking_nombre else (f"Año {self.filtro_ranking_anio}" if self.filtro_ranking_anio else "Histórico completo")

            es_pc = (self.page.width >= 600) if self.page.width else True
            
            if es_pc:
                ancho_dialogo = 650
                contenedor_torta_leyenda = ft.Row(
                    controls=[
                        ft.Container(content=chart, width=280, height=280),
                        ft.Container(content=leyenda, padding=ft.padding.only(left=20))
                    ],
                    alignment=ft.MainAxisAlignment.CENTER, vertical_alignment=ft.CrossAxisAlignment.CENTER
                )
            else:
                ancho_dialogo = self.page.width - 20
                contenedor_torta_leyenda = ft.Column(
                    controls=[
                        ft.Container(content=chart, width=220, height=220),
                        ft.Container(content=leyenda, padding=ft.padding.only(top=10))
                    ],
                    alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER
                )

            columna_principal = ft.Column([
                ft.Row(
                    controls=[
                        ft.Column([ft.Text(titulo_txt, size=22, weight="bold"), ft.Text(subtitulo_txt, size=14, color="white54")], expand=True),
                        ft.IconButton(icon=ft.Icons.CLOSE, on_click=lambda e: self._limpiar_memoria_dialogo(self.dlg_grafico_torta_full))
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                ),
                ft.Divider(),
                contenedor_torta_leyenda,
                ft.Container(height=20),
                ft.Text(f"Total Partidos Jugados: {total}", size=12, italic=True, text_align=ft.TextAlign.CENTER),
                ft.Container(height=10)
            ], scroll=ft.ScrollMode.ALWAYS, horizontal_alignment=ft.CrossAxisAlignment.CENTER)

            contenido_final = ft.Container(
                width=ancho_dialogo, padding=20, bgcolor="#1E1E1E", border_radius=10,
                content=columna_principal
            )
            
            self._limpiar_memoria_dialogo(self.dlg_carga_grafico)
            self._limpiar_memoria_dialogo(self.dlg_gen_usuarios) # Cierra el modal genérico

            if hasattr(self, 'dlg_grafico_full') and self.dlg_grafico_full:
                    self.dlg_grafico_full = None

            self.dlg_grafico_torta_full = ft.AlertDialog(content=contenido_final, modal=True, content_padding=0, bgcolor=ft.Colors.TRANSPARENT)
            self.page.open(self.dlg_grafico_torta_full)

        threading.Thread(target=_tarea, daemon=True).start()

    def _generar_grafico_torta_firmeza(self, e):
        """Genera el gráfico de torta de Grado de Firmeza con diseño responsivo infalible."""
        
        loading_content = ft.Column(
            controls=[
                ft.Text("Analizando cambios...", size=16, weight="bold", color="white"),
                ft.Container(height=10),
                ft.ProgressBar(width=200, color="amber", bgcolor="#222222"),
                ft.Text("Calculando historial de ediciones...", size=12, color="white70")
            ],
            height=100, width=300, alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER
        )
        self.dlg_carga_grafico = ft.AlertDialog(content=loading_content, modal=True)
        self.page.open(self.dlg_carga_grafico)

        # 1. Obtenemos el usuario del nuevo modal genérico y los filtros globales
        usuario_sel = self.temp_usuarios_seleccionados[0]
        edicion_id = self.filtro_ranking_edicion_id
        anio_filtro = self.filtro_ranking_anio

        def _tarea():
            time.sleep(0.8)
            bd = BaseDeDatos()
            stats = bd.obtener_estadisticas_firmeza_pronostico(usuario_sel, edicion_id, anio_filtro)
            
            if not stats or stats[0] == 0:
                self._limpiar_memoria_dialogo(self.dlg_carga_grafico)
                GestorMensajes.mostrar(self.page, "Info", "No hay datos históricos para generar el gráfico.", "info")
                return

            total = stats[0]
            sin_pron = stats[1] or 0
            firme = stats[2] or 0
            dudoso = stats[3] or 0
            cambiante = stats[4] or 0

            def calc_pct(val): return (val / total) * 100 if total > 0 else 0

            secciones = []
            if firme > 0: secciones.append(ft.PieChartSection(value=firme, title=f"{calc_pct(firme):.0f}%", color=ft.Colors.GREEN, radius=100, title_style=ft.TextStyle(size=14, weight="bold", color="white")))
            if dudoso > 0: secciones.append(ft.PieChartSection(value=dudoso, title=f"{calc_pct(dudoso):.0f}%", color=ft.Colors.AMBER, radius=100, title_style=ft.TextStyle(size=14, weight="bold", color="black")))
            if cambiante > 0: secciones.append(ft.PieChartSection(value=cambiante, title=f"{calc_pct(cambiante):.0f}%", color=ft.Colors.RED, radius=100, title_style=ft.TextStyle(size=14, weight="bold", color="white")))
            if sin_pron > 0: secciones.append(ft.PieChartSection(value=sin_pron, title=f"{calc_pct(sin_pron):.0f}%", color=ft.Colors.TRANSPARENT, radius=98, border_side=ft.BorderSide(2, "white54"), title_style=ft.TextStyle(size=12, color="white70")))

            chart = ft.PieChart(sections=secciones, sections_space=2, center_space_radius=0)

            items_leyenda = [(ft.Colors.GREEN, "🧱 Firme (1 intento)"), (ft.Colors.AMBER, "🤔 Dudoso (2 intentos)"), (ft.Colors.RED, "🔄 Cambiante (3+ intentos)")]
            controles_leyenda = [ft.Row([ft.Container(width=18, height=18, bgcolor=col, shape=ft.BoxShape.CIRCLE), ft.Text(txt, weight="bold", size=14)], spacing=10) for col, txt in items_leyenda]
            controles_leyenda.append(ft.Row([ft.Container(width=18, height=18, bgcolor=ft.Colors.TRANSPARENT, border=ft.border.all(2, "white"), shape=ft.BoxShape.CIRCLE), ft.Text("💤 No participativo", color="white70", size=14)], spacing=10))

            leyenda = ft.Column(controls=controles_leyenda, alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.START)

            titulo_txt = f"Grado de firmeza: {usuario_sel}"
            subtitulo_txt = self.filtro_ranking_nombre if self.filtro_ranking_nombre else (f"Año {self.filtro_ranking_anio}" if self.filtro_ranking_anio else "Histórico completo")

            es_pc = (self.page.width >= 600) if self.page.width else True
            
            if es_pc:
                ancho_dialogo = 650
                contenedor_torta_leyenda = ft.Row(
                    controls=[
                        ft.Container(content=chart, width=280, height=280),
                        ft.Container(content=leyenda, padding=ft.padding.only(left=20))
                    ],
                    alignment=ft.MainAxisAlignment.CENTER, vertical_alignment=ft.CrossAxisAlignment.CENTER
                )
            else:
                ancho_dialogo = self.page.width - 20
                contenedor_torta_leyenda = ft.Column(
                    controls=[
                        ft.Container(content=chart, width=220, height=220),
                        ft.Container(content=leyenda, padding=ft.padding.only(top=10))
                    ],
                    alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER
                )

            columna_principal = ft.Column([
                ft.Row(
                    controls=[
                        ft.Column([ft.Text(titulo_txt, size=22, weight="bold"), ft.Text(subtitulo_txt, size=14, color="white54")], expand=True),
                        ft.IconButton(icon=ft.Icons.CLOSE, on_click=lambda e: self._limpiar_memoria_dialogo(self.dlg_grafico_torta_full))
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                ),
                ft.Divider(),
                contenedor_torta_leyenda,
                ft.Container(height=20),
                ft.Text(f"Total Partidos Jugados: {total}", size=12, italic=True, text_align=ft.TextAlign.CENTER),
                ft.Container(height=10)
            ], scroll=ft.ScrollMode.ALWAYS, horizontal_alignment=ft.CrossAxisAlignment.CENTER)

            contenido_final = ft.Container(
                width=ancho_dialogo, padding=20, bgcolor="#1E1E1E", border_radius=10,
                content=columna_principal
            )
            
            self._limpiar_memoria_dialogo(self.dlg_carga_grafico)
            self._limpiar_memoria_dialogo(self.dlg_gen_usuarios) # Cierra el modal genérico

            if hasattr(self, 'dlg_grafico_full') and self.dlg_grafico_full:
                    self.dlg_grafico_full = None

            self.dlg_grafico_torta_full = ft.AlertDialog(content=contenido_final, modal=True, content_padding=0, bgcolor=ft.Colors.TRANSPARENT)
            self.page.open(self.dlg_grafico_torta_full)

        threading.Thread(target=_tarea, daemon=True).start()

    def _obtener_color_error(self, valor_error):
        """
        Devuelve el color según el error absoluto:
        0 = Cyan
        <= 1 = Green
        <= 2 = Yellow
        > 2 = Red
        """
        if valor_error is None:
            return "white"
            
        try:
            val = float(valor_error) # Convertimos a float para manejar decimales si los hubiera
            if val == 0:
                return "cyan"
            elif val <= 1.0:
                return "green"
            elif val <= 2.0:
                return "yellow"
            else:
                return "red"
        except:
            return "white"
        
    def _generar_tabla_mayores_errores(self, e):
        """
        Genera la tabla de mayores errores (Top Payasos) directamente usando
        el filtro global seleccionado. Diseño corregido para scroll nativo y con AÑO en la fecha.
        """
        # 1. Obtenemos los filtros globales de la pantalla principal
        edicion_id = self.filtro_ranking_edicion_id
        anio_filtro = self.filtro_ranking_anio

        # 2. Abrir spinner de carga en un modal nuevo
        loading_content = ft.Column(
            controls=[
                ft.Text("Procesando datos...", size=16, weight="bold", color="white"),
                ft.Container(height=10),
                ft.ProgressBar(width=200, color="red", bgcolor="#222222")
            ],
            height=100, width=300, alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER
        )
        self.dlg_carga_errores = ft.AlertDialog(content=loading_content, modal=True)
        self.page.open(self.dlg_carga_errores)

        def _tarea():
            time.sleep(0.5)
            try:
                bd = BaseDeDatos()
                datos = bd.obtener_ranking_mayores_errores(usuario=None, edicion_id=edicion_id, anio=anio_filtro)
                
                # Cerrar modal de carga
                self._limpiar_memoria_dialogo(self.dlg_carga_errores)

                if not datos:
                    GestorMensajes.mostrar(self.page, "Info", "No hay datos históricos para calcular errores con este filtro.", "info")
                    return

                # --- LÓGICA DE FILTRADO (Top 10 + Empates) ---
                filas_filtradas = []
                limite_ranking = 10
                valor_corte = -1
                for i, fila in enumerate(datos):
                    error_actual = fila[8] 
                    if i < limite_ranking:
                        filas_filtradas.append(fila)
                        if i == (limite_ranking - 1): valor_corte = error_actual
                    elif error_actual == valor_corte:
                        filas_filtradas.append(fila)
                    else: break
                
                # --- CÁLCULO DE ANCHOS (Ajustado para que entre el año completo) ---
                w_cols = [ANCHO_COLUMNA_USUARIO, 120, 115, 115, 60, 60, 80] 
                w_spacing = 10
                ancho_tabla_neto = sum(w_cols) + (w_spacing * (len(w_cols) - 1))
                
                borde_gris = ft.border.all(1, "white10")
                borde_inferior = ft.border.only(bottom=ft.border.BorderSide(1, "white10"))
                borde_derecho = ft.border.only(right=ft.border.BorderSide(1, "white10"))

                # --- 1. ENCABEZADO ---
                titulos = ["Usuario", "Rival", "F. Partido", "F. Pronos.", "Pron.", "Res.", "Error"]
                celdas_header = []
                for i, titulo in enumerate(titulos):
                    estilo_borde = borde_derecho if i < len(titulos) - 1 else None
                    celdas_header.append(
                        ft.Container(
                            content=ft.Text(titulo, weight="bold", size=14, color="white"),
                            width=w_cols[i],
                            alignment=ft.alignment.center,
                            border=estilo_borde
                        )
                    )
                
                header_row = ft.Container(
                    content=ft.Row(controls=celdas_header, spacing=w_spacing, alignment=ft.MainAxisAlignment.START),
                    bgcolor="black", height=60, border=borde_inferior, padding=0, width=ancho_tabla_neto
                )

                # --- 2. CUERPO ---
                rows_controls = []
                previous_error = None

                for fila in filas_filtradas:
                    user = fila[0]
                    rival = fila[1]
                    
                    f_part_raw = fila[2]
                    f_pron_raw = fila[3]
                    
                    # --- CAMBIO REALIZADO AQUÍ: SE AGREGA EL AÑO (%Y) ---
                    f_part = f_part_raw.strftime("%d/%m/%Y %H:%M") if hasattr(f_part_raw, 'strftime') else str(f_part_raw)[:16]
                    f_pron = f_pron_raw.strftime("%d/%m/%Y %H:%M") if hasattr(f_pron_raw, 'strftime') else str(f_pron_raw)[:16]
                    
                    pc, pr = fila[4], fila[5] 
                    rc, rr = fila[6], fila[7] 
                    err_abs = fila[8]
                    
                    pron_str = f"{pc}-{pr}"
                    res_str = f"{rc}-{rr}"
                    err_str = f"{int(err_abs)}" if err_abs is not None else "0"

                    if previous_error is not None and err_abs == previous_error: pass 
                    previous_error = err_abs

                    if err_abs == 0: color_error = "#00FF00"
                    elif err_abs <= 2: color_error = "cyan"
                    elif err_abs <= 4: color_error = "yellow"
                    else: color_error = "#FF4444"

                    celdas_fila = []
                    datos_fila = [
                        (user, "white", True),
                        (rival, "white70", False),
                        (f_part, "white", False),
                        (f_pron, "cyan", False),
                        (pron_str, "cyan", True),
                        (res_str, "yellow", True),
                        (err_str, color_error, True)
                    ]

                    for i, (txt, col, bold) in enumerate(datos_fila):
                        estilo_borde = borde_derecho if i < len(datos_fila) - 1 else None
                        size_txt = 16 if i == 6 else (13 if i < 2 else 12)
                        
                        celdas_fila.append(
                            ft.Container(
                                content=ft.Text(str(txt), weight="bold" if bold else "normal", size=size_txt, color=col),
                                width=w_cols[i],
                                alignment=ft.alignment.center,
                                border=estilo_borde
                            )
                        )

                    row_visual = ft.Container(
                        content=ft.Row(controls=celdas_fila, spacing=w_spacing, alignment=ft.MainAxisAlignment.START),
                        height=50, border=borde_inferior, padding=0
                    )
                    rows_controls.append(row_visual)

                body_column = ft.Column(controls=rows_controls, spacing=0)

                # --- 3. ENSAMBLADO ---
                tabla_simulada = ft.Container(
                    content=ft.Column(controls=[header_row, body_column], spacing=0),
                    border=borde_gris, width=ancho_tabla_neto
                )
                
                # Barra horizontal nativa SOLO para la tabla
                contenedor_tabla_nativa = ft.Row(
                    scroll=ft.ScrollMode.ALWAYS,
                    controls=[tabla_simulada]
                )

                titulo_modal = "Ranking de Mayores Errores 🤡"
                if self.filtro_ranking_nombre: 
                    titulo_modal = f"Mayores Errores ({self.filtro_ranking_nombre})"
                elif self.filtro_ranking_anio:
                    titulo_modal = f"Mayores Errores ({self.filtro_ranking_anio})"

                # Contenedor principal con la barra vertical siempre visible en el borde de la pantalla
                contenido_scroll = ft.Column(
                    controls=[
                        ft.Row(
                            controls=[
                                ft.Container(
                                    content=ft.Text(titulo_modal, size=20, weight="bold", color="white"),
                                    expand=True
                                ),
                                ft.IconButton(
                                    icon=ft.Icons.CLOSE, 
                                    icon_color="white", 
                                    on_click=lambda e: self._limpiar_memoria_dialogo(self.dlg_tabla_errores)
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                        ft.Text("Top 10 (con empates) - Ordenado por error absoluto", size=12, color="white54"),
                        ft.Divider(color="white24"),
                        contenedor_tabla_nativa, # <--- La tabla desliza horizontalmente por su cuenta
                        ft.Container(height=10),
                        ft.Row([ft.ElevatedButton("Cerrar", on_click=lambda e: self._limpiar_memoria_dialogo(self.dlg_tabla_errores))], alignment=ft.MainAxisAlignment.END)
                    ],
                    spacing=10, 
                    scroll=ft.ScrollMode.ALWAYS # <--- La barra vertical se ancla aquí
                )

                # --- 4. APERTURA DINÁMICA ---
                ancho_pantalla = self.page.width if self.page.width else 600
                alto_pantalla = self.page.height if self.page.height else 700
                
                ancho_dialogo = min(800, ancho_pantalla - 20)
                altura_estimada = 60 + (len(filas_filtradas) * 50) + 220
                alto_dialogo = min(alto_pantalla - 50, altura_estimada)

                contenedor_dialogo = ft.Container(
                    content=contenido_scroll,
                    width=ancho_dialogo,
                    height=alto_dialogo,
                    bgcolor="#1E1E1E", padding=20, border_radius=10, alignment=ft.alignment.center
                )
                
                if hasattr(self, 'dlg_tabla_errores') and self.dlg_tabla_errores:
                    self.dlg_tabla_errores = None

                self.dlg_tabla_errores = ft.AlertDialog(
                    content=contenedor_dialogo, 
                    modal=True, 
                    content_padding=0, 
                    bgcolor=ft.Colors.TRANSPARENT 
                )
                self.page.open(self.dlg_tabla_errores)

            except Exception as ex:
                self._limpiar_memoria_dialogo(self.dlg_carga_errores)
                GestorMensajes.mostrar(self.page, "Error", f"Error al generar tabla: {ex}", "error")
                self._enviar_alerta_correo_admins("Error al generar tabla de mayores errores", f"Ocurrió un error al generar la tabla de mayores errores: {ex}", tipo=str(ex), nombre_función="SistemaIndependiente._generar_tabla_mayores_errores._tarea")

        threading.Thread(target=_tarea, daemon=True).start()

def main(page: ft.Page):
    # Aquí adentro está todo tu código de configuración inicial de la página
    app = SistemaIndependiente(page)

if __name__ == "__main__":

    def main(page: ft.Page):
        app = SistemaIndependiente(page)
    
    puerto_nube = os.getenv("PORT")
    es_ejecutable = getattr(sys, 'frozen', False)
    
    # --- RUTA ABSOLUTA BLINDADA ---
    if es_ejecutable:
        # Si es un .EXE, usa la memoria temporal interna donde PyInstaller guardó las imágenes
        directorio_raiz = sys._MEIPASS
    else:
        # Si es tu código .py o Render, usa la carpeta real del proyecto
        directorio_raiz = os.path.dirname(os.path.abspath(__file__))
        
    ruta_assets = os.path.join(directorio_raiz, "assets")
    
    # Prevenir colapsos
    if not os.path.exists(ruta_assets):
        try: os.makedirs(ruta_assets)
        except: pass
    
    # --- MOTOR DE ARRANQUE TRIPLE ---
    if es_ejecutable:
        # MODO 1: USUARIO FINAL (.exe)
        # Abre ventana nativa y apunta los recursos a la memoria interna
        ft.app(target=main, assets_dir=ruta_assets)
        
    elif puerto_nube:
        # MODO 2: RENDER (Nube)
        ft.app(target=main, view=ft.AppView.WEB_BROWSER, port=int(puerto_nube), host="0.0.0.0", assets_dir=ruta_assets)
        
    else:
        # MODO 3: DEPURACIÓN LOCAL (Navegador)
        ft.app(target=main)#, view=ft.AppView.WEB_BROWSER, port=8555, assets_dir=ruta_assets)