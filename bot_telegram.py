import os
import random
import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, 
    filters, ContextTypes, ConversationHandler
)

from base_de_datos import BaseDeDatos

load_dotenv(override=True)
TOKEN = os.getenv("TELEGRAM_TOKEN")
EMAIL_EMISOR = os.getenv("EMAIL_EMISOR")
EMAIL_PASS = os.getenv("EMAIL_PASSWORD")
LIMITE_MAYORES_ERRORES = 10

db = BaseDeDatos()

# Estados de la máquina de conversación
ESPERANDO_IDENTIFICADOR = 1
ESPERANDO_CODIGO = 2
ESPERANDO_PARTIDO_ID = 3
ESPERANDO_PRONOSTICO = 4
ESPERANDO_TIPO_TABLA = 5
ESPERANDO_EDICION_TABLA = 6
ESPERANDO_EDICION_PRONOSTICOS = 7
ESPERANDO_USUARIO_PRONOSTICOS = 8
ESPERANDO_TIPO_OPT_PES = 9
ESPERANDO_EDICION_OPT_PES = 10
ESPERANDO_TIPO_MAYORES_ERRORES = 11
ESPERANDO_EDICION_MAYORES_ERRORES = 12
ESPERANDO_TIPO_FALSO_PROFETA = 13
ESPERANDO_EDICION_FALSO_PROFETA = 14

def enviar_correo_codigo(destinatario, codigo):
    if not EMAIL_EMISOR or not EMAIL_PASS:
        print("❌ Faltan credenciales de email en el .env")
        return False
    try:
        msg = EmailMessage()
        msg['Subject'] = 'Código de Asociación - Prode Independiente 🔴'
        msg['From'] = EMAIL_EMISOR
        msg['To'] = destinatario
        
        cuerpo = (
            f"¡Hola!\n\n"
            f"Alguien ha solicitado asociar tu cuenta del Prode a un dispositivo móvil en Telegram.\n\n"
            f"Tu código de seguridad es: {codigo}\n\n"
            f"Si no fuiste vos, ignorá este mensaje."
        )
        msg.set_content(cuerpo)
        
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(EMAIL_EMISOR, EMAIL_PASS)
            smtp.send_message(msg)
        return True
    except Exception as e:
        print(f"Error enviando correo: {e}")
        return False

async def mostrar_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra un menú dinámico dependiendo de si el usuario está asociado o no."""
    if not update.message:
        return ConversationHandler.END

    id_telegram = update.message.from_user.id
    username = db.obtener_usuario_por_telegram(id_telegram)
    
    if username:
        # 🌟 CAMBIO: Se agrega el sexto botón
        botones = [
            ["1_ Cargar pronóstico", "2_ Ver posiciones"],
            ["3_ Consultar pronósticos", "4_ Optimismo/Pesimismo"],
            ["5_ Mayores errores", "6_ Ranking Falso Profeta"]
        ]
        mensaje = f"¡Hola {username}! Bienvenido de nuevo al Prode. 🔴\n¿Qué querés hacer hoy?"
    else:
        botones = [
            ["1_ Asociar cuenta"]
        ]
        mensaje = "¡Hola! Bienvenido al Prode. 🔴\nPara empezar a jugar, primero necesitás vincular tu cuenta:"
        
    menu = ReplyKeyboardMarkup(botones, resize_keyboard=True)
    await update.message.reply_text(mensaje, reply_markup=menu)
    
    return ConversationHandler.END

async def cancelar_conversacion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Permite al usuario abortar cualquier proceso escribiendo /cancelar."""
    await update.message.reply_text("Operación cancelada.")
    await mostrar_menu(update, context)
    return ConversationHandler.END

# ==========================================
# FLUJO 1: ASOCIAR CUENTA
# ==========================================
async def iniciar_asociacion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔐 *Asociar Cuenta*\n\n"
        "Por favor, escribí tu *Nombre de Usuario* o tu *Correo Electrónico* registrado en el Prode.\n\n"
        "_(Para cancelar escribí /cancelar)_",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove()
    )
    return ESPERANDO_IDENTIFICADOR

