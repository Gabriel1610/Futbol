import flet as ft
from estilos import Estilos

class VentanaCarga:
    """
    Muestra una ventana modal de espera con una animación giratoria.
    Es estática para poder llamarla desde cualquier lugar sin instanciarla.
    """
    dialogo = None

    @staticmethod
    def mostrar(page: ft.Page, mensaje: str):
        contenido = ft.Row(
            controls=[
                ft.ProgressRing(color=Estilos.COLOR_ROJO_CAI, width=30, height=30),
                ft.Text(mensaje, size=16, color=Estilos.COLOR_BLANCO, weight=ft.FontWeight.BOLD)
            ],
            alignment=ft.MainAxisAlignment.START,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=20
        )

        VentanaCarga.dialogo = ft.AlertDialog(
            modal=True,
            content=ft.Container(
                content=contenido,
                width=300,
                bgcolor="#2d2d2d",
                padding=20,
                border_radius=10
            ),
            bgcolor="transparent",
        )

        # --- APILAR FORZOSAMENTE SOBRE EL FORMULARIO ---
        page.overlay.append(VentanaCarga.dialogo)
        VentanaCarga.dialogo.open = True
        page.update()

    @staticmethod
    def cerrar(page: ft.Page):
        if VentanaCarga.dialogo:
            VentanaCarga.dialogo.open = False
            page.update()
            if VentanaCarga.dialogo in page.overlay:
                page.overlay.remove(VentanaCarga.dialogo)
            VentanaCarga.dialogo = None