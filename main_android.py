import os
import re
import sys
import threading
import urllib.request
import zipfile
import yt_dlp

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.progressbar import ProgressBar
from kivy.uix.spinner import Spinner
from kivy.uix.scrollview import ScrollView
from kivy.uix.togglebutton import ToggleButton
from kivy.utils import platform

# Establecer tamaño inicial de ventana para pruebas en PC (aspecto móvil)
if platform not in ('android', 'ios'):
    Window.size = (400, 700)


def obtener_ruta_salida():
    """Retorna la ruta por defecto para guardar descargas en Android o PC."""
    if platform == 'android':
        try:
            from android.storage import primary_external_storage_path
            dir_base = primary_external_storage_path()
            return os.path.join(dir_base, "Download")
        except Exception:
            return "/sdcard/Download"
    else:
        return os.path.join(os.path.expanduser("~"), "Downloads")


def solicitar_permisos_android():
    """Solicita permisos de almacenamiento si se ejecuta en Android."""
    if platform == 'android':
        try:
            from android.permissions import request_permissions, Permission
            request_permissions([
                Permission.READ_EXTERNAL_STORAGE,
                Permission.WRITE_EXTERNAL_STORAGE
            ])
        except Exception as e:
            print(f"Error solicitando permisos: {e}")


class YTDLPLoggerAndroid:
    def __init__(self, app):
        self.app = app
        self.errors = []

    def debug(self, msg):
        pass

    def warning(self, msg):
        Clock.schedule_once(lambda dt: self.app.log(f"[ADVERTENCIA] {msg}"))

    def error(self, msg):
        self.errors.append(msg)
        Clock.schedule_once(lambda dt: self.app.log(f"[ERROR] {msg}"))


