Option Explicit
Dim shell, fso, root, pythonw, appPy, cmd
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)
pythonw = fso.BuildPath(root, ".venv\Scripts\pythonw.exe")
appPy = fso.BuildPath(root, "src\app.py")
If Not fso.FileExists(pythonw) Then
    MsgBox "TapeLadySuite8 needs to finish installing. Please run INSTALL_TAPELADYSUITE8.bat.", 48, "TapeLadySuite8"
    WScript.Quit 1
End If
If Not fso.FileExists(appPy) Then
    MsgBox "TapeLadySuite8 application files are missing. Please run the installer again.", 16, "TapeLadySuite8"
    WScript.Quit 1
End If
cmd = Chr(34) & pythonw & Chr(34) & " " & Chr(34) & appPy & Chr(34)
shell.CurrentDirectory = root
shell.Run cmd, 0, False
