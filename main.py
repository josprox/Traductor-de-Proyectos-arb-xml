import sys
from PySide6.QtWidgets import QApplication
from controller.translation_controller import TranslatorAppController

if __name__ == "__main__":
    app = QApplication(sys.argv)
    controller = TranslatorAppController(app)
    sys.exit(app.exec())
