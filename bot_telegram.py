import os
import random
import datetime
from datetime import timedelta
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
        esperando_tipo_opt_pes, esperando_edicion_opt_pes,
        esperando_tipo_mayores_errores, esperando_edicion_mayores_errores,
        esperando_tipo_falso_profeta, esperando_edicion_falso_profeta,
        esperando_menu_estadisticas, 
        esperando_tipo_estilo_decision, esperando_edicion_estilo_decision,
        esperando_tipo_mufa, esperando_edicion_mufa,
        esperando_tipo_mejor_predictor, esperando_edicion_mejor_predictor,
        esperando_tipo_racha_record, esperando_edicion_racha_record,
        esperando_tipo_racha_actual, esperando_edicion_racha_actual,
        esperando_tipo_cambios, esperando_edicion_cambios,
        esperando_menu_rankings, esperando_menu_perfil,
        esperando_tipo_perfil,
        esperando_edicion_perfil, esperando_usuario_perfil
    ) = range(1, 34)

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

    # --- MÉTODOS PRIVADOS DE CONFIGURACIÓN ---

    def _setup_handlers(self):
        """Configura todos los comandos y manejadores de conversación."""
        conv_handler = ConversationHandler(
            entry_points=[
                MessageHandler(filters.Regex("^1_ Asociar cuenta$"), self.iniciar_asociacion),
                MessageHandler(filters.Regex("^1_ Cargar pronóstico$"), self.iniciar_carga_pronostico),
                MessageHandler(filters.Regex("^2_ Ver Estadísticas$"), self.iniciar_ver_estadisticas)
            ],
            states={
                # --- NUEVA RAÍZ DE ESTADÍSTICAS ---
                self.esperando_menu_estadisticas: [
                    MessageHandler(filters.Regex("^1_ Rankings$"), self.iniciar_menu_rankings),
                    MessageHandler(filters.Regex("^2_ Perfil de la comunidad$"), self.iniciar_menu_perfil),
                    MessageHandler(filters.Regex("^🔙 Volver al menú principal$"), self.mostrar_menu)
                ],

                # --- SUBMENÚ: RANKINGS ---
                self.esperando_menu_rankings: [
                    MessageHandler(filters.Regex("^1_ Ver posiciones$"), self._crear_iniciar("🏆 *Tabla de Posiciones*\n\n¿Qué posiciones querés ver?", self.esperando_tipo_tabla)),
                    MessageHandler(filters.Regex("^2_ Consultar pronósticos$"), self._crear_iniciar("👀 *Consultar Pronósticos*\n\n¿Qué querés consultar?", self.esperando_tipo_pronosticos)),
                    MessageHandler(filters.Regex("^3_ Optimismo/Pesimismo$"), self._crear_iniciar("☯️ *Optimismo/Pesimismo*\n\n¿Qué datos querés consultar?", self.esperando_tipo_opt_pes)),
                    MessageHandler(filters.Regex("^4_ Mayores errores$"), self._crear_iniciar("📉 *Mayores Errores*\n\n¿Qué datos querés consultar?", self.esperando_tipo_mayores_errores)),
                    MessageHandler(filters.Regex("^5_ Ranking Falso Profeta$"), self._crear_iniciar("🤥 *Falso Profeta*\n\n¿Qué datos querés consultar?", self.esperando_tipo_falso_profeta)),
                    MessageHandler(filters.Regex("^6_ Estilos de decisión$"), self._crear_iniciar("🧠 *Estilos de Decisión*\n\n¿Qué datos querés consultar?", self.esperando_tipo_estilo_decision)),
                    MessageHandler(filters.Regex("^7_ Ranking mufas$"), self._crear_iniciar("🐈‍⬛ *Ranking Mufas*\n\n¿Qué datos querés consultar?", self.esperando_tipo_mufa)),
                    MessageHandler(filters.Regex("^8_ Mejor predictor$"), self._crear_iniciar("🎯 *Mejor Predictor*\n\n¿Qué datos querés consultar?", self.esperando_tipo_mejor_predictor)),
                    MessageHandler(filters.Regex("^9_ Racha récord$"), self._crear_iniciar("🔥 *Racha Récord*\n\n¿Qué datos querés consultar?", self.esperando_tipo_racha_record)),
                    MessageHandler(filters.Regex("^10_ Racha actual$"), self._crear_iniciar("⏳ *Racha Actual*\n\n¿Qué datos querés consultar?", self.esperando_tipo_racha_actual)),
                    MessageHandler(filters.Regex("^11_ Cambio de pronósticos$"), self._crear_iniciar("🔄 *Estabilidad de Pronósticos*\n\n¿Qué datos querés consultar?", self.esperando_tipo_cambios)),
                    
                    MessageHandler(filters.Regex("^🔙 Atrás$"), self.iniciar_ver_estadisticas),
                    MessageHandler(filters.Regex("^🔙 Volver al menú principal$"), self.mostrar_menu)
                ],
                
                # --- FLUJOS BASE (Se mantienen igual) ---
                self.esperando_identificador: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.procesar_identificador)],
                self.esperando_codigo: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.procesar_codigo)],
                self.esperando_partido_id: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.procesar_partido_id)],
                self.esperando_pronostico: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.procesar_pronostico)],

                # --- FLUJOS GENÉRICOS ---
                # 1. Posiciones
                self.esperando_tipo_tabla: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._crear_procesar_tipo(self.imprimir_tabla, self.esperando_tipo_tabla, self.esperando_edicion_tabla, 'dicc_posiciones'))],
                self.esperando_edicion_tabla: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._crear_procesar_edicion(self.imprimir_tabla, self.esperando_edicion_tabla, 'dicc_posiciones'))],
                
                # 2. Consultar pronósticos (Acá el puente de imprimir es preguntar_usuario)
                self.esperando_tipo_pronosticos: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._crear_procesar_tipo(self.preguntar_usuario_pronosticos, self.esperando_tipo_pronosticos, self.esperando_edicion_pronosticos, 'dicc_pronosticos'))],
                self.esperando_edicion_pronosticos: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._crear_procesar_edicion(self.preguntar_usuario_pronosticos, self.esperando_edicion_pronosticos, 'dicc_pronosticos'))],
                self.esperando_usuario_pronosticos: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.imprimir_pronosticos)],
                
                # 3. Optimismo/Pesimismo
                self.esperando_tipo_opt_pes: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._crear_procesar_tipo(self.imprimir_tabla_opt_pes, self.esperando_tipo_opt_pes, self.esperando_edicion_opt_pes, 'dicc_opt_pes'))],
                self.esperando_edicion_opt_pes: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._crear_procesar_edicion(self.imprimir_tabla_opt_pes, self.esperando_edicion_opt_pes, 'dicc_opt_pes'))],
                
                # 4. Mayores Errores (Usa solo_finalizados=True)
                self.esperando_tipo_mayores_errores: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._crear_procesar_tipo(self.imprimir_tabla_mayores_errores, self.esperando_tipo_mayores_errores, self.esperando_edicion_mayores_errores, 'dicc_errores', solo_finalizados=True))],
                self.esperando_edicion_mayores_errores: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._crear_procesar_edicion(self.imprimir_tabla_mayores_errores, self.esperando_edicion_mayores_errores, 'dicc_errores'))],
                
                # 5. Falso Profeta
                self.esperando_tipo_falso_profeta: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._crear_procesar_tipo(self.imprimir_tabla_falso_profeta, self.esperando_tipo_falso_profeta, self.esperando_edicion_falso_profeta, 'dicc_fp'))],
                self.esperando_edicion_falso_profeta: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._crear_procesar_edicion(self.imprimir_tabla_falso_profeta, self.esperando_edicion_falso_profeta, 'dicc_fp'))],
                
                # 6. Estilos de Decisión
                self.esperando_tipo_estilo_decision: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._crear_procesar_tipo(self.imprimir_tabla_estilo_decision, self.esperando_tipo_estilo_decision, self.esperando_edicion_estilo_decision, 'dicc_estilos'))],
                self.esperando_edicion_estilo_decision: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._crear_procesar_edicion(self.imprimir_tabla_estilo_decision, self.esperando_edicion_estilo_decision, 'dicc_estilos'))],
                
                # 7. Ranking Mufa
                self.esperando_tipo_mufa: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._crear_procesar_tipo(self.imprimir_tabla_mufa, self.esperando_tipo_mufa, self.esperando_edicion_mufa, 'dicc_mufa'))],
                self.esperando_edicion_mufa: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._crear_procesar_edicion(self.imprimir_tabla_mufa, self.esperando_edicion_mufa, 'dicc_mufa'))],
                
                # 8. Mejor Predictor
                self.esperando_tipo_mejor_predictor: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._crear_procesar_tipo(self.imprimir_tabla_mejor_predictor, self.esperando_tipo_mejor_predictor, self.esperando_edicion_mejor_predictor, 'dicc_predictor', solo_finalizados=True))],
                self.esperando_edicion_mejor_predictor: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._crear_procesar_edicion(self.imprimir_tabla_mejor_predictor, self.esperando_edicion_mejor_predictor, 'dicc_predictor'))],
                
                # 9. Racha Récord
                self.esperando_tipo_racha_record: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._crear_procesar_tipo(self.imprimir_tabla_racha_record, self.esperando_tipo_racha_record, self.esperando_edicion_racha_record, 'dicc_racha', solo_finalizados=True))],
                self.esperando_edicion_racha_record: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._crear_procesar_edicion(self.imprimir_tabla_racha_record, self.esperando_edicion_racha_record, 'dicc_racha'))],

                # 10. Racha Actual
                self.esperando_tipo_racha_actual: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._crear_procesar_tipo(self.imprimir_tabla_racha_actual, self.esperando_tipo_racha_actual, self.esperando_edicion_racha_actual, 'dicc_racha_actual', solo_finalizados=True))],
                self.esperando_edicion_racha_actual: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._crear_procesar_edicion(self.imprimir_tabla_racha_actual, self.esperando_edicion_racha_actual, 'dicc_racha_actual'))],

                # 11. Cambios de Pronósticos
                self.esperando_tipo_cambios: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._crear_procesar_tipo(self.imprimir_tabla_cambios, self.esperando_tipo_cambios, self.esperando_edicion_cambios, 'dicc_cambios', solo_finalizados=True))],
                self.esperando_edicion_cambios: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._crear_procesar_edicion(self.imprimir_tabla_cambios, self.esperando_edicion_cambios, 'dicc_cambios'))],

                # --- FLUJO PERFIL DE COMUNIDAD (CASCADA) ---
                self.esperando_menu_perfil: [
                    MessageHandler(filters.Regex("^1_ Estilo de pronóstico$"), self.setear_grafico_estilo),
                    MessageHandler(filters.Regex("^🔙 Atrás$"), self.iniciar_ver_estadisticas)
                ],

                self.esperando_tipo_perfil: [
                    MessageHandler(filters.Regex("^Histórico$|^Por Torneo$"), self.preguntar_tiempo_perfil),
                    MessageHandler(filters.Regex("^🔙 Atrás$"), self.iniciar_menu_perfil)
                ],

                self.esperando_edicion_perfil: [
                    MessageHandler(filters.Regex("^🔙 Atrás$"), self.setear_grafico_estilo),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.procesar_edicion_perfil)
                ],

                self.esperando_usuario_perfil: [
                    MessageHandler(filters.Regex("^🔙 Atrás$"), self.setear_grafico_estilo),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.calcular_y_mostrar_grafico_perfil)
                ],
            },
            fallbacks=[CommandHandler("cancelar", self.cancelar_conversacion)],
        )
        self.app.add_handler(CommandHandler("actualizar_cronometros", self.forzar_actualizacion_cronometros))
        self.app.add_handler(CommandHandler("start", self.mostrar_menu))
        self.app.add_handler(conv_handler)
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.mostrar_menu))

    def _programar_cronometros_partidos(self):
        """Busca partidos futuros y crea alarmas con nombre para poder resetearlas."""
        partidos = self.db.obtener_partidos_futuros_crudo()
        if not partidos: return
        
        zona_horaria = pytz.timezone('America/Argentina/Buenos_Aires')
        ahora = datetime.datetime.now(zona_horaria)
        
        for p_id, rival, fecha in partidos:
            fecha_local = zona_horaria.localize(fecha)
            horas_aviso = [96, 48, 24, 1]
            
            for horas in horas_aviso:
                fecha_alarma = fecha_local - timedelta(hours=horas)
                if fecha_alarma > ahora:
                    self.app.job_queue.run_once(
                        self._disparar_recordatorio, 
                        when=fecha_alarma, 
                        data={'partido_id': p_id, 'rival': rival, 'fecha': fecha_local, 'horas': horas},
                        name="recordatorio_partido" # 🌟 NOMBRE CLAVE PARA BORRARLAS
                    )
        print("⏰ Cronómetros configurados.")

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
                await context.bot.send_message(chat_id=tg_id, text=mensaje, parse_mode="Markdown", reply_markup=teclado)
            except Exception as e:
                print(f"No se pudo avisar a {username}: {e}")

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
            botones = [["1_ Cargar pronóstico"], ["2_ Ver Estadísticas"]]
            mensaje = f"¡Hola {username}! Bienvenido al Prode. 🔴"
        else:
            botones = [["1_ Asociar cuenta"]]
            mensaje = "¡Hola! Bienvenido. Primero vinculá tu cuenta:"
            
        await update.message.reply_text(mensaje, reply_markup=ReplyKeyboardMarkup(botones, resize_keyboard=True))
        return ConversationHandler.END

    async def iniciar_ver_estadisticas(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Menú principal de estadísticas (Raíz)."""
        botones = [
            ["1_ Rankings", "2_ Perfil de la comunidad"],
            ["🔙 Volver al menú principal"]
        ]
        await update.message.reply_text("📊 *Panel de Estadísticas*\n\nElegí una categoría para explorar:", parse_mode="Markdown", 
                                       reply_markup=ReplyKeyboardMarkup(botones, resize_keyboard=True))
        return self.esperando_menu_estadisticas

    async def iniciar_menu_rankings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Submenú con todos los rankings actuales."""
        botones = [
            ["1_ Ver posiciones", "2_ Consultar pronósticos"],
            ["3_ Optimismo/Pesimismo", "4_ Mayores errores"],
            ["5_ Ranking Falso Profeta", "6_ Estilos de decisión"],
            ["7_ Ranking mufas", "8_ Mejor predictor"],
            ["9_ Racha récord", "10_ Racha actual"],
            ["11_ Cambio de pronósticos"],
            ["🔙 Atrás", "🔙 Volver al menú principal"]
        ]
        await update.message.reply_text("🏆 *Rankings del Prode*\n\nSeleccioná un ranking para consultar:", parse_mode="Markdown", 
                                       reply_markup=ReplyKeyboardMarkup(botones, resize_keyboard=True))
        return self.esperando_menu_rankings

    async def iniciar_menu_perfil(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Submenú para los gráficos y porcentajes con explicación detallada."""
        botones = [
            ["1_ Estilo de pronóstico"],
            ["🔙 Atrás", "🔙 Volver al menú principal"]
        ]
        
        # Armamos el mensaje con la explicación de cada botón
        mensaje = (
            "👥 *Perfil de la comunidad*\n\n"
            "Elegí qué estadísticas querés ver:\n\n"
            "📊 *1_ Estilo de pronóstico:* Desglosa tus predicciones mostrando el porcentaje "
            "de veces que pronosticaste victoria, empate o derrota del Rojo."
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
        """Paso 1: Valida al usuario y muestra la lista de partidos futuros."""
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
        
        # 🌟 CAMBIO: En lugar de guardar solo los IDs, guardamos un diccionario con el nombre del rival y la localía
        partidos_info = {}
        
        for p in partidos_futuros:
            p_id = p[0]
            rival = p[1]
            torneo = p[3]
            fecha_display = p[7]
            condicion = p[12]
            pred_cai = p[8]
            pred_rival = p[9]
            
            # Guardamos la info en la memoria de este partido
            partidos_info[str(p_id)] = {'rival': rival, 'condicion': condicion}
            
            # Formateamos el texto dependiendo de si Independiente es visitante o local (-1 o 1)
            if condicion == -1:
                partido_str = f"{rival} vs Independiente"
                # Formateamos el pronóstico previo si es que existe
                if pred_cai is not None:
                    txt_previo = f"{rival} {pred_rival} - {pred_cai} Independiente"
            else:
                partido_str = f"Independiente vs {rival}"
                if pred_cai is not None:
                    txt_previo = f"Independiente {pred_cai} - {pred_rival} {rival}"
                
            mensaje += f"🔹 *ID: {p_id}* | {partido_str}\n"
            mensaje += f"🏆 {torneo} | 🗓️ {fecha_display}\n"
            
            # 🌟 CAMBIO: Ahora el pronóstico actual muestra el nombre real
            if pred_cai is not None:
                mensaje += f"👉 _Tu pronóstico actual: {txt_previo}_\n"
            else:
                mensaje += "👉 _Sin pronóstico cargado_\n"
                
            mensaje += "—\n"
            
        mensaje += "\n✍️ Respondé con el *NÚMERO DE ID* del partido que querés pronosticar (o escribí /cancelar):"
        
        # Guardamos el diccionario completo en la memoria del usuario
        context.user_data['partidos_info'] = partidos_info
        
        await update.message.reply_text(mensaje, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
        return self.esperando_partido_id

    async def procesar_partido_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Paso 2: Valida el ID y le pide el resultado."""
        texto = update.message.text.strip()
        partidos_info = context.user_data.get('partidos_info', {})
        
        if texto not in partidos_info:
            await update.message.reply_text(
                "❌ Ese ID no es válido o el partido ya no pertenece al futuro.\n"
                "Intentá de nuevo con un ID de la lista o escribí /cancelar."
            )
            return self.esperando_partido_id
            
        context.user_data['partido_id_elegido'] = int(texto)
        # 🌟 CAMBIO: Separamos la info específica del partido que acaba de elegir
        context.user_data['info_partido_elegido'] = partidos_info[texto]
        
        await update.message.reply_text(
            "⚽ *¡Excelente!*\n\n"
            "Ahora escribí tu pronóstico con el formato *GolesCAI-GolesRival*.\n"
            "Ejemplo: *2-0* o *1-1*\n\n"
            "_(Recordá que siempre el primer número corresponde a Independiente)_",
            parse_mode="Markdown"
        )
        return self.esperando_pronostico

    async def procesar_pronostico(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Paso 3: Guarda el resultado en la base de datos."""
        texto = update.message.text.strip()
        partido_id = context.user_data.get('partido_id_elegido')
        username = context.user_data.get('username_pronostico')
        
        # 🌟 CAMBIO: Recuperamos la info del partido para usar el nombre real
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
            
            # 🌟 CAMBIO: Armamos el texto final respetando quién es local y quién visitante
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

    async def imprimir_tabla(self, update: Update, context: ContextTypes.DEFAULT_TYPE, edicion_id, titulo):
        """Función de apoyo: Dibuja la tabla en formato texto incluyendo a los que no jugaron."""
        # 1. Obtenemos el ranking de los que tienen puntos
        ranking = self.db.obtener_ranking(edicion_id=edicion_id)
        
        # 2. Obtenemos la lista completa de todos los usuarios del sistema
        todos_los_usuarios = self.db.obtener_usuarios()
        
        # 3. Identificamos quiénes sí tienen puntos en esta tabla
        usuarios_con_puntos = [row[0] for row in ranking]
        
        # 4. Filtramos para encontrar a los que no tienen ningún pronóstico en este contexto
        usuarios_sin_pronosticos = [u for u in todos_los_usuarios if u not in usuarios_con_puntos]
        
        if not ranking and not usuarios_sin_pronosticos:
            await update.message.reply_text("📉 Todavía no hay usuarios registrados en el sistema.")
            # 🌟 CAMBIO: Agregado self.
            await self.mostrar_menu(update, context)
            return ConversationHandler.END
            
        mensaje = f"🏆 *Tabla de Posiciones: {titulo}* 🏆\n\n"
        
        # Dibujamos la tabla de los que puntuaron
        if ranking:
            for i, row in enumerate(ranking):
                username = row[0]
                puntos = row[1]
                pj = row[5]
                
                # 🌟 CAMBIO: Agregado self. y el guion bajo
                ant_str = self._formatear_anticipacion(row[6])
                
                # Cast seguro para el error promedio
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

        # Mostrar a los que no pronosticaron nada
        if usuarios_sin_pronosticos:
            # Los unimos con comas para que no ocupe tanto espacio vertical
            lista_nombres = ", ".join(usuarios_sin_pronosticos)
            mensaje += f"🚫 *Últimos (Sin pronósticos):*\n_{lista_nombres}_"
            
        # Enviamos el mensaje final
        await update.message.reply_text(mensaje, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
        
        # 🌟 CAMBIO: Agregado self.
        await self.mostrar_menu(update, context)
        return ConversationHandler.END

    # ==========================================
    # FLUJO 4: CONSULTAR PRONÓSTICOS
    # ==========================================
    async def preguntar_usuario_pronosticos(self, update: Update, context: ContextTypes.DEFAULT_TYPE, edicion_id, titulo):
        """Actúa como 'funcion_imprimir' puente: pregunta de quién ver los pronósticos antes de imprimirlos."""
        # Guardamos el título del torneo (o 'Histórica') para usarlo en el siguiente paso
        context.user_data['torneo_elegido_pronosticos'] = titulo

        id_telegram = update.message.from_user.id
        username_propio = self.db.obtener_usuario_por_telegram(id_telegram)
        usuarios = self.db.obtener_usuarios()

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

            bloque = ""
            if target_user == "todos":
                bloque += f"👤 *{user}*\n"
                
            bloque += f"⚽ vs {rival} | 📅 {fecha_partido}\n"
            bloque += f"👉 *Independiente {pred_cai} - {pred_rival} {rival}*\n"
            bloque += f"⏱️ _Cargado el: {fecha_pred}_\n"
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
        datos = self.db.obtener_indice_optimismo_pesimismo(edicion_id=edicion_id)
        
        if not datos:
            await update.message.reply_text("📉 Todavía no hay datos de optimismo/pesimismo para esta selección.")
            # 🌟 CAMBIO: Agregado self.
            await self.mostrar_menu(update, context)
            return ConversationHandler.END
            
        # 🌟 CAMBIO: Se agrega el texto explicativo debajo del título
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
            
        await update.message.reply_text(mensaje, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
        
        # 🌟 CAMBIO: Agregado self.
        await self.mostrar_menu(update, context)
        return ConversationHandler.END
    
    # ==========================================
    # FLUJO 6: MAYORES ERRORES
    # ==========================================
    async def imprimir_tabla_mayores_errores(self, update: Update, context: ContextTypes.DEFAULT_TYPE, edicion_id, titulo):
        datos = self.db.obtener_ranking_mayores_errores(edicion_id=edicion_id)
        
        if not datos:
            await update.message.reply_text("📉 Todavía no hay datos de errores para esta selección.")
            # 🌟 CAMBIO: Agregado self.
            await self.mostrar_menu(update, context)
            return ConversationHandler.END
            
        mensajes = []
        mensaje_actual = f"📉 *Mayores Errores: {titulo}* 📉\n"
        
        # 🌟 CAMBIO: Usamos self.limite_errores en vez de la variable global suelta
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
            
        # Enviamos los globos de texto secuencialmente
        for m in mensajes:
            await update.message.reply_text(m, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
        
        # 🌟 CAMBIO: Agregado self.
        await self.mostrar_menu(update, context)
        return ConversationHandler.END
    
    # ==========================================
    # FLUJO 7: RANKING FALSO PROFETA
    # ==========================================
    async def imprimir_tabla_falso_profeta(self, update: Update, context: ContextTypes.DEFAULT_TYPE, edicion_id, titulo):
        """Construye y envía el ranking invirtiendo el % de acierto al % de falso profeta."""
        # 🌟 CAMBIO: Acceso a la base de datos vía self.db
        datos = self.db.obtener_ranking_falso_profeta(edicion_id=edicion_id)
        
        if not datos:
            await update.message.reply_text("📉 Todavía no hay suficientes datos para calcular falsos profetas en esta selección.")
            # 🌟 CAMBIO: Uso de self.
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
            
        for m in mensajes:
            await update.message.reply_text(m, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
        
        # 🌟 CAMBIO: Uso de self.
        await self.mostrar_menu(update, context)
        return ConversationHandler.END

    # ==========================================
    # FLUJO 8: ESTILOS DE DECISIÓN
    # ==========================================
    async def imprimir_tabla_estilo_decision(self, update: Update, context: ContextTypes.DEFAULT_TYPE, edicion_id, titulo):
        """Construye y envía el ranking de estilos de decisión."""
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
            
        for m in mensajes:
            await update.message.reply_text(m, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
        
        await self.mostrar_menu(update, context)
        return ConversationHandler.END

    # ==========================================
    # FLUJO 9: RANKING MUFA
    # ==========================================
    async def imprimir_tabla_mufa(self, update: Update, context: ContextTypes.DEFAULT_TYPE, edicion_id, titulo):
        """Construye y envía el ranking Mufa."""
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
            
        for m in mensajes:
            await update.message.reply_text(m, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
        
        await self.mostrar_menu(update, context)
        return ConversationHandler.END

    # ==========================================
    # FLUJO 10: MEJOR PREDICTOR
    # ==========================================
    async def imprimir_tabla_mejor_predictor(self, update: Update, context: ContextTypes.DEFAULT_TYPE, edicion_id, titulo):
        """Construye y envía el ranking de Mejor Predictor basado en error absoluto."""
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
            
        for m in mensajes:
            await update.message.reply_text(m, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
        
        await self.mostrar_menu(update, context)
        return ConversationHandler.END
    
    # ==========================================
    # FLUJO 11: RACHA RÉCORD
    # ==========================================
    async def imprimir_tabla_racha_record(self, update: Update, context: ContextTypes.DEFAULT_TYPE, edicion_id, titulo):
        """Construye y envía el ranking de Racha Récord."""
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
            
        # Envío de los mensajes
        for m in mensajes:
            await update.message.reply_text(m, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
        
        # Vuelta al menú principal
        await self.mostrar_menu(update, context)
        return ConversationHandler.END

    # ==========================================
    # FLUJO 12: RACHA ACTUAL
    # ==========================================
    async def imprimir_tabla_racha_actual(self, update: Update, context: ContextTypes.DEFAULT_TYPE, edicion_id, titulo):
        """Construye y envía el ranking de Racha Actual."""
        datos = self.db.obtener_racha_actual(edicion_id=edicion_id, anio=None)
        
        if not datos:
            await update.message.reply_text("📉 Todavía no hay datos de rachas para esta selección.")
            await self.mostrar_menu(update, context)
            return ConversationHandler.END
            
        mensajes = []
        mensaje_actual = f"⏳ *Racha Actual: {titulo}* ⏳\n"
        mensaje_actual += "_Cantidad de aciertos exactos consecutivos vigentes al día de hoy._\n\n"
        
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
            
        # Envío de los mensajes
        for m in mensajes:
            await update.message.reply_text(m, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
        
        # Vuelta al menú principal
        await self.mostrar_menu(update, context)
        return ConversationHandler.END
    
    # ==========================================
    # FLUJO 13: ESTABILIDAD DE PRONÓSTICOS
    # ==========================================
    async def imprimir_tabla_cambios(self, update: Update, context: ContextTypes.DEFAULT_TYPE, edicion_id, titulo):
        """Construye y envía el ranking de Estabilidad (Cambios de pronóstico)."""
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
            
            # Control de paginación de Telegram
            if len(mensaje_actual) + len(bloque) > 3800:
                mensajes.append(mensaje_actual)
                mensaje_actual = bloque
            else:
                mensaje_actual += bloque
                
        if mensaje_actual:
            mensajes.append(mensaje_actual)
            
        # Envío secuencial de los globos de texto
        for m in mensajes:
            await update.message.reply_text(m, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
        
        await self.mostrar_menu(update, context)
        return ConversationHandler.END

    async def procesar_edicion_y_preguntar_usuario(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Paso 2: Guarda la edición elegida y arma el teclado con todos los usuarios."""
        texto_edicion = update.message.text
        
        # 1. Guardamos la edición en la memoria temporal
        if texto_edicion == "Histórico":
            context.user_data['perfil_edicion_id'] = None
            context.user_data['perfil_anio'] = None
        else:
            # Aquí podés mapear el nombre del torneo a su ID si lo preferís
            context.user_data['perfil_edicion_id'] = texto_edicion 
            context.user_data['perfil_anio'] = None

        # 2. Identificamos quién está consultando
        id_telegram = update.effective_user.id
        usuario_actual = self.db.obtener_usuario_por_telegram(id_telegram)
        
        # 3. Obtenemos todos los usuarios (id, username) de la tabla usuarios
        usuarios_db = self.db.obtener_usuarios() 
        
        botones = []
        
        # Primero el botón "Yo" para el usuario que está operando
        if usuario_actual:
            botones.append([f"Yo ({usuario_actual})"])
            
        # Armamos los botones de los demás usuarios de a dos por fila
        fila_temp = []
        for u in usuarios_db:
            # u[1] es el username (índice 1 de la tupla devuelta por SELECT id, username)
            nombre_u = u[1] 
            
            # Solo agregamos si el nombre en la BD es distinto al "Yo" actual
            # Usamos strip() por si hay espacios invisibles en la base de datos
            if str(nombre_u).strip().lower() != str(usuario_actual).strip().lower():
                fila_temp.append(nombre_u)
                
                # Cuando completamos una fila de 2, la agregamos a la lista principal
                if len(fila_temp) == 2:
                    botones.append(fila_temp)
                    fila_temp = []
        
        # ⚠️ IMPORTANTE: Si quedó un usuario "suelto" en la última fila, lo agregamos ahora
        if fila_temp:
            botones.append(fila_temp)
            
        # Agregamos los botones de navegación al final
        botones.append(["🔙 Atrás", "🔙 Volver al menú principal"])
        
        # 4. Enviamos el mensaje con el teclado dinámico
        await update.message.reply_text(
            "👤 ¿De qué usuario querés ver el reporte?", 
            reply_markup=ReplyKeyboardMarkup(botones, resize_keyboard=True)
        )
        return self.esperando_usuario_perfil

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

        # Limpiamos la memoria por prolijidad
        context.user_data.clear()
        
        # 🌟 MODIFICACIÓN PRINCIPAL: Volver al menú principal y cerrar el flujo de conversación
        await self.mostrar_menu(update, context)
        return ConversationHandler.END   

    async def setear_grafico_estilo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """PASO 1: Pregunta si quiere ver datos Históricos o por un Torneo específico."""
        context.user_data['tipo_grafico_perfil'] = 'estilo_pronostico' # Identificador del reporte
        
        botones = [["Histórico", "Por Torneo"], ["🔙 Atrás", "🔙 Volver al menú principal"]]
        await update.message.reply_text(
            "📊 *Estilo de pronóstico*\n\n¿Querés ver los datos de toda la historia o de un torneo en particular?",
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
        usuarios_db = self.db.obtener_usuarios()
        
        botones = []
        if usuario_actual:
            botones.append([f"Yo ({usuario_actual})"])
            
        fila = []
        for u in usuarios_db:
            nombre = u[1]
            if str(nombre).strip().lower() != str(usuario_actual).strip().lower():
                fila.append(nombre)
                if len(fila) == 2:
                    botones.append(fila)
                    fila = []
        if fila: botones.append(fila)
            
        botones.append(["🔙 Atrás", "🔙 Volver al menú principal"])
        await update.message.reply_text("👤 ¿De qué usuario querés ver el reporte?", 
                                       reply_markup=ReplyKeyboardMarkup(botones, resize_keyboard=True))
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

    def run(self):
        """Lanza el bot."""
        print("Bot escuchando...")
        self.app.run_polling()

# --- BLOQUE PRINCIPAL ---
if __name__ == '__main__':
    print("Iniciando Sistema de Robot...")
    bot = RobotTelegram()
    bot.run()