async def procesar_identificador(update: Update, context: ContextTypes.DEFAULT_TYPE):
    identificador = update.message.text.strip()
    usuario = db.buscar_usuario_para_asociar(identificador)
    
    if not usuario:
        await update.message.reply_text(
            "❌ No encontré ninguna cuenta con ese usuario o correo.\n"
            "Intentá nuevamente o escribí /cancelar."
        )
        return ESPERANDO_IDENTIFICADOR 
        
    username = usuario['username']
    email_dest = usuario['email']
    
    if not email_dest:
        await update.message.reply_text("❌ Tu cuenta no tiene un email registrado. Contactá al administrador.")
        await mostrar_menu(update, context)
        return ConversationHandler.END

    codigo = str(random.randint(100000, 999999))
    
    if db.guardar_token_recuperacion(username, codigo):
        envio_ok = enviar_correo_codigo(email_dest, codigo)
        
        if envio_ok:
            context.user_data['username_asociar'] = username
            mail_oculto = email_dest[0] + "******" + email_dest[email_dest.find("@"):]
            
            await update.message.reply_text(
                f"✅ ¡Usuario encontrado!\n\n"
                f"Acabo de enviar un código a tu correo: <b>{mail_oculto}</b>\n\n"
                f"Revisá tu bandeja de entrada o Spam y escribí el código aquí:",
                parse_mode="HTML"
            )
            return ESPERANDO_CODIGO
        else:
            await update.message.reply_text("❌ Hubo un problema enviando el correo. Intentá más tarde.")
    else:
        await update.message.reply_text("❌ Error interno generando el token en la base de datos.")
        
    await mostrar_menu(update, context)
    return ConversationHandler.END

