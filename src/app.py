from __future__ import annotations
import os, sys, subprocess, shutil
from pathlib import Path
from dotenv import dotenv_values, load_dotenv
from PySide6.QtCore import Qt, QThread, Signal, QUrl, QPropertyAnimation, QTimer
from PySide6.QtGui import QAction, QDesktopServices, QIcon, QPixmap
from PySide6.QtWidgets import (QApplication,QDialog,QDialogButtonBox,QDoubleSpinBox,QFileDialog,QFormLayout,QFrame,QGraphicsOpacityEffect,QGridLayout,QHBoxLayout,QLabel,QLineEdit,QListWidget,QMainWindow,QMessageBox,QPushButton,QProgressBar,QRadioButton,QSpinBox,QSplitter,QStackedLayout,QVBoxLayout,QWidget)
from database import Database
from job_manager import create_job_structure
from importer import import_receipt_folder
from processor import process_job
from review_app import ReviewWindow
from theme import apply_warm_classic
from version import APP_NAME, BUILD_DATE, VERSION
from window_geometry import restore_or_center, save_window_geometry
APP_ROOT=Path(__file__).resolve().parent.parent
ENV_PATH=APP_ROOT/'.env'
ENV_TXT_PATH=APP_ROOT/'.env.txt'
PLACEHOLDER_KEYS={'your_api_key_here','your_api*****here','your_api_key'}

def _repair_env_file():
    """Prefer a real .env.txt over a placeholder .env created by Notepad/older installers."""
    try:
        current=dotenv_values(ENV_PATH) if ENV_PATH.exists() else {}
        current_key=str(current.get('OPENAI_API_KEY') or '').strip()
        txt=dotenv_values(ENV_TXT_PATH) if ENV_TXT_PATH.exists() else {}
        txt_key=str(txt.get('OPENAI_API_KEY') or '').strip()
        current_is_bad=(not current_key) or current_key.lower() in PLACEHOLDER_KEYS
        txt_is_real=bool(txt_key) and txt_key.lower() not in PLACEHOLDER_KEYS
        if current_is_bad and txt_is_real:
            ENV_PATH.write_text(ENV_TXT_PATH.read_text(encoding='utf-8-sig'),encoding='utf-8')
            try: ENV_TXT_PATH.unlink()
            except OSError: pass
    except Exception:
        pass

_repair_env_file()
load_dotenv(ENV_PATH, override=True)
DB_PATH=APP_ROOT/'data'/'tapelady_receipts.db'; DEFAULT_CLIENTS_DIR=APP_ROOT/'clients'; ASSETS_DIR=APP_ROOT/'assets'; APP_ICON=ASSETS_DIR/'TapeLadySuite8.ico'; HEADER_LOGO=ASSETS_DIR/'Suite Logo White Long Header.png'
def env_float(name,default):
    try:return float(os.getenv(name,str(default)))
    except:return default
def env_int(name,default):
    try:return int(os.getenv(name,str(default)))
    except:return default
def update_env(updates):
    lines=ENV_PATH.read_text(encoding='utf-8').splitlines() if ENV_PATH.exists() else []
    left=dict(updates); out=[]
    for line in lines:
        if '=' in line and not line.lstrip().startswith('#'):
            k=line.split('=',1)[0].strip()
            if k in left: out.append(f"{k}={left.pop(k)}"); continue
        out.append(line)
    if out and out[-1].strip(): out.append('')
    out += [f"{k}={v}" for k,v in left.items()]
    ENV_PATH.write_text('\n'.join(out).rstrip()+'\n',encoding='utf-8')
    for k,v in updates.items(): os.environ[k]=v
class ProcessWorker(QThread):
    progress=Signal(int,int,str); finished_ok=Signal(dict); failed=Signal(str)
    def __init__(self,job_root): super().__init__(); self.job_root=job_root
    def run(self):
        try:
            load_dotenv(ENV_PATH, override=True)
            key=os.getenv('OPENAI_API_KEY','').strip()
            if not key: raise RuntimeError(f'OPENAI_API_KEY is missing from {ENV_PATH}')
            if key.lower() in PLACEHOLDER_KEYS or key.lower().startswith('your_api'):
                raise RuntimeError(f'The API key in {ENV_PATH} is still the sample placeholder. Open that exact file and replace OPENAI_API_KEY=your_api_key_here with your real key.')
            r=process_job(self.job_root,key,os.getenv('OPENAI_MODEL','gpt-4.1-mini'),env_float('MIN_READY_CONFIDENCE',0.92),os.getenv('EXPECTED_START_DATE',''),os.getenv('EXPECTED_END_DATE',''),lambda d,t,m:self.progress.emit(d,t,m),env_int('PROCESSING_WORKERS',3)); self.finished_ok.emit(r)
        except Exception as e:self.failed.emit(str(e))
