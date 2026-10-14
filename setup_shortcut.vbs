
Set oWS = WScript.CreateObject("WScript.Shell")
sUserDesktop = oWS.SpecialFolders("Desktop")
sOneDriveDesktop = oWS.ExpandEnvironmentStrings("%USERPROFILE%") & "\OneDrive\Área de Trabalho"

Sub CreateShortcutIn(sFolder)
    Dim oFSO, sLinkFile, oLink
    Set oFSO = CreateObject("Scripting.FileSystemObject")
    If oFSO.FolderExists(sFolder) Then
        sLinkFile = sFolder & "\ARPego.lnk"
        Set oLink = oWS.CreateShortcut(sLinkFile)
        oLink.TargetPath = "C:\\Users\\renat\\OneDrive\\Documentos\\AssistentePessoal\\ARPego.bat"
        oLink.WorkingDirectory = "C:\\Users\\renat\\OneDrive\\Documentos\\AssistentePessoal"
        oLink.Description = "ARPego - Assistente Pessoal"
        oLink.IconLocation = "C:\\Users\\renat\\OneDrive\\Documentos\\AssistentePessoal\\icon.ico,0"
        oLink.WindowStyle = 7
        oLink.Save
        
        ' Limpa atalhos soltos extras para deixar apenas o oficial
        On Error Resume Next
        If oFSO.FileExists(sFolder & "\ARPego - Painel Web.url") Then oFSO.DeleteFile(sFolder & "\ARPego - Painel Web.url")
        If oFSO.FileExists(sFolder & "\ARPego - Base Forte (SQL Server).bat") Then oFSO.DeleteFile(sFolder & "\ARPego - Base Forte (SQL Server).bat")
        If oFSO.FileExists(sFolder & "\ARPego - Sincronizar Agora.bat") Then oFSO.DeleteFile(sFolder & "\ARPego - Sincronizar Agora.bat")
        If oFSO.FileExists(sFolder & "\ARPego.url") Then oFSO.DeleteFile(sFolder & "\ARPego.url")
        On Error GoTo 0
    End If
End Sub

CreateShortcutIn sUserDesktop
CreateShortcutIn sOneDriveDesktop
