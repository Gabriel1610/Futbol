import os
import asyncio
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import mysql.connector
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

# Cargamos las variables del .env (las mismas que usas para Flet)
load_dotenv(override=True)
TOKEN = os.getenv("TELEGRAM_TOKEN")

def conectar_bd():
    """Usa la misma lógica que tu archivo base_de_datos.py"""
    return mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        ssl_ca="isrgrootx1.pem" # Tu certificado de TiDB
    )

async def mostrar_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Responde a cualquier texto o /start mostrando el menú principal"""
    
    # 1. Definimos los botones (Es una lista dentro de otra lista, representando filas)
    botones = [
        ["1_ Cargar pronóstico"]
    ]
    
    # 2. Creamos el teclado visual. resize_keyboard=True hace que no ocupe media pantalla
    menu = ReplyKeyboardMarkup(botones, resize_keyboard=True)
    
    mensaje = "¡Hola! Bienvenido al Prode. 🔴\nPor favor, selecciona una opción abajo:"
    
    # 3. Enviamos el mensaje y le "adjuntamos" el menú
    await update.message.reply_text(mensaje, reply_markup=menu)

async def recibir_pronostico(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Procesa el comando /pronostico 2-1"""
    # context.args guarda lo que el usuario escribe después del comando
    if not context.args:
        await update.message.reply_text("❌ Te faltó el resultado. Ejemplo: /pronostico 2-1")
        return

    texto_resultado = context.args[0] # "2-1"
    username_telegram = update.message.from_user.username # Ej: @Gabriel
    
    try:
        # 1. Extraemos los goles separando por el guion
        goles_local, goles_visitante = texto_resultado.split('-')
        
        # 2. Conectamos a TiDB (Igual que en tu app Flet)
        conexion = conectar_bd()
        cursor = conexion.cursor()
        
        # 3. Insertamos o actualizamos en la tabla (Ejemplo básico)
        sql = """
            INSERT INTO pronosticos (usuario_telegram, local, visitante) 
            VALUES (%s, %s, %s)
        """
        cursor.execute(sql, (username_telegram, int(goles_local), int(goles_visitante)))
        conexion.commit()
        
        await update.message.reply_text(f"✅ ¡Pronóstico guardado! Independiente {goles_local} - {goles_visitante} Rival")
        
    except ValueError:
        await update.message.reply_text("❌ Formato inválido. Usa el guion. Ejemplo: /pronostico 2-1")
    except Exception as e:
        await update.message.reply_text(f"❌ Error en la base de datos: {e}")
    finally:
        if 'cursor' in locals(): cursor.close()
        if 'conexion' in locals(): conexion.close()

if __name__ == '__main__':
    # Arrancamos el motor del bot
    print("Iniciando Bot de Telegram...")
    app = ApplicationBuilder().token(TOKEN).build()
    
    # Le enseñamos qué comandos escuchar
    # Escucha el comando tradicional /start
    app.add_handler(CommandHandler("start", mostrar_menu))
    # ¡La magia! Escucha CUALQUIER texto normal, excluyendo comandos
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mostrar_menu))
    # Tu comando de pronóstico queda igual
    app.add_handler(CommandHandler("pronostico", recibir_pronostico))
    app.add_handler(CommandHandler("pronostico", recibir_pronostico))
    
    # Se queda escuchando para siempre
    print("Bot escuchando...")
    app.run_polling()