class DownloaderRoot(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'
        self.padding = 15
        self.spacing = 10

        self.download_path = obtener_ruta_salida()
        self.format_val = "mp3"
        self.quality_val = "192 kbps (Media)"
        self.is_downloading = False

        self._crear_interfaz()

    def _crear_interfaz(self):
        # Título
        lbl_title = Label(
            text="Descargador de YouTube",
            font_size='20sp',
            bold=True,
            size_hint_y=None,
            height=40,
            color=(0.1, 0.6, 1, 1)
        )
        self.add_widget(lbl_title)

        # 1. Campo de URL
        self.add_widget(Label(
            text="Enlace del Video o Lista:",
            font_size='14sp',
            size_hint_y=None,
            height=25,
            halign='left',
            valign='middle'
        ))
        
        self.entry_url = TextInput(
            hint_text="Pega la URL de YouTube aquí...",
            multiline=False,
            size_hint_y=None,
            height=45,
            font_size='14sp'
        )
        self.add_widget(self.entry_url)

        # 2. Opciones de Formato
        self.add_widget(Label(
            text="Formato de salida:",
            font_size='14sp',
            size_hint_y=None,
            height=25
        ))
        
        box_fmt = BoxLayout(orientation='horizontal', spacing=10, size_hint_y=None, height=40)
        self.btn_mp3 = ToggleButton(text="Audio (MP3)", group="fmt", state="down")
        self.btn_mp3.bind(on_press=lambda x: self._cambiar_formato("mp3"))
        self.btn_mp4 = ToggleButton(text="Video (MP4)", group="fmt")
        self.btn_mp4.bind(on_press=lambda x: self._cambiar_formato("mp4"))
        
        box_fmt.add_widget(self.btn_mp3)
        box_fmt.add_widget(self.btn_mp4)
        self.add_widget(box_fmt)

        # 3. Opciones de Calidad
        self.add_widget(Label(
            text="Calidad:",
            font_size='14sp',
            size_hint_y=None,
            height=25
        ))
        
        self.spinner_quality = Spinner(
            text="192 kbps (Media)",
            values=["320 kbps (Alta)", "192 kbps (Media)", "128 kbps (Baja)"],
            size_hint_y=None,
            height=40
        )
        self.spinner_quality.bind(text=self._on_quality_change)
        self.add_widget(self.spinner_quality)

        # 4. Carpeta de Salida
        lbl_dir = Label(
            text=f"Guardar en: {self.download_path}",
            font_size='11sp',
            size_hint_y=None,
            height=25,
            color=(0.7, 0.7, 0.7, 1)
        )
        self.add_widget(lbl_dir)

        # 5. Botón de Iniciar Descarga
        self.btn_download = Button(
            text="Iniciar Descarga",
            font_size='16sp',
            bold=True,
            background_color=(0.1, 0.7, 0.3, 1),
            size_hint_y=None,
            height=50
        )
        self.btn_download.bind(on_press=self._iniciar_descarga)
        self.add_widget(self.btn_download)

        # 6. Información de Estado y Progreso
        self.lbl_file = Label(
            text="Archivo: -",
            font_size='12sp',
            size_hint_y=None,
            height=25,
            shorten=True,
            shorten_from='right'
        )
        self.add_widget(self.lbl_file)

        self.lbl_status = Label(
            text="Listo para descargar.",
            font_size='12sp',
            size_hint_y=None,
            height=25,
            color=(0.2, 0.8, 0.2, 1)
        )
        self.add_widget(self.lbl_status)

        self.progress_bar = ProgressBar(max=100, value=0, size_hint_y=None, height=20)
        self.add_widget(self.progress_bar)

        # 7. Consola de Registro (Logs)
        self.txt_log = TextInput(
            readonly=True,
            font_size='11sp',
            size_hint=(1, 1),
            background_color=(0.15, 0.15, 0.15, 1),
            foreground_color=(0.9, 0.9, 0.9, 1)
        )
        self.add_widget(self.txt_log)

    def _cambiar_formato(self, fmt):
        self.format_val = fmt
        if fmt == "mp3":
            calidades = ["320 kbps (Alta)", "192 kbps (Media)", "128 kbps (Baja)"]
            self.spinner_quality.values = calidades
            self.spinner_quality.text = "192 kbps (Media)"
        else:
            calidades = ["Máxima Calidad", "1080p", "720p", "480p", "360p"]
            self.spinner_quality.values = calidades
            self.spinner_quality.text = "Máxima Calidad"

    def _on_quality_change(self, spinner, text):
        self.quality_val = text

    def log(self, mensaje):
        self.txt_log.text += mensaje + "\n"

    def _iniciar_descarga(self, instance):
        url = self.entry_url.text.strip()
        if not url:
            self.log("[ATENCIÓN] Debes ingresar un enlace válido.")
            self.lbl_status.text = "Ingresa una URL de YouTube."
            self.lbl_status.color = (1, 0.5, 0, 1)
            return

        if self.is_downloading:
            return

        self.is_downloading = True
        self.btn_download.disabled = True
        self.progress_bar.value = 0
        self.lbl_file.text = "Archivo: Obteniendo datos..."
        self.lbl_status.text = "Iniciando descarga..."
        self.lbl_status.color = (0.2, 0.6, 1, 1)
        self.log(f"--- Iniciando descarga: {url} ---")

        threading.Thread(target=self._proceso_descarga, args=(url,), daemon=True).start()

    def _clean_ansi(self, text):
        return re.sub(r'\x1b\[[0-9;]*m', '', str(text)).strip()

    def _progreso_hook(self, d):
        if d['status'] == 'downloading':
            filename = os.path.basename(d.get('filename', ''))
            info = d.get('info_dict', {})
            title = info.get('title') or filename
            p_idx = info.get('playlist_index')
            p_cnt = info.get('playlist_count')

            if p_idx and p_cnt:
                nombre_mostrar = f"[{p_idx}/{p_cnt}] {title}"
            else:
                nombre_mostrar = title

            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            downloaded = d.get('downloaded_bytes', 0)
            porcentaje = 0.0

            if total > 0:
                porcentaje = (downloaded / total) * 100
            else:
                p_str = self._clean_ansi(d.get('_percent_str', '0')).replace('%', '')
                try:
                    porcentaje = float(p_str)
                except ValueError:
                    porcentaje = 0.0

            vel = self._clean_ansi(d.get('_speed_str', 'N/A'))
            eta = self._clean_ansi(d.get('_eta_str', 'N/A'))
            p_texto = f"{porcentaje:.1f}%"

            Clock.schedule_once(lambda dt: self._actualizar_progreso_ui(nombre_mostrar, porcentaje, p_texto, vel, eta))

        elif d['status'] == 'finished':
            Clock.schedule_once(lambda dt: self._finalizar_archivo_ui())

    def _actualizar_progreso_ui(self, nombre_mostrar, porcentaje, p_texto, vel, eta):
        self.lbl_file.text = f"Archivo: {nombre_mostrar}"
        self.progress_bar.value = porcentaje
        self.lbl_status.text = f"Progreso: {p_texto} | Vel: {vel} | Restante: {eta}"
        self.lbl_status.color = (0.2, 0.6, 1, 1)

    def _finalizar_archivo_ui(self):
        self.progress_bar.value = 100
        self.lbl_status.text = "Descarga finalizada. Procesando/Convirtiendo..."
        self.lbl_status.color = (0.8, 0.4, 1, 1)

    def _proceso_descarga(self, url):
        formato = self.format_val
        calidad = self.quality_val
        ruta_salida = self.download_path

        outtmpl = os.path.join(ruta_salida, "%(playlist_title,playlist)s", "%(title)s.%(ext)s")
        logger = YTDLPLoggerAndroid(self)

        ydl_opts = {
            "outtmpl": outtmpl,
            "ignoreerrors": True,
            "noplaylist": False,
            "progress_hooks": [self._progreso_hook],
            "logger": logger,
            "no_warnings": False,
        }

        if formato == "mp3":
            bitrate = "192"
            if "320" in calidad:
                bitrate = "320"
            elif "128" in calidad:
                bitrate = "128"

            ydl_opts.update({
                "format": "bestaudio/best",
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": bitrate,
                }],
            })
        else:
            if calidad == "1080p":
                fmt_str = "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best[height<=1080]/best"
            elif calidad == "720p":
                fmt_str = "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/best[height<=720]/best"
            elif calidad == "480p":
                fmt_str = "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=480]+bestaudio/best[height<=480]/best"
            elif calidad == "360p":
                fmt_str = "bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=360]+bestaudio/best[height<=360]/best"
            else:
                fmt_str = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"

            ydl_opts.update({
                "format": fmt_str,
                "merge_output_format": "mp4",
            })

        exito = False
        error_msg = ""
        hubo_omitidos = False

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            exito = True
            if logger.errors:
                hubo_omitidos = True
                error_msg = "\n".join(logger.errors)
        except Exception as e:
            exito = False
            error_msg = str(e)
            if logger.errors and error_msg not in logger.errors:
                error_msg = f"{error_msg}\n" + "\n".join(logger.errors)

        Clock.schedule_once(lambda dt: self._finalizar_proceso(exito, error_msg, hubo_omitidos))

    def _finalizar_proceso(self, exito, error_msg, hubo_omitidos):
        self.is_downloading = False
        self.btn_download.disabled = False

        if exito:
            self.progress_bar.value = 100
            if hubo_omitidos:
                self.lbl_status.text = "Descarga completada (con omisiones)."
                self.lbl_status.color = (1, 0.6, 0, 1)
                self.log(f"[AVISO] Omisiones:\n{error_msg}")
            else:
                self.lbl_status.text = "¡Descarga completada con éxito!"
                self.lbl_status.color = (0, 0.8, 0, 1)
                self.log("Descarga completada correctamente.")
        else:
            self.lbl_status.text = "Error en descarga."
            self.lbl_status.color = (1, 0.2, 0.2, 1)
            self.log(f"[ERROR FIN]: {error_msg}")


class YouTubeDownloaderApp(App):
    def build(self):
        self.title = "YouTube Downloader Mobile"
        solicitar_permisos_android()
        return DownloaderRoot()


if __name__ == '__main__':
    YouTubeDownloaderApp().run()