class NewClientDialog(QDialog):
    def __init__(self,parent=None):
        super().__init__(parent); self.setWindowTitle('New Client'); l=QFormLayout(self); self.name=QLineEdit(); l.addRow('Client name',self.name); b=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel); b.accepted.connect(self.accept); b.rejected.connect(self.reject); l.addRow(b)
class NewJobDialog(QDialog):
    def __init__(self,parent=None):
        super().__init__(parent); self.setWindowTitle('New Job'); l=QFormLayout(self); self.name=QLineEdit(); self.location=QLineEdit(str(DEFAULT_CLIENTS_DIR)); x=QPushButton('Browse'); x.clicked.connect(self.choose); r=QHBoxLayout(); r.addWidget(self.location,1); r.addWidget(x); l.addRow('Job name',self.name); l.addRow('Store jobs in',r); b=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel); b.accepted.connect(self.accept); b.rejected.connect(self.reject); l.addRow(b)
    def choose(self):
        p=QFileDialog.getExistingDirectory(self,'Choose folder',self.location.text())
        if p:self.location.setText(p)

class ImportFolderDialog(QDialog):
    def __init__(self,parent=None):
        super().__init__(parent); self.setWindowTitle('Import Existing Receipt Folder'); self.setMinimumWidth(560); l=QVBoxLayout(self)
        intro=QLabel('Choose how the selected source folder is organized. Original files will only be copied—never moved, renamed, or overwritten.'); intro.setWordWrap(True); l.addWidget(intro)
        self.organized=QRadioButton('Preserve existing folder structure (scan this folder and all subfolders)'); self.organized.setChecked(True); l.addWidget(self.organized)
        self.unsorted=QRadioButton('Treat as one unsorted folder (scan files directly inside this folder only)'); l.addWidget(self.unsorted)
        form=QFormLayout(); self.location=QLineEdit(); browse=QPushButton('Browse'); browse.clicked.connect(self.choose); row=QHBoxLayout(); row.addWidget(self.location,1); row.addWidget(browse); form.addRow('Source folder',row); l.addLayout(form)
        note=QLabel('A manifest will record each receipt’s original path. Organized imports are flattened safely into Incoming with their subfolder names added to avoid filename collisions.'); note.setWordWrap(True); note.setStyleSheet('color:#666'); l.addWidget(note)
        b=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel); b.button(QDialogButtonBox.Ok).setText('Import Receipts'); b.accepted.connect(self.validate); b.rejected.connect(self.reject); l.addWidget(b)
    def choose(self):
        p=QFileDialog.getExistingDirectory(self,'Select receipt folder',self.location.text())
        if p:self.location.setText(p)
    def validate(self):
        p=Path(self.location.text().strip())
        if not p.is_dir(): QMessageBox.warning(self,'Select folder','Choose a valid source folder.'); return
        self.accept()
    def mode(self): return 'organized' if self.organized.isChecked() else 'unsorted'
    def source_folder(self): return Path(self.location.text().strip())

