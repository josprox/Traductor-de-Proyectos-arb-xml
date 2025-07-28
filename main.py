import sys
from PySide6.QtWidgets import QApplication
from controller import TranslatorAppController # Importar el controlador

if __name__ == "__main__":
    app = QApplication(sys.argv)
    controller = TranslatorAppController(app) # Instanciar el controlador
    sys.exit(app.exec())
