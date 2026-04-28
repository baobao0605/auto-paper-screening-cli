Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "cmd /c """ & Replace(WScript.ScriptFullName, "start_gui_hidden.vbs", "start_gui.bat") & """", 0, False
