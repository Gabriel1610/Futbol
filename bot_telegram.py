import os
import random
import datetime
import sys
from datetime import timedelta
import threading
import pytz
import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, 
    filters, ContextTypes, ConversationHandler
)

from base_de_datos import BaseDeDatos

class RobotTelegram:
    # --- ESTADOS DE CONVERSACIÓN (Atributos de Clase) ---
    (
        esperando_identificador, esperando_codigo, esperando_partido_id,
        esperando_pronostico, esperando_tipo_tabla, esperando_edicion_tabla,
        esperando_tipo_pronosticos, esperando_edicion_pronosticos, esperando_usuario_pronosticos,
        esperando_tipo_opt_pes, esperando_edicion_opt_pes, esperando_accion_opt_pes,
        esperando_tipo_mayores_errores, esperando_edicion_mayores_errores, esperando_accion_mayores_errores,
        esperando_tipo_falso_profeta, esperando_edicion_falso_profeta, esperando_accion_falso_profeta,
        esperando_menu_estadisticas, 
        esperando_tipo_estilo_decision, esperando_edicion_estilo_decision,
        esperando_accion_estilo_decision,
        esperando_tipo_mufa, esperando_edicion_mufa, esperando_accion_mufa,
        esperando_tipo_mejor_predictor, esperando_edicion_mejor_predictor,
        esperando_accion_mejor_predictor,
        esperando_tipo_racha_record, esperando_edicion_racha_record, esperando_accion_racha_record,
        esperando_tipo_racha_actual, esperando_edicion_racha_actual, esperando_accion_racha_actual,
        esperando_tipo_cambios, esperando_edicion_cambios,
        esperando_accion_cambios,
        esperando_menu_rankings, esperando_menu_perfil,
        esperando_tipo_perfil,
        esperando_edicion_perfil, esperando_usuario_perfil,
        esperando_accion_perfil,
        esperando_menu_administracion, esperando_fecha_resultado, esperando_goles_resultado,
        esperando_edicion_ver_partidos,
        esperando_menu_admin_partidos, esperando_menu_admin_equipos,
        esperando_nombre_nuevo_equipo,
        esperando_equipo_a_editar, esperando_nuevo_nombre_equipo,
        esperando_equipo_a_eliminar,
        esperando_confirmacion_eliminar_equipo,
        esperando_crear_partido_rival, esperando_crear_partido_edicion,
        esperando_crear_partido_condicion, esperando_crear_partido_fecha,
        esperando_crear_partido_goles,
        esperando_fecha_partido_a_editar, esperando_editar_partido_rival,
        esperando_editar_partido_edicion, esperando_editar_partido_condicion,
        esperando_editar_partido_fecha_final,
        esperando_accion_tabla_posiciones,
        esperando_archivo_a_leer
    ) = range(1, 67)

    def __init__(self):
        """Inicializa las configuraciones, la base de datos y la app de Telegram."""
        load_dotenv(override=True)
        self.token = os.getenv("TELEGRAM_TOKEN")
        self.email_emisor = os.getenv("EMAIL_USER")
        self.email_pass = os.getenv("EMAIL_PASSWORD")
        self.limite_errores = 10 # Podría ser un env también

        # Instanciamos la base de datos
        self.db = BaseDeDatos()

        # Construimos la aplicación de Telegram
        self.app = ApplicationBuilder().token(self.token).build()
        
        # Registramos los flujos
        self._setup_handlers()

        # 🚀 DISPARAMOS EL CÁLCULO DE CRONÓMETROS 
        self._programar_cronometros_partidos()
    
    # --- MÉTODOS GENÉRICOS PARA RANKINGS ---
    
    async def _iniciar_ranking_generico(self, update: Update, context: ContextTypes.DEFAULT_TYPE, mensaje: str, estado_siguiente: int):
        """Paso 1 Genérico: Pregunta Histórica vs Torneo."""
        id_telegram = update.message.from_user.id
        if not self.db.obtener_usuario_por_telegram(id_telegram):
            await update.message.reply_text("❌ Tenés que asociar tu cuenta primero.")
            return ConversationHandler.END

        botones = [["1_ Histórica"], ["2_ Por Torneo"], ["🔙 Volver al menú"]]
        await update.message.reply_text(
            mensaje, parse_mode="Markdown", reply_markup=ReplyKeyboardMarkup(botones, resize_keyboard=True)
        )
        return estado_siguiente

    async def _procesar_tipo_ranking_generico(self, update: Update, context: ContextTypes.DEFAULT_TYPE, 
                                              funcion_imprimir, estado_actual: int, estado_siguiente: int, 
                                              clave_dicc: str, solo_finalizados: bool = False):
        """Paso 2 Genérico: Imprime histórica o muestra la lista de torneos."""
        texto = update.message.text.strip()
        
        if texto == "🔙 Volver al menú":
            await self.mostrar_menu(update, context)
            return ConversationHandler.END
            
        if texto == "1_ Histórica":
            return await funcion_imprimir(update, context, edicion_id=None, titulo="Histórica")
            
        elif texto == "2_ Por Torneo":
            ediciones = self.db.obtener_ediciones(solo_finalizados=solo_finalizados)
            if not ediciones:
                await update.message.reply_text("❌ No hay torneos registrados (o con partidos finalizados) todavía.")
                await self.mostrar_menu(update, context)
                return ConversationHandler.END
                
            botones = []
            diccionario_ediciones = {}
            for ed in ediciones:
                id_edicion = ed[0]
                nombre_completo = f"{ed[1]} {ed[2]}"
                botones.append([nombre_completo])
                diccionario_ediciones[nombre_completo] = id_edicion
                
            botones.append(["🔙 Volver al menú"])
            context.user_data[clave_dicc] = diccionario_ediciones
            
            await update.message.reply_text(
                "🏆 Elegí el torneo:",
                reply_markup=ReplyKeyboardMarkup(botones, resize_keyboard=True)
            )
            return estado_siguiente
        else:
            await update.message.reply_text("❌ Opción no válida. Elegí un botón.")
            return estado_actual

    async def _procesar_edicion_ranking_generico(self, update: Update, context: ContextTypes.DEFAULT_TYPE, 
                                                 funcion_imprimir, estado_actual: int, clave_dicc: str):
        """Paso 3 Genérico: Captura el torneo elegido e imprime."""
        texto = update.message.text.strip()
        
        if texto == "🔙 Volver al menú":
            await self.mostrar_menu(update, context)
            return ConversationHandler.END
            
        diccionario = context.user_data.get(clave_dicc, {})
        if texto not in diccionario:
            await update.message.reply_text("❌ Torneo no válido. Elegí usando los botones.")
            return estado_actual
            
        edicion_id = diccionario[texto]
        return await funcion_imprimir(update, context, edicion_id=edicion_id, titulo=texto)

    # --- FÁBRICAS DE CALLBACKS (Solución al error de __name__) ---
    def _generar_botones_ediciones(self, incluir_historico=True):
        """Genera el teclado con todos los torneos disponibles leyendo la BD."""
        ediciones = self.db.obtener_ediciones()
        botones = []
        
        # Opcionalmente agregamos el botón Histórico al principio
        if incluir_historico:
            botones.append(["Histórico"])
            
        # Armamos los botones de a dos columnas
        fila_temp = []
        for ed in ediciones:
            # ed[1] es el nombre (ej. LPF) y ed[2] es el año
            fila_temp.append(f"{ed[1]} {ed[2]}")
            if len(fila_temp) == 2:
                botones.append(fila_temp)
                fila_temp = []
                
        # Si quedó alguno suelto, lo agregamos al final
        if fila_temp:
            botones.append(fila_temp)
            
        # Opciones de navegación predeterminadas
        botones.append(["🔙 Atrás", "🔙 Volver al menú principal"])
        
        return botones
    
    def _crear_iniciar(self, mensaje: str, estado_siguiente: int):
        async def enrutador(update: Update, context: ContextTypes.DEFAULT_TYPE):
            return await self._iniciar_ranking_generico(update, context, mensaje, estado_siguiente)
        enrutador.__name__ = f"iniciar_{estado_siguiente}" # Engañamos al logger de Telegram
        return enrutador

    def _crear_procesar_tipo(self, funcion_imprimir, estado_actual: int, estado_siguiente: int, clave_dicc: str, solo_finalizados: bool = False):
        async def enrutador(update: Update, context: ContextTypes.DEFAULT_TYPE):
            return await self._procesar_tipo_ranking_generico(update, context, funcion_imprimir, estado_actual, estado_siguiente, clave_dicc, solo_finalizados)
        enrutador.__name__ = f"procesar_tipo_{estado_actual}"
        return enrutador

    def _crear_procesar_edicion(self, funcion_imprimir, estado_actual: int, clave_dicc: str):
        async def enrutador(update: Update, context: ContextTypes.DEFAULT_TYPE):
            return await self._procesar_edicion_ranking_generico(update, context, funcion_imprimir, estado_actual, clave_dicc)
        enrutador.__name__ = f"procesar_edicion_{estado_actual}"
        return enrutador

    async def iniciar_administracion(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Menú principal de Administración (Exclusivo para Admins)."""
        id_telegram = update.message.from_user.id
        username = self.db.obtener_usuario_por_telegram(id_telegram)
        
        if username not in self.db.obtener_administradores():
            await update.message.reply_text("⛔ *Acceso Denegado*", parse_mode="Markdown")
            return ConversationHandler.END
            
        botones = [
            ["1_ Partidos", "2_ Equipos"],
            ["3_ Leer archivos"], # <--- NUEVO BOTÓN
            ["🔙 Volver al menú principal"]
        ]
        
        mensaje = (
            "⚙️ *Panel de Administración*\n\n"
            "Bienvenido al panel de control. Elegí el área que querés gestionar:\n\n"
            "⚽ *1_ Partidos:* Carga manual de resultados finales y listado de encuentros por torneo.\n"
            "🛡️ *2_ Equipos:* Gestión de los clubes rivales (altas, bajas y modificaciones) en la base de datos.\n"
            "📂 *3_ Leer archivos:* Consulta y limpieza de los archivos de registro (logs) generados por el bot." # <--- NUEVO TEXTO
        )
        
        await update.message.reply_text(
            mensaje, 
            parse_mode="Markdown", 
            reply_markup=ReplyKeyboardMarkup(botones, resize_keyboard=True)
        )
        return self.esperando_menu_administracion

    async def iniciar_admin_partidos(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Submenú de gestión de Partidos."""
        botones = [
            ["1_ Cargar resultado", "2_ Ver partidos"],
            ["3_ Crear partido", "4_ Editar partido"], # 🌟 CORRECCIÓN: Botones alineados con el handler
            ["🔙 Atrás", "🔙 Volver al menú principal"]
        ]
        mensaje = (
            "⚽ *Gestión de Partidos*\n\n"
            "Elegí una opción:\n\n"
            "📝 *1_ Cargar resultado:* Buscá un partido por fecha e ingresá su resultado.\n"
            "📋 *2_ Ver partidos:* Consultá el listado completo de partidos de un torneo.\n"
            "➕ *3_ Crear partido:* Registrá un nuevo encuentro en la base de datos.\n"
            "✏️ *4_ Editar partido:* Modificá los datos de un partido ya creado."
        )
        await update.message.reply_text(
            mensaje, parse_mode="Markdown", reply_markup=ReplyKeyboardMarkup(botones, resize_keyboard=True)
        )
        return self.esperando_menu_admin_partidos

    async def iniciar_admin_equipos(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Submenú de gestión de Equipos."""
        botones = [
            ["1_ Agregar", "2_ Editar"],
            ["3_ Eliminar"],
            ["🔙 Atrás", "🔙 Volver al menú principal"]
        ]
        mensaje = (
            "🛡️ *Gestión de Equipos*\n\n"
            "Elegí una opción:\n\n"
            "➕ *1_ Agregar:* Añadí un nuevo club rival a la base de datos.\n"
            "✏️ *2_ Editar:* Modificá el nombre de un club existente.\n"
            "🗑️ *3_ Eliminar:* Borrá un equipo (solo si no tiene partidos registrados)."
        )
        await update.message.reply_text(
            mensaje, parse_mode="Markdown", reply_markup=ReplyKeyboardMarkup(botones, resize_keyboard=True)
        )
        return self.esperando_menu_admin_equipos

    async def iniciar_eliminar_equipo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Paso 1 Eliminar: Imprime la lista de equipos usando la función reutilizable."""
        pregunta = "🗑️ *Respondé con el NÚMERO del equipo que querés eliminar:*"
        # Reutilizamos la función mágica que creaste en el paso anterior
        exito = await self._mostrar_lista_equipos(update, context, pregunta)
        
        if not exito:
            return await self.iniciar_admin_equipos(update, context)
            
        return self.esperando_equipo_a_eliminar

    async def procesar_equipo_a_eliminar(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Paso 2 Eliminar: Valida el número y elimina, o deriva si hay conflicto."""
        texto = update.message.text.strip()
        mapa = context.user_data.get('mapa_equipos', {})
        
        if texto not in mapa:
            await update.message.reply_text("❌ Número inválido. Ingresá un número de la lista o tocá \"Atrás\".")
            return self.esperando_equipo_a_eliminar
            
        equipo_elegido = mapa[texto]
        
        try:
            # Mandamos a eliminar de forma limpia
            self.db.eliminar_rival_manual(equipo_elegido['id'])
            
            await update.message.reply_text(
                f"✅ ¡El equipo *{equipo_elegido['nombre']}* fue eliminado correctamente de la base de datos!",
                parse_mode="Markdown"
            )
            context.user_data.pop('mapa_equipos', None)
            return await self.iniciar_admin_equipos(update, context)
            
        except Exception as e:
            # 🌟 INTERCEPTAMOS EL ERROR DE MYSQL (Error 1451 configurado en tu BaseDeDatos)
            if "No se puede eliminar este equipo porque ya tiene partidos registrados" in str(e):
                context.user_data['equipo_a_eliminar_forzado'] = equipo_elegido
                
                botones = [
                    ["1_ Ver partidos", "2_ Sí"],
                    ["3_ No"],
                    ["🔙 Atrás", "🔙 Volver al menú principal"]
                ]
                
                mensaje = (
                    f"⚠️ *ATENCIÓN: EQUIPO CON HISTORIAL* ⚠️\n\n"
                    f"El equipo *{equipo_elegido['nombre']}* posee partidos en la base de datos.\n\n"
                    f"Si decidís eliminarlo, *se borrarán de manera definitiva todos sus partidos y los pronósticos* "
                    f"que hayan hecho los usuarios. Esto alterará drásticamente el Prode: cambiarán las tablas de posiciones, "
                    f"los puntos acumulados, la efectividad y los historiales de la comunidad.\n\n"
                    f"Elegí una opción:\n\n"
                    f"📋 *1_ Ver partidos:* Muestra los partidos registrados con este equipo.\n"
                    f"🗑️ *2_ Sí:* Eliminar el equipo y destruir todo su historial de partidos.\n"
                    f"🚫 *3_ No:* Cancelar la operación."
                )
                
                await update.message.reply_text(
                    mensaje, parse_mode="Markdown", reply_markup=ReplyKeyboardMarkup(botones, resize_keyboard=True)
                )
                return self.esperando_confirmacion_eliminar_equipo
            else:
                await update.message.reply_text(f"❌ Error: {e}\n\nElegí otro número o tocá \"Atrás\".")
                return self.esperando_equipo_a_eliminar

    async def procesar_confirmacion_eliminar_equipo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Paso 3 Eliminar: Decide qué hacer con el equipo bloqueado."""
        texto = update.message.text.strip()
        equipo = context.user_data.get('equipo_a_eliminar_forzado')
        
        if not equipo:
            await update.message.reply_text("❌ La sesión expiró. Volvé a empezar.")
            return await self.iniciar_admin_equipos(update, context)
            
        if texto == "1_ Ver partidos":
            partidos = self.db.obtener_partidos_por_rival(equipo['id'])
            if not partidos:
                await update.message.reply_text("No se encontraron partidos.")
                return self.esperando_confirmacion_eliminar_equipo
                
            mensajes = []
            mensaje_actual = f"📋 *Partidos de {equipo['nombre']}*\n\n"
            
            for p in partidos:
                fecha_str = p['fecha_hora'].strftime('%d/%m/%Y %H:%M') if p['fecha_hora'] else "A conf."
                torneo = f"{p['torneo']} {p['anio']}"
                
                if p['condicion'] == -1:
                    encuentro = f"{equipo['nombre']} vs Independiente"
                    res = f"{p['goles_rival']} - {p['goles_cai']}"
                else:
                    encuentro = f"Independiente vs {equipo['nombre']}"
                    res = f"{p['goles_cai']} - {p['goles_rival']}"
                
                estado = f"✅ Finalizado ({res})" if p['goles_cai'] is not None else "⏳ Pendiente"
                
                bloque = f"📅 {fecha_str}\n🏆 {torneo}\n⚔️ {encuentro}\n📊 {estado}\n—\n"
                
                if len(mensaje_actual) + len(bloque) > 3800:
                    mensajes.append(mensaje_actual)
                    mensaje_actual = bloque
                else:
                    mensaje_actual += bloque
                    
            if mensaje_actual: mensajes.append(mensaje_actual)
                
            for m in mensajes:
                await update.message.reply_text(m, parse_mode="Markdown")
                
            # No retornamos a ningún lado, nos quedamos esperando que decida "2_ Sí" o "3_ No"
            return self.esperando_confirmacion_eliminar_equipo
            
        elif texto == "2_ Sí":
            try:
                # 1. Primero borramos todos los partidos (y sus pronósticos caen solos)
                self.db.eliminar_partidos_por_rival(equipo['id'])
                
                # 2. Ahora que el equipo está "limpio", lo borramos
                self.db.eliminar_equipo_forzado(equipo['id']) # O usar self.db.eliminar_rival_manual(equipo['id'])
                
                await update.message.reply_text(
                    f"✅ *¡ELIMINACIÓN FORZADA EXITOSA!*\n\nEl equipo *{equipo['nombre']}* y todo su rastro "
                    f"fueron borrados permanentemente del Prode.",
                    parse_mode="Markdown"
                )
            except Exception as e:
                await update.message.reply_text(f"❌ Error crítico al intentar eliminar: {e}")
            
            context.user_data.pop('equipo_a_eliminar_forzado', None)
            context.user_data.pop('mapa_equipos', None)
            return await self.iniciar_admin_equipos(update, context)
            
        elif texto == "3_ No":
            await update.message.reply_text("🚫 Operación cancelada. El equipo y sus partidos están a salvo.")
            context.user_data.pop('equipo_a_eliminar_forzado', None)
            return await self.iniciar_admin_equipos(update, context)
            
        else:
            await update.message.reply_text("❌ Opción inválida. Tocá \"1_ Ver partidos\", \"2_ Sí\" o \"3_ No\".")
            return self.esperando_confirmacion_eliminar_equipo

    async def _mostrar_lista_equipos(self, update: Update, context: ContextTypes.DEFAULT_TYPE, texto_pregunta: str):
        """Función reutilizable: Lista los equipos enumerados desde 1 y devuelve un mapa de IDs."""
        rivales = self.db.obtener_rivales()
        if not rivales:
            await update.message.reply_text("❌ No hay equipos registrados en la base de datos.")
            return False
            
        mapa_equipos = {}
        mensajes = []
        mensaje_actual = "🛡️ *Listado de Equipos*\n\n"
        
        # Iteramos empezando desde el número 1
        for i, rival in enumerate(rivales, start=1):
            r_id = rival[0]
            r_nombre = rival[1]
            
            # Guardamos la relación { "1": {"id": 15, "nombre": "Boca"} }
            mapa_equipos[str(i)] = {'id': r_id, 'nombre': r_nombre}
            
            bloque = f"*{i}_* {r_nombre}\n"
            
            # Paginación para no superar el límite de 4000 caracteres de Telegram
            if len(mensaje_actual) + len(bloque) > 3800:
                mensajes.append(mensaje_actual)
                mensaje_actual = bloque
            else:
                mensaje_actual += bloque
                
        if mensaje_actual:
            mensajes.append(mensaje_actual)
            
        # Enviamos los globos de texto (todos menos el último van sin botones)
        for m in mensajes[:-1]:
            await update.message.reply_text(m, parse_mode="Markdown")
            
        botones = [
            ["🚫 Cancelar"],
            ["🔙 Volver al menú principal"]
        ]
        
        await update.message.reply_text(
            mensajes[-1] + f"\n\n{texto_pregunta}",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(botones, resize_keyboard=True)
        )
        
        # Guardamos el mapa en la memoria para que el siguiente paso lo pueda leer
        context.user_data['mapa_equipos'] = mapa_equipos
        return True

    async def iniciar_editar_equipo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Paso 1 Editar: Imprime la lista de equipos usando la función reutilizable."""
        pregunta = "✏️ *Respondé con el NÚMERO del equipo que querés editar:*"
        exito = await self._mostrar_lista_equipos(update, context, pregunta)
        
        if not exito:
            return await self.iniciar_admin_equipos(update, context)
            
        return self.esperando_equipo_a_editar

    async def procesar_equipo_a_editar(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Paso 2 Editar: Valida el número y pide el nuevo nombre."""
        texto = update.message.text.strip()
        mapa = context.user_data.get('mapa_equipos', {})
        
        if texto not in mapa:
            await update.message.reply_text("❌ Número inválido. Ingresá un número de la lista o tocá \"Atrás\".")
            return self.esperando_equipo_a_editar
            
        equipo_elegido = mapa[texto]
        context.user_data['equipo_a_editar'] = equipo_elegido
        
        botones = [["🔙 Atrás", "🔙 Volver al menú principal"]]
        await update.message.reply_text(
            f"✏️ Elegiste editar: *{equipo_elegido['nombre']}*\n\n"
            f"Ingresá el *nuevo nombre* para este club:",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(botones, resize_keyboard=True)
        )
        return self.esperando_nuevo_nombre_equipo

    async def procesar_nuevo_nombre_equipo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Paso 3 Editar: Valida, recorta espacios y guarda en DB."""
        nuevo_nombre = update.message.text.strip() # Recorta por izquierda y derecha
        equipo = context.user_data.get('equipo_a_editar')
        
        if not equipo:
            await update.message.reply_text("❌ La sesión expiró. Empecemos de nuevo.")
            return await self.iniciar_admin_equipos(update, context)
            
        if not nuevo_nombre:
            await update.message.reply_text("❌ El nombre no puede estar vacío. Intentá de nuevo o tocá \"Atrás\".")
            return self.esperando_nuevo_nombre_equipo
            
        try:
            # Usamos la función actualizar_rival que ya tiene el manejo de errores MySQL integrado
            self.db.actualizar_rival(equipo['id'], nuevo_nombre)
            
            await update.message.reply_text(
                f"✅ ¡Excelente! El equipo *{equipo['nombre']}* ahora se llama *{nuevo_nombre}* en la base de datos.",
                parse_mode="Markdown"
            )
            
            # Limpiamos la memoria
            context.user_data.pop('mapa_equipos', None)
            context.user_data.pop('equipo_a_editar', None)
            
            return await self.iniciar_admin_equipos(update, context)
            
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}\n\nIngresá otro nombre o tocá \"Atrás\".")
            return self.esperando_nuevo_nombre_equipo
        
    async def iniciar_agregar_equipo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Paso 1 Equipos: Solicita el nombre del nuevo club."""
        botones = [["🔙 Atrás", "🔙 Volver al menú principal"]]
        await update.message.reply_text(
            "➕ *Agregar Equipo*\n\n"
            "Por favor, ingresá el nombre del nuevo equipo:\n"
            "_(Ejemplo: Boca Juniors o Racing Club)_",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(botones, resize_keyboard=True)
        )
        return self.esperando_nombre_nuevo_equipo

    async def procesar_nombre_nuevo_equipo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Paso 2 Equipos: Valida y guarda el equipo en la BD."""
        texto = update.message.text.strip() # Recortamos espacios por izquierda y derecha
        
        # Validación de cadena vacía
        if not texto:
            await update.message.reply_text(
                "❌ El nombre no puede estar vacío.\n"
                "Por favor, ingresá un nombre válido o tocá \"Atrás\"."
            )
            return self.esperando_nombre_nuevo_equipo
            
        try:
            # Intentamos insertar en la base de datos
            self.db.insertar_rival_manual(texto)
            
            await update.message.reply_text(
                f"✅ ¡El equipo *{texto}* fue agregado con éxito a la base de datos!",
                parse_mode="Markdown"
            )
            # Devolvemos al submenú de equipos tras el éxito
            return await self.iniciar_admin_equipos(update, context)
            
        except Exception as e:
            # Si MySQL tira error por duplicado o vacío (capturado en base_de_datos.py)
            await update.message.reply_text(
                f"❌ Error: {e}\n\n"
                f"Intentá con otro nombre o tocá \"Atrás\"."
            )
            return self.esperando_nombre_nuevo_equipo
    
    async def iniciar_ver_partidos_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Paso 1 Admin Ver Partidos: Usa la función existente para listar los torneos."""
        botones = self._generar_botones_ediciones(incluir_historico=False)
        await update.message.reply_text(
            "📋 *Ver Partidos*\n\n"
            "Seleccioná el torneo del cual querés ver el listado de partidos:",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(botones, resize_keyboard=True)
        )
        return self.esperando_edicion_ver_partidos

    async def procesar_edicion_ver_partidos(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Paso 2 Admin Ver Partidos: Busca los partidos y los envía."""
        texto_edicion = update.message.text.strip()
        
        # 1. Obtenemos el ID del torneo usando tu lógica reutilizable
        ediciones = self.db.obtener_ediciones()
        edicion_id_real = None
        
        for ed in ediciones:
            if f"{ed[1]} {ed[2]}" == texto_edicion:
                edicion_id_real = ed[0]
                break
                
        if not edicion_id_real:
            await update.message.reply_text("❌ Torneo no válido. Elegí usando los botones.")
            return self.esperando_edicion_ver_partidos
            
        # 2. Buscamos los partidos usando la nueva función
        partidos = self.db.obtener_partidos_admin_por_edicion(edicion_id_real)
        
        if not partidos:
            await update.message.reply_text(f"🤷‍♂️ Todavía no hay partidos cargados para *{texto_edicion}*.", parse_mode="Markdown")
            return await self.iniciar_admin_partidos(update, context)
            
        # 3. Armamos el listado (con paginación inteligente por el límite de caracteres de Telegram)
        mensajes = []
        mensaje_actual = f"📋 *Listado de Partidos: {texto_edicion}*\n\n"
        
        for p in partidos:
            p_id = p['id']
            rival = p['rival']
            fecha_dt = p['fecha_hora']
            condicion = p['condicion']
            g_cai = p['goles_cai']
            g_rival = p['goles_rival']
            
            fecha_str = fecha_dt.strftime('%d/%m/%Y %H:%M') if fecha_dt else "A conf."
            
            # Formateo correcto dependiendo de la localía
            if condicion == -1:
                partido_str = f"{rival} vs Independiente"
                if g_cai is not None:
                    resultado_str = f"✅ Finalizado: {g_rival} - {g_cai}"
                else:
                    resultado_str = "⏳ Pendiente"
            else:
                partido_str = f"Independiente vs {rival}"
                if g_cai is not None:
                    resultado_str = f"✅ Finalizado: {g_cai} - {g_rival}"
                else:
                    resultado_str = "⏳ Pendiente"
                    
            bloque = f"📅 *{fecha_str}*\n"
            bloque += f"⚔️ {partido_str}\n"
            bloque += f"📊 {resultado_str}\n—\n"
            
            if len(mensaje_actual) + len(bloque) > 3800:
                mensajes.append(mensaje_actual)
                mensaje_actual = bloque
            else:
                mensaje_actual += bloque
                
        if mensaje_actual:
            mensajes.append(mensaje_actual)
            
        # 4. Enviamos y volvemos al menú de admin
        for m in mensajes:
            await update.message.reply_text(m, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
            
        return await self.iniciar_admin_partidos(update, context)

    async def iniciar_carga_resultado(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Paso 1 Admin: Solicita la fecha del partido."""
        botones = [["🔙 Atrás", "🔙 Volver al menú principal"]]
        await update.message.reply_text(
            "📝 *Cargar Resultado Manual*\n\n"
            "Por favor, ingresá la fecha del partido en formato *dd/mm/aaaa* (ej: 25/04/2026).\n\n"
            "_Solo podés cargar resultados de partidos disputados hoy o en el pasado._",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(botones, resize_keyboard=True)
        )
        return self.esperando_fecha_resultado

    async def procesar_fecha_resultado(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Paso 2 Admin: Valida la fecha, busca el partido y pide el resultado."""
        texto_fecha = update.message.text.strip()
        
        try:
            # 1. Validar que la fecha sea del presente o pasado
            fecha_ingresada = datetime.datetime.strptime(texto_fecha, "%d/%m/%Y").date()
            fecha_actual = self.db.obtener_hora_argentina().date()
            
            if fecha_ingresada > fecha_actual:
                await update.message.reply_text(
                    "❌ La fecha ingresada es en el futuro.\n"
                    "Por favor, ingresá una fecha del presente o pasado, o tocá \"Atrás\"."
                )
                return self.esperando_fecha_resultado
                
            # 2. Buscar en la base de datos
            partido = self.db.obtener_partido_por_fecha_exacta(texto_fecha)
            
            if not partido:
                await update.message.reply_text(
                    f"❌ No se encontró ningún partido oficial registrado el *{texto_fecha}*.\n"
                    "Revisá la fecha, ingresala nuevamente o tocá \"Atrás\".",
                    parse_mode="Markdown"
                )
                return self.esperando_fecha_resultado
            
            # Guardamos el partido en memoria para el siguiente paso
            context.user_data['partido_admin'] = partido
            
            # Extraemos la información para mostrarla
            rival = partido['rival']
            condicion = partido['condicion']
            torneo = f"{partido['torneo']} {partido['anio']}"
            
            # Formateamos fecha y hora (ej: 24/04/2026 a las 15:30)
            fecha_dt = partido['fecha_hora']
            fecha_str = fecha_dt.strftime('%d/%m/%Y a las %H:%M') if fecha_dt else "A conf."
            
            if condicion == -1:
                partido_str = f"{rival} vs Independiente"
            else:
                partido_str = f"Independiente vs {rival}"
                
            await update.message.reply_text(
                f"⚽ *Partido Encontrado*\n\n"
                f"📅 *Fecha:* {fecha_str}\n"
                f"🏆 *Torneo:* {torneo}\n"
                f"⚔️ *Encuentro:* {partido_str}\n\n"
                f"Por favor, ingresá el resultado final con el formato *golesCAI-golesRival* (Ej: 2-0 o 1-1).",
                parse_mode="Markdown"
            )
            return self.esperando_goles_resultado
            
        except ValueError:
            await update.message.reply_text("❌ Formato de fecha inválido. Asegurate de usar el formato dd/mm/aaaa (ej: 25/04/2026).")
            return self.esperando_fecha_resultado

    async def procesar_goles_resultado(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Paso 3 Admin: Valida el resultado y actualiza la base de datos."""
        texto = update.message.text.strip()
        partido = context.user_data.get('partido_admin')
        
        if not partido:
            await update.message.reply_text("❌ La sesión expiró. Volvé a iniciar el proceso.")
            return await self.iniciar_admin_partidos(update, context)
            
        try:
            # Validamos el formato del resultado
            if "-" not in texto: raise ValueError()
            partes = texto.split("-")
            if len(partes) != 2: raise ValueError()
                
            goles_cai = int(partes[0].strip())
            goles_rival = int(partes[1].strip())
            
            # 1. Actualizar DB
            self.db.actualizar_goles_partido(partido['id'], goles_cai, goles_rival)
            
            # 2. Armar texto de confirmación
            rival = partido['rival']
            condicion = partido['condicion']
            
            # 🌟 CAMBIO CLAVE: Agregamos "%H:%M" al formateo de la fecha
            fecha_dt = partido['fecha_hora']
            fecha_partido = fecha_dt.strftime('%d/%m/%Y %H:%M') if fecha_dt else "A conf."
            
            torneo = f"{partido['torneo']} {partido['anio']}"
            
            if condicion == -1:
                resultado_str = f"{rival} {goles_rival} - {goles_cai} Independiente 🔴"
            else:
                resultado_str = f"🔴 Independiente {goles_cai} - {goles_rival} {rival}"
                
            await update.message.reply_text(
                f"✅ *¡RESULTADO CARGADO CON ÉXITO!*\n\n"
                f"Has actualizado la base de datos correctamente con los siguientes detalles:\n\n"
                f"📅 *Fecha:* {fecha_partido}\n"
                f"🏆 *Torneo:* {torneo}\n"
                f"🎯 *Resultado oficial:*\n"
                f"*{resultado_str}*\n\n"
                f"_Los rankings de todos los usuarios han sido actualizados._",
                parse_mode="Markdown"
            )
            
            # Limpiamos la memoria
            context.user_data.pop('partido_admin', None)
            
            # Devolvemos al usuario al menú de administración
            return await self.iniciar_administracion(update, context)
            
        except ValueError:
            await update.message.reply_text(
                "❌ Formato inválido.\n"
                "Debe ser solo números separados por un guion. Ejemplo: 2-0\n\n"
                "Intentá de nuevo o tocá \"Atrás\"."
            )
            return self.esperando_goles_resultado
        except Exception as e:
            await update.message.reply_text(f"❌ Error en la base de datos: {e}\nIntentá de nuevo o tocá \"Atrás\".")
            return self.esperando_goles_resultado

    # --- MÉTODOS PRIVADOS DE CONFIGURACIÓN ---

    def _setup_handlers(self):
        """Configura todos los comandos y manejadores de conversación."""
        conv_handler = ConversationHandler(
            # 🌟 CAMBIO 1: Se suman los nuevos botones principales a los puntos de entrada
            entry_points=[
                MessageHandler(filters.Regex("^1_ Asociar cuenta$"), self.iniciar_asociacion),
                MessageHandler(filters.Regex("^1_ Cargar pronóstico$"), self.iniciar_carga_pronostico),
                MessageHandler(filters.Regex("^2_ Ver posiciones$"), self._crear_iniciar("🏆 *Tabla de Posiciones*\n\n¿Qué posiciones querés ver?", self.esperando_tipo_tabla)),
                MessageHandler(filters.Regex("^3_ Consultar pronósticos$"), self._crear_iniciar("👀 *Consultar Pronósticos*\n\n¿Qué querés consultar?", self.esperando_tipo_pronosticos)),
                MessageHandler(filters.Regex("^4_ Ver Estadísticas$"), self.iniciar_ver_estadisticas),
                MessageHandler(filters.Regex("^5_ Administración$"), self.iniciar_administracion)
            ],
            states={
                # --- NUEVA RAÍZ DE ESTADÍSTICAS ---
                self.esperando_menu_estadisticas: [
                    MessageHandler(filters.Regex("^1_ Rankings$"), self.iniciar_menu_rankings),
                    MessageHandler(filters.Regex("^2_ Perfil de la comunidad$"), self.iniciar_menu_perfil),
                    MessageHandler(filters.Regex("^🔙 Volver al menú principal$"), self.mostrar_menu)
                ],

                # 🌟 CAMBIO 2: Se eliminan las posiciones 1 y 2, y se reenumeran las Regex del 1 al 9
                self.esperando_menu_rankings: [
                    MessageHandler(filters.Regex("^1_ Optimismo/Pesimismo$"), self._crear_iniciar("☯️ *Optimismo/Pesimismo*\n\n¿Qué datos querés consultar?", self.esperando_tipo_opt_pes)),
                    MessageHandler(filters.Regex("^2_ Mayores errores$"), self._crear_iniciar("📉 *Mayores Errores*\n\n¿Qué datos querés consultar?", self.esperando_tipo_mayores_errores)),
                    MessageHandler(filters.Regex("^3_ Falso Profeta$"), self._crear_iniciar("🤥 *Falso Profeta*\n\n¿Qué datos querés consultar?", self.esperando_tipo_falso_profeta)),
                    MessageHandler(filters.Regex("^4_ Estilos de decisión$"), self._crear_iniciar("🧠 *Estilos de Decisión*\n\n¿Qué datos querés consultar?", self.esperando_tipo_estilo_decision)),
                    MessageHandler(filters.Regex("^5_ Mufa$"), self._crear_iniciar("🐈‍⬛ *Ranking Mufas*\n\n¿Qué datos querés consultar?", self.esperando_tipo_mufa)),
                    MessageHandler(filters.Regex("^6_ Mejor predictor$"), self._crear_iniciar("🎯 *Mejor Predictor*\n\n¿Qué datos querés consultar?", self.esperando_tipo_mejor_predictor)),
                    MessageHandler(filters.Regex("^7_ Racha récord$"), self._crear_iniciar("🔥 *Racha Récord*\n\n¿Qué datos querés consultar?", self.esperando_tipo_racha_record)),
                    MessageHandler(filters.Regex("^8_ Racha actual$"), self._crear_iniciar("⏳ *Racha Actual*\n\n¿Qué datos querés consultar?", self.esperando_tipo_racha_actual)),
                    MessageHandler(filters.Regex("^9_ Cambio de pronósticos$"), self._crear_iniciar("🔄 *Estabilidad de Pronósticos*\n\n¿Qué datos querés consultar?", self.esperando_tipo_cambios)),
                    
                    MessageHandler(filters.Regex("^🔙 Atrás$"), self.iniciar_ver_estadisticas),
                    MessageHandler(filters.Regex("^🔙 Volver al menú principal$"), self.mostrar_menu)
                ],
                
                # --- FLUJOS BASE (Se mantienen igual) ---
                self.esperando_identificador: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.procesar_identificador)],
                self.esperando_codigo: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.procesar_codigo)],
                self.esperando_partido_id: [
                    MessageHandler(filters.Regex("^🔙 Volver al menú principal$"), self.mostrar_menu),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.procesar_partido_id)
                ],
                
                self.esperando_pronostico: [
                    MessageHandler(filters.Regex("^🔙 Volver al menú principal$"), self.mostrar_menu),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.procesar_pronostico)
                ],

                # --- FLUJOS GENÉRICOS ---
                # 1. Posiciones
                self.esperando_tipo_tabla: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._crear_procesar_tipo(self.imprimir_tabla, self.esperando_tipo_tabla, self.esperando_edicion_tabla, 'dicc_posiciones'))],
                self.esperando_edicion_tabla: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._crear_procesar_edicion(self.imprimir_tabla, self.esperando_edicion_tabla, 'dicc_posiciones'))],
                self.esperando_accion_tabla_posiciones: [
                    MessageHandler(filters.Regex("^1_ Explicar las reglas$"), self.procesar_accion_tabla_posiciones),
                    MessageHandler(filters.Regex("^🔙 Volver al menú principal$"), self.mostrar_menu)
                ],

                # 2. Consultar pronósticos (Acá el puente de imprimir es preguntar_usuario)
                self.esperando_tipo_pronosticos: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._crear_procesar_tipo(self.preguntar_usuario_pronosticos, self.esperando_tipo_pronosticos, self.esperando_edicion_pronosticos, 'dicc_pronosticos'))],
                self.esperando_edicion_pronosticos: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._crear_procesar_edicion(self.preguntar_usuario_pronosticos, self.esperando_edicion_pronosticos, 'dicc_pronosticos'))],
                self.esperando_usuario_pronosticos: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.imprimir_pronosticos)],
                
                # 3. Optimismo/Pesimismo
                self.esperando_tipo_opt_pes: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._crear_procesar_tipo(self.imprimir_tabla_opt_pes, self.esperando_tipo_opt_pes, self.esperando_edicion_opt_pes, 'dicc_opt_pes'))],
                self.esperando_edicion_opt_pes: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._crear_procesar_edicion(self.imprimir_tabla_opt_pes, self.esperando_edicion_opt_pes, 'dicc_opt_pes'))],
                self.esperando_accion_opt_pes: [
                    MessageHandler(filters.Regex("(?i).*(menú principal).*"), self.mostrar_menu),
                    MessageHandler(filters.Regex("(?i).*(Atrás|Cancelar).*"), self.iniciar_menu_rankings),
                    MessageHandler(filters.Regex("^1_ Ver referencias$"), self.procesar_accion_opt_pes)
                ],

                # 4. Mayores Errores
                self.esperando_tipo_mayores_errores: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._crear_procesar_tipo(self.imprimir_tabla_mayores_errores, self.esperando_tipo_mayores_errores, self.esperando_edicion_mayores_errores, 'dicc_errores', solo_finalizados=True))],
                self.esperando_edicion_mayores_errores: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._crear_procesar_edicion(self.imprimir_tabla_mayores_errores, self.esperando_edicion_mayores_errores, 'dicc_errores'))],
                self.esperando_accion_mayores_errores: [
                    MessageHandler(filters.Regex("(?i).*(menú principal).*"), self.mostrar_menu),
                    MessageHandler(filters.Regex("(?i).*(Atrás|Cancelar).*"), self.iniciar_menu_rankings)
                ],

                # 5. Falso Profeta
                self.esperando_tipo_falso_profeta: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._crear_procesar_tipo(self.imprimir_tabla_falso_profeta, self.esperando_tipo_falso_profeta, self.esperando_edicion_falso_profeta, 'dicc_fp'))],
                self.esperando_edicion_falso_profeta: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._crear_procesar_edicion(self.imprimir_tabla_falso_profeta, self.esperando_edicion_falso_profeta, 'dicc_fp'))],
                self.esperando_accion_falso_profeta: [
                    MessageHandler(filters.Regex("(?i).*(menú principal).*"), self.mostrar_menu),
                    MessageHandler(filters.Regex("(?i).*(Atrás|Cancelar).*"), self.iniciar_menu_rankings)
                ],

                # 6. Estilos de Decisión
                self.esperando_tipo_estilo_decision: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._crear_procesar_tipo(self.imprimir_tabla_estilo_decision, self.esperando_tipo_estilo_decision, self.esperando_edicion_estilo_decision, 'dicc_estilos'))],
                self.esperando_edicion_estilo_decision: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._crear_procesar_edicion(self.imprimir_tabla_estilo_decision, self.esperando_edicion_estilo_decision, 'dicc_estilos'))],
                self.esperando_accion_estilo_decision: [
                    MessageHandler(filters.Regex("(?i).*(menú principal).*"), self.mostrar_menu),
                    MessageHandler(filters.Regex("(?i).*(Atrás|Cancelar).*"), self.iniciar_menu_rankings),
                    MessageHandler(filters.Regex("^1_ Ver referencias$"), self.procesar_accion_estilo_decision)
                ],

                # 7. Ranking Mufa
                self.esperando_tipo_mufa: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._crear_procesar_tipo(self.imprimir_tabla_mufa, self.esperando_tipo_mufa, self.esperando_edicion_mufa, 'dicc_mufa'))],
                self.esperando_edicion_mufa: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._crear_procesar_edicion(self.imprimir_tabla_mufa, self.esperando_edicion_mufa, 'dicc_mufa'))],
                self.esperando_accion_mufa: [
                    MessageHandler(filters.Regex("(?i).*(menú principal).*"), self.mostrar_menu),
                    MessageHandler(filters.Regex("(?i).*(Atrás|Cancelar).*"), self.iniciar_menu_rankings)
                ],

                # 8. Mejor Predictor
                self.esperando_tipo_mejor_predictor: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._crear_procesar_tipo(self.imprimir_tabla_mejor_predictor, self.esperando_tipo_mejor_predictor, self.esperando_edicion_mejor_predictor, 'dicc_predictor', solo_finalizados=True))],
                self.esperando_edicion_mejor_predictor: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._crear_procesar_edicion(self.imprimir_tabla_mejor_predictor, self.esperando_edicion_mejor_predictor, 'dicc_predictor'))],
                self.esperando_accion_mejor_predictor: [
                    MessageHandler(filters.Regex("(?i).*(menú principal).*"), self.mostrar_menu),
                    MessageHandler(filters.Regex("(?i).*(Atrás|Cancelar).*"), self.iniciar_menu_rankings),
                    MessageHandler(filters.Regex("^1_ Ver referencias$"), self.procesar_accion_mejor_predictor)
                ],

                # 9. Racha Récord
                self.esperando_tipo_racha_record: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._crear_procesar_tipo(self.imprimir_tabla_racha_record, self.esperando_tipo_racha_record, self.esperando_edicion_racha_record, 'dicc_racha', solo_finalizados=True))],
                self.esperando_edicion_racha_record: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._crear_procesar_edicion(self.imprimir_tabla_racha_record, self.esperando_edicion_racha_record, 'dicc_racha'))],
                self.esperando_accion_racha_record: [
                    MessageHandler(filters.Regex("(?i).*(menú principal).*"), self.mostrar_menu),
                    MessageHandler(filters.Regex("(?i).*(Atrás|Cancelar).*"), self.iniciar_menu_rankings)
                ],

                # 10. Racha Actual
                self.esperando_tipo_racha_actual: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._crear_procesar_tipo(self.imprimir_tabla_racha_actual, self.esperando_tipo_racha_actual, self.esperando_edicion_racha_actual, 'dicc_racha_actual', solo_finalizados=True))],
                self.esperando_edicion_racha_actual: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._crear_procesar_edicion(self.imprimir_tabla_racha_actual, self.esperando_edicion_racha_actual, 'dicc_racha_actual'))],
                self.esperando_accion_racha_actual: [
                    MessageHandler(filters.Regex("(?i).*(menú principal).*"), self.mostrar_menu),
                    MessageHandler(filters.Regex("(?i).*(Atrás|Cancelar).*"), self.iniciar_menu_rankings)
                ],
                
                # 11. Cambios de Pronósticos
                self.esperando_tipo_cambios: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._crear_procesar_tipo(self.imprimir_tabla_cambios, self.esperando_tipo_cambios, self.esperando_edicion_cambios, 'dicc_cambios', solo_finalizados=True))],
                self.esperando_edicion_cambios: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._crear_procesar_edicion(self.imprimir_tabla_cambios, self.esperando_edicion_cambios, 'dicc_cambios'))],
                self.esperando_accion_cambios: [
                    MessageHandler(filters.Regex("(?i).*(menú principal).*"), self.mostrar_menu),
                    MessageHandler(filters.Regex("(?i).*(Atrás|Cancelar).*"), self.iniciar_menu_rankings),
                    MessageHandler(filters.Regex("^1_ Ver referencias$"), self.procesar_accion_cambios)
                ],

                # --- FLUJO PERFIL DE COMUNIDAD (CASCADA GENÉRICA) ---
                self.esperando_menu_perfil: [
                    MessageHandler(filters.Regex("(?i).*(menú principal).*"), self.mostrar_menu),
                    MessageHandler(filters.Regex("(?i).*(Atrás|Cancelar).*"), self.iniciar_ver_estadisticas),
                    MessageHandler(filters.Regex("^(1_ Estilo de pronóstico|2_ Tendencia de pronóstico|3_ Grado de firmeza)$"), self.iniciar_grafico_perfil_generico)
                ],

                self.esperando_tipo_perfil: [
                    MessageHandler(filters.Regex("(?i).*(menú principal).*"), self.mostrar_menu),
                    MessageHandler(filters.Regex("(?i).*(Atrás|Cancelar).*"), self.iniciar_menu_perfil),
                    MessageHandler(filters.Regex("^Histórico$|^Por Torneo$"), self.preguntar_tiempo_perfil)
                ],

                self.esperando_edicion_perfil: [
                    MessageHandler(filters.Regex("(?i).*(menú principal).*"), self.mostrar_menu),
                    MessageHandler(filters.Regex("(?i).*(Atrás|Cancelar).*"), self.iniciar_grafico_perfil_generico), 
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.procesar_edicion_perfil)
                ],

                self.esperando_usuario_perfil: [
                    MessageHandler(filters.Regex("(?i).*(menú principal).*"), self.mostrar_menu),
                    MessageHandler(filters.Regex("(?i).*(Atrás|Cancelar).*"), self.iniciar_grafico_perfil_generico), 
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.calcular_y_mostrar_grafico_perfil)
                ],

                self.esperando_accion_perfil: [
                    MessageHandler(filters.Regex("(?i).*(menú principal).*"), self.mostrar_menu),
                    MessageHandler(filters.Regex("(?i).*(Atrás|Cancelar).*"), self.iniciar_menu_perfil)
                ],

                # --- FLUJO DE ADMINISTRACIÓN ---
                self.esperando_menu_administracion: [
                    MessageHandler(filters.Regex("^1_ Partidos$"), self.iniciar_admin_partidos),
                    MessageHandler(filters.Regex("^2_ Equipos$"), self.iniciar_admin_equipos),
                    MessageHandler(filters.Regex("^3_ Leer archivos$"), self.iniciar_admin_archivos),
                    MessageHandler(filters.Regex("^🔙 Volver al menú principal$"), self.mostrar_menu)
                ],
                
                self.esperando_menu_admin_partidos: [
                    MessageHandler(filters.Regex("^1_ Cargar resultado$"), self.iniciar_carga_resultado),
                    MessageHandler(filters.Regex("^2_ Ver partidos$"), self.iniciar_ver_partidos_admin),
                    MessageHandler(filters.Regex("^3_ Crear partido$"), self.iniciar_crear_partido), 
                    MessageHandler(filters.Regex("^4_ Editar partido$"), self.iniciar_editar_partido),
                    MessageHandler(filters.Regex("^🔙 Atrás$"), self.iniciar_administracion),
                    MessageHandler(filters.Regex("^🔙 Volver al menú principal$"), self.mostrar_menu)
                ],

                self.esperando_crear_partido_rival: [
                    MessageHandler(filters.Regex("(?i).*(menú principal).*"), self.mostrar_menu),
                    MessageHandler(filters.Regex("(?i).*(Atrás|Cancelar).*"), self.iniciar_admin_partidos),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.procesar_crear_partido_rival)
                ],
                self.esperando_crear_partido_edicion: [
                    MessageHandler(filters.Regex("(?i).*(Atrás|Cancelar).*"), self.iniciar_admin_partidos),
                    MessageHandler(filters.Regex("(?i).*(menú principal).*"), self.mostrar_menu),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.procesar_crear_partido_edicion)
                ],
                self.esperando_crear_partido_condicion: [
                    MessageHandler(filters.Regex("(?i).*(Atrás|Cancelar).*"), self.iniciar_admin_partidos),
                    MessageHandler(filters.Regex("(?i).*(menú principal).*"), self.mostrar_menu),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.procesar_crear_partido_condicion)
                ],
                self.esperando_crear_partido_fecha: [
                    MessageHandler(filters.Regex("(?i).*(Atrás|Cancelar).*"), self.iniciar_admin_partidos),
                    MessageHandler(filters.Regex("(?i).*(menú principal).*"), self.mostrar_menu),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.procesar_crear_partido_fecha)
                ],
                self.esperando_crear_partido_goles: [
                    MessageHandler(filters.Regex("(?i).*(Atrás|Cancelar).*"), self.iniciar_admin_partidos),
                    MessageHandler(filters.Regex("(?i).*(menú principal).*"), self.mostrar_menu),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.procesar_crear_partido_goles)
                ],
                
                self.esperando_edicion_ver_partidos: [
                    MessageHandler(filters.Regex("^🔙 Atrás$"), self.iniciar_admin_partidos), # Vuelve al submenú
                    MessageHandler(filters.Regex("^🔙 Volver al menú principal$"), self.mostrar_menu),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.procesar_edicion_ver_partidos)
                ],
                
                self.esperando_fecha_resultado: [
                    MessageHandler(filters.Regex("^🔙 Atrás$"), self.iniciar_admin_partidos), # Vuelve al submenú
                    MessageHandler(filters.Regex("^🔙 Volver al menú principal$"), self.mostrar_menu),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.procesar_fecha_resultado)
                ],
                
                self.esperando_goles_resultado: [
                    MessageHandler(filters.Regex("^🔙 Atrás$"), self.iniciar_carga_resultado),
                    MessageHandler(filters.Regex("^🔙 Volver al menú principal$"), self.mostrar_menu),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.procesar_goles_resultado)
                ],

                self.esperando_menu_admin_equipos: [
                    # RUTA DE ENTRADA A AGREGAR EQUIPO
                    MessageHandler(filters.Regex("^1_ Agregar$"), self.iniciar_agregar_equipo),
                    MessageHandler(filters.Regex("^2_ Editar$"), self.iniciar_editar_equipo),
                    MessageHandler(filters.Regex("^3_ Eliminar$"), self.iniciar_eliminar_equipo),
                    MessageHandler(filters.Regex("^🔙 Atrás$"), self.iniciar_administracion),
                    MessageHandler(filters.Regex("^🔙 Volver al menú principal$"), self.mostrar_menu)
                ],
                
                self.esperando_nombre_nuevo_equipo: [
                    MessageHandler(filters.Regex("^🔙 Atrás$"), self.iniciar_admin_equipos),
                    MessageHandler(filters.Regex("^🔙 Volver al menú principal$"), self.mostrar_menu),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.procesar_nombre_nuevo_equipo)
                ],

                self.esperando_equipo_a_editar: [
                    MessageHandler(filters.Regex("^🔙 Atrás$"), self.iniciar_admin_equipos),
                    MessageHandler(filters.Regex("^🔙 Volver al menú principal$"), self.mostrar_menu),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.procesar_equipo_a_editar)
                ],
                
                self.esperando_nuevo_nombre_equipo: [
                    # Si toca atrás mientras iba a escribir el nuevo nombre, lo devolvemos a la lista numérica
                    MessageHandler(filters.Regex("^🔙 Atrás$"), self.iniciar_editar_equipo),
                    MessageHandler(filters.Regex("^🔙 Volver al menú principal$"), self.mostrar_menu),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.procesar_nuevo_nombre_equipo)
                ],

                self.esperando_equipo_a_eliminar: [
                    MessageHandler(filters.Regex("^🔙 Atrás$"), self.iniciar_admin_equipos),
                    MessageHandler(filters.Regex("^🔙 Volver al menú principal$"), self.mostrar_menu),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.procesar_equipo_a_eliminar)
                ],

                self.esperando_confirmacion_eliminar_equipo: [
                    MessageHandler(filters.Regex("^🔙 Atrás$"), self.iniciar_eliminar_equipo),
                    MessageHandler(filters.Regex("^🔙 Volver al menú principal$"), self.mostrar_menu),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.procesar_confirmacion_eliminar_equipo)
                ],

                self.esperando_archivo_a_leer: [
                    MessageHandler(filters.Regex("(?i).*(menú principal).*"), self.mostrar_menu),
                    MessageHandler(filters.Regex("(?i).*(Atrás|Cancelar).*"), self.iniciar_administracion),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.procesar_archivo_a_leer)
                ],

                # --- RUTAS DE EDICIÓN ---
                self.esperando_fecha_partido_a_editar: [
                    MessageHandler(filters.Regex("(?i).*(menú principal).*"), self.mostrar_menu),
                    MessageHandler(filters.Regex("(?i).*(Atrás|Cancelar).*"), self.iniciar_admin_partidos),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.procesar_fecha_busqueda_editar)
                ],
                self.esperando_editar_partido_rival: [
                    MessageHandler(filters.Regex("(?i).*(menú principal).*"), self.mostrar_menu),
                    MessageHandler(filters.Regex("(?i).*(Atrás|Cancelar).*"), self.iniciar_admin_partidos),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.procesar_editar_partido_rival)
                ],
                self.esperando_editar_partido_edicion: [
                    MessageHandler(filters.Regex("(?i).*(menú principal).*"), self.mostrar_menu),
                    MessageHandler(filters.Regex("(?i).*(Atrás|Cancelar).*"), self.iniciar_admin_partidos),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.procesar_editar_partido_edicion)
                ],
                self.esperando_editar_partido_condicion: [
                    MessageHandler(filters.Regex("(?i).*(menú principal).*"), self.mostrar_menu),
                    MessageHandler(filters.Regex("(?i).*(Atrás|Cancelar).*"), self.iniciar_admin_partidos),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.procesar_editar_partido_condicion)
                ],
                self.esperando_editar_partido_fecha_final: [
                    MessageHandler(filters.Regex("(?i).*(menú principal).*"), self.mostrar_menu),
                    MessageHandler(filters.Regex("(?i).*(Atrás|Cancelar).*"), self.iniciar_admin_partidos),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.procesar_editar_partido_fecha_final)
                ],
            },
            fallbacks=[CommandHandler("cancelar", self.cancelar_conversacion)],
        )
        self.app.add_handler(CommandHandler("actualizar_cronometros", self.forzar_actualizacion_cronometros))
        self.app.add_handler(CommandHandler("start", self.mostrar_menu))
        self.app.add_handler(conv_handler)
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.mostrar_menu))

    def _generar_texto_tabla_posiciones(self, edicion_id, titulo):
        """Extrae la lógica de dibujo de la tabla para que el bot pueda enviarla automáticamente."""
        ranking = self.db.obtener_ranking(edicion_id=edicion_id)
        usuarios_db = self.db.obtener_usuarios_con_id()
        todos_los_usuarios = [u[1] for u in usuarios_db]
        usuarios_con_puntos = [row[0] for row in ranking]
        usuarios_sin_pronosticos = [u for u in todos_los_usuarios if u not in usuarios_con_puntos]
        
        if not ranking and not usuarios_sin_pronosticos:
            return "📉 Todavía no hay usuarios registrados en el sistema."
            
        mensaje = f"🏆 *Tabla de Posiciones: {titulo}* 🏆\n\n"
        
        if ranking:
            for i, row in enumerate(ranking):
                username = row[0]
                puntos = row[1]
                pj = row[5]
                ant_str = self._formatear_anticipacion(row[6])
                error_prom = round(float(row[7]), 2) if row[7] is not None else 0.0
                efectividad = row[8]
                
                if i == 0: medalla = "🥇"
                elif i == 1: medalla = "🥈"
                elif i == 2: medalla = "🥉"
                else: medalla = f"*{i+1}°*"
                    
                mensaje += f"{medalla} *{username}* - {puntos} pts\n"
                mensaje += f"└ _PJ: {pj} | Err: {error_prom} | Ant: {ant_str} | Efec: {efectividad}%_\n\n"
        else:
            mensaje += "_Aún no hay puntos cargados en esta categoría._\n\n"

        if usuarios_sin_pronosticos:
            lista_nombres = ", ".join(usuarios_sin_pronosticos)
            mensaje += f"🚫 *Últimos (Sin pronósticos):*\n_{lista_nombres}_"
            
        return mensaje

    async def imprimir_tabla(self, update: Update, context: ContextTypes.DEFAULT_TYPE, edicion_id, titulo):
        """Se activa cuando el usuario toca manualmente 'Ver posiciones'."""
        threading.Thread(
            target=self._auditar_consulta_estadistica, 
            args=(update, f"Posiciones ({titulo})"), 
            daemon=True
        ).start()

        mensaje = self._generar_texto_tabla_posiciones(edicion_id, titulo)
        
        # Agregamos el botón de explicar reglas junto al de volver
        botones_tabla = [
            ["1_ Explicar las reglas"],
            ["🔙 Volver al menú principal"]
        ]
        teclado = ReplyKeyboardMarkup(botones_tabla, resize_keyboard=True)
        
        await update.message.reply_text(mensaje, parse_mode="Markdown", reply_markup=teclado)
        
        # Mantenemos la conversación viva en el nuevo estado
        return self.esperando_accion_tabla_posiciones

    async def procesar_accion_tabla_posiciones(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Muestra el detalle y los fundamentos de cómo se define el ranking."""
        mensaje_reglas = (
            "⚖️ *REGLAMENTO Y CRITERIOS DE DESEMPATE*\n\n"
            "Para garantizar que el ranking sea justo, las posiciones se definen siguiendo este orden estricto:\n\n"
            "*1º El que más puntos saca:*\n"
            "Es la meta suprema y el objetivo principal del juego. Quien más puntos acumula acertando resultados lógicamente merece estar en la cima.\n\n"
            "*2º El que más partidos pronosticó:*\n"
            "Ante igualdad de puntos, priorizamos a los jugadores más activos. Queremos valorar a quienes les gusta jugar a esto y participan constantemente del programa por sobre los que juegan de forma esporádica.\n\n"
            "*3º El mejor predictor:*\n"
            "Si la paridad persiste, sos un mejor jugador si cometés menos errores absolutos en tus predicciones. Un buen predictor demuestra su capacidad acercándose siempre a la cantidad de goles exacta del encuentro.\n\n"
            "*4º Mayor anticipación promedio:*\n"
            "Una vez valorado todo lo restante, se premia al jugador más decidido. Alguien que pronostica con mayor anticipación demuestra que es firme y que sabe mirar mejor los partidos, porque mucho antes del pitazo inicial ya sabe cómo saldrá el partido."
        )
        
        botones_volver = [["🔙 Volver al menú principal"]]
        
        await update.message.reply_text(
            mensaje_reglas, 
            parse_mode="Markdown", 
            reply_markup=ReplyKeyboardMarkup(botones_volver, resize_keyboard=True)
        )
        
        # Nos quedamos en este estado esperando que decida volver al menú
        return self.esperando_accion_tabla_posiciones

    async def _disparar_recordatorio_cumplidores(self, context: ContextTypes.DEFAULT_TYPE):
        """Envía un recordatorio 24 horas antes del partido a los usuarios que ya pronosticaron."""
        datos = context.job.data
        partido_id = datos['partido_id']
        rival = datos['rival']
        fecha_str = datos['fecha'].strftime('%d/%m a las %H:%M')
        
        # Obtenemos quiénes SÍ pronosticaron este partido
        cumplidores = self.db.obtener_usuarios_con_pronostico_por_partido(partido_id)
        if not cumplidores: return
        
        # Botón único para limpiar la pantalla y dejar solo el regreso al menú
        botones = [["🔙 Volver al menú principal"]]
        teclado = ReplyKeyboardMarkup(botones, resize_keyboard=True)
        
        # Mensaje simplificado y enfocado en la previa
        mensaje = (
            f"⏳ *¡FALTAN 24 HORAS!* ⏳\n\n"
            f"Mañana juega el Rojo contra *{rival}* ({fecha_str}).\n\n"
            f"Tu pronóstico ya se encuentra registrado y asegurado. ¡Éxitos! 👹"
        )
        
        for tg_id, username in cumplidores:
            try:
                if username == 'Gabriel':
                    await context.bot.send_message(chat_id=tg_id, text=mensaje, parse_mode="Markdown", reply_markup=teclado)
                    self._registrar_log(f"Aviso enviado a {username} (Faltan 24 hs - Partido: {rival})")
            except Exception as e:
                self._registrar_log(f"FALLO al avisar a {username} (Faltan 24 hs): {e}", archivo="logs_errores_bot.txt")

    def _programar_cronometros_partidos(self):
        """Busca partidos futuros y crea alarmas con nombre para poder resetearlas."""
        partidos = self.db.obtener_agenda_partidos_futuros()
        if not partidos: return
        
        zona_horaria = pytz.timezone('America/Argentina/Buenos_Aires')
        ahora = datetime.datetime.now(zona_horaria)
        
        for p_id, rival, fecha, edicion_id, nombre_torneo in partidos:
            fecha_local = zona_horaria.localize(fecha)
            
            # 1. Alarmas de insistencia para los que NO pronosticaron
            horas_aviso = [96, 48, 24, 1]
            for horas in horas_aviso:
                fecha_alarma = fecha_local - timedelta(hours=horas)
                if fecha_alarma > ahora:
                    self.app.job_queue.run_once(
                        self._disparar_recordatorio, 
                        when=fecha_alarma, 
                        data={'partido_id': p_id, 'rival': rival, 'fecha': fecha_local, 'horas': horas},
                        name="recordatorio_partido"
                    )
            
            # 2. ALARMA DE TABLA (1 HORA ANTES) para los que SÍ pronosticaron
            fecha_alarma_posiciones = fecha_local - timedelta(hours=1)
            if fecha_alarma_posiciones > ahora:
                self.app.job_queue.run_once(
                    self._disparar_alerta_posiciones, 
                    when=fecha_alarma_posiciones, 
                    data={'partido_id': p_id, 'rival': rival, 'edicion_id': edicion_id, 'nombre_torneo': nombre_torneo},
                    name="recordatorio_partido" 
                )

            # 🌟 3. NUEVA ALARMA: RECORDATORIO 24 HORAS PARA LOS QUE YA PRONOSTICARON
            fecha_alarma_24h = fecha_local - timedelta(hours=24)
            if fecha_alarma_24h > ahora:
                self.app.job_queue.run_once(
                    self._disparar_recordatorio_cumplidores, 
                    when=fecha_alarma_24h, 
                    data={'partido_id': p_id, 'rival': rival, 'fecha': fecha_local},
                    name="recordatorio_partido" 
                )
                
        print("\n\n⏰ Cronómetros de recordatorios y posiciones configurados a las " + ahora.strftime('%Y-%m-%d %H:%M:%S') + "\n\n")

    async def _disparar_recordatorio(self, context: ContextTypes.DEFAULT_TYPE):
        """Se ejecuta cuando un cronómetro llega a 0."""
        datos = context.job.data
        partido_id = datos['partido_id']
        rival = datos['rival']
        horas_faltantes = datos['horas']
        fecha_str = datos['fecha'].strftime('%d/%m a las %H:%M')
        
        # Buscamos quiénes NO pronosticaron este partido en concreto
        colgados = self.db.obtener_usuarios_sin_pronostico_por_partido(partido_id)
        if not colgados: return # Si todos pronosticaron, muere acá sin molestar
        
        # Botones para ofrecer atajo directo o volver al menú
        botones = [["1_ Cargar pronóstico"], ["🔙 Volver al menú"]]
        teclado = ReplyKeyboardMarkup(botones, resize_keyboard=True)
        
        # Armamos el texto adaptativo según si falta 1 hora o varios días
        if horas_faltantes == 1:
            alerta = "🚨 *¡ÚLTIMA OPORTUNIDAD!* 🚨\nFalta solo *1 HORA*"
        else:
            alerta = f"⚠️ *RECORDATORIO* ⚠️\nFaltan solo *{horas_faltantes} horas*"
            
        for tg_id, username in colgados:
            mensaje = (
                f"{alerta} para el partido contra *{rival}* ({fecha_str}).\n\n"
                f"Todavía no tenemos tu pronóstico registrado, {username}.\n\n"
                f"👇 ¡Usá el botón de abajo para cargarlo rápido y sumar puntos!"
            )
            try:
                if username == 'Gabriel':
                    await context.bot.send_message(chat_id=tg_id, text=mensaje, parse_mode="Markdown", reply_markup=teclado)
                    self._registrar_log(f"Aviso enviado a {username} (Faltan {horas_faltantes}hs - Partido: {rival})")
            except Exception as e:
                self._registrar_log(f"FALLO al avisar a {username} (Faltan {horas_faltantes}hs): {e}", archivo="logs_errores_bot.txt")

    async def _disparar_alerta_posiciones(self, context: ContextTypes.DEFAULT_TYPE):
        """Envía la tabla de posiciones 1 hora antes del partido a los usuarios que ya pronosticaron."""
        datos = context.job.data
        partido_id = datos['partido_id']
        rival = datos['rival']
        edicion_id = datos['edicion_id']
        nombre_torneo = datos['nombre_torneo']
        
        # Obtenemos quiénes ya cumplieron con su pronóstico
        cumplidores = self.db.obtener_usuarios_con_pronostico_por_partido(partido_id)
        if not cumplidores: return
        
        # Armamos el mensaje invocando a la función generadora de la tabla
        mensaje_intro = f"📊 Informamos la tabla de posiciones a falta de 1 hora para el partido contra *{rival}*:\n\n"
        tabla_texto = self._generar_texto_tabla_posiciones(edicion_id, nombre_torneo)
        mensaje_final = mensaje_intro + tabla_texto
        
        # Se lo mandamos por privado a cada usuario cumplidor
        for tg_id, username in cumplidores:
            try:
                if username == 'Gabriel':
                    await context.bot.send_message(chat_id=tg_id, text=mensaje_final, parse_mode="Markdown")
                    self._registrar_log(f"Tabla de posiciones enviada a {username} (Falta 1h - Partido: {rival})")
            except Exception as e:
                self._registrar_log(f"FALLO al enviar tabla de posiciones a {username} (Falta 1h - Partido: {rival}): {e}", archivo="logs_errores_bot.txt")

    # --- MÉTODOS DE APOYO (HELPERS) ---

    def _enviar_correo_codigo(self, destinatario, codigo):
        """Lógica interna para envío de emails."""
        if not self.email_emisor or not self.email_pass:
            print("❌ Faltan credenciales de email en el .env")
            return False
        try:
            msg = EmailMessage()
            msg['Subject'] = 'Código de Asociación - Prode Independiente 🔴'
            msg['From'] = self.email_emisor
            msg['To'] = destinatario
            
            cuerpo = (
                f"¡Hola!\n\n"
                f"Alguien ha solicitado asociar tu cuenta del Prode a un dispositivo móvil en Telegram.\n\n"
                f"Tu código de seguridad es: {codigo}\n\n"
                f"Si no fuiste vos, ignorá este mensaje."
            )
            msg.set_content(cuerpo)
            
            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
                smtp.login(self.email_emisor, self.email_pass)
                smtp.send_message(msg)
            return True
        except Exception as e:
            print(f"Error enviando correo: {e}")
            return False

    # --- MANEJADORES (HANDLERS) ---
    # Todos ahora reciben 'self' y acceden a la DB como 'self.db'

    async def mostrar_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message: return ConversationHandler.END
        id_telegram = update.message.from_user.id
        username = self.db.obtener_usuario_por_telegram(id_telegram)
        
        if username:
            botones = [
                ["1_ Cargar pronóstico", "2_ Ver posiciones"],
                ["3_ Consultar pronósticos", "4_ Ver Estadísticas"]
            ]
            
            # Verificamos si es admin y agregamos el botón
            es_admin = username in self.db.obtener_administradores()
            if es_admin:
                botones.append(["5_ Administración"])
            
            mensaje = (
                f"¡Hola {username}! Bienvenido al Prode. 🔴\n\n"
                "Elegí una opción para continuar:\n\n"
                "📝 *1_ Cargar pronóstico:* Ingresá o modificá tu predicción para los próximos partidos.\n"
                "🏆 *2_ Ver posiciones:* Consultá la tabla general con los puntos acumulados y tu efectividad.\n"
                "🔍 *3_ Consultar pronósticos:* Mirá el historial completo de todos los resultados cargados.\n"
                "📊 *4_ Ver Estadísticas:* Descubrí rachas, rankings curiosos y el perfil de la comunidad."
            )
            
            # Agregamos el texto explicativo si es admin
            if es_admin:
                mensaje += "\n⚙️ *5_ Administración:* Panel exclusivo para gestionar el bot."
            
            mensaje += (
                "\n\n🌐 *¿Sabías que podés hacer mucho más en nuestra web?*\n"
                "Entrá ahora en: https://independiente.onrender.com"
            )
                
        else:
            botones = [["1_ Asociar cuenta"]]
            mensaje = (
                "¡Hola! Bienvenido al bot del Prode Independiente. 🔴\n\n"
                "⚠️ *Primero necesitás vincular tu cuenta.*\n\n"
                "*¿Por qué es necesario?*\n"
                "Para proteger tu identidad, asegurar tus puntos y confirmar que nadie más pueda cargar o modificar pronósticos en tu nombre.\n\n"
                "*¿Cómo lo hago?*\n"
                "1. Tocá el botón *1_ Asociar cuenta* que aparece acá abajo.\n"
                "2. Escribí tu nombre de usuario o email registrado.\n"
                "3. Ingresá el código de 6 dígitos que te enviaremos a tu correo.\n\n"
                "👇 ¡Tocá el botón para empezar!"
            )
            
        await update.message.reply_text(
            mensaje, 
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(botones, resize_keyboard=True)
        )
        return ConversationHandler.END

    async def iniciar_ver_estadisticas(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Menú principal de estadísticas (Raíz)."""
        botones = [
            ["1_ Rankings", "2_ Perfil de la comunidad"],
            ["🔙 Volver al menú principal"]
        ]
        
        # Armamos el mensaje explicativo para el panel principal
        mensaje = (
            "📊 *Panel de Estadísticas*\n\n"
            "🏆 *1_ Rankings:* Tablas de posiciones, rachas, aciertos y comparativas de toda la competencia.\n\n"
            "👥 *2_ Perfil de la comunidad:* Análisis individual y porcentajes detallados sobre las tendencias de cada usuario.\n\n"
            "Elegí una categoría para explorar:"
        )
        
        await update.message.reply_text(
            mensaje, 
            parse_mode="Markdown", 
            reply_markup=ReplyKeyboardMarkup(botones, resize_keyboard=True)
        )
        return self.esperando_menu_estadisticas

    async def iniciar_menu_rankings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Submenú con todos los rankings actuales y sus descripciones reenumeradas."""
        botones = [
            ["1_ Optimismo/Pesimismo", "2_ Mayores errores"],
            ["3_ Falso Profeta", "4_ Estilos de decisión"],
            ["5_ Mufa", "6_ Mejor predictor"],
            ["7_ Racha récord", "8_ Racha actual"],
            ["9_ Cambio de pronósticos"],
            ["🔙 Atrás", "🔙 Volver al menú principal"]
        ]
        
        mensaje = (
            "🏆 *Rankings del Prode*\n\n"
            "☯️ *1_ Optimismo/Pesimismo:* Mide tu tendencia a pronosticar resultados a favor (Optimista) o en contra (Pesimista) del Rojo.\n"
            "📉 *2_ Mayores errores:* El top 10 histórico de los peores pronósticos (mayor diferencia absoluta de goles).\n"
            "🤥 *3_ Falso profeta:* Usuarios que más le erran cuando dicen que el Rojo va a ganar.\n"
            "🧠 *4_ Estilos de decisión:* Clasifica tu estilo según el tiempo de anticipación con el que guardás tus pronósticos.\n"
            "🐈‍⬛ *5_ Mufa:* Usuarios que más aciertan el resultado cuando pronostican que el Rojo pierde.\n"
            "🎯 *6_ Mejor predictor:* Premia a quienes tienen el menor margen de error en la cantidad de goles pronosticados.\n"
            "🔥 *7_ Racha récord:* La mejor racha histórica de partidos consecutivos sumando puntos por jugador.\n"
            "⏳ *8_ Racha actual:* Cantidad de partidos consecutivos actuales en los que sumaste puntos.\n"
            "🔄 *9_ Cambios de pronóstico:* Muestra quiénes dudan más y cambian su resultado constantemente antes del partido.\n\n"
            "Seleccioná un ranking para consultar:"
        )
        
        await update.message.reply_text(
            mensaje, 
            parse_mode="Markdown", 
            reply_markup=ReplyKeyboardMarkup(botones, resize_keyboard=True)
        )
        return self.esperando_menu_rankings

    async def iniciar_menu_perfil(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Submenú para los gráficos y porcentajes con explicación detallada."""
        threading.Thread(
            target=self._auditar_consulta_estadistica, 
            args=(update, "Menú Perfil de la Comunidad"), 
            daemon=True
        ).start()
        # Sumamos el botón 3 en una nueva fila
        botones = [
            ["1_ Estilo de pronóstico", "2_ Tendencia de pronóstico"],
            ["3_ Grado de firmeza"],
            ["🔙 Atrás", "🔙 Volver al menú principal"]
        ]
        
        mensaje = (
            "👥 *Perfil de la comunidad*\n\n"
            "Elegí qué estadísticas querés ver:\n\n"
            "📊 *1_ Estilo de pronóstico:* Desglosa tus predicciones mostrando el porcentaje "
            "de veces que pronosticaste victoria, empate o derrota del Rojo.\n\n"
            "📈 *2_ Tendencia de pronóstico:* Analiza si tus pronósticos suelen ser optimistas, neutrales o pesimistas respecto al resultado final.\n\n"
            "🧱 *3_ Grado de firmeza:* Analiza la cantidad de veces que cambiaste de opinión antes del partido."
        )
        
        await update.message.reply_text(
            mensaje, 
            parse_mode="Markdown", 
            reply_markup=ReplyKeyboardMarkup(botones, resize_keyboard=True)
        )
        return self.esperando_menu_perfil

    async def cancelar_conversacion(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Permite al usuario abortar cualquier proceso escribiendo /cancelar."""
        await update.message.reply_text("Operación cancelada.")
        await self.mostrar_menu(update, context)
        return ConversationHandler.END

    # ==========================================
    # FLUJO 1: ASOCIAR CUENTA
    # ==========================================
    async def iniciar_asociacion(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "🔐 *Asociar Cuenta*\n\n"
            "Por favor, escribí tu *Nombre de Usuario* o tu *Correo Electrónico* registrado en el Prode.\n\n"
            "_(Para cancelar escribí /cancelar)_",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove()
        )
        return self.esperando_identificador

    async def procesar_identificador(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        identificador = update.message.text.strip()
        usuario = self.db.buscar_usuario_para_asociar(identificador)
        
        if not usuario:
            await update.message.reply_text(
                "❌ No encontré ninguna cuenta con ese usuario o correo.\n"
                "Intentá nuevamente o escribí /cancelar."
            )
            return self.esperando_identificador 
            
        username = usuario['username']
        email_dest = usuario['email']
        
        if not email_dest:
            await update.message.reply_text("❌ Tu cuenta no tiene un email registrado. Contactá al administrador.")
            await self.mostrar_menu(update, context)
            return ConversationHandler.END

        codigo = str(random.randint(100000, 999999))
        
        if self.db.guardar_token_recuperacion(username, codigo):
            # Usamos self._enviar_correo_codigo
            envio_ok = self._enviar_correo_codigo(email_dest, codigo)
            
            if envio_ok:
                context.user_data['username_asociar'] = username
                mail_oculto = email_dest[0] + "******" + email_dest[email_dest.find("@"):]
                
                await update.message.reply_text(
                    f"✅ ¡Usuario encontrado!\n\n"
                    f"Acabo de enviar un código a tu correo: <b>{mail_oculto}</b>\n\n"
                    f"Revisá tu bandeja de entrada o Spam y escribí el código aquí:",
                    parse_mode="HTML"
                )
                return self.esperando_codigo
            else:
                await update.message.reply_text("❌ Hubo un problema enviando el correo. Intentá más tarde.")
        else:
            await update.message.reply_text("❌ Error interno generando el token en la base de datos.")
            
        await self.mostrar_menu(update, context)
        return ConversationHandler.END

    async def procesar_codigo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        codigo_ingresado = update.message.text.strip()
        username = context.user_data.get('username_asociar')
        
        if not username:
            await update.message.reply_text("❌ La sesión expiró. Volvé a iniciar el proceso.")
            await self.mostrar_menu(update, context)
            return ConversationHandler.END

        try:
            self.db.validar_token_recuperacion(username, codigo_ingresado)
            id_telegram = update.message.from_user.id
            self.db.actualizar_id_telegram(username, id_telegram)
            
            await update.message.reply_text(
                f"🎉 *¡Éxito!* 🎉\n\n"
                f"Tu Telegram ha quedado vinculado al usuario *{username}*.\n\n"
                f"Ya podés empezar a cargar tus pronósticos.",
                parse_mode="Markdown"
            )
        except Exception as e:
            await update.message.reply_text(f"❌ {e}\nIntentá ingresarlo nuevamente o /cancelar.")
            return self.esperando_codigo
            
        await self.mostrar_menu(update, context)
        return ConversationHandler.END

    # ==========================================
    # FLUJO 2: CARGAR PRONÓSTICO
    # ==========================================
    async def iniciar_carga_pronostico(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Paso 1: Valida al usuario y muestra la lista de partidos futuros enumerados desde el 1."""
        id_telegram = update.message.from_user.id
        username = self.db.obtener_usuario_por_telegram(id_telegram)
        
        if not username:
            await update.message.reply_text(
                "❌ *Acceso Denegado*\n\n"
                "Todavía no asociaste tu cuenta del Prode. Por favor, usá la opción *1_ Asociar cuenta* del menú principal primero.", 
                parse_mode="Markdown"
            )
            return ConversationHandler.END
            
        context.user_data['username_pronostico'] = username
        partidos_futuros = self.db.obtener_partidos(username, filtro_tiempo='futuros')
        
        if not partidos_futuros:
            await update.message.reply_text("⚽ No hay partidos futuros programados en este momento.")
            await self.mostrar_menu(update, context)
            return ConversationHandler.END
            
        mensaje = "📅 *Partidos Disponibles para Pronosticar:*\n\n"
        partidos_info = {}
        
        for i, p in enumerate(partidos_futuros, start=1):
            p_id = p[0]
            rival = p[1]
            torneo = p[3]
            fecha_display = p[7]
            condicion = p[12]
            pred_cai = p[8]
            pred_rival = p[9]
            
            # Guardamos el ID de BD adentro de un diccionario oculto
            partidos_info[str(i)] = {'id': p_id, 'rival': rival, 'condicion': condicion}
            
            # 1. Armamos el texto del partido y el pronóstico previo (si existe) según la localía
            if condicion == -1:
                partido_str = f"{rival} vs Independiente"
                if pred_cai is not None:
                    txt_previo = f"{rival} {pred_rival} - {pred_cai} Independiente"
            else:
                partido_str = f"Independiente vs {rival}"
                if pred_cai is not None:
                    txt_previo = f"Independiente {pred_cai} - {pred_rival} {rival}"
                
            # 2. Ensamblamos el bloque del mensaje
            mensaje += f"*{i}_* {partido_str}\n"
            mensaje += f"🏆 {torneo} | 🗓️ {fecha_display}\n"
            
            if pred_cai is not None:
                mensaje += f"👉 _Tu pronóstico actual: {txt_previo}_\n"
            else:
                mensaje += "👉 _Sin pronóstico cargado_\n"
                
            mensaje += "—\n"
            
        # 3. Pregunta final
        mensaje += "\n✍️ Respondé con el *NÚMERO* del partido que querés pronosticar:"
        
        context.user_data['partidos_info'] = partidos_info
        
        # Botón para volver
        botones_volver = [["🔙 Volver al menú principal"]]
        
        await update.message.reply_text(
            mensaje, 
            parse_mode="Markdown", 
            reply_markup=ReplyKeyboardMarkup(botones_volver, resize_keyboard=True)
        )
        return self.esperando_partido_id
    
    async def iniciar_crear_partido(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Paso 1: Lista rivales para el nuevo partido."""
        pregunta = "🤝 *Elegí el RIVAL para el nuevo partido:*"
        exito = await self._mostrar_lista_equipos(update, context, pregunta)
        if not exito:
            return await self.iniciar_admin_partidos(update, context)
        return self.esperando_crear_partido_rival

    async def iniciar_editar_partido(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Paso 1 Editar: Solicita la fecha actual del partido en BD."""
        await update.message.reply_text(
            "🔍 *Editar Partido*\n\nIngresá la fecha del partido que querés modificar (dd/mm/aaaa):",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup([["🔙 Cancelar"]], resize_keyboard=True)
        )
        return self.esperando_fecha_partido_a_editar

    async def procesar_fecha_busqueda_editar(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Paso 2 Editar: Busca el partido y, si lo encuentra, pide el nuevo Rival."""
        fecha_texto = update.message.text.strip()
        # Reutilizamos la función de búsqueda por fecha exacta
        partido = self.db.obtener_partido_por_fecha_exacta(fecha_texto)

        if not partido:
            await update.message.reply_text("❌ No se encontró ningún partido en esa fecha. Intentá de nuevo o tocá Cancelar.")
            return self.esperando_fecha_partido_a_editar

        context.user_data['partido_a_editar_id'] = partido['id']
        context.user_data['partido_a_editar_goles'] = (partido.get('goles_cai'), partido.get('goles_rival'))
        
        # Extraemos y formateamos todos los detalles
        rival = partido['rival']
        condicion = partido['condicion']
        torneo = f"{partido['torneo']} {partido['anio']}"
        
        fecha_dt = partido['fecha_hora']
        fecha_str = fecha_dt.strftime('%d/%m/%Y a las %H:%M') if fecha_dt else "A confirmar"
        
        if condicion == -1:
            partido_str = f"{rival} vs Independiente"
            cond_str = "Visitante"
        elif condicion == 1:
            partido_str = f"Independiente vs {rival}"
            cond_str = "Local"
        else:
            partido_str = f"Independiente vs {rival}"
            cond_str = "Neutral"
            
        mensaje_encontrado = (
            f"✅ *Partido encontrado*\n\n"
            f"📅 *Fecha:* {fecha_str}\n"
            f"🏆 *Torneo:* {torneo}\n"
            f"⚔️ *Encuentro:* {partido_str}\n"
            f"🏠 *Condición:* {cond_str}"
        )
        
        await update.message.reply_text(mensaje_encontrado, parse_mode="Markdown")
        
        # Pasamos a pedir el nuevo Rival usando la función existente
        pregunta = "🤝 *Elegí el NUEVO RIVAL (o seleccioná el mismo si no cambia):*"
        await self._mostrar_lista_equipos(update, context, pregunta)
        return self.esperando_editar_partido_rival

    async def procesar_editar_partido_rival(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Paso 3 Editar: Valida rival y pide la nueva Edición."""
        texto = update.message.text.strip()
        mapa = context.user_data.get('mapa_equipos', {})
        if texto not in mapa:
            await update.message.reply_text("❌ Elegí un número de la lista.")
            return self.esperando_editar_partido_rival
        
        context.user_data['edit_rival_id'] = mapa[texto]['id']
        botones = self._generar_botones_ediciones(incluir_historico=False)
        botones.insert(0, ["🔙 Cancelar"])
        
        await update.message.reply_text("🏆 *Seleccioná el Torneo:*", parse_mode="Markdown", reply_markup=ReplyKeyboardMarkup(botones, resize_keyboard=True))
        return self.esperando_editar_partido_edicion

    async def procesar_editar_partido_edicion(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Paso 4 Editar: Valida edición y pide la Condición."""
        texto_edicion = update.message.text.strip()
        ediciones = self.db.obtener_ediciones()
        ed_id = next((e[0] for e in ediciones if f"{e[1]} {e[2]}" == texto_edicion), None)
        
        if not ed_id:
            await update.message.reply_text("❌ Torneo no válido.")
            return self.esperando_editar_partido_edicion
            
        context.user_data['edit_edicion_id'] = ed_id
        botones = [["1_ Local", "2_ Visitante"], ["3_ Neutral"], ["🔙 Cancelar"]]
        await update.message.reply_text("🏠 *¿Condición de Independiente?*", parse_mode="Markdown", reply_markup=ReplyKeyboardMarkup(botones, resize_keyboard=True))
        return self.esperando_editar_partido_condicion

    async def procesar_editar_partido_condicion(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Paso 5 Editar: Valida condición y pide la nueva Fecha/Hora."""
        opciones = {"1_ Local": 1, "2_ Visitante": -1, "3_ Neutral": 0}
        if update.message.text not in opciones:
            await update.message.reply_text("❌ Opción inválida.")
            return self.esperando_editar_partido_condicion
            
        context.user_data['edit_condicion'] = opciones[update.message.text]
        await update.message.reply_text("📅 *Ingresá la NUEVA fecha y hora* (dd/mm/aaaa hh:mm):", parse_mode="Markdown", reply_markup=ReplyKeyboardMarkup([["🔙 Cancelar"]], resize_keyboard=True))
        return self.esperando_editar_partido_fecha_final

    async def procesar_editar_partido_fecha_final(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Paso 6 Editar: Valida restricción contra pronósticos y guarda."""
        try:
            nueva_fecha_dt = datetime.datetime.strptime(update.message.text.strip(), "%d/%m/%Y %H:%M")
            partido_id = context.user_data['partido_a_editar_id']
            
            # Validamos contra el pronóstico más reciente
            ultima_pred = self.db.obtener_ultima_fecha_pronostico(partido_id) # ⚠️ Debés agregar este método a BaseDeDatos
            
            if ultima_pred and nueva_fecha_dt < ultima_pred:
                fecha_limite = ultima_pred.strftime('%d/%m/%Y %H:%M:%S')
                await update.message.reply_text(f"🚫 *Error de Seguridad*\n\nNo podés poner una fecha menor al último pronóstico cargado ({fecha_limite}).", parse_mode="Markdown")
                return self.esperando_editar_partido_fecha_final

            # Guardamos los cambios
            g_cai, g_rival = context.user_data['partido_a_editar_goles']
            self.db.actualizar_partido_manual(
                partido_id,
                context.user_data['edit_edicion_id'],
                context.user_data['edit_rival_id'],
                context.user_data['edit_condicion'],
                nueva_fecha_dt.strftime("%Y-%m-%d %H:%M:%S"),
                g_cai, g_rival
            )
            
            await update.message.reply_text("✅ ¡Partido editado con éxito!")
            return await self.iniciar_admin_partidos(update, context)
            
        except ValueError:
            await update.message.reply_text("❌ Formato incorrecto. Usá dd/mm/aaaa hh:mm")
            return self.esperando_editar_partido_fecha_final

    async def procesar_crear_partido_rival(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Paso 2: Valida rival y pide el torneo (edición)."""
        texto = update.message.text.strip()
        mapa = context.user_data.get('mapa_equipos', {})
        if texto not in mapa:
            await update.message.reply_text("❌ Número inválido. Elegí uno de la lista.")
            return self.esperando_crear_partido_rival
        
        context.user_data['nuevo_partido_rival'] = mapa[texto]
        botones = self._generar_botones_ediciones(incluir_historico=False)
        botones.insert(0, ["🚫 Cancelar"])
        
        await update.message.reply_text(
            "🏆 *Seleccioná el Torneo* para este partido:",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(botones, resize_keyboard=True)
        )
        return self.esperando_crear_partido_edicion

    async def procesar_crear_partido_edicion(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Paso 3: Valida edición y pide condición."""
        texto_edicion = update.message.text.strip()
        ediciones = self.db.obtener_ediciones()
        ed_id = next((e[0] for e in ediciones if f"{e[1]} {e[2]}" == texto_edicion), None)
        
        if not ed_id:
            await update.message.reply_text("❌ Torneo no válido. Usá los botones.")
            return self.esperando_crear_partido_edicion
            
        context.user_data['nuevo_partido_edicion_id'] = ed_id
        botones = [["1_ Local", "2_ Visitante"], ["3_ Neutral"], ["🚫 Cancelar"]]
        
        await update.message.reply_text(
            "🏠 *¿En qué condición juega Independiente?*",
            reply_markup=ReplyKeyboardMarkup(botones, resize_keyboard=True)
        )
        return self.esperando_crear_partido_condicion

    async def procesar_crear_partido_condicion(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Paso 4: Valida condición y pide fecha/hora."""
        opciones = {"1_ Local": 1, "2_ Visitante": -1, "3_ Neutral": 0}
        if update.message.text not in opciones:
            await update.message.reply_text("❌ Elegí una opción válida.")
            return self.esperando_crear_partido_condicion
            
        context.user_data['nuevo_partido_condicion'] = opciones[update.message.text]
        await update.message.reply_text(
            "📅 *Ingresá la fecha y hora* (Formato: DD/MM/AAAA HH:MM)\n"
            "Ejemplo: 15/05/2026 21:00",
            reply_markup=ReplyKeyboardMarkup([["🚫 Cancelar"]], resize_keyboard=True)
        )
        return self.esperando_crear_partido_fecha

    async def procesar_crear_partido_fecha(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Paso 5: Valida fecha. Si es pasado pide goles, si es futuro guarda."""
        try:
            fecha_dt = datetime.datetime.strptime(update.message.text.strip(), "%d/%m/%Y %H:%M")
            context.user_data['nuevo_partido_fecha'] = fecha_dt
            ahora = self.db.obtener_hora_argentina()
            
            if fecha_dt < ahora:
                await update.message.reply_text(
                    "⚽ El partido es del pasado. *Ingresá el resultado final* (Formato: GolesCAI-GolesRival)\n"
                    "Ejemplo: 2-0",
                    reply_markup=ReplyKeyboardMarkup([["🚫 Cancelar"]], resize_keyboard=True)
                )
                return self.esperando_crear_partido_goles
            else:
                # Es futuro, guardamos directo
                return await self._guardar_nuevo_partido(update, context, None, None)
        except ValueError:
            await update.message.reply_text("❌ Formato incorrecto. Usá DD/MM/AAAA HH:MM")
            return self.esperando_crear_partido_fecha

    async def procesar_crear_partido_goles(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Paso 6: Valida goles y guarda."""
        texto = update.message.text.strip()
        try:
            partes = texto.split("-")
            return await self._guardar_nuevo_partido(update, context, int(partes[0]), int(partes[1]))
        except (ValueError, IndexError):
            await update.message.reply_text("❌ Formato inválido. Ejemplo: 1-0")
            return self.esperando_crear_partido_goles

    async def _guardar_nuevo_partido(self, update, context, g_cai, g_rival):
        """Función interna para insertar en BD y finalizar."""
        try:
            # Se eliminó la etiqueta de texto que causaba el SyntaxError
            self.db.insertar_partido_manual(
                context.user_data['nuevo_partido_edicion_id'],
                context.user_data['nuevo_partido_rival']['id'],
                context.user_data['nuevo_partido_condicion'],
                context.user_data['nuevo_partido_fecha'].strftime("%Y-%m-%d %H:%M:%S"),
                g_cai, g_rival
            )
            await update.message.reply_text("✅ ¡Partido creado con éxito!")
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")
            
        return await self.iniciar_admin_partidos(update, context)
    
    async def procesar_partido_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Paso 2: Valida el NÚMERO visual y le pide el resultado."""
        texto = update.message.text.strip()
        partidos_info = context.user_data.get('partidos_info', {})
        
        if texto not in partidos_info:
            await update.message.reply_text(
                "❌ Ese número no es válido\n"
                "Intentá de nuevo con un NÚMERO de la lista o escribí /cancelar."
            )
            return self.esperando_partido_id
            
        # Extraemos el ID real desde la memoria
        info_partido_elegido = partidos_info[texto]
        context.user_data['partido_id_elegido'] = info_partido_elegido['id']
        context.user_data['info_partido_elegido'] = info_partido_elegido
        
        # Creamos el botón para el teclado
        botones = [["🔙 Volver al menú principal"]]
        
        await update.message.reply_text(
            "⚽ *¡Excelente!*\n\n"
            "Ahora escribí tu pronóstico con el formato *GolesCAI-GolesRival*.\n"
            "Ejemplo: *2-0* o *1-1*\n\n"
            "_(Recordá que siempre el primer número corresponde a Independiente)_",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(botones, resize_keyboard=True) # 🌟 Se inyecta el botón acá
        )
        return self.esperando_pronostico
    
    async def procesar_pronostico(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Paso 3: Guarda el resultado en la base de datos."""
        texto = update.message.text.strip()
        partido_id = context.user_data.get('partido_id_elegido')
        username = context.user_data.get('username_pronostico')
        
        # Recuperamos la info del partido para usar el nombre real
        info_partido = context.user_data.get('info_partido_elegido', {})
        rival = info_partido.get('rival', 'Rival')
        condicion = info_partido.get('condicion', 1)
        
        if not partido_id or not username:
            await update.message.reply_text("❌ La sesión expiró. Volvé a iniciar el proceso.")
            await self.mostrar_menu(update, context)
            return ConversationHandler.END
            
        try:
            if "-" not in texto:
                raise ValueError()
            
            partes = texto.split("-")
            if len(partes) != 2:
                raise ValueError()
                
            goles_cai = int(partes[0].strip())
            goles_rival = int(partes[1].strip())
            
            fecha_actual = self.db.obtener_hora_argentina()
            
            # Hacemos el INSERT. Si el usuario lo hace 1000 veces, se guardan 1000 filas
            # pero self.db.obtener_partidos siempre leerá el de la fecha_actual más grande.
            self.db.insertar_pronostico(username, partido_id, goles_cai, goles_rival, fecha_actual)
            
            # --- AVISAR AL ADMINISTRADOR SI NO FUE ÉL MISMO ---
            if username != "Gabriel":
                admin_id = self.db.obtener_id_telegram_por_username("Gabriel")
                if admin_id:
                    texto_alerta = (
                        f"🔔 *Nuevo Pronóstico*\n\n"
                        f"👤 *Usuario:* {username} (vía Telegram)\n"
                        f"⚽ *Partido:* vs {rival}\n"
                        f"👉 *Resultado:* {goles_cai} - {goles_rival}"
                    )
                    try:
                        # Mandar mensaje sin modificar el teclado (reply_markup) de Gabriel
                        await context.bot.send_message(
                            chat_id=admin_id, 
                            text=texto_alerta, 
                            parse_mode="Markdown",
                            disable_notification=True
                        )
                    except Exception as e:
                        print(f"No se pudo notificar al admin: {e}")
            # ---------------------------------------------------------

            # Armamos el texto final respetando quién es local y quién visitante
            if condicion == -1:
                resultado_str = f"{rival} {goles_rival} - {goles_cai} Independiente 🔴"
            else:
                resultado_str = f"🔴 Independiente {goles_cai} - {goles_rival} {rival}"
                
            await update.message.reply_text(
                f"✅ *¡Pronóstico guardado con éxito!*\n\n"
                f"Tu jugada para este partido es:\n"
                f"*{resultado_str}*",
                parse_mode="Markdown"
            )
            
        except ValueError:
            await update.message.reply_text(
                "❌ Formato inválido.\n"
                "Debe ser solo números separados por un guion. Ejemplo: 2-0\n\n"
                "Intentá de nuevo o escribí /cancelar:"
            )
            return self.esperando_pronostico
        except Exception as e:
            await update.message.reply_text(f"❌ Error en la base de datos: {e}\nIntentá de nuevo o /cancelar.")
            return self.esperando_pronostico
            
        await self.mostrar_menu(update, context)
        return ConversationHandler.END

    # ==========================================
    # FLUJO 3: VER TABLA DE POSICIONES
    # ==========================================
    def _formatear_anticipacion(self, segundos):
        """Convierte los segundos a un formato compacto y legible para el celular: 'Xd HH:MM:SS'"""
        if segundos is None:
            return "00:00:00"
            
        segundos = float(segundos)
        dias = int(segundos // 86400)
        horas = int((segundos % 86400) // 3600)
        minutos = int((segundos % 3600) // 60)
        segs = int(segundos % 60)
        
        if dias > 0:
            return f"{dias}d {horas:02d}:{minutos:02d}:{segs:02d}"
        else:
            return f"{horas:02d}:{minutos:02d}:{segs:02d}"

    def _registrar_log(self, mensaje, archivo="logs_bot.txt"):
        """Escribe un registro en un archivo de texto con la fecha y hora actuales."""
        try:
            # Obtener la hora de Argentina para el log
            zona_horaria = pytz.timezone('America/Argentina/Buenos_Aires')
            ahora = datetime.datetime.now(zona_horaria)
            marca_tiempo = ahora.strftime("%Y-%m-%d %H:%M:%S")
            
            # Construir la línea de log
            linea_log = f"[{marca_tiempo}] : {mensaje}\n"
            
            # Obtener la ruta correcta dependiendo de si es un ejecutable o script
            if getattr(sys, 'frozen', False):
                carpeta = sys._MEIPASS
            else:
                carpeta = os.path.dirname(os.path.abspath(__file__))
                
            ruta_archivo = os.path.join(carpeta, archivo)
            
            # Escribir en el archivo en modo 'append' (añadir)
            with open(ruta_archivo, "a", encoding="utf-8") as f:
                f.write(linea_log)
        except Exception as e:
            # Fallback seguro en caso de que no pueda escribir en el archivo
            print(f"Error crítico al intentar guardar el log: {e}")

    def _auditar_consulta_estadistica(self, update: Update, nombre_estadistica):
        """Registra en el log cuando un usuario (no admin) consulta una estadística."""
        id_telegram = update.effective_user.id
        username = self.db.obtener_usuario_por_telegram(id_telegram)
        
        if username and username != "Gabriel":
            mensaje = f"👁️ CONSULTA: El usuario '{username}' revisó la estadística de '{nombre_estadistica}'."
            self._registrar_log(mensaje, archivo="logs_estadisticas_bot.txt")

    # ==========================================
    # FLUJO 4: CONSULTAR PRONÓSTICOS
    # ==========================================
    async def preguntar_usuario_pronosticos(self, update: Update, context: ContextTypes.DEFAULT_TYPE, edicion_id, titulo):
        """Actúa como 'funcion_imprimir' puente: pregunta de quién ver los pronósticos antes de imprimirlos."""
        # Guardamos el título del torneo (o 'Histórica') para usarlo en el siguiente paso
        context.user_data['torneo_elegido_pronosticos'] = titulo

        id_telegram = update.message.from_user.id
        username_propio = self.db.obtener_usuario_por_telegram(id_telegram)
        usuarios_db = self.db.obtener_usuarios_con_id()
        usuarios = [u[1] for u in usuarios_db]

        botones = [["1_ De todos"], ["2_ Míos"]]
        mapa_usuarios = {"1_ De todos": "todos", "2_ Míos": username_propio}

        contador = 3
        fila = []
        for u in usuarios:
            if u != username_propio:
                texto_btn = f"{contador}_ {u}"
                fila.append(texto_btn)
                mapa_usuarios[texto_btn] = u
                contador += 1
                
                if len(fila) == 2:
                    botones.append(fila)
                    fila = []
                    
        if fila:
            botones.append(fila)

        botones.append(["🔙 Volver al menú"])
        context.user_data['mapa_usuarios_pronosticos'] = mapa_usuarios

        await update.message.reply_text(
            "👤 ¿De quién querés ver los pronósticos?",
            reply_markup=ReplyKeyboardMarkup(botones, resize_keyboard=True)
        )
        return self.esperando_usuario_pronosticos

    async def imprimir_pronosticos(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Paso final: Busca los pronósticos y los imprime en pantalla."""
        texto = update.message.text.strip()
        
        if texto == "🔙 Volver al menú":
            await self.mostrar_menu(update, context)
            return ConversationHandler.END

        mapa = context.user_data.get('mapa_usuarios_pronosticos', {})
        if texto not in mapa:
            await update.message.reply_text("❌ Opción no válida. Elegí usando los botones.")
            return self.esperando_usuario_pronosticos

        target_user = mapa[texto]
        titulo_torneo = context.user_data.get('torneo_elegido_pronosticos', 'Histórica')
        
        # Si es histórica, el filtro de la DB debe ser None. Si es torneo, le pasamos el nombre.
        filtro_torneo = None if titulo_torneo == "Histórica" else titulo_torneo

        if target_user == "todos":
            datos = self.db.obtener_todos_pronosticos(filtro_torneo=filtro_torneo)
        else:
            datos = self.db.obtener_todos_pronosticos(filtro_torneo=filtro_torneo, filtro_usuario=target_user)

        if not datos:
            await update.message.reply_text("📝 No hay pronósticos cargados para esta selección.")
            await self.mostrar_menu(update, context)
            return ConversationHandler.END

        # ORDEN ESTRICTO: Ordenamos descendentemente por fecha y hora del pronóstico (índice 9)
        datos_ordenados = sorted(datos, key=lambda x: x[9], reverse=True)

        mensajes = []
        if target_user == "todos":
            mensaje_actual = f"📋 *Historial de TODOS - {titulo_torneo}*\n\n"
        else:
            mensaje_actual = f"📋 *Historial de {target_user} - {titulo_torneo}*\n\n"

        for row in datos_ordenados:
            rival = row[0]
            fecha_partido = row[1].strftime('%d/%m/%Y %H:%M') if row[1] else "A conf."
            user = row[5]
            pred_cai = row[6]
            pred_rival = row[7]
            fecha_pred = row[9].strftime('%d/%m/%Y %H:%M:%S') if row[9] else "N/A"

            # Extraemos los datos del resultado real, puntos y error
            real_cai = row[3]
            real_rival = row[4]
            puntos = row[8]
            error_abs = row[10]

            bloque = ""
            if target_user == "todos":
                bloque += f"👤 *{user}*\n"
                
            # Formateamos el rival para incluir el resultado si existe
            if real_cai is not None and real_rival is not None:
                texto_rival = f"{rival} ({real_cai}-{real_rival})"
            else:
                texto_rival = rival
                
            bloque += f"⚽ vs {texto_rival} | 📅 {fecha_partido}\n"
            bloque += f"👉 *Independiente {pred_cai} - {pred_rival} {rival}*\n"
            bloque += f"⏱️ _Cargado el: {fecha_pred}_\n"
            
            # Agregamos Puntos y Error Absoluto solo si corresponden
            # (Si es NULL en la BD es porque el partido no se jugó o el usuario cambió el pronóstico después)
            if puntos is not None:
                txt_puntos = f"🏅 Puntos: {int(puntos)}"
                txt_error = f" | ❌ Error abs: {int(error_abs)}" if error_abs is not None else ""
                bloque += f"{txt_puntos}{txt_error}\n"
                
            bloque += "—\n"

            if len(mensaje_actual) + len(bloque) > 3800:
                mensajes.append(mensaje_actual)
                mensaje_actual = bloque
            else:
                mensaje_actual += bloque

        if mensaje_actual:
            mensajes.append(mensaje_actual)

        for m in mensajes:
            await update.message.reply_text(m, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())

        await self.mostrar_menu(update, context)
        return ConversationHandler.END
    
    # ==========================================
    # FLUJO 5: OPTIMISMO/PESIMISMO
    # ==========================================
    async def imprimir_tabla_opt_pes(self, update: Update, context: ContextTypes.DEFAULT_TYPE, edicion_id, titulo):
        """Construye y envía la tabla con las lógicas del programa de escritorio."""
        threading.Thread(
            target=self._auditar_consulta_estadistica, 
            args=(update, f"Optimismo/Pesimismo ({titulo})"), 
            daemon=True
        ).start()
        datos = self.db.obtener_indice_optimismo_pesimismo(edicion_id=edicion_id)
        
        if not datos:
            await update.message.reply_text("📉 Todavía no hay datos de optimismo/pesimismo para esta selección.")
            # Agregado self.
            await self.mostrar_menu(update, context)
            return ConversationHandler.END
            
        # Se agrega el texto explicativo debajo del título
        mensaje = f"🧠 *Optimismo/Pesimismo: {titulo}* 🧠\n"
        mensaje += "_Mide tu tendencia a pronosticar resultados a favor (Optimista) o en contra (Pesimista) del Rojo._\n\n"
        
        for i, row in enumerate(datos, start=1):
            user = row[0]
            val = row[1]
            desvio = row[2]
            
            # --- LÓGICA REPLICADA DE FLET ---
            if desvio is None or val is None:
                txt_desvio = "-"
                clasif_desvio = "-"
                txt_val = "-"
                clasificacion = "-"
            else:
                val_float = float(val)
                desvio_float = float(desvio)
                
                # Formateo del desvío (Perfil)
                txt_desvio = f"{desvio_float:.2f}".replace('.', ',')
                if desvio_float < 0.8:
                    clasif_desvio = "🎯 Consistente"
                elif desvio_float < 1.5:
                    clasif_desvio = "📊 Normal"
                else:
                    clasif_desvio = "🎢 Inestable"
                    
                # Formateo del valor (+.2f asegura que siempre tenga el signo + o -)
                txt_val = f"{val_float:+.2f}".replace('.', ',')
                if val_float >= 1.5:
                    clasificacion = "🔴 Muy optimista"
                elif 0.5 <= val_float < 1.5:
                    clasificacion = "🙂 Optimista"
                elif -0.5 < val_float < 0.5:
                    clasificacion = "⚖️ Neutral"
                elif -1.5 < val_float <= -0.5:
                    clasificacion = "😐 Pesimista"
                else:
                    clasificacion = "🔵 Muy pesimista"
                    
            # Armamos el mensaje compacto y fácil de leer
            mensaje += f"*{i}º {user}*\n"
            mensaje += f"└ Índice: {txt_val} | {clasificacion}\n"
            mensaje += f"└ Perfil: {txt_desvio} | {clasif_desvio}\n\n"
            
        botones = [
            ["1_ Ver referencias"],
            ["🔙 Atrás", "🔙 Volver al menú principal"]
        ]
        
        await update.message.reply_text(
            mensaje, 
            parse_mode="Markdown", 
            reply_markup=ReplyKeyboardMarkup(botones, resize_keyboard=True)
        )
        
        return self.esperando_accion_opt_pes

    async def procesar_accion_opt_pes(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Muestra el glosario detallado reflejando el sesgo vs la realidad futbolística."""
        mensaje_ref = (
            "📋 *REFERENCIAS DE OPTIMISMO Y PESIMISMO*\n\n"
            "El *Índice* compara tus expectativas con el rendimiento real de los equipos. "
            "Ser optimista no significa predecir una victoria, sino esperar que a Independiente le vaya *mejor* de lo que realmente le termina yendo.\n\n"
            "🔴 *Muy optimista (≥ +1.50):* Tus expectativas están muy por encima de la realidad. Si predijiste perder 2-0 y perdimos 4-0, sos muy optimista porque esperabas un escenario mucho más favorable.\n"
            "🙂 *Optimista (+0.50 a +1.49):* Tendés a sobreestimar el desempeño del equipo, esperando resultados levemente mejores a los reales.\n"
            "⚖️ *Neutral (-0.49 a +0.49):* Tus predicciones son un reflejo sumamente fiel de la realidad futbolística y el nivel mostrado en el campo.\n"
            "😐 *Pesimista (-0.50 a -1.49):* Solés subestimar el rendimiento real, esperando resultados peores a los que finalmente se logran (ej: esperar un empate y que el equipo gane).\n"
            "🔵 *Muy pesimista (≤ -1.50):* Tus expectativas están sistemáticamente muy por debajo de lo que el equipo termina demostrando en cada partido.\n\n"
            "El *Perfil (Variabilidad)* mide qué tan constante es ese sesgo a lo largo del tiempo:\n"
            "🎯 *Consistente (< 0.80):* Mantenés siempre la misma postura. Si sos optimista, lo sos casi siempre por el mismo margen de error.\n"
            "📊 *Normal (0.80 a 1.49):* Tus expectativas fluctúan de forma natural según el rival o el contexto del torneo.\n"
            "🎢 *Inestable (≥ 1.50):* Tu tendencia es impredecible. Podés pasar de una fe ciega a un pesimismo extremo entre un partido y otro."
        )
        
        # Creamos un teclado solo con las opciones de salida
        botones = [
            ["🔙 Atrás", "🔙 Volver al menú principal"]
        ]
        
        # Adjuntamos el reply_markup para forzar el scroll de Telegram
        await update.message.reply_text(
            mensaje_ref, 
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(botones, resize_keyboard=True)
        )
        
        # Nos mantenemos en el estado de acción esperando que toque "Atrás" o "Volver"
        return self.esperando_accion_opt_pes

    # ==========================================
    # FLUJO 6: MAYORES ERRORES
    # ==========================================
    async def imprimir_tabla_mayores_errores(self, update: Update, context: ContextTypes.DEFAULT_TYPE, edicion_id, titulo):
        threading.Thread(
            target=self._auditar_consulta_estadistica, 
            args=(update, f"Mayores Errores ({titulo})"), 
            daemon=True
        ).start()
        datos = self.db.obtener_ranking_mayores_errores(edicion_id=edicion_id)
        if not datos:
            await update.message.reply_text("📉 Todavía no hay datos de errores para esta selección.")
            # Agregado self.
            await self.mostrar_menu(update, context)
            return ConversationHandler.END
            
        mensajes = []
        mensaje_actual = f"📉 *Mayores Errores: {titulo}* 📉\n"
        
        # Usamos self.limite_errores en vez de la variable global suelta
        mensaje_actual += f"_Los pronósticos más alejados de la realidad (Top {self.limite_errores})._\n\n"
        
        for i, row in enumerate(datos, start=1):
            user = row[0]
            rival = row[1]
            fecha_partido = row[2].strftime('%d/%m/%Y') if row[2] else "N/A"
            pred_cai = row[4]
            pred_rival = row[5]
            real_cai = row[6]
            real_rival = row[7]
            error_abs = row[8]
            
            # Armamos el texto de cada error
            bloque = f"*{i}º {user}* | ❌ Error: {error_abs}\n"
            bloque += f"⚽ vs {rival} ({fecha_partido})\n"
            bloque += f"👉 _Dijo:_ CAI {pred_cai} - {pred_rival} Rival\n"
            bloque += f"🎯 _Real:_ CAI {real_cai} - {real_rival} Rival\n"
            bloque += "—\n"
            
            # Si el texto está por superar el límite de Telegram, guardamos y empezamos otro globo
            if len(mensaje_actual) + len(bloque) > 3800:
                mensajes.append(mensaje_actual)
                mensaje_actual = bloque
            else:
                mensaje_actual += bloque
                
        if mensaje_actual:
            mensajes.append(mensaje_actual)
            
        # Creamos los botones
        botones = [
            ["🔙 Atrás", "🔙 Volver al menú principal"]
        ]
            
        # Enviamos los globos de texto secuencialmente
        for m in mensajes[:-1]:
            await update.message.reply_text(m, parse_mode="Markdown")
            
        # Enviamos el último mensaje con el teclado y devolvemos el estado
        await update.message.reply_text(
            mensajes[-1], 
            parse_mode="Markdown", 
            reply_markup=ReplyKeyboardMarkup(botones, resize_keyboard=True)
        )
        
        return self.esperando_accion_mayores_errores
    
    # ==========================================
    # FLUJO 7: RANKING FALSO PROFETA
    # ==========================================
    async def imprimir_tabla_falso_profeta(self, update: Update, context: ContextTypes.DEFAULT_TYPE, edicion_id, titulo):
        """Construye y envía el ranking invirtiendo el % de acierto al % de falso profeta."""
        threading.Thread(
            target=self._auditar_consulta_estadistica, 
            args=(update, f"Falso Profeta ({titulo})"), 
            daemon=True
        ).start()

        # Acceso a la base de datos vía self.db
        datos = self.db.obtener_ranking_falso_profeta(edicion_id=edicion_id)
        
        if not datos:
            await update.message.reply_text("📉 Todavía no hay suficientes datos para calcular falsos profetas en esta selección.")
            # Uso de self.
            await self.mostrar_menu(update, context)
            return ConversationHandler.END
            
        mensajes = []
        mensaje_actual = f"🤡 *Ranking Falso Profeta: {titulo}* 🤡\n"
        mensaje_actual += "_Usuarios que más le erran cuando dicen que el Rojo va a ganar._\n\n"
        
        for i, fila in enumerate(datos, start=1):
            user = fila[0]
            victorias_pred = fila[1]
            porcentaje_acierto = float(fila[2])
            
            # Matemática de Flet
            porcentaje_falso = 100.0 - porcentaje_acierto
            txt_porcentaje = f"{porcentaje_falso:.1f}%".replace('.', ',')
            
            # Colores pasados a emojis de semáforo
            if porcentaje_falso >= 80: 
                emoji_color = "🔴"
            elif porcentaje_falso >= 50: 
                emoji_color = "🟠"
            else: 
                emoji_color = "🟢"
                
            bloque = f"*{i}º {user}*\n"
            bloque += f"└ {emoji_color} % Falso Profeta: {txt_porcentaje}\n"
            bloque += f"└ 🗣️ Predijo victoria: {victorias_pred} veces\n\n"
            
            if len(mensaje_actual) + len(bloque) > 3800:
                mensajes.append(mensaje_actual)
                mensaje_actual = bloque
            else:
                mensaje_actual += bloque
                
        if mensaje_actual:
            mensajes.append(mensaje_actual)
            
        # Creamos los botones de navegación
        botones = [
            ["🔙 Atrás", "🔙 Volver al menú principal"]
        ]
            
        # Enviamos los globos de texto secuencialmente (sin botones)
        for m in mensajes[:-1]:
            await update.message.reply_text(m, parse_mode="Markdown")
            
        # Enviamos el último mensaje con el teclado y devolvemos el estado
        await update.message.reply_text(
            mensajes[-1], 
            parse_mode="Markdown", 
            reply_markup=ReplyKeyboardMarkup(botones, resize_keyboard=True)
        )
        
        return self.esperando_accion_falso_profeta

    # ==========================================
    # FLUJO 8: ESTILOS DE DECISIÓN
    # ==========================================
    async def imprimir_tabla_estilo_decision(self, update: Update, context: ContextTypes.DEFAULT_TYPE, edicion_id, titulo):
        """Construye y envía el ranking de estilos de decisión."""
        threading.Thread(
            target=self._auditar_consulta_estadistica, 
            args=(update, f"Estilo de Decisión ({titulo})"), 
            daemon=True
        ).start()
        # Obtenemos el ranking base que ya trae el promedio de anticipación (índice 6)
        datos_ranking = self.db.obtener_ranking(edicion_id=edicion_id, anio=None)
        
        # Filtramos solo los que tienen anticipación válida (mayor a 0)
        datos_validos = [row for row in datos_ranking if row[6] is not None and float(row[6]) > 0]
        
        if not datos_validos:
            await update.message.reply_text(
                "⚠️ *No hay datos suficientes.*\n\n"
                "Este análisis requiere que los usuarios hayan pronosticado partidos pasados para calcular sus promedios de tiempo.",
                parse_mode="Markdown"
            )
            await self.mostrar_menu(update, context)
            return ConversationHandler.END

        # Ordenamos de mayor anticipación a menor
        datos_validos.sort(key=lambda x: float(x[6]), reverse=True)
            
        mensajes = []
        mensaje_actual = f"⏱️ *Estilo de Decisión: {titulo}* ⏱️\n"
        mensaje_actual += "_Promedio de tiempo de anticipación al cargar pronósticos._\n\n"
        
        for i, row in enumerate(datos_validos, start=1):
            user = row[0]
            val_sec = float(row[6])
            
            # Cálculo de horas totales para la clasificación
            horas_totales_float = val_sec / 3600
            
            # Lógica de Clasificación de Flet
            if horas_totales_float > 72:   # +3 días
                estilo = "🧠 Convencido temprano"
            elif horas_totales_float > 24: # +1 día
                estilo = "🗓️ Anticipado"
            elif horas_totales_float > 6:  # +6 horas
                estilo = "⚖️ Balanceado"
            elif horas_totales_float > 1:  # +1 hora
                estilo = "⏳ Último momento"
            else:                    # -1 hora
                estilo = "🔥 Impulsivo"

            # Formato Visual (HH:MM:SS h)
            horas_display = int(val_sec // 3600) 
            segundos_restantes = val_sec % 3600
            minutos_display = int(segundos_restantes // 60)
            segundos_display = int(segundos_restantes % 60)
            
            txt_tiempo = f"{horas_display:02d}:{minutos_display:02d}:{segundos_display:02d} h"
            
            bloque = f"*{i}º {user}*\n"
            bloque += f"└ ⏱️ {txt_tiempo}\n"
            bloque += f"└ {estilo}\n\n"
            
            if len(mensaje_actual) + len(bloque) > 3800:
                mensajes.append(mensaje_actual)
                mensaje_actual = bloque
            else:
                mensaje_actual += bloque
                
        if mensaje_actual:
            mensajes.append(mensaje_actual)
        
        botones = [
            ["1_ Ver referencias"],
            ["🔙 Atrás", "🔙 Volver al menú principal"]
        ]
            
        for m in mensajes[:-1]:
            await update.message.reply_text(m, parse_mode="Markdown")
            
        # Enviamos el último globo con el teclado
        await update.message.reply_text(
            mensajes[-1], 
            parse_mode="Markdown", 
            reply_markup=ReplyKeyboardMarkup(botones, resize_keyboard=True)
        )
        
        return self.esperando_accion_estilo_decision

    async def procesar_accion_estilo_decision(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Muestra el glosario detallado de los tiempos de carga con navegación completa."""
        mensaje_ref = (
            "📋 *REFERENCIAS DE ESTILOS DE DECISIÓN*\n\n"
            "Este ranking analiza el promedio de tiempo de anticipación con el que cargás tus pronósticos antes del pitazo inicial:\n\n"
            "🧠 *Convencido temprano (más de 3 días):* Sos de los que ya tienen el resultado en la cabeza apenas termina el partido anterior. No necesitás ver cómo llega el equipo ni quién es el árbitro.\n"
            "🗓️ *Anticipado (1 a 3 días):* Organizás tu semana con tiempo. Cargás tus jugadas con tranquilidad, generalmente cuando sale la lista de concentrados.\n"
            "⚖️ *Balanceado (6 a 24 horas):* El estilo más analítico. Esperás a las últimas noticias del día previo o la mañana del partido para decidir tu pálpito.\n"
            "⏳ *Último momento (1 a 6 horas):* Vivís al límite. Cargás tu pronóstico mientras vas a la cancha o preparás la previa, con la formación confirmada en mano.\n"
            "🔥 *Impulsivo (menos de 1 hora):* Pura adrenalina. Tu decisión es visceral y de último segundo, quizás influenciada por el clima del estadio o un pálpito repentino antes del cierre."
        )
        
        # Teclado con ambas opciones para refrescar la vista y permitir navegación
        botones = [
            ["🔙 Atrás"],
            ["🔙 Volver al menú principal"]
        ]
        
        await update.message.reply_text(
            mensaje_ref, 
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(botones, resize_keyboard=True)
        )
        
        return self.esperando_accion_estilo_decision
    
    # ==========================================
    # FLUJO 9: RANKING MUFA
    # ==========================================
    async def imprimir_tabla_mufa(self, update: Update, context: ContextTypes.DEFAULT_TYPE, edicion_id, titulo):
        """Construye y envía el ranking Mufa."""
        threading.Thread(
            target=self._auditar_consulta_estadistica, 
            args=(update, f"Mufa ({titulo})"), 
            daemon=True
        ).start()

        datos = self.db.obtener_ranking_mufa(edicion_id=edicion_id, anio=None)
        
        if not datos:
            await update.message.reply_text("📉 Todavía no hay suficientes datos de derrotas pronosticadas en esta selección.")
            await self.mostrar_menu(update, context)
            return ConversationHandler.END
            
        mensajes = []
        mensaje_actual = f"🌩️ *Ranking Mufa: {titulo}* 🌩️\n"
        mensaje_actual += "_Usuarios que más aciertan cuando pronostican que el Rojo pierde._\n\n"
        
        for i, fila in enumerate(datos, start=1):
            user = fila[0]
            pred_derrotas = fila[1]
            aciertos = fila[2]
            porcentaje = float(fila[3])
            
            txt_porcentaje = f"{porcentaje:.1f}%".replace('.', ',')
            
            # Lógica de colores de Flet convertida a Emojis para Telegram
            if porcentaje >= 50: 
                emoji_color = "🔴"
            elif porcentaje >= 20: 
                emoji_color = "🟠"
            else: 
                emoji_color = "🟢"
                
            bloque = f"*{i}º {user}*\n"
            bloque += f"└ {emoji_color} % Mufa: {txt_porcentaje}\n"
            bloque += f"└ 📉 Predijo derrota: {pred_derrotas} | 🎯 Acertó: {aciertos}\n\n"
            
            if len(mensaje_actual) + len(bloque) > 3800:
                mensajes.append(mensaje_actual)
                mensaje_actual = bloque
            else:
                mensaje_actual += bloque
                
        if mensaje_actual:
            mensajes.append(mensaje_actual)
            
        botones = [
            ["🔙 Atrás", "🔙 Volver al menú principal"]
        ]
            
        for m in mensajes[:-1]:
            await update.message.reply_text(m, parse_mode="Markdown")
            
        await update.message.reply_text(
            mensajes[-1], 
            parse_mode="Markdown", 
            reply_markup=ReplyKeyboardMarkup(botones, resize_keyboard=True)
        )
        
        return self.esperando_accion_mufa

    # ==========================================
    # FLUJO 10: MEJOR PREDICTOR
    # ==========================================
    async def imprimir_tabla_mejor_predictor(self, update: Update, context: ContextTypes.DEFAULT_TYPE, edicion_id, titulo):
        """Construye y envía el ranking de Mejor Predictor basado en error absoluto."""
        threading.Thread(
            target=self._auditar_consulta_estadistica, 
            args=(update, f"Mejor Predictor ({titulo})"), 
            daemon=True
        ).start()

        datos = self.db.obtener_ranking_mejor_predictor(edicion_id=edicion_id, anio=None)
        
        if not datos:
            await update.message.reply_text("📉 Todavía no hay datos de predicciones para esta selección.")
            await self.mostrar_menu(update, context)
            return ConversationHandler.END
            
        mensajes = []
        mensaje_actual = f"🎯 *Ranking Mejor Predictor: {titulo}* 🎯\n"
        mensaje_actual += "_Promedio de error absoluto de goles por partido._\n\n"
        
        for i, row in enumerate(datos, start=1):
            user = row[0]
            val = float(row[1])
            
            txt_val = f"{val:.2f}".replace('.', ',')
            
            # Lógica de Flet traducida a Emojis de Telegram
            if val == 0:
                clasificacion = "🎯 Predictor perfecto"
                emoji_color = "🔵"
            elif val <= 1.0:
                clasificacion = "👌 Muy preciso"
                emoji_color = "🟢"
            elif val <= 2.0:
                clasificacion = "👍 Aceptable"
                emoji_color = "🟡"
            else: 
                clasificacion = "🎲 Poco realista / arriesgado"
                emoji_color = "🔴"
                
            bloque = f"*{i}º {user}*\n"
            bloque += f"└ {emoji_color} Promedio de error: {txt_val}\n"
            bloque += f"└ {clasificacion}\n\n"
            
            if len(mensaje_actual) + len(bloque) > 3800:
                mensajes.append(mensaje_actual)
                mensaje_actual = bloque
            else:
                mensaje_actual += bloque
                
        if mensaje_actual:
            mensajes.append(mensaje_actual)
            
        botones = [
            ["1_ Ver referencias"],
            ["🔙 Atrás", "🔙 Volver al menú principal"]
        ]
            
        for m in mensajes[:-1]:
            await update.message.reply_text(m, parse_mode="Markdown")
            
        # Enviamos el último globo con el teclado activo
        await update.message.reply_text(
            mensajes[-1], 
            parse_mode="Markdown", 
            reply_markup=ReplyKeyboardMarkup(botones, resize_keyboard=True)
        )
        
        return self.esperando_accion_mejor_predictor
    
    async def procesar_accion_mejor_predictor(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Muestra el glosario detallado sobre la precisión de los goles."""
        mensaje_ref = (
            "📋 *REFERENCIAS DE MEJOR PREDICTOR*\n\n"
            "Este ranking premia la exactitud numérica. Se calcula sumando la diferencia absoluta entre tus goles pronosticados y los reales de ambos equipos:\n"
            "_Fórmula: |Goles Independiente (Tu pred. - Real)| + |Goles Rival (Tu pred. - Real)|_\n\n"
            "🎯 *Predictor perfecto (0,00):* Acertaste el resultado exacto. No hubo diferencia entre tu pálpito y la realidad.\n\n"
            "👌 *Muy preciso (0,01 a 1,00):* Estuviste a solo un gol de diferencia en uno de los dos equipos. Un margen de error mínimo.\n\n"
            "👍 *Aceptable (1,01 a 2,00):* Le erraste por un gol a cada equipo o por dos goles a uno solo. Es el promedio normal de la comunidad.\n\n"
            "🎲 *Poco realista / arriesgado (más de 2,00):* Tus pronósticos están muy lejos de la realidad. Sos un jugador que toma decisiones arriesgadas o poco realistas."
        )
        
        botones = [
            ["🔙 Atrás"],
            ["🔙 Volver al menú principal"]
        ]
        
        await update.message.reply_text(
            mensaje_ref, 
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(botones, resize_keyboard=True)
        )
        
        return self.esperando_accion_mejor_predictor
    
    # ==========================================
    # FLUJO 11: RACHA RÉCORD
    # ==========================================
    async def imprimir_tabla_racha_record(self, update: Update, context: ContextTypes.DEFAULT_TYPE, edicion_id, titulo):
        """Construye y envía el ranking de Racha Récord."""
        threading.Thread(
            target=self._auditar_consulta_estadistica, 
            args=(update, f"Racha Récord ({titulo})"), 
            daemon=True
        ).start()
        datos = self.db.obtener_racha_record(edicion_id=edicion_id, anio=None)
        
        if not datos:
            await update.message.reply_text("📉 Todavía no hay datos de rachas para esta selección.")
            await self.mostrar_menu(update, context)
            return ConversationHandler.END
            
        mensajes = []
        mensaje_actual = f"🔥 *Racha Récord: {titulo}* 🔥\n"
        mensaje_actual += "_Mayor cantidad de aciertos exactos de forma consecutiva._\n\n"
        
        for i, row in enumerate(datos, start=1):
            user = row[0]
            racha = row[1]
            
            # Lógica de colores traducida a Emojis de Telegram
            if racha >= 10: 
                emoji_color = "🟣" # purple
            elif racha >= 7: 
                emoji_color = "🔵" # cyan
            elif racha >= 4: 
                emoji_color = "🟢" # green
            else: 
                emoji_color = "⚪" # white
                
            bloque = f"*{i}º {user}*\n"
            bloque += f"└ {emoji_color} Racha máxima: {racha} aciertos seguidos\n\n"
            
            # Control de paginación para evitar el límite de caracteres de Telegram
            if len(mensaje_actual) + len(bloque) > 3800:
                mensajes.append(mensaje_actual)
                mensaje_actual = bloque
            else:
                mensaje_actual += bloque
                
        if mensaje_actual:
            mensajes.append(mensaje_actual)
            
        # Creamos los botones de navegación
        botones = [
            ["🔙 Atrás", "🔙 Volver al menú principal"]
        ]
            
        # Enviamos los globos de texto secuencialmente (sin botones)
        for m in mensajes[:-1]:
            await update.message.reply_text(m, parse_mode="Markdown")
            
        # Enviamos el último mensaje con el teclado y devolvemos el estado
        await update.message.reply_text(
            mensajes[-1], 
            parse_mode="Markdown", 
            reply_markup=ReplyKeyboardMarkup(botones, resize_keyboard=True)
        )
        
        return self.esperando_accion_racha_record

    # ==========================================
    # FLUJO 12: RACHA ACTUAL
    # ==========================================
    async def imprimir_tabla_racha_actual(self, update: Update, context: ContextTypes.DEFAULT_TYPE, edicion_id, titulo):
        """Construye y envía el ranking de Racha Actual."""
        threading.Thread(
            target=self._auditar_consulta_estadistica, 
            args=(update, f"Racha Actual ({titulo})"), 
            daemon=True
        ).start()
        datos = self.db.obtener_racha_actual(edicion_id=edicion_id, anio=None)
        
        if not datos:
            await update.message.reply_text("📉 Todavía no hay datos de rachas para esta selección.")
            await self.mostrar_menu(update, context)
            return ConversationHandler.END
            
        mensajes = []
        mensaje_actual = f"⏳ *Racha Actual: {titulo}* ⏳\n"
        mensaje_actual += "_Cantidad de partidos consecutivos actuales en los que sumaste puntos._\n\n"
        
        for i, row in enumerate(datos, start=1):
            user = row[0]
            racha = row[1]
            
            # Lógica de colores traducida a Emojis de Telegram
            if racha >= 5: 
                emoji_color = "🔵" # cyan
            elif racha >= 3: 
                emoji_color = "🟢" # green
            elif racha == 0: 
                emoji_color = "🔴" # red (Racha cortada o en 0)
            else: 
                emoji_color = "⚪" # white
                
            bloque = f"*{i}º {user}*\n"
            bloque += f"└ {emoji_color} Racha activa: {racha} aciertos seguidos\n\n"
            
            # Control de paginación para evitar el límite de caracteres
            if len(mensaje_actual) + len(bloque) > 3800:
                mensajes.append(mensaje_actual)
                mensaje_actual = bloque
            else:
                mensaje_actual += bloque
                
        if mensaje_actual:
            mensajes.append(mensaje_actual)
            
        # Creamos los botones de navegación
        botones = [
            ["🔙 Atrás", "🔙 Volver al menú principal"]
        ]
            
        # Enviamos los globos de texto secuencialmente (sin botones)
        for m in mensajes[:-1]:
            await update.message.reply_text(m, parse_mode="Markdown")
            
        # Enviamos el último mensaje con el teclado y devolvemos el estado
        await update.message.reply_text(
            mensajes[-1], 
            parse_mode="Markdown", 
            reply_markup=ReplyKeyboardMarkup(botones, resize_keyboard=True)
        )
        
        return self.esperando_accion_racha_actual
    
    # ==========================================
    # FLUJO 13: ESTABILIDAD DE PRONÓSTICOS
    # ==========================================
    async def imprimir_tabla_cambios(self, update: Update, context: ContextTypes.DEFAULT_TYPE, edicion_id, titulo):
        """Construye y envía el ranking de Estabilidad (Cambios de pronóstico)."""
        threading.Thread(
            target=self._auditar_consulta_estadistica, 
            args=(update, f"Cambio de Pronósticos ({titulo})"), 
            daemon=True
        ).start()
        datos = self.db.obtener_ranking_estabilidad(edicion_id=edicion_id, anio=None)
        
        if not datos:
            await update.message.reply_text("📉 Todavía no hay datos históricos de pronósticos para esta selección.")
            await self.mostrar_menu(update, context)
            return ConversationHandler.END
            
        # Filtramos y ordenamos igual que en la versión de Flet
        datos_validos = [row for row in datos if row[1] is not None]
        datos_validos.sort(key=lambda x: float(x[1]))
        
        mensajes = []
        mensaje_actual = f"🔄 *Estabilidad de Pronósticos: {titulo}* 🔄\n"
        mensaje_actual += "_Promedio de veces que cada usuario guarda/cambia su pronóstico por partido._\n\n"
        
        for i, row in enumerate(datos_validos, start=1):
            user = row[0]
            val_cambios = float(row[1])
            txt_cambios = f"{val_cambios:.2f}".replace('.', ',')
            
            # Lógica de colores y estilos traducida de Flet a Telegram
            if val_cambios <= 1.10:
                estilo = "🧱 Firme"
                emoji_color = "🟤" # brown
            elif val_cambios <= 1.50:
                estilo = "👍 Estable"
                emoji_color = "🟡" # amber
            elif val_cambios <= 2.50:
                estilo = "🔄 Cambiante"
                emoji_color = "🔵" # blue
            else: 
                estilo = "📉 Muy volátil"
                emoji_color = "🔴" # red
                
            bloque = f"*{i}º {user}*\n"
            bloque += f"└ {emoji_color} Promedio: {txt_cambios} veces/partido\n"
            bloque += f"└ Perfil: {estilo}\n\n"
            
            if len(mensaje_actual) + len(bloque) > 3800:
                mensajes.append(mensaje_actual)
                mensaje_actual = bloque
            else:
                mensaje_actual += bloque
                
        if mensaje_actual:
            mensajes.append(mensaje_actual)
            
        # Botones de navegación
        botones = [
            ["1_ Ver referencias"],
            ["🔙 Atrás", "🔙 Volver al menú principal"]
        ]
            
        for m in mensajes[:-1]:
            await update.message.reply_text(m, parse_mode="Markdown")
            
        # Enviamos el último globo con el teclado activo
        await update.message.reply_text(
            mensajes[-1], 
            parse_mode="Markdown", 
            reply_markup=ReplyKeyboardMarkup(botones, resize_keyboard=True)
        )
        
        return self.esperando_accion_cambios

    async def procesar_accion_cambios(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Muestra el glosario detallado sobre la estabilidad de los pálpitos."""
        mensaje_ref = (
            "📋 *REFERENCIAS DE ESTABILIDAD (CAMBIOS)*\n\n"
            "Este ranking mide cuántas veces guardás o modificás un mismo pronóstico antes de que empiece el partido. Refleja tu seguridad o tus dudas al decidir:\n\n"
            "🧱 *Firme (1,10 o menos):* Tenés las ideas claras. Una vez que cargás tu resultado, es casi imposible que lo cambies. Confías plenamente en tu primer pálpito.\n\n"
            "👍 *Estable (1,11 a 1,50):* Sos un jugador equilibrado. Podés corregir un error de tipeo o ajustar un gol tras leer una noticia de último momento, pero no solés dudar.\n\n"
            "🔄 *Cambiante (1,51 a 2,50):* Analizás mucho. Es probable que cambies tu jugada varias veces según las formaciones confirmadas o cómo sentís la previa del partido.\n\n"
            "📉 *Muy volátil (más de 2,50):* La indecisión te define. Modificás tu pronóstico constantemente, buscando ajustar hasta el último detalle antes de que ruede la pelota."
        )
        
        botones = [
            ["🔙 Atrás"],
            ["🔙 Volver al menú principal"]
        ]
        
        await update.message.reply_text(
            mensaje_ref, 
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(botones, resize_keyboard=True)
        )
        
        return self.esperando_accion_cambios
    
    async def calcular_y_mostrar_grafico_perfil(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Paso 3: Lee la memoria, procesa los datos y dibuja los emojis."""
        texto_usuario = update.message.text
        
        # Si eligió "Yo (Gabriel)", extraemos solo "Gabriel"
        if texto_usuario.startswith("Yo ("):
            usuario_seleccionado = texto_usuario[4:-1]
        else:
            usuario_seleccionado = texto_usuario

        # Recuperamos los datos de la memoria
        tipo_grafico = context.user_data.get('tipo_grafico_perfil')
        edicion_id = context.user_data.get('perfil_edicion_id')
        anio = context.user_data.get('perfil_anio')

        # --- LÓGICA ESPECÍFICA PARA "ESTILO DE PRONÓSTICO" ---
        if tipo_grafico == "estilo_pronostico":
            stats = self.db.obtener_estadisticas_estilo_pronostico(usuario_seleccionado, edicion_id, anio)
            
            if not stats or stats[0] == 0:
                await update.message.reply_text("ℹ️ No hay datos suficientes para generar el reporte de este usuario.")
                context.user_data.clear()
                
                # 🌟 MODIFICACIÓN: Si no hay datos, también vuelve al menú principal
                await self.mostrar_menu(update, context)
                return ConversationHandler.END

            total = stats[0]
            sin_pron = stats[1]
            victorias = stats[2]
            empates = stats[3]
            derrotas = stats[4]

            def calc_pct(val): return (val / total) * 100 if total > 0 else 0

            # Armamos el "Gráfico de torta de texto"
            mensaje = f"📊 *Estilo de pronóstico: {usuario_seleccionado}*\n"
            mensaje += f"Partidos analizados: _{total}_\n\n"
            
            if victorias > 0: mensaje += f"🟢 *Victorias:* {calc_pct(victorias):.1f}% ({victorias})\n"
            if empates > 0:   mensaje += f"🟡 *Empates:* {calc_pct(empates):.1f}% ({empates})\n"
            if derrotas > 0:  mensaje += f"🔴 *Derrotas:* {calc_pct(derrotas):.1f}% ({derrotas})\n"
            if sin_pron > 0:  mensaje += f"⚪ *Sin pronóstico:* {calc_pct(sin_pron):.1f}% ({sin_pron})\n"

            await update.message.reply_text(mensaje, parse_mode="Markdown")

        # --- LÓGICA ESPECÍFICA PARA "TENDENCIA DE PRONÓSTICO" ---
        elif tipo_grafico == "tendencia_pronostico":
            stats = self.db.obtener_estadisticas_tendencia_pronostico(usuario_seleccionado, edicion_id, anio)
            
            if not stats or stats[0] == 0:
                await update.message.reply_text("ℹ️ No hay datos suficientes para generar el reporte de este usuario.")
                context.user_data.clear()
                await self.mostrar_menu(update, context)
                return ConversationHandler.END

            total = stats[0]
            # Usamos "or 0" por seguridad en caso de que la BD retorne None
            sin_pron = stats[1] or 0
            muy_opt = stats[2] or 0
            opt = stats[3] or 0
            real = stats[4] or 0
            pes = stats[5] or 0
            muy_pes = stats[6] or 0

            def calc_pct(val): return (val / total) * 100 if total > 0 else 0

            mensaje = f"📈 *Tendencia de pronóstico: {usuario_seleccionado}*\n"
            mensaje += f"Partidos analizados: _{total}_\n\n"
            
            if muy_opt > 0: mensaje += f"🔴 *Muy optimista:* {calc_pct(muy_opt):.1f}% ({muy_opt})\n"
            if opt > 0:     mensaje += f"🟠 *Optimista:* {calc_pct(opt):.1f}% ({opt})\n"
            if real > 0:    mensaje += f"🟢 *Neutral:* {calc_pct(real):.1f}% ({real})\n"
            if pes > 0:     mensaje += f"🔵 *Pesimista:* {calc_pct(pes):.1f}% ({pes})\n"
            if muy_pes > 0: mensaje += f"🟣 *Muy pesimista:* {calc_pct(muy_pes):.1f}% ({muy_pes})\n"
            if sin_pron > 0: mensaje += f"⚪ *Sin pronóstico:* {calc_pct(sin_pron):.1f}% ({sin_pron})\n"

            await update.message.reply_text(mensaje, parse_mode="Markdown")
            
        # --- LÓGICA ESPECÍFICA PARA "GRADO DE FIRMEZA" ---
        elif tipo_grafico == "firmeza_pronostico":
            stats = self.db.obtener_estadisticas_firmeza_pronostico(usuario_seleccionado, edicion_id, anio)
            
            if not stats or stats[0] == 0:
                await update.message.reply_text("ℹ️ No hay datos suficientes para generar el reporte de este usuario.")
                context.user_data.clear()
                await self.mostrar_menu(update, context)
                return ConversationHandler.END

            total = stats[0]
            sin_pron = stats[1] or 0
            firme = stats[2] or 0
            dudoso = stats[3] or 0
            cambiante = stats[4] or 0

            def calc_pct(val): return (val / total) * 100 if total > 0 else 0

            mensaje = f"🧱 *Grado de firmeza: {usuario_seleccionado}*\n"
            mensaje += f"Partidos analizados: _{total}_\n\n"
            
            if firme > 0:     mensaje += f"🟢 *Firme (1 intento):* {calc_pct(firme):.1f}% ({firme})\n"
            if dudoso > 0:    mensaje += f"🟡 *Dudoso (2 intentos):* {calc_pct(dudoso):.1f}% ({dudoso})\n"
            if cambiante > 0: mensaje += f"🔴 *Cambiante (3+ intentos):* {calc_pct(cambiante):.1f}% ({cambiante})\n"
            if sin_pron > 0:  mensaje += f"⚪ *No participativo:* {calc_pct(sin_pron):.1f}% ({sin_pron})\n"

            await update.message.reply_text(mensaje, parse_mode="Markdown")

        botones = [
            ["🔙 Atrás"],
            ["🔙 Volver al menú principal"]
        ]
        
        await update.message.reply_text(
            "Elegí una opción para continuar:",
            reply_markup=ReplyKeyboardMarkup(botones, resize_keyboard=True)
        )

        return self.esperando_accion_perfil 

    async def iniciar_grafico_perfil_generico(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """PASO 1 Genérico: Identifica el gráfico elegido y pregunta si es Histórico o por Torneo."""
        texto_boton = update.message.text.strip()
        
        if texto_boton == "1_ Estilo de pronóstico":
            context.user_data['tipo_grafico_perfil'] = 'estilo_pronostico'
        elif texto_boton == "2_ Tendencia de pronóstico":
            context.user_data['tipo_grafico_perfil'] = 'tendencia_pronostico'
        # 🌟 NUEVO BLOQUE: Detectamos el botón 3
        elif texto_boton == "3_ Grado de firmeza":
            context.user_data['tipo_grafico_perfil'] = 'firmeza_pronostico'
            
        tipo_grafico = context.user_data.get('tipo_grafico_perfil', 'estilo_pronostico')
        
        if tipo_grafico == 'estilo_pronostico':
            titulo = "📊 *Estilo de pronóstico*"
        elif tipo_grafico == 'tendencia_pronostico':
            titulo = "📈 *Tendencia de pronóstico*"
        # 🌟 NUEVO BLOQUE: Seteamos el título
        elif tipo_grafico == 'firmeza_pronostico':
            titulo = "🧱 *Grado de firmeza*"
        else:
            titulo = "👥 *Perfil de la comunidad*"
            
        botones = [["Histórico", "Por Torneo"], ["🔙 Atrás", "🔙 Volver al menú principal"]]
        
        await update.message.reply_text(
            f"{titulo}\n\n¿Querés ver los datos de toda la historia o de un torneo en particular?",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(botones, resize_keyboard=True)
        )
        return self.esperando_tipo_perfil

    async def preguntar_tiempo_perfil(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """PASO 2: Bifurca. Si es Histórico, salta al usuario. Si es Torneo, muestra la lista."""
        opcion = update.message.text

        if opcion == "Histórico":
            context.user_data['perfil_edicion_id'] = None
            context.user_data['perfil_anio'] = None
            # Salto directo al paso del usuario
            return await self.preguntar_usuario_perfil(update, context)
        
        elif opcion == "Por Torneo":
            # Usamos tu generador de botones de ediciones (solo torneos, sin 'Histórico')
            botones = self._generar_botones_ediciones(incluir_historico=False)
            await update.message.reply_text(
                "🏆 *Seleccioná el Torneo*",
                reply_markup=ReplyKeyboardMarkup(botones, resize_keyboard=True)
            )
            return self.esperando_edicion_perfil
        
        return self.esperando_tipo_perfil

    async def procesar_edicion_perfil(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """PASO 2b: Guarda el torneo elegido y pasa a preguntar el usuario."""
        texto_edicion = update.message.text
        
        # 1. Buscamos el ID numérico que corresponde al texto del botón
        ediciones = self.db.obtener_ediciones()
        edicion_id_real = None
        
        for ed in ediciones:
            # ed[0] es ID, ed[1] es el nombre (ej. LPF), ed[2] es el año
            if f"{ed[1]} {ed[2]}" == texto_edicion:
                edicion_id_real = ed[0]
                break
                
        # 2. Guardamos el ID real en la memoria, no el texto
        context.user_data['perfil_edicion_id'] = edicion_id_real 
        context.user_data['perfil_anio'] = None
        
        return await self.preguntar_usuario_perfil(update, context)

    async def preguntar_usuario_perfil(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """PASO 3 (Genérico): Pregunta por 'Yo' o el resto de la comunidad."""
        id_telegram = update.effective_user.id
        usuario_actual = self.db.obtener_usuario_por_telegram(id_telegram)
        
        # Obtenemos todos los usuarios de la base de datos (lista de tuplas: [(id, username), ...])
        usuarios_db = self.db.obtener_usuarios_con_id()
        
        botones = []
        
        # Primero el botón "Yo" para el usuario que está operando
        if usuario_actual:
            botones.append([f"Yo ({usuario_actual})"])
            
        # Armamos los botones de los demás usuarios de a dos por fila
        fila_temp = []
        for u in usuarios_db:
            nombre_u = u[1] # Índice 1 porque la BD devuelve (id, username)
            
            # Solo agregamos si el nombre es distinto al "Yo" actual
            if str(nombre_u).strip().lower() != str(usuario_actual).strip().lower():
                fila_temp.append(nombre_u)
                
                # Cuando completamos una fila de 2, la agregamos a la matriz principal
                if len(fila_temp) == 2:
                    botones.append(fila_temp)
                    fila_temp = []
                    
        # Si quedó un usuario "suelto" en la última fila impar, lo agregamos ahora
        if fila_temp:
            botones.append(fila_temp)
            
        # Agregamos los botones de navegación al final
        botones.append(["🔙 Atrás", "🔙 Volver al menú principal"])
        
        await update.message.reply_text(
            "👤 ¿De qué usuario querés ver el reporte?", 
            reply_markup=ReplyKeyboardMarkup(botones, resize_keyboard=True)
        )
        return self.esperando_usuario_perfil

    async def forzar_actualizacion_cronometros(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Borra todas las alarmas programadas y las vuelve a crear desde la DB."""
        # Solo el admin puede disparar esto (Seguridad)
        id_telegram = update.effective_user.id
        if self.db.obtener_usuario_por_telegram(id_telegram) != "Gabriel":
            return

        # 1. Buscamos y borramos todos los jobs con el nombre que definimos
        jobs_actuales = context.job_queue.get_jobs_by_name("recordatorio_partido")
        for job in jobs_actuales:
            job.schedule_removal()
            
        # 2. Volvemos a leer la DB y programar todo de cero
        self._programar_cronometros_partidos()
        
        await update.message.reply_text("✅ Agenda de cronómetros actualizada correctamente.")
    
    async def iniciar_admin_archivos(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Busca y muestra exclusivamente los archivos de log disponibles para leer."""
        # Detectamos la ruta (Script o EXE)
        if getattr(sys, 'frozen', False):
            carpeta = sys._MEIPASS
        else:
            carpeta = os.path.dirname(os.path.abspath(__file__))
            
        # 🌟 CAMBIO: Definimos estrictamente los 3 archivos permitidos
        archivos_permitidos = ["logs_bot.txt", "logs_errores_bot.txt", "logs_estadisticas_bot.txt"]
        
        # Filtramos para mostrar solo los que realmente se han creado (existen en la carpeta)
        archivos_txt = [f for f in archivos_permitidos if os.path.exists(os.path.join(carpeta, f))]
        
        if not archivos_txt:
            await update.message.reply_text("📂 No hay archivos de registro (logs) generados en este momento para leer.")
            return await self.iniciar_administracion(update, context)
            
        botones = [[f] for f in archivos_txt]
        botones.append(["🔙 Atrás", "🔙 Volver al menú principal"])
        
        # Guardamos la carpeta en la memoria para seguridad de la lectura
        context.user_data['carpeta_archivos'] = carpeta
        
        await update.message.reply_text(
            "📂 *Lectura de Archivos de Log*\n\n"
            "⚠️ *ATENCIÓN:* Una vez leído, el archivo será **ELIMINADO AUTOMÁTICAMENTE** del servidor.\n\n"
            "Seleccioná el archivo que querés revisar:",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(botones, resize_keyboard=True)
        )
        return self.esperando_archivo_a_leer

    async def procesar_archivo_a_leer(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Lee el archivo, envía el contenido (paginado si es largo) y lo destruye."""
        nombre_archivo = update.message.text.strip()
        carpeta = context.user_data.get('carpeta_archivos')
        
        if not carpeta or not nombre_archivo.endswith('.txt'):
            await update.message.reply_text("❌ Archivo inválido. Usa los botones para seleccionar un archivo.")
            return self.esperando_archivo_a_leer
            
        ruta_archivo = os.path.join(carpeta, nombre_archivo)
        
        if not os.path.exists(ruta_archivo):
            await update.message.reply_text("❌ El archivo ya no existe (probablemente ya fue leído y eliminado).")
            return await self.iniciar_admin_archivos(update, context)
            
        try:
            with open(ruta_archivo, 'r', encoding='utf-8') as f:
                contenido = f.read()
                
            if not contenido.strip():
                await update.message.reply_text(f"📄 El archivo *{nombre_archivo}* se encuentra completamente **vacío**.", parse_mode="Markdown")
            else:
                # Si el archivo tiene texto, lo fraccionamos para no chocar con el límite de Telegram
                mensajes = []
                bloque_actual = ""
                
                # Leemos línea por línea para evitar cortar frases a la mitad
                for linea in contenido.splitlines(True):
                    if len(bloque_actual) + len(linea) > 3800:
                        mensajes.append(bloque_actual)
                        bloque_actual = linea
                    else:
                        bloque_actual += linea
                        
                if bloque_actual:
                    mensajes.append(bloque_actual)
                    
                await update.message.reply_text(f"📄 *Contenido de {nombre_archivo}:*", parse_mode="Markdown")
                
                # Enviamos el contenido dentro de bloques de código (monospaciado) para mejor lectura
                for m in mensajes:
                    await update.message.reply_text(f"```\n{m}\n```", parse_mode="Markdown")
            
            # Destrucción final del archivo
            os.remove(ruta_archivo)
            await update.message.reply_text(f"🗑️ El archivo *{nombre_archivo}* fue leído y **eliminado exitosamente** del sistema.", parse_mode="Markdown")
            
        except Exception as e:
            await update.message.reply_text(f"❌ Error interno al intentar leer o borrar el archivo: {e}")
            
        # Volvemos a mostrar la lista de archivos restantes (o regresa al panel si no queda ninguno)
        return await self.iniciar_admin_archivos(update, context)

    def run(self):
        """Lanza el bot."""
        print("Bot escuchando...")
        self.app.run_polling()

# --- BLOQUE PRINCIPAL ---
if __name__ == '__main__':
    print("Iniciando Sistema de Robot...")
    bot = RobotTelegram()
    bot.run()