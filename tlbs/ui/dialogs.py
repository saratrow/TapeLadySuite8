from PySide6.QtWidgets import QDialog,QDialogButtonBox,QFormLayout,QLineEdit,QMessageBox,QVBoxLayout
from ..core.models import Customer
class NewCustomerDialog(QDialog):
    def __init__(self,parent=None):
        super().__init__(parent); self.setWindowTitle("New Customer"); self.setMinimumWidth(420)
        self.name=QLineEdit(); self.company=QLineEdit(); self.email=QLineEdit(); self.phone=QLineEdit()
        form=QFormLayout(); form.addRow("Name *",self.name); form.addRow("Company",self.company); form.addRow("Email",self.email); form.addRow("Phone",self.phone)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._validate); buttons.rejected.connect(self.reject)
        layout=QVBoxLayout(self); layout.addLayout(form); layout.addWidget(buttons)
    def _validate(self):
        if not self.name.text().strip(): QMessageBox.information(self,"Name required","Enter the customer's name."); return
        self.accept()
    def customer(self):
        return Customer(name=self.name.text().strip(),company=self.company.text().strip(),email=self.email.text().strip(),phone=self.phone.text().strip())
