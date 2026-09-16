# -*- coding: utf-8 -*-
import datetime
import os

from qgis.PyQt.QtCore import QDate, QSettings
from qgis.PyQt.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from .sentinel_client import (
    SentinelAuthError,
    download_scenes,
    get_access_token,
    search_scenes,
)

SETTINGS_GROUP = "QuickSentinel"


class QuickSentinelDialog(QDialog):
    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setWindowTitle("QuickSentinel — Busca e download Sentinel-2")
        self.resize(560, 560)

        self._scenes = []
        self._bbox = None

        self._build_ui()
        self._load_saved_credentials()
        self._use_canvas_extent()

    # ------------------------------------------------------------------ UI

    def _build_ui(self):
        layout = QVBoxLayout(self)

        form = QFormLayout()

        self.client_id_edit = QLineEdit()
        self.client_id_edit.setPlaceholderText("client_id (dataspace.copernicus.eu)")
        form.addRow("Client ID:", self.client_id_edit)

        self.client_secret_edit = QLineEdit()
        self.client_secret_edit.setEchoMode(QLineEdit.Password)
        self.client_secret_edit.setPlaceholderText("client_secret")
        form.addRow("Client Secret:", self.client_secret_edit)

        self.save_credentials_check = QPushButton("Salvar credenciais localmente")
        self.save_credentials_check.setCheckable(True)
        self.save_credentials_check.setChecked(True)
        form.addRow("", self.save_credentials_check)

        extent_row = QHBoxLayout()
        self.extent_label = QLabel("(nenhuma)")
        btn_use_extent = QPushButton("Usar extensão atual do mapa")
        btn_use_extent.clicked.connect(self._use_canvas_extent)
        extent_row.addWidget(self.extent_label, 1)
        extent_row.addWidget(btn_use_extent)
        form.addRow("Área de interesse:", extent_row)

        self.date_start = QDateEdit(calendarPopup=True)
        self.date_start.setDate(QDate.currentDate().addMonths(-3))
        form.addRow("Data inicial:", self.date_start)

        self.date_end = QDateEdit(calendarPopup=True)
        self.date_end.setDate(QDate.currentDate())
        form.addRow("Data final:", self.date_end)

        self.cloud_cover_spin = QSpinBox()
        self.cloud_cover_spin.setRange(0, 100)
        self.cloud_cover_spin.setValue(30)
        self.cloud_cover_spin.setSuffix(" % nuvens (máx.)")
        form.addRow("Cobertura de nuvens:", self.cloud_cover_spin)

        self.composite_combo = QComboBox()
        self.composite_combo.addItem("Cor real (RGB)", "true_color")
        self.composite_combo.addItem("Falso-cor (infravermelho)", "false_color")
        self.composite_combo.addItem("NDVI", "ndvi")
        form.addRow("Composição:", self.composite_combo)

        out_row = QHBoxLayout()
        self.output_dir_edit = QLineEdit(os.path.join(os.path.expanduser("~"), "QuickSentinel_downloads"))
        btn_browse = QPushButton("...")
        btn_browse.setMaximumWidth(32)
        btn_browse.clicked.connect(self._browse_output_dir)
        out_row.addWidget(self.output_dir_edit, 1)
        out_row.addWidget(btn_browse)
        form.addRow("Pasta de saída:", out_row)

        layout.addLayout(form)

        btn_search = QPushButton("Buscar cenas")
        btn_search.clicked.connect(self._on_search)
        layout.addWidget(btn_search)

        self.scene_list = QListWidget()
        self.scene_list.setSelectionMode(QListWidget.ExtendedSelection)
        layout.addWidget(self.scene_list, 1)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

        buttons = QDialogButtonBox()
        self.btn_download = buttons.addButton("Baixar selecionadas", QDialogButtonBox.ActionRole)
        self.btn_download.clicked.connect(self._on_download)
        buttons.addButton(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # -------------------------------------------------------------- helpers

    def _load_saved_credentials(self):
        settings = QSettings()
        self.client_id_edit.setText(settings.value(f"{SETTINGS_GROUP}/client_id", "", type=str))
        self.client_secret_edit.setText(settings.value(f"{SETTINGS_GROUP}/client_secret", "", type=str))

    def _maybe_save_credentials(self):
        if not self.save_credentials_check.isChecked():
            return
        settings = QSettings()
        settings.setValue(f"{SETTINGS_GROUP}/client_id", self.client_id_edit.text().strip())
        settings.setValue(f"{SETTINGS_GROUP}/client_secret", self.client_secret_edit.text().strip())

    def _use_canvas_extent(self):
        canvas = self.iface.mapCanvas()
        extent = canvas.extent()
        crs = canvas.mapSettings().destinationCrs()

        if crs.authid() != "EPSG:4326":
            from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject
            transform = QgsCoordinateTransform(crs, QgsCoordinateReferenceSystem("EPSG:4326"), QgsProject.instance())
            extent = transform.transformBoundingBox(extent)

        self._bbox = (extent.xMinimum(), extent.yMinimum(), extent.xMaximum(), extent.yMaximum())
        self.extent_label.setText(
            "{:.4f}, {:.4f}, {:.4f}, {:.4f}".format(*self._bbox)
        )

    def _browse_output_dir(self):
        directory = QFileDialog.getExistingDirectory(self, "Escolher pasta de saída", self.output_dir_edit.text())
        if directory:
            self.output_dir_edit.setText(directory)

    # --------------------------------------------------------------- slots

    def _on_search(self):
        if not self._bbox:
            QMessageBox.warning(self, "QuickSentinel", "Defina a área de interesse primeiro.")
            return

        client_id = self.client_id_edit.text().strip()
        client_secret = self.client_secret_edit.text().strip()
        if not client_id or not client_secret:
            QMessageBox.warning(self, "QuickSentinel", "Informe client_id e client_secret.")
            return

        self._maybe_save_credentials()

        try:
            token = get_access_token(client_id, client_secret)
        except SentinelAuthError as exc:
            QMessageBox.critical(self, "QuickSentinel", "Falha de autenticação:\n{}".format(exc))
            return

        start = self.date_start.date().toPyDate()
        end = self.date_end.date().toPyDate()
        max_cloud = self.cloud_cover_spin.value()

        self.status_label.setText("Buscando cenas...")
        try:
            self._scenes = search_scenes(token, self._bbox, start, end, max_cloud_cover=max_cloud)
        except Exception as exc:
            QMessageBox.critical(self, "QuickSentinel", "Falha na busca:\n{}".format(exc))
            self.status_label.setText("")
            return

        self._token = token

        self.scene_list.clear()
        for scene in self._scenes:
            cc = scene.get("cloud_cover")
            cc_txt = "{:.1f}% nuvens".format(cc) if cc is not None else "cobertura de nuvens desconhecida"
            item = QListWidgetItem("{} — {}".format(scene["date"], cc_txt))
            item.setData(1000, scene["date"])
            self.scene_list.addItem(item)

        self.status_label.setText("{} cena(s) encontrada(s).".format(len(self._scenes)))

    def _on_download(self):
        selected_items = self.scene_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "QuickSentinel", "Selecione ao menos uma cena na lista.")
            return
        if not getattr(self, "_token", None):
            QMessageBox.warning(self, "QuickSentinel", "Faça a busca antes de baixar.")
            return

        selected_dates = {item.data(1000) for item in selected_items}
        scenes_to_download = [s for s in self._scenes if s["date"] in selected_dates]

        composite = self.composite_combo.currentData()
        output_dir = self.output_dir_edit.text().strip()

        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, len(scenes_to_download))
        self.progress_bar.setValue(0)
        self._downloaded_count = 0

        def _on_progress(date_str, ok, resolution_m):
            self._downloaded_count += 1
            self.progress_bar.setValue(self._downloaded_count)
            status = "ok ({}m)".format(resolution_m) if ok else "falhou"
            self.status_label.setText("Baixando... {} — {}".format(date_str, status))

        results = download_scenes(
            self._token,
            self._bbox,
            scenes_to_download,
            composite,
            output_dir,
            progress_callback=_on_progress,
        )

        self.progress_bar.setVisible(False)

        if not results:
            QMessageBox.warning(self, "QuickSentinel", "Nenhuma cena pôde ser baixada.")
            return

        self.status_label.setText("{} de {} cena(s) baixada(s) em {}.".format(
            len(results), len(scenes_to_download), output_dir
        ))

        self._load_results_into_qgis(results)

    def _load_results_into_qgis(self, results):
        from qgis.core import QgsProject, QgsRasterLayer

        for result in results:
            layer_name = os.path.splitext(os.path.basename(result["path"]))[0]
            layer = QgsRasterLayer(result["path"], layer_name)
            if layer.isValid():
                QgsProject.instance().addMapLayer(layer)
