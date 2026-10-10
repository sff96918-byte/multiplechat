' EVA Dashboard — windowless launcher (no black console window)
' exe thakle exe chalabe, na thakle pythonw diye chalabe
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh  = CreateObject("WScript.Shell")
root = fso.GetParentFolderName(WScript.ScriptFullName)

exe = root & "\dist\EVA Dashboard\EVA Dashboard.exe"
If fso.FileExists(exe) Then
    sh.CurrentDirectory = fso.GetParentFolderName(exe)
    sh.Run """" & exe & """", 0, False
Else
    sh.CurrentDirectory = root
    sh.Run "pythonw -m eva.gui.dashboard", 0, False
End If
