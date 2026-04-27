import os
import smtplib
import ssl
from email.message import EmailMessage
import random
import threading
from dotenv import load_dotenv
from ventana_mensaje import GestorMensajes

class GestorCorreo:
    def __init__(self):
        # Carga las variables de entorno desde el archivo .env (útil en modo local)
        load_dotenv()
        
        # TUS CREDENCIALES OBTENIDAS DE LAS VARIABLES DE ENTORNO
        self.email_emisor = os.getenv("EMAIL_USER")
        self.email_password = os.getenv("EMAIL_PASSWORD")
        
    def generar_codigo(self):
        """Genera un código numérico de 6 dígitos."""
        return str(random.randint(100000, 999999))

    def enviar_codigo(self, email_destino, codigo, es_registro=False):
        """
        Envía un código de verificación.
        - Si es_registro=True: Envía mensaje de Bienvenida.
        - Si es_registro=False: Envía mensaje de Recuperación de contraseña.
        """
        def _enviar():
            # Verificación de seguridad rápida por si faltan las credenciales
            if not self.email_emisor or not self.email_password:
                print("❌ Faltan credenciales de email (EMAIL_USER o EMAIL_PASSWORD).")
                return
                
            try:
                msg = EmailMessage()
                
                # --- DEFINIMOS ASUNTO Y TEXTO SEGÚN EL TIPO ---
                if es_registro:
                    msg['Subject'] = "Código de Registro - Club A. Independiente"
                    saludo = "¡Bienvenido al Prode!"
                    motivo = "Estás a un paso de completar tu registro."
                    accion = "tu código de alta"
                else:
                    msg['Subject'] = "Recuperación de Contraseña - Club A. Independiente"
                    saludo = "Hola,"
                    motivo = "Has solicitado restablecer tu contraseña."
                    accion = "tu código de verificación"

                msg['From'] = self.email_emisor
                msg['To'] = email_destino
                
                cuerpo = f"""
                {saludo}
                
                {motivo}
                El número para validar {accion} es: {codigo}
                
                Este código expira en 15 minutos.
                Si no fuiste tú, por favor ignora este mensaje.
                """
                msg.set_content(cuerpo)

                # --- CONFIGURACIÓN SSL (Igual que antes) ---
                context = ssl.create_default_context()
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE

                with smtplib.SMTP_SSL('smtp.gmail.com', 465, context=context) as smtp:
                    smtp.login(self.email_emisor, self.email_password)
                    smtp.send_message(msg)
                
                print(f"Correo ({'Registro' if es_registro else 'Recuperación'}) enviado a {email_destino}")
                
            except Exception as e:
                print(f"Error enviando correo: {e}")
                self._mostrar_mensaje_admin("Error enviando correo", f"No se pudo enviar el correo a {email_destino}: {e}", "error")

        threading.Thread(target=_enviar, daemon=True).start()

    def _mostrar_mensaje_admin(self, titulo, mensaje, tipo="error"):
        """
        Función auxiliar que verifica si el usuario es admin y muestra
        una ventana de mensaje. Si no es admin, no hace nada visual.
        """
        # Verificamos si existe usuario logueado y si está en la lista de admins
        if hasattr(self, 'usuario_actual') and self.usuario_actual in getattr(self, 'lista_administradores', []):
            # Usamos GestorMensajes para mostrar el error en pantalla
            if hasattr(self, 'page'):
                GestorMensajes.mostrar(self.page, titulo, mensaje, tipo)
                # Como puede ser llamado desde un hilo secundario, forzamos update
                self.page.update()