import flet as ft
from estilos import Estilos

class GestorMensajes:
    """Clase estática para mostrar mensajes modales con estilo del CAI"""

    @staticmethod
    def mostrar(page: ft.Page, titulo: str, mensaje: str, tipo: str = "info"):
        if tipo == "error":
            icono = "error_outline"
            color_icono = Estilos.COLOR_ROJO_CAI
            titulo_color = Estilos.COLOR_ROJO_CAI
        elif tipo == "exito":
            icono = "check_circle_outline"
            color_icono = "green" 
            titulo_color = Estilos.COLOR_BLANCO
        else:
            icono = "info_outline"
            color_icono = Estilos.COLOR_BLANCO
            titulo_color = Estilos.COLOR_BLANCO

        dialogo = None

        # --- LÓGICA DE CIERRE EN CAPAS ---
        def cerrar_dialogo(e):
            if dialogo:
                dialogo.open = False
                page.update()
                if dialogo in page.overlay:
                    page.overlay.remove(dialogo)

        boton = ft.ElevatedButton(
            text="Aceptar",
            style=ft.ButtonStyle(
                color=Estilos.COLOR_BLANCO,
                bgcolor=Estilos.COLOR_ROJO_CAI
            ),
            on_click=cerrar_dialogo
        )

        contenido = ft.Column(
            tight=True,
            controls=[
                ft.Row(
                    controls=[
                        ft.Icon(icono, color=color_icono, size=40),
                        ft.Text(titulo, size=20, weight=ft.FontWeight.BOLD, color=titulo_color)
                    ],
                    alignment=ft.MainAxisAlignment.START,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER
                ),
                ft.Divider(color="grey"),
                ft.Text(mensaje, size=16, color=Estilos.COLOR_BLANCO),
                ft.Container(height=20),
                ft.Row(
                    controls=[boton],
                    alignment=ft.MainAxisAlignment.END
                )
            ]
        )

        dialogo = ft.AlertDialog(
            modal=True,
            title_padding=0,
            content_padding=0,
            content=ft.Container(
                content=contenido,
                width=450,
                bgcolor="#2d2d2d",
                border_radius=15,
                padding=25
            ),
            bgcolor="transparent",
        )

        # --- APILAR FORZOSAMENTE SOBRE EL FORMULARIO ---
        page.overlay.append(dialogo)
        dialogo.open = True
        page.update()