class SettingsDialog(QDialog):
    def __init__(self,parent=None):
        super().__init__(parent); self.setWindowTitle('Receipt Manager Settings'); self.setMinimumWidth(430); v=dotenv_values(ENV_PATH); l=QFormLayout(self)
        self.model=QLineEdit(str(v.get('OPENAI_MODEL') or 'gpt-4.1-mini'))
        self.ready=QDoubleSpinBox(); self.ready.setRange(.5,1); self.ready.setDecimals(2); self.ready.setValue(float(v.get('MIN_READY_CONFIDENCE') or .92))
        self.auto=QDoubleSpinBox(); self.auto.setRange(.5,1); self.auto.setDecimals(2); self.auto.setValue(float(v.get('AUTO_APPROVE_CONFIDENCE') or .95))
        self.start=QLineEdit(str(v.get('EXPECTED_START_DATE') or '')); self.end=QLineEdit(str(v.get('EXPECTED_END_DATE') or ''))
        self.workers=QSpinBox(); self.workers.setRange(1,6); self.workers.setValue(int(v.get('PROCESSING_WORKERS') or 3)); self.workers.setToolTip('More workers process receipts simultaneously. Start with 3; lower this if the API reports rate limits.')
        for label,w in [('OpenAI model',self.model),('Ready threshold',self.ready),('Auto Approve threshold',self.auto),('Parallel workers',self.workers),('Expected start date',self.start),('Expected end date',self.end)]: l.addRow(label,w)
        n=QLabel('Your OpenAI API key is intentionally not displayed here.'); n.setWordWrap(True); l.addRow(n)
        b=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel); b.accepted.connect(self.validate); b.rejected.connect(self.reject); l.addRow(b)
    def validate(self):
        if self.auto.value()<self.ready.value(): QMessageBox.warning(self,'Invalid thresholds','Auto Approve must be equal to or higher than Ready.'); return
        self.accept()
    def values(self): return {'OPENAI_MODEL':self.model.text().strip() or 'gpt-4.1-mini','MIN_READY_CONFIDENCE':f'{self.ready.value():.2f}','AUTO_APPROVE_CONFIDENCE':f'{self.auto.value():.2f}','PROCESSING_WORKERS':str(self.workers.value()),'EXPECTED_START_DATE':self.start.text().strip(),'EXPECTED_END_DATE':self.end.text().strip()}
class AboutDialog(QDialog):
    def __init__(self,parent=None):
        super().__init__(parent); self.setWindowTitle(f'About {APP_NAME}'); l=QVBoxLayout(self); h=QLabel(APP_NAME); h.setStyleSheet('font-size:22px;font-weight:bold'); l.addWidget(h); d=QLabel(f'<b>Version:</b> {VERSION}<br><b>Build date:</b> {BUILD_DATE}<br><b>Ready threshold:</b> {env_float("MIN_READY_CONFIDENCE",.92):.0%}<br><b>Auto Approve threshold:</b> {env_float("AUTO_APPROVE_CONFIDENCE",.95):.0%}<br><b>OpenAI model:</b> {os.getenv("OPENAI_MODEL","gpt-4.1-mini")}<br><b>Parallel workers:</b> {env_int("PROCESSING_WORKERS",3)}'); l.addWidget(d); b=QDialogButtonBox(QDialogButtonBox.Close); b.rejected.connect(self.reject); l.addWidget(b)