async def procesar_codigo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    codigo_ingresado = update.message.text.strip()
    username = context.user_data.get('username_asociar')
    
    if not username:
        await update.message.reply_text("❌ La sesión expiró. Volvé a iniciar el proceso.")
        await mostrar_menu(update, context)
        return ConversationHandler.END

    try:
        db.validar_token_recuperacion(username, codigo_ingresado)
        id_telegram = update.message.from_user.id
        db.actualizar_id_telegram(username, id_telegram)
        
        await update.message.reply_text(
            f"🎉 *¡Éxito!* 🎉\n\n"
            f"Tu Telegram ha quedado vinculado al usuario *{username}*.\n\n"
            f"Ya podés empezar a cargar tus pronósticos.",
            parse_mode="Markdown"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ {e}\nIntentá ingresarlo nuevamente o /cancelar.")
        return ESPERANDO_CODIGO
        
    await mostrar_menu(update, context)
    return ConversationHandler.END


# ==========================================
# FLUJO 2: CARGAR PRONÓSTICO
# ==========================================
async def iniciar_carga_pronostico(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Paso 1: Valida al usuario y muestra la lista de partidos futuros."""
    id_telegram = update.message.from_user.id
    username = db.obtener_usuario_por_telegram(id_telegram)
    
    if not username:
        await update.message.reply_text(
            "❌ *Acceso Denegado*\n\n"
            "Todavía no asociaste tu cuenta del Prode. Por favor, usá la opción *1_ Asociar cuenta* del menú principal primero.", 
            parse_mode="Markdown"
        )
        return ConversationHandler.END
        
    context.user_data['username_pronostico'] = username
    partidos_futuros = db.obtener_partidos(username, filtro_tiempo='futuros')
    
    if not partidos_futuros:
        await update.message.reply_text("⚽ No hay partidos futuros programados en este momento.")
        await mostrar_menu(update, context)
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
    return ESPERANDO_PARTIDO_ID


async def procesar_partido_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Paso 2: Valida el ID y le pide el resultado."""
    texto = update.message.text.strip()
    partidos_info = context.user_data.get('partidos_info', {})
    
    if texto not in partidos_info:
        await update.message.reply_text(
            "❌ Ese ID no es válido o el partido ya no pertenece al futuro.\n"
            "Intentá de nuevo con un ID de la lista o escribí /cancelar."
        )
        return ESPERANDO_PARTIDO_ID
        
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
    return ESPERANDO_PRONOSTICO


async def procesar_pronostico(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        await mostrar_menu(update, context)
        return ConversationHandler.END
        
    try:
        if "-" not in texto:
            raise ValueError()
        
        partes = texto.split("-")
        if len(partes) != 2:
            raise ValueError()
            
        goles_cai = int(partes[0].strip())
        goles_rival = int(partes[1].strip())
        
        fecha_actual = db.obtener_hora_argentina()
        
        # Hacemos el INSERT. Si el usuario lo hace 1000 veces, se guardan 1000 filas
        # pero db.obtener_partidos siempre leerá el de la fecha_actual más grande.
        db.insertar_pronostico(username, partido_id, goles_cai, goles_rival, fecha_actual)
        
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
        return ESPERANDO_PRONOSTICO
    except Exception as e:
        await update.message.reply_text(f"❌ Error en la base de datos: {e}\nIntentá de nuevo o /cancelar.")
        return ESPERANDO_PRONOSTICO
        
    await mostrar_menu(update, context)
    return ConversationHandler.END

# ==========================================
# FLUJO 3: VER TABLA DE POSICIONES
# ==========================================
async def iniciar_ver_posiciones(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Paso 1: Pregunta qué tipo de tabla quiere ver."""
    id_telegram = update.message.from_user.id
    if not db.obtener_usuario_por_telegram(id_telegram):
        await update.message.reply_text("❌ Tenés que asociar tu cuenta primero.")
        return ConversationHandler.END

    botones = [
        ["1_ Histórica"],
        ["2_ Por Torneo"],
        ["🔙 Volver al menú"]
    ]
    await update.message.reply_text(
        "📊 *Tabla de Posiciones*\n\n¿Qué ranking querés consultar?",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(botones, resize_keyboard=True)
    )
    return ESPERANDO_TIPO_TABLA

async def procesar_tipo_tabla(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Paso 2: Evalúa si muestra la histórica o pide elegir un torneo."""
    texto = update.message.text.strip()
    
    if texto == "🔙 Volver al menú":
        await mostrar_menu(update, context)
        return ConversationHandler.END
        
    if texto == "1_ Histórica":
        return await imprimir_tabla(update, context, edicion_id=None, titulo="Histórica")
        
    elif texto == "2_ Por Torneo":
        ediciones = db.obtener_ediciones()
        if not ediciones:
            await update.message.reply_text("❌ No hay torneos registrados todavía.")
            await mostrar_menu(update, context)
            return ConversationHandler.END
            
        botones = []
        diccionario_ediciones = {}
        
        # Creamos un botón por cada torneo existente
        for ed in ediciones:
            id_edicion = ed[0]
            nombre_completo = f"{ed[1]} {ed[2]}"
            botones.append([nombre_completo])
            diccionario_ediciones[nombre_completo] = id_edicion
            
        botones.append(["🔙 Volver al menú"])
        
        # Guardamos en memoria para el siguiente paso
        context.user_data['diccionario_ediciones'] = diccionario_ediciones
        
        await update.message.reply_text(
            "🏆 Elegí el torneo:",
            reply_markup=ReplyKeyboardMarkup(botones, resize_keyboard=True)
        )
        return ESPERANDO_EDICION_TABLA
    else:
        await update.message.reply_text("❌ Opción no válida. Elegí un botón del teclado.")
        return ESPERANDO_TIPO_TABLA

async def procesar_edicion_tabla(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Paso 3: Muestra la tabla del torneo elegido."""
    texto = update.message.text.strip()
    
    if texto == "🔙 Volver al menú":
        await mostrar_menu(update, context)
        return ConversationHandler.END
        
    diccionario_ediciones = context.user_data.get('diccionario_ediciones', {})
    
    if texto not in diccionario_ediciones:
        await update.message.reply_text("❌ Torneo no válido. Elegí usando los botones.")
        return ESPERANDO_EDICION_TABLA
        
    edicion_id = diccionario_ediciones[texto]
    return await imprimir_tabla(update, context, edicion_id=edicion_id, titulo=texto)

def formatear_anticipacion(segundos):
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

async def imprimir_tabla(update: Update, context: ContextTypes.DEFAULT_TYPE, edicion_id, titulo):
    """Función de apoyo: Dibuja la tabla en formato texto incluyendo a los que no jugaron."""
    # 1. Obtenemos el ranking de los que tienen puntos
    ranking = db.obtener_ranking(edicion_id=edicion_id)
    
    # 2. Obtenemos la lista completa de todos los usuarios del sistema
    todos_los_usuarios = db.obtener_usuarios()
    
    # 3. Identificamos quiénes sí tienen puntos en esta tabla
    usuarios_con_puntos = [row[0] for row in ranking]
    
    # 4. Filtramos para encontrar a los que no tienen ningún pronóstico en este contexto
    usuarios_sin_pronosticos = [u for u in todos_los_usuarios if u not in usuarios_con_puntos]
    
    if not ranking and not usuarios_sin_pronosticos:
        await update.message.reply_text("📉 Todavía no hay usuarios registrados en el sistema.")
        await mostrar_menu(update, context)
        return ConversationHandler.END
        
    mensaje = f"🏆 *Tabla de Posiciones: {titulo}* 🏆\n\n"
    
    # Dibujamos la tabla de los que puntuaron
    if ranking:
        for i, row in enumerate(ranking):
            username = row[0]
            puntos = row[1]
            pj = row[5]
            
            # Extraemos y formateamos la anticipación (row[6] trae los segundos promedio)
            ant_str = formatear_anticipacion(row[6])
            
            # Cast seguro para el error promedio
            error_prom = round(float(row[7]), 2) if row[7] is not None else 0.0
            efectividad = row[8]
            
            if i == 0: medalla = "🥇"
            elif i == 1: medalla = "🥈"
            elif i == 2: medalla = "🥉"
            else: medalla = f"*{i+1}°*"
                
            mensaje += f"{medalla} *{username}* - {puntos} pts\n"
            # 🌟 CAMBIO: Inyectamos la anticipación formateada antes de la efectividad
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
    
    # Volvemos al menú principal
    await mostrar_menu(update, context)
    return ConversationHandler.END

# ==========================================
# FLUJO 4: CONSULTAR PRONÓSTICOS
# ==========================================
async def iniciar_consultar_pronosticos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Paso 1: Muestra los torneos para consultar pronósticos."""
    id_telegram = update.message.from_user.id
    username = db.obtener_usuario_por_telegram(id_telegram)
    
    if not username:
        await update.message.reply_text("❌ Tenés que asociar tu cuenta primero.")
        return ConversationHandler.END

    # Guardamos el usuario activo en memoria para el siguiente paso
    context.user_data['username_activo'] = username

    ediciones = db.obtener_ediciones()
    if not ediciones:
        await update.message.reply_text("❌ No hay torneos registrados todavía.")
        await mostrar_menu(update, context)
        return ConversationHandler.END

    botones = []
    diccionario_ediciones = {}

    # Las ediciones ya vienen ordenadas descendentemente desde la BD
    for ed in ediciones:
        nombre_completo = f"{ed[1]} {ed[2]}"
        botones.append([nombre_completo])
        diccionario_ediciones[nombre_completo] = nombre_completo 

    botones.append(["🔙 Volver al menú"])
    context.user_data['diccionario_ediciones_pronosticos'] = diccionario_ediciones

    await update.message.reply_text(
        "🔎 *Consultar Pronósticos*\n\nElegí de qué torneo querés ver el historial:",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(botones, resize_keyboard=True)
    )
    return ESPERANDO_EDICION_PRONOSTICOS

async def procesar_edicion_pronosticos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Paso 2: Evalúa el torneo y muestra la lista numerada de usuarios."""
    texto = update.message.text.strip()
    
    if texto == "🔙 Volver al menú":
        await mostrar_menu(update, context)
        return ConversationHandler.END

    diccionario_ediciones = context.user_data.get('diccionario_ediciones_pronosticos', {})
    if texto not in diccionario_ediciones:
        await update.message.reply_text("❌ Torneo no válido. Elegí usando los botones.")
        return ESPERANDO_EDICION_PRONOSTICOS

    # Guardamos el torneo elegido
    context.user_data['torneo_elegido_pronosticos'] = texto

    # Obtenemos todos los usuarios (ya vienen ordenados alfabéticamente)
    usuarios = db.obtener_usuarios()
    username_propio = context.user_data.get('username_activo')

    botones = [["1_ De todos"], ["2_ Míos"]]
    mapa_usuarios = {"1_ De todos": "todos", "2_ Míos": username_propio}

    # Armamos los botones a partir del número 3 (de a dos columnas para que se vea bien)
    contador = 3
    fila = []
    for u in usuarios:
        if u != username_propio:  # Excluimos al usuario actual porque ya tiene la opción 2
            texto_btn = f"{contador}_ {u}"
            fila.append(texto_btn)
            mapa_usuarios[texto_btn] = u
            contador += 1
            
            if len(fila) == 2:
                botones.append(fila)
                fila = []
                
    if fila: # Si quedó algún botón suelto impar, lo agregamos al final
        botones.append(fila)

    botones.append(["🔙 Volver al menú"])
    
    # Guardamos este mapa para validar la respuesta después
    context.user_data['mapa_usuarios_pronosticos'] = mapa_usuarios

    await update.message.reply_text(
        "👤 ¿De quién querés ver los pronósticos?",
        reply_markup=ReplyKeyboardMarkup(botones, resize_keyboard=True)
    )
    return ESPERANDO_USUARIO_PRONOSTICOS

async def procesar_usuario_pronosticos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Paso 3: Busca los pronósticos y los imprime en pantalla."""
    texto = update.message.text.strip()
    
    if texto == "🔙 Volver al menú":
        await mostrar_menu(update, context)
        return ConversationHandler.END

    mapa = context.user_data.get('mapa_usuarios_pronosticos', {})
    if texto not in mapa:
        await update.message.reply_text("❌ Opción no válida. Elegí usando los botones.")
        return ESPERANDO_USUARIO_PRONOSTICOS

    target_user = mapa[texto]
    torneo = context.user_data.get('torneo_elegido_pronosticos')

    # Traemos los datos de la BD usando tus métodos existentes
    if target_user == "todos":
        datos = db.obtener_todos_pronosticos(filtro_torneo=torneo)
    else:
        datos = db.obtener_todos_pronosticos(filtro_torneo=torneo, filtro_usuario=target_user)

    if not datos:
        await update.message.reply_text("📝 No hay pronósticos cargados para esta selección.")
        await mostrar_menu(update, context)
        return ConversationHandler.END

    # 🌟 ORDEN ESTRICTO: Ordenamos descendentemente por fecha y hora del pronóstico (índice 9)
    datos_ordenados = sorted(datos, key=lambda x: x[9], reverse=True)

    # Preparamos el envío en bloques (Telegram no deja enviar mensajes de más de 4000 letras de golpe)
    mensajes = []
    
    if target_user == "todos":
        mensaje_actual = f"📋 *Historial de TODOS - {torneo}*\n\n"
    else:
        mensaje_actual = f"📋 *Historial de {target_user} - {torneo}*\n\n"

    for row in datos_ordenados:
        rival = row[0]
        fecha_partido = row[1].strftime('%d/%m/%Y %H:%M') if row[1] else "A conf."
        user = row[5]
        pred_cai = row[6]
        pred_rival = row[7]
        fecha_pred = row[9].strftime('%d/%m/%Y %H:%M:%S') if row[9] else "N/A"

        # Armamos el texto de cada pronóstico
        bloque = ""
        # Si eligió de todos, mostramos de quién es el pronóstico
        if target_user == "todos":
            bloque += f"👤 *{user}*\n"
            
        bloque += f"⚽ vs {rival} | 📅 {fecha_partido}\n"
        bloque += f"👉 *Independiente {pred_cai} - {pred_rival} {rival}*\n"
        bloque += f"⏱️ _Cargado el: {fecha_pred}_\n"
        bloque += "—\n"

        # Si el mensaje actual se hace muy largo, lo guardamos y empezamos uno nuevo
        if len(mensaje_actual) + len(bloque) > 3800:
            mensajes.append(mensaje_actual)
            mensaje_actual = bloque
        else:
            mensaje_actual += bloque

    if mensaje_actual:
        mensajes.append(mensaje_actual)

    # Enviamos todos los mensajes que se hayan generado, quitando el teclado al finalizar
    for m in mensajes:
        await update.message.reply_text(m, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())

    # Volvemos al menú principal
    await mostrar_menu(update, context)
    return ConversationHandler.END

# ==========================================
# FLUJO 5: OPTIMISMO/PESIMISMO
# ==========================================
async def iniciar_opt_pes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Paso 1: Pregunta si quiere ver el índice histórico o de un torneo."""
    id_telegram = update.message.from_user.id
    if not db.obtener_usuario_por_telegram(id_telegram):
        await update.message.reply_text("❌ Tenés que asociar tu cuenta primero.")
        return ConversationHandler.END

    botones = [
        ["1_ Histórica"],
        ["2_ Por Torneo"],
        ["🔙 Volver al menú"]
    ]
    await update.message.reply_text(
        "🧠 *Índice de Optimismo/Pesimismo*\n\n¿Qué datos querés consultar?",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(botones, resize_keyboard=True)
    )
    return ESPERANDO_TIPO_OPT_PES

async def procesar_tipo_opt_pes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Paso 2: Evalúa tipo de tabla y muestra torneos si es necesario."""
    texto = update.message.text.strip()
    
    if texto == "🔙 Volver al menú":
        await mostrar_menu(update, context)
        return ConversationHandler.END
        
    if texto == "1_ Histórica":
        return await imprimir_tabla_opt_pes(update, context, edicion_id=None, titulo="Histórica")
        
    elif texto == "2_ Por Torneo":
        ediciones = db.obtener_ediciones()
        if not ediciones:
            await update.message.reply_text("❌ No hay torneos registrados todavía.")
            await mostrar_menu(update, context)
            return ConversationHandler.END
            
        botones = []
        diccionario_ediciones = {}
        for ed in ediciones:
            id_edicion = ed[0]
            nombre_completo = f"{ed[1]} {ed[2]}"
            botones.append([nombre_completo])
            diccionario_ediciones[nombre_completo] = id_edicion
            
        botones.append(["🔙 Volver al menú"])
        context.user_data['diccionario_ediciones_opt_pes'] = diccionario_ediciones
        
        await update.message.reply_text(
            "🏆 Elegí el torneo:",
            reply_markup=ReplyKeyboardMarkup(botones, resize_keyboard=True)
        )
        return ESPERANDO_EDICION_OPT_PES
    else:
        await update.message.reply_text("❌ Opción no válida. Elegí un botón.")
        return ESPERANDO_TIPO_OPT_PES

async def procesar_edicion_opt_pes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Paso 3: Captura el torneo e imprime la tabla."""
    texto = update.message.text.strip()
    
    if texto == "🔙 Volver al menú":
        await mostrar_menu(update, context)
        return ConversationHandler.END
        
    diccionario = context.user_data.get('diccionario_ediciones_opt_pes', {})
    if texto not in diccionario:
        await update.message.reply_text("❌ Torneo no válido. Elegí usando los botones.")
        return ESPERANDO_EDICION_OPT_PES
        
    edicion_id = diccionario[texto]
    return await imprimir_tabla_opt_pes(update, context, edicion_id=edicion_id, titulo=texto)

async def imprimir_tabla_opt_pes(update: Update, context: ContextTypes.DEFAULT_TYPE, edicion_id, titulo):
    """Construye y envía la tabla con las lógicas del programa de escritorio."""
    datos = db.obtener_indice_optimismo_pesimismo(edicion_id=edicion_id)
    
    if not datos:
        await update.message.reply_text("📉 Todavía no hay datos de optimismo/pesimismo para esta selección.")
        await mostrar_menu(update, context)
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
    
    await mostrar_menu(update, context)
    return ConversationHandler.END

# ==========================================
# FLUJO 6: MAYORES ERRORES
# ==========================================
async def iniciar_mayores_errores(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Paso 1: Pregunta si quiere ver los peores errores históricos o de un torneo."""
    id_telegram = update.message.from_user.id
    if not db.obtener_usuario_por_telegram(id_telegram):
        await update.message.reply_text("❌ Tenés que asociar tu cuenta primero.")
        return ConversationHandler.END

    botones = [
        ["1_ Histórica"],
        ["2_ Por Torneo"],
        ["🔙 Volver al menú"]
    ]
    await update.message.reply_text(
        "🤦‍♂️ *Ranking de Mayores Errores*\n\n¿Qué datos querés consultar?",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(botones, resize_keyboard=True)
    )
    return ESPERANDO_TIPO_MAYORES_ERRORES

async def procesar_tipo_mayores_errores(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Paso 2: Evalúa tipo de tabla y muestra torneos si es necesario."""
    texto = update.message.text.strip()
    
    if texto == "🔙 Volver al menú":
        await mostrar_menu(update, context)
        return ConversationHandler.END
        
    if texto == "1_ Histórica":
        return await imprimir_tabla_mayores_errores(update, context, edicion_id=None, titulo="Histórica")
        
    elif texto == "2_ Por Torneo":
        ediciones = db.obtener_ediciones(solo_finalizados=True) # Usamos tu método para que muestre torneos jugados
        if not ediciones:
            await update.message.reply_text("❌ No hay torneos finalizados o con partidos jugados todavía.")
            await mostrar_menu(update, context)
            return ConversationHandler.END
            
        botones = []
        diccionario_ediciones = {}
        for ed in ediciones:
            id_edicion = ed[0]
            nombre_completo = f"{ed[1]} {ed[2]}"
            botones.append([nombre_completo])
            diccionario_ediciones[nombre_completo] = id_edicion
            
        botones.append(["🔙 Volver al menú"])
        context.user_data['diccionario_ediciones_errores'] = diccionario_ediciones
        
        await update.message.reply_text(
            "🏆 Elegí el torneo:",
            reply_markup=ReplyKeyboardMarkup(botones, resize_keyboard=True)
        )
        return ESPERANDO_EDICION_MAYORES_ERRORES
    else:
        await update.message.reply_text("❌ Opción no válida. Elegí un botón.")
        return ESPERANDO_TIPO_MAYORES_ERRORES

async def procesar_edicion_mayores_errores(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Paso 3: Captura el torneo e imprime la lista de errores."""
    texto = update.message.text.strip()
    
    if texto == "🔙 Volver al menú":
        await mostrar_menu(update, context)
        return ConversationHandler.END
        
    diccionario = context.user_data.get('diccionario_ediciones_errores', {})
    if texto not in diccionario:
        await update.message.reply_text("❌ Torneo no válido. Elegí usando los botones.")
        return ESPERANDO_EDICION_MAYORES_ERRORES
        
    edicion_id = diccionario[texto]
    return await imprimir_tabla_mayores_errores(update, context, edicion_id=edicion_id, titulo=texto)

async def imprimir_tabla_mayores_errores(update: Update, context: ContextTypes.DEFAULT_TYPE, edicion_id, titulo):
    datos = db.obtener_ranking_mayores_errores(edicion_id=edicion_id)
    
    if not datos:
        await update.message.reply_text("📉 Todavía no hay datos de errores para esta selección.")
        await mostrar_menu(update, context)
        return ConversationHandler.END
        
    mensajes = []
    mensaje_actual = f"📉 *Mayores Errores: {titulo}* 📉\n"
    mensaje_actual += f"_Los pronósticos más alejados de la realidad (Top {LIMITE_MAYORES_ERRORES})._\n\n"
    
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
    
    await mostrar_menu(update, context)
    return ConversationHandler.END

# ==========================================
# FLUJO 7: RANKING FALSO PROFETA
# ==========================================
async def iniciar_falso_profeta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Paso 1: Pregunta si quiere ver los Falsos Profetas históricos o de un torneo."""
    id_telegram = update.message.from_user.id
    if not db.obtener_usuario_por_telegram(id_telegram):
        await update.message.reply_text("❌ Tenés que asociar tu cuenta primero.")
        return ConversationHandler.END

    botones = [
        ["1_ Histórica"],
        ["2_ Por Torneo"],
        ["🔙 Volver al menú"]
    ]
    await update.message.reply_text(
        "🤡 *Ranking Falso Profeta*\n\n¿Qué datos querés consultar?",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(botones, resize_keyboard=True)
    )
    return ESPERANDO_TIPO_FALSO_PROFETA

async def procesar_tipo_falso_profeta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Paso 2: Evalúa tipo de tabla y muestra torneos."""
    texto = update.message.text.strip()
    
    if texto == "🔙 Volver al menú":
        await mostrar_menu(update, context)
        return ConversationHandler.END
        
    if texto == "1_ Histórica":
        return await imprimir_tabla_falso_profeta(update, context, edicion_id=None, titulo="Histórica")
        
    elif texto == "2_ Por Torneo":
        ediciones = db.obtener_ediciones()
        if not ediciones:
            await update.message.reply_text("❌ No hay torneos registrados todavía.")
            await mostrar_menu(update, context)
            return ConversationHandler.END
            
        botones = []
        diccionario_ediciones = {}
        for ed in ediciones:
            id_edicion = ed[0]
            nombre_completo = f"{ed[1]} {ed[2]}"
            botones.append([nombre_completo])
            diccionario_ediciones[nombre_completo] = id_edicion
            
        botones.append(["🔙 Volver al menú"])
        context.user_data['diccionario_ediciones_fp'] = diccionario_ediciones
        
        await update.message.reply_text(
            "🏆 Elegí el torneo:",
            reply_markup=ReplyKeyboardMarkup(botones, resize_keyboard=True)
        )
        return ESPERANDO_EDICION_FALSO_PROFETA
    else:
        await update.message.reply_text("❌ Opción no válida. Elegí un botón.")
        return ESPERANDO_TIPO_FALSO_PROFETA

async def procesar_edicion_falso_profeta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Paso 3: Captura el torneo e imprime la lista."""
    texto = update.message.text.strip()
    
    if texto == "🔙 Volver al menú":
        await mostrar_menu(update, context)
        return ConversationHandler.END
        
    diccionario = context.user_data.get('diccionario_ediciones_fp', {})
    if texto not in diccionario:
        await update.message.reply_text("❌ Torneo no válido. Elegí usando los botones.")
        return ESPERANDO_EDICION_FALSO_PROFETA
        
    edicion_id = diccionario[texto]
    return await imprimir_tabla_falso_profeta(update, context, edicion_id=edicion_id, titulo=texto)

async def imprimir_tabla_falso_profeta(update: Update, context: ContextTypes.DEFAULT_TYPE, edicion_id, titulo):
    """Construye y envía el ranking invirtiendo el % de acierto al % de falso profeta."""
    datos = db.obtener_ranking_falso_profeta(edicion_id=edicion_id)
    
    if not datos:
        await update.message.reply_text("📉 Todavía no hay suficientes datos para calcular falsos profetas en esta selección.")
        await mostrar_menu(update, context)
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
    
    await mostrar_menu(update, context)
    return ConversationHandler.END

if __name__ == '__main__':
    print("Iniciando Bot de Telegram...")
    app = ApplicationBuilder().token(TOKEN).build()
    
    # Creamos un único ConversationHandler que maneja TODOS los flujos
    conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^1_ Asociar cuenta$"), iniciar_asociacion),
            MessageHandler(filters.Regex("^1_ Cargar pronóstico$"), iniciar_carga_pronostico),
            MessageHandler(filters.Regex("^2_ Ver posiciones$"), iniciar_ver_posiciones),
            MessageHandler(filters.Regex("^3_ Consultar pronósticos$"), iniciar_consultar_pronosticos),
            MessageHandler(filters.Regex("^4_ Optimismo/Pesimismo$"), iniciar_opt_pes),
            MessageHandler(filters.Regex("^5_ Mayores errores$"), iniciar_mayores_errores),
            # 🌟 CAMBIO: Se agrega la opción 6
            MessageHandler(filters.Regex("^6_ Ranking Falso Profeta$"), iniciar_falso_profeta)
        ],
        states={
            ESPERANDO_IDENTIFICADOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, procesar_identificador)],
            ESPERANDO_CODIGO: [MessageHandler(filters.TEXT & ~filters.COMMAND, procesar_codigo)],
            
            ESPERANDO_PARTIDO_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, procesar_partido_id)],
            ESPERANDO_PRONOSTICO: [MessageHandler(filters.TEXT & ~filters.COMMAND, procesar_pronostico)],
            
            ESPERANDO_TIPO_TABLA: [MessageHandler(filters.TEXT & ~filters.COMMAND, procesar_tipo_tabla)],
            ESPERANDO_EDICION_TABLA: [MessageHandler(filters.TEXT & ~filters.COMMAND, procesar_edicion_tabla)],
            
            ESPERANDO_EDICION_PRONOSTICOS: [MessageHandler(filters.TEXT & ~filters.COMMAND, procesar_edicion_pronosticos)],
            ESPERANDO_USUARIO_PRONOSTICOS: [MessageHandler(filters.TEXT & ~filters.COMMAND, procesar_usuario_pronosticos)],

            ESPERANDO_TIPO_OPT_PES: [MessageHandler(filters.TEXT & ~filters.COMMAND, procesar_tipo_opt_pes)],
            ESPERANDO_EDICION_OPT_PES: [MessageHandler(filters.TEXT & ~filters.COMMAND, procesar_edicion_opt_pes)],

            ESPERANDO_TIPO_MAYORES_ERRORES: [MessageHandler(filters.TEXT & ~filters.COMMAND, procesar_tipo_mayores_errores)],
            ESPERANDO_EDICION_MAYORES_ERRORES: [MessageHandler(filters.TEXT & ~filters.COMMAND, procesar_edicion_mayores_errores)],

            # 🌟 CAMBIO: Nuevos estados para Falso Profeta
            ESPERANDO_TIPO_FALSO_PROFETA: [MessageHandler(filters.TEXT & ~filters.COMMAND, procesar_tipo_falso_profeta)],
            ESPERANDO_EDICION_FALSO_PROFETA: [MessageHandler(filters.TEXT & ~filters.COMMAND, procesar_edicion_falso_profeta)]
        },
        fallbacks=[CommandHandler("cancelar", cancelar_conversacion)],
    )
    
    app.add_handler(CommandHandler("start", mostrar_menu))
    app.add_handler(conv_handler)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mostrar_menu))
    
    print("Bot escuchando...")
    app.run_polling()