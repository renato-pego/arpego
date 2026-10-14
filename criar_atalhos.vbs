Set oWS = WScript.CreateObject("WScript.Shell")
sUserDesktop = oWS.SpecialFolders("Desktop")

Sub CreateShortcutIn(sFolder)
    Dim oFSO, sLinkFile1, sLinkFile2, oLink1, oLink2
    Set oFSO = CreateObject("Scripting.FileSystemObject")
    If oFSO.FolderExists(sFolder) Then
        sLinkFile1 = sFolder & "\ARPego.lnk"
        Set oLink1 = oWS.CreateShortcut(sLinkFile1)
        oLink1.TargetPath = "C:\Users\renat\OneDrive\Documentos\AssistentePessoal\ARPego.bat"
        oLink1.WorkingDirectory = "C:\Users\renat\OneDrive\Documentos\AssistentePessoal"
        oLink1.Description = "Assistente Pessoal - ARPego"
        oLink1.IconLocation = "C:\Users\renat\OneDrive\Documentos\AssistentePessoal\icon.ico,0"
        oLink1.WindowStyle = 7
        oLink1.Save

        On Error Resume Next
        If oFSO.FileExists(sFolder & "\Assistente Pessoal - ARPego.lnk") Then oFSO.DeleteFile(sFolder & "\Assistente Pessoal - ARPego.lnk")
        If oFSO.FileExists(sFolder & "\ARPego - Painel Web.url") Then oFSO.DeleteFile(sFolder & "\ARPego - Painel Web.url")
        If oFSO.FileExists(sFolder & "\ARPego - Base Forte (SQL Server).bat") Then oFSO.DeleteFile(sFolder & "\ARPego - Base Forte (SQL Server).bat")
        If oFSO.FileExists(sFolder & "\ARPego - Sincronizar Agora.bat") Then oFSO.DeleteFile(sFolder & "\ARPego - Sincronizar Agora.bat")
        If oFSO.FileExists(sFolder & "\ARPego.url") Then oFSO.DeleteFile(sFolder & "\ARPego.url")
        On Error GoTo 0
    End If
End Sub

CreateShortcutIn sUserDesktop