class DiagnosticsDialog(QDialog):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setWindowTitle('TapeLadySuite8 Diagnostics')
        self.setMinimumWidth(680)
        layout=QVBoxLayout(self)
        key_value=os.getenv('OPENAI_API_KEY','').strip()
        key_found=bool(key_value) and not key_value.lower().startswith('your_api')
        details=[
            f"Application folder: {APP_ROOT}",
            f"Configuration file: {ENV_PATH} ({'FOUND' if ENV_PATH.exists() else 'MISSING'})",
            f"API key loaded: {'YES' if key_found else 'NO'}",
            f"Database: {DB_PATH} ({'FOUND' if DB_PATH.exists() else 'MISSING'})",
            f"Clients folder: {DEFAULT_CLIENTS_DIR}",
            f"OpenAI model: {os.getenv('OPENAI_MODEL','gpt-4.1-mini')}",
            f"Python: {sys.executable}",
        ]
        box=QLabel('\n'.join(details)); box.setTextInteractionFlags(Qt.TextSelectableByMouse); box.setWordWrap(True); layout.addWidget(box)
        row=QHBoxLayout()
        open_env=QPushButton('Open App Folder'); open_env.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(APP_ROOT))))
        row.addWidget(open_env)
        copy=QPushButton('Copy Diagnostics'); copy.clicked.connect(lambda: QApplication.clipboard().setText('\n'.join(details)))
        row.addWidget(copy)
        close=QPushButton('Close'); close.clicked.connect(self.accept); row.addWidget(close)
        layout.addLayout(row)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__(); self.setWindowTitle(f'{APP_NAME} v{VERSION}'); self.resize(1100,720);
        if APP_ICON.exists(): self.setWindowIcon(QIcon(str(APP_ICON)))
        self.db=Database(DB_PATH); self.client_ids={}; self.job_records=[]; self.worker=None; self.review_window=None; self.build_menu(); self.build_ui(); self.refresh_clients(); self.apply_tlbs_context(); restore_or_center(self, "main_window")
    def build_menu(self):
        s=QAction('Settings',self); s.triggered.connect(self.open_settings); a=QAction(f'About {APP_NAME}',self); a.triggered.connect(lambda:AboutDialog(self).exec()); file_menu=self.menuBar().addMenu('File'); file_menu.addAction(s); shortcut=QAction('Create Desktop Shortcut',self); shortcut.triggered.connect(self.create_desktop_shortcut); file_menu.addAction(shortcut); help_menu=self.menuBar().addMenu('Help'); diagnostics=QAction('Diagnostics',self); diagnostics.triggered.connect(lambda:DiagnosticsDialog(self).exec()); help_menu.addAction(diagnostics); help_menu.addAction(a)
    def create_desktop_shortcut(self):
        script=APP_ROOT/'CREATE_DESKTOP_SHORTCUT.ps1'
        if os.name!='nt':
            QMessageBox.information(self,'Desktop shortcut','Desktop shortcut creation is available on Windows.')
            return
        if not script.exists():
            QMessageBox.warning(self,'Desktop shortcut','The shortcut helper is missing from this installation.')
            return
        try:
            result=subprocess.run([
                'powershell','-NoProfile','-ExecutionPolicy','Bypass','-File',str(script)
            ],capture_output=True,text=True,timeout=30)
            if result.returncode!=0:
                raise RuntimeError((result.stderr or result.stdout or 'Unknown PowerShell error').strip())
            QMessageBox.information(self,'Desktop shortcut','TapeLadySuite8 is now available from an icon on your desktop.')
        except Exception as exc:
            QMessageBox.warning(self,'Could not create shortcut',str(exc))

    def build_ui(self):
        c=QWidget(); self.setCentralWidget(c); outer=QVBoxLayout(c); outer.setContentsMargins(18,12,18,16); outer.setSpacing(9)

        header=QFrame(); header.setObjectName('headerCard'); header.setMaximumHeight(92)
        hl=QHBoxLayout(header); hl.setContentsMargins(12,4,12,4); hl.setSpacing(14)
        self.brand_logo=QLabel(); self.brand_logo.setObjectName('brandLogo')
        self.brand_logo.setMinimumWidth(500); self.brand_logo.setMaximumHeight(78)
        self.brand_logo.setAlignment(Qt.AlignLeft|Qt.AlignVCenter)
        if HEADER_LOGO.exists():
            logo=QPixmap(str(HEADER_LOGO))
            self.brand_logo.setPixmap(logo.scaled(760,74,Qt.KeepAspectRatio,Qt.SmoothTransformation))
        else:
            self.brand_logo.setText('TapeLadySuite8')
        hl.addWidget(self.brand_logo,1)

        badges=QFrame(); badges.setObjectName('headerBadges'); badge_layout=QHBoxLayout(badges); badge_layout.setContentsMargins(8,6,8,6); badge_layout.setSpacing(7)
        self.version_badge=QLabel(); self.version_badge.setObjectName('statusBadge')
        self.ready_badge=QLabel(); self.ready_badge.setObjectName('statusBadgeGreen')
        self.auto_badge=QLabel(); self.auto_badge.setObjectName('statusBadgeGold')
        self.worker_badge=QLabel(); self.worker_badge.setObjectName('statusBadgeTeal')
        for badge in (self.version_badge,self.ready_badge,self.auto_badge,self.worker_badge):
            badge.setAlignment(Qt.AlignCenter); badge_layout.addWidget(badge)
        hl.addWidget(badges)
        outer.addWidget(header); self.refresh_subtitle()

        self.logo_effect=QGraphicsOpacityEffect(self.brand_logo); self.brand_logo.setGraphicsEffect(self.logo_effect); self.logo_effect.setOpacity(0.0)
        self.logo_animation=QPropertyAnimation(self.logo_effect,b'opacity',self); self.logo_animation.setDuration(650); self.logo_animation.setStartValue(0.0); self.logo_animation.setEndValue(1.0)
        QTimer.singleShot(100,self.logo_animation.start)

        welcome=QLabel('Welcome back, Sara'); welcome.setObjectName('pageTitle'); outer.addWidget(welcome)
        tagline=QLabel('Receipt Manager  •  Preserve the paperwork. Protect the business.'); tagline.setObjectName('mutedText'); outer.addWidget(tagline)

        sp=QSplitter(Qt.Horizontal); outer.addWidget(sp,1)
        l=QFrame(); l.setObjectName('panelCard'); ll=QVBoxLayout(l); ll.setContentsMargins(14,14,14,14); clients_title=QLabel('Clients'); clients_title.setObjectName('sectionTitle'); ll.addWidget(clients_title)
        client_stack_widget=QWidget(); self.client_stack=QStackedLayout(client_stack_widget); self.client_stack.setContentsMargins(0,0,0,0)
        self.clients=QListWidget(); self.clients.currentTextChanged.connect(self.client_changed); self.client_stack.addWidget(self.clients)
        self.clients_empty=QLabel('No clients yet.\n\nClick “+ New Client” to begin.'); self.clients_empty.setObjectName('emptyState'); self.clients_empty.setAlignment(Qt.AlignCenter); self.clients_empty.setWordWrap(True); self.client_stack.addWidget(self.clients_empty)
        ll.addWidget(client_stack_widget,1); client_buttons=QHBoxLayout(); b=QPushButton('+ New Client'); b.setObjectName('accentButton'); b.clicked.connect(self.create_client); client_buttons.addWidget(b); delete_client=QPushButton('Delete Client'); delete_client.setObjectName('dangerButton'); delete_client.clicked.connect(self.delete_client); client_buttons.addWidget(delete_client); ll.addLayout(client_buttons); sp.addWidget(l)

        r=QFrame(); r.setObjectName('panelCard'); rl=QVBoxLayout(r); rl.setContentsMargins(14,14,14,14); jobs_title=QLabel('Receipt Jobs'); jobs_title.setObjectName('sectionTitle'); rl.addWidget(jobs_title)
        job_stack_widget=QWidget(); self.job_stack=QStackedLayout(job_stack_widget); self.job_stack.setContentsMargins(0,0,0,0)
        self.jobs=QListWidget(); self.jobs.currentRowChanged.connect(self.job_changed); self.job_stack.addWidget(self.jobs)
        self.jobs_empty=QLabel('Select a client to view jobs.'); self.jobs_empty.setObjectName('emptyState'); self.jobs_empty.setAlignment(Qt.AlignCenter); self.jobs_empty.setWordWrap(True); self.job_stack.addWidget(self.jobs_empty)
        rl.addWidget(job_stack_widget,1)
        row=QGridLayout(); row.setHorizontalSpacing(8); row.setVerticalSpacing(8); actions=[('New Job',self.create_job),('Delete Job',self.delete_job),('Import Receipt Folder',self.import_receipt_folder),('Open Incoming',self.open_incoming),('Process Receipts',self.process_receipts),('Review Receipts',self.review_receipts),('Retry Failed',self.retry_failed_receipts)]
        for i,(text,fn) in enumerate(actions):
            x=QPushButton(text); x.clicked.connect(fn); row.addWidget(x,i//3,i%3)
            if text=='Process Receipts': self.process_button=x; x.setObjectName('accentButton')
            if text=='Review Receipts': x.setObjectName('primaryButton')
            if text=='Delete Job': x.setObjectName('dangerButton')
        rl.addLayout(row); self.path_label=QLabel(); self.path_label.setObjectName('mutedText'); self.path_label.setWordWrap(True); rl.addWidget(self.path_label)
        status=QFrame(); status.setObjectName('accentCard'); sl=QVBoxLayout(status); sl.setContentsMargins(12,9,12,9); st=QLabel('Processing Status'); st.setObjectName('sectionTitle'); sl.addWidget(st); self.progress=QProgressBar(); sl.addWidget(self.progress); self.progress_text=QLabel('Ready'); self.progress_text.setObjectName('statusGood'); sl.addWidget(self.progress_text); rl.addWidget(status)
        sp.addWidget(r); sp.setSizes([300,800])

        footer=QHBoxLayout(); footer.addStretch(1)
        footer_text=QLabel(f"TapeLadySuite8 Receipt Manager  •  Version {VERSION}"); footer_text.setObjectName('mutedText'); footer.addWidget(footer_text); outer.addLayout(footer)

    def apply_tlbs_context(self):
        customer_name=os.getenv('TLBS_RECEIPT_CONTEXT_CUSTOMER','').strip()
        project_name=os.getenv('TLBS_RECEIPT_CONTEXT_PROJECT','').strip()
        job_root=os.getenv('TLBS_RECEIPT_CONTEXT_JOB_ROOT','').strip()
        customer_id=os.getenv('TLBS_RECEIPT_CONTEXT_CUSTOMER_ID','').strip()
        project_id=os.getenv('TLBS_RECEIPT_CONTEXT_PROJECT_ID','').strip()
        folder_path=os.getenv('TLBS_RECEIPT_CONTEXT_FOLDER_PATH','').strip()
        if not customer_name and not project_name and not job_root:
            return
        try:
            client_id=None
            for cid, name in self.db.list_clients():
                if name.casefold()==customer_name.casefold():
                    client_id=cid
                    break
            if client_id is None and customer_name:
                client_id=self.db.add_client(customer_name)
            if client_id and project_name and job_root:
                try:
                    self.db.add_job(client_id, project_name, job_root)
                except Exception:
                    pass
                self.refresh_clients()
                if customer_name in self.client_ids:
                    self.clients.setCurrentRow(self.clients.findItems(customer_name, Qt.MatchExactly)[0].row())
                    self.client_changed(customer_name)
            elif customer_name:
                self.refresh_clients()
                if customer_name in self.client_ids:
                    self.clients.setCurrentRow(self.clients.findItems(customer_name, Qt.MatchExactly)[0].row())
                    self.client_changed(customer_name)
            if customer_id and project_id and folder_path:
                self.path_label.setText(folder_path)
        except Exception:
            pass

    def refresh_subtitle(self):
        self.version_badge.setText(f'v{VERSION}')
        self.ready_badge.setText(f'● Ready {env_float("MIN_READY_CONFIDENCE",.92):.0%}')
        self.auto_badge.setText(f'⚡ Auto {env_float("AUTO_APPROVE_CONFIDENCE",.95):.0%}')
        self.worker_badge.setText(f'Workers {env_int("PROCESSING_WORKERS",3)}')

    def open_settings(self):
        d=SettingsDialog(self)
        if d.exec()==QDialog.Accepted: update_env(d.values()); self.refresh_subtitle(); QMessageBox.information(self,'Settings saved','New processing and review windows will use these settings.')
    def refresh_clients(self):
        self.clients.clear(); self.client_ids={}
        for cid,n in self.db.list_clients(): self.client_ids[n]=cid; self.clients.addItem(n)
        self.client_stack.setCurrentWidget(self.clients if self.clients.count() else self.clients_empty)
        if not self.clients.count():
            self.jobs.clear(); self.job_records=[]; self.jobs_empty.setText('Create a client first, then add a receipt job.'); self.job_stack.setCurrentWidget(self.jobs_empty)
    def client_changed(self,n):
        self.jobs.clear(); self.job_records=[]; self.path_label.clear()
        if not n:
            self.jobs_empty.setText('Select a client to view jobs.'); self.job_stack.setCurrentWidget(self.jobs_empty); return
        self.job_records=self.db.list_jobs(self.client_ids[n])
        for _,j,_ in self.job_records:self.jobs.addItem(j)
        if self.jobs.count(): self.job_stack.setCurrentWidget(self.jobs)
        else:
            self.jobs_empty.setText(f'No jobs yet for {n}.\n\nClick “New Job” to begin.'); self.job_stack.setCurrentWidget(self.jobs_empty)
    def job_changed(self,row): self.path_label.setText(self.job_records[row][2] if 0<=row<len(self.job_records) else '')
    def selected_job(self):
        row=self.jobs.currentRow()
        if not 0<=row<len(self.job_records): QMessageBox.information(self,'Select job','Select a job first.'); return None
        return Path(self.job_records[row][2])
    def create_client(self):
        d=NewClientDialog(self)
        if d.exec()!=QDialog.Accepted:return
        n=d.name.text().strip()
        if n:
            try:self.db.add_client(n); self.refresh_clients()
            except Exception as e:QMessageBox.warning(self,'Could not create client',str(e))
    def create_job(self):
        item=self.clients.currentItem()
        if not item:QMessageBox.information(self,'Select client','Select a client first.'); return
        d=NewJobDialog(self)
        if d.exec()!=QDialog.Accepted:return
        j=d.name.text().strip()
        if not j:return
        try:p=create_job_structure(Path(d.location.text()),item.text(),j); self.db.add_job(self.client_ids[item.text()],j,str(p)); self.client_changed(item.text())
        except Exception as e:QMessageBox.warning(self,'Could not create job',str(e))

    def delete_job(self):
        row=self.jobs.currentRow()
        if not 0<=row<len(self.job_records):
            QMessageBox.information(self,'Select job','Select the job you want to delete first.'); return
        job_id, job_name, root_path=self.job_records[row]
        answer=QMessageBox.warning(
            self,'Delete Job',
            f'Permanently delete the job “{job_name}” and all receipt files inside it?\n\n{root_path}\n\nThis cannot be undone.',
            QMessageBox.Yes|QMessageBox.No,QMessageBox.No)
        if answer!=QMessageBox.Yes:return
        try:
            path=Path(root_path)
            if path.exists(): shutil.rmtree(path)
            self.db.delete_job(job_id)
            current=self.clients.currentItem()
            self.client_changed(current.text() if current else '')
            QMessageBox.information(self,'Job deleted',f'“{job_name}” was deleted.')
        except Exception as e: QMessageBox.critical(self,'Could not delete job',str(e))

    def delete_client(self):
        item=self.clients.currentItem()
        if not item:
            QMessageBox.information(self,'Select client','Select the client you want to delete first.'); return
        name=item.text(); client_id=self.client_ids[name]; jobs=self.db.list_jobs(client_id)
        job_count=len(jobs)
        answer=QMessageBox.warning(
            self,'Delete Client',
            f'Permanently delete client “{name}” and {job_count} job{"s" if job_count!=1 else ""}, including all receipt files?\n\nThis cannot be undone.',
            QMessageBox.Yes|QMessageBox.No,QMessageBox.No)
        if answer!=QMessageBox.Yes:return
        try:
            roots=[Path(root) for _,_,root in jobs]
            for path in roots:
                if path.exists(): shutil.rmtree(path)
            # Remove the now-empty client folder when all jobs used the standard layout.
            parents={path.parent for path in roots}
            for parent in parents:
                try:
                    if parent.exists() and not any(parent.iterdir()): parent.rmdir()
                except OSError: pass
            self.db.delete_client(client_id)
            self.refresh_clients()
            QMessageBox.information(self,'Client deleted',f'“{name}” was deleted.')
        except Exception as e: QMessageBox.critical(self,'Could not delete client',str(e))

    def import_receipt_folder(self):
        job=self.selected_job()
        if not job:return
        d=ImportFolderDialog(self)
        if d.exec()!=QDialog.Accepted:return
        source=d.source_folder(); mode=d.mode()
        self.progress.setValue(0); self.progress_text.setText('Scanning source folder...')
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            result=import_receipt_folder(job,source,mode,self.on_progress)
        except Exception as e:
            QMessageBox.critical(self,'Import failed',str(e)); self.progress_text.setText('Import failed'); return
        finally:
            QApplication.restoreOverrideCursor()
        self.progress.setMaximum(max(result.discovered,1)); self.progress.setValue(result.discovered)
        self.progress_text.setText(f'Imported {result.imported} | Duplicate files skipped {result.skipped_duplicates} | Failed {result.failed}')
        message=(f'Found {result.discovered} supported receipt files.\n\n'
                 f'Imported: {result.imported}\n'
                 f'Duplicates skipped: {result.skipped_duplicates}\n'
                 f'Failed: {result.failed}\n\n'
                 'The customer’s original files were not changed.\n'
                 f'Import manifest: {result.manifest_path}')
        if result.imported:
            message += '\n\nYou can now click Process Receipts.'
        QMessageBox.information(self,'Import complete',message)

    def open_incoming(self):
        j=self.selected_job()
        if j:QDesktopServices.openUrl(QUrl.fromLocalFile(str(j/'Incoming')))
    def retry_failed_receipts(self):
        root=self.selected_job()
        if not root:return
        problems=root/'Problem_Receipts'; incoming=root/'Incoming'
        files=[p for p in problems.iterdir() if p.is_file() and p.suffix.lower() in {'.jpg','.jpeg','.png','.webp'}] if problems.exists() else []
        if not files:
            QMessageBox.information(self,'Retry Failed','There are no failed receipt images to restore.'); return
        answer=QMessageBox.question(self,'Retry Failed',f'Restore {len(files)} failed receipt image(s) to Incoming for another attempt?\n\nThe copies in Problem_Receipts will be kept.',QMessageBox.Yes|QMessageBox.No,QMessageBox.No)
        if answer!=QMessageBox.Yes:return
        incoming.mkdir(parents=True,exist_ok=True); restored=0
        for source in files:
            destination=incoming/source.name; n=2
            while destination.exists():
                destination=incoming/f'{source.stem}_{n}{source.suffix}'; n+=1
            shutil.copy2(source,destination); restored+=1
        QMessageBox.information(self,'Retry Failed',f'{restored} receipt image(s) were restored to Incoming.')

    def process_receipts(self):
        if self.worker and self.worker.isRunning(): QMessageBox.information(self,'Processing','Receipt processing is already running.'); return
        j=self.selected_job()
        if not j:return
        self.progress.setValue(0); self.progress_text.setText('Starting...'); self.worker=ProcessWorker(j); self.worker.progress.connect(self.on_progress); self.worker.finished_ok.connect(self.on_finished); self.worker.failed.connect(self.on_failed); self.process_button.setEnabled(False); self.worker.finished.connect(self.processing_stopped); self.worker.start()
    def processing_stopped(self): self.process_button.setEnabled(True); self.worker=None
    def on_progress(self,d,t,m): self.progress.setMaximum(max(t,1)); self.progress.setValue(d); self.progress_text.setText(m)
    def closeEvent(self, event):
        save_window_geometry(self, "main_window")
        super().closeEvent(event)
    def on_finished(self,r):
        self.progress.setValue(self.progress.maximum())
        warnings = int(r.get('checkpoint_warnings', 0) or 0)
        recovery = r.get('recovery_csv', '')
        status = f"Processed {r['processed']} | Skipped {r['skipped']} | Receipt errors {r['failed']} | Workers {r.get('workers',1)}"
        if recovery:
            status += " | Results saved to RECOVERY CSV"
        elif warnings:
            status += f" | Recovered from {warnings} temporary save lock(s)"
        self.progress_text.setText(status)
        if r.get('failed',0):
            message = (f"Processing finished with {r['failed']} receipt error(s).\n\n"
                       f"First error: {r.get('first_error') or 'Unknown error'}\n\n"
                       f"Error log: {r.get('log_path','')}\n\n"
                       "Failed originals were left in Incoming so they can be retried after the issue is fixed.")
            QMessageBox.critical(self,'Receipt processing errors',message)
            return
        message = 'Processing completed.'
        if recovery:
            message += ('\n\nThe normal review CSV was locked, probably by OneDrive or Excel. '
                        'No results were lost; they were saved as receipt_review_accuracy_RECOVERY.csv. '
                        'Close any open CSV window before processing again.')
        elif warnings:
            message += f'\n\nTapeLadySuite8 recovered from {warnings} temporary file lock(s). No results were lost.'
        message += '\n\nOpen Review Receipts now?'
        if QMessageBox.question(self,'Processing complete',message)==QMessageBox.Yes:self.review_receipts()
    def on_failed(self,m):
        self.progress_text.setText(f'Processing stopped: {m}')
        QMessageBox.critical(self,'Processing stopped',f'{m}\n\nThe receipts already completed remain saved. You can safely run Process Receipts again to continue with the remaining files.')
    def review_receipts(self):
        j=self.selected_job()
        if j:self.review_window=ReviewWindow(j,env_float('MIN_READY_CONFIDENCE',.92),env_float('AUTO_APPROVE_CONFIDENCE',.95)); self.review_window.show()
if __name__=='__main__':
    app=QApplication(sys.argv);
    if APP_ICON.exists(): app.setWindowIcon(QIcon(str(APP_ICON)))
    apply_warm_classic(app); w=MainWindow(); w.show(); sys.exit(app.exec())
