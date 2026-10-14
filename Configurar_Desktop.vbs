' =====================================================================
' Assistente Pessoal - ARPego - Configurador de Atalho Unico
' =====================================================================
Dim oWS, oFSO, sDesktop, sOneDriveDesktop, sUserDesktop
Set oWS = CreateObject("WScript.Shell")
Set oFSO = CreateObject("Scripting.FileSystemObject")

sDesktop = oWS.SpecialFolders("Desktop")
sUserDesktop = oWS.ExpandEnvironmentStrings("%USERPROFILE%") & "\Desktop"
sOneDriveDesktop = oWS.ExpandEnvironmentStrings("%USERPROFILE%") & "\OneDrive\Área de Trabalho"

Dim folders(2)
folders(0) = sDesktop
folders(1) = sUserDesktop
folders(2) = sOneDriveDesktop

Dim i, fld, sFile
Dim filesToDelete
filesToDelete = Array( _
    "ARPego - Painel Web.url", _
    "ARPego - Base Forte (SQL Server).bat", _
    "ARPego - Sincronizar Agora.bat", _
    "ARPego.url", _
    "ARPego.bat", _
    "ARPego.lnk", _
    "Assist Pe - Arpego.lnk" _
)

' 1. Remove atalhos antigos e temporarios
For i = 0 To UBound(folders)
    fld = folders(i)
    If oFSO.FolderExists(fld) Then
        Dim j
        For j = 0 To UBound(filesToDelete)
            sFile = fld & "\" & filesToDelete(j)
            If oFSO.FileExists(sFile) Then
                On Error Resume Next
                oFSO.DeleteFile sFile, True
                On Error GoTo 0
            End If
        Next
    End If
Next

' 2. Gera o icone oficial (.ico) com a identidade visual do robo azul
Dim sTargetPath, sWorkDir, sLinkFile, oLink
sTargetPath = "c:\Users\renat\OneDrive\Documentos\AssistentePessoal\ARPego.bat"
sWorkDir = "c:\Users\renat\OneDrive\Documentos\AssistentePessoal"

If oFSO.FileExists(sWorkDir & "\gerar_icone.py") Then
    On Error Resume Next
    oWS.Run "python """ & sWorkDir & "\gerar_icone.py""", 0, True
    On Error GoTo 0
End If

' 3. Cria o Atalho Oficial "Assistente Pessoal - ARPego.lnk"
For i = 0 To UBound(folders)
    fld = folders(i)
    If oFSO.FolderExists(fld) Then
        sLinkFile = fld & "\Assistente Pessoal - ARPego.lnk"
        On Error Resume Next
        Set oLink = oWS.CreateShortcut(sLinkFile)
        oLink.TargetPath = sTargetPath
        oLink.WorkingDirectory = sWorkDir
        oLink.Description = "Assistente Pessoal - ARPego (Nuvem e Desktop)"
        If oFSO.FileExists(sWorkDir & "\icon.ico") Then
            oLink.IconLocation = sWorkDir & "\icon.ico, 0"
        Else
            oLink.IconLocation = "%SystemRoot%\System32\shell32.dll, 220"
        End If
        oLink.Save
        On Error GoTo 0
    End If
Next

' 4. Remove este configurador para deixar a tela 100% limpa
On Error Resume Next
oFSO.DeleteFile WScript.ScriptFullName, True
On Error GoTo 0

MsgBox "Pronto! Área de Trabalho configurada com sucesso." & vbCrLf & vbCrLf & "Agora você tem apenas o ícone oficial com a identidade visual:" & vbCrLf & "👉 'Assistente Pessoal - ARPego'", vbInformation, "Assistente Pessoal - ARPego"
