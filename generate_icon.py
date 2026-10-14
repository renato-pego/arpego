"""
Gera o ícone oficial do ARPego (icon.ico) correspondente ao icon.svg do celular
e configura o atalho único ARPego.lnk na Área de Trabalho com a identidade visual.
"""

import os
import struct

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ICO_PATH = os.path.join(BASE_DIR, "icon.ico")
BAT_PATH = os.path.join(BASE_DIR, "ARPego.bat")

def create_ico_file():
    """Gera um arquivo icon.ico de 48x48 pixels em 32-bit RGBA com a cara do robozinho ARPego."""
    width = 48
    height = 48

    # Cria grid de pixels 48x48 (formato BGRA)
    # Inicializa transparente
    pixels = [[(0, 0, 0, 0) for _ in range(width)] for _ in range(height)]

    c_dark_bg = (0x16, 0x0d, 0x09, 0xff)    # #090d16
    c_cyan_border = (0xc7, 0x84, 0x02, 0xff) # #0284c7
    c_robot_head = (0x2a, 0x17, 0x0f, 0xff)  # #0f172a
    c_cyan_glow = (0xf8, 0xbd, 0x38, 0xff)   # #38bdf8
    c_white = (0xff, 0xff, 0xff, 0xff)

    # 1. Desenha cartão arredondado de fundo
    for y in range(height):
        for x in range(width):
            # Cantos arredondados (raio 10)
            dx = max(10 - x, 0, x - (width - 11))
            dy = max(10 - y, 0, y - (height - 11))
            if dx * dx + dy * dy <= 100:
                if x in (0, 1, width-2, width-1) or y in (0, 1, height-2, height-1):
                    pixels[y][x] = c_cyan_border
                else:
                    pixels[y][x] = c_dark_bg

    # 2. Cabeça do Robô (círculo centro 24, 21, raio 13)
    cx, cy, r = 24, 21, 13
    for y in range(cy - r - 2, cy + r + 3):
        for x in range(cx - r - 2, cx + r + 3):
            dist2 = (x - cx) ** 2 + (y - cy) ** 2
            if dist2 <= r * r:
                if dist2 >= (r - 2) * (r - 2):
                    pixels[y][x] = c_cyan_glow
                else:
                    pixels[y][x] = c_robot_head

    # 3. Olhos (centros em 19, 19 e 29, 19, raio 2)
    for ox in (19, 29):
        for y in range(17, 22):
            for x in range(ox - 2, ox + 3):
                if (x - ox) ** 2 + (y - 19) ** 2 <= 5:
                    pixels[y][x] = c_cyan_glow

    # 4. Sorriso (arco entre x=20 e 28, y=26)
    for x in range(20, 29):
        pixels[25][x] = c_cyan_glow
        pixels[26][x] = c_cyan_glow

    # 5. Antena (linha vertical em x=24 de y=7 a y=4, bolinha em y=4)
    for y in range(5, 8):
        pixels[y][24] = c_cyan_glow
    for y in range(2, 6):
        for x in range(22, 27):
            if (x - 24) ** 2 + (y - 4) ** 2 <= 4:
                pixels[y][x] = c_cyan_glow

    # 6. Orelhas laterais
    for y in range(19, 24):
        for x in range(9, 12):
            pixels[y][x] = c_cyan_border
        for x in range(36, 39):
            pixels[y][x] = c_cyan_border

    # 7. Barra de destaque inferior "ARPego"
    for y in range(37, 40):
        for x in range(12, 36):
            pixels[y][x] = c_cyan_glow

    # Monta dados BMP (linhas de baixo para cima)
    bmp_pixel_bytes = bytearray()
    for y in reversed(range(height)):
        for x in range(width):
            b, g, r_col, a = pixels[y][x]
            bmp_pixel_bytes.extend([b, g, r_col, a])

    # Máscara AND (1 bit por pixel, alinhado a 32 bits = 8 bytes por linha)
    and_mask_row = bytes(8)
    and_mask = and_mask_row * height

    # BITMAPINFOHEADER (40 bytes)
    bi_size = 40
    bi_width = width
    bi_height = height * 2  # 96
    bi_planes = 1
    bi_bit_count = 32
    bi_compression = 0
    bi_size_image = len(bmp_pixel_bytes)
    bi_xpels = 0
    bi_ypels = 0
    bi_clr_used = 0
    bi_clr_important = 0

    bih = struct.pack(
        '<IIIHHIIIIII',
        bi_size, bi_width, bi_height, bi_planes, bi_bit_count,
        bi_compression, bi_size_image, bi_xpels, bi_ypels,
        bi_clr_used, bi_clr_important
    )

    image_data = bih + bmp_pixel_bytes + and_mask
    image_size = len(image_data)
    image_offset = 22  # 6 (header) + 16 (dir entry)

    # ICO Header (6 bytes)
    ico_header = struct.pack('<HHH', 0, 1, 1)

    # ICO Directory Entry (16 bytes)
    ico_dir = struct.pack(
        '<BBBBHHII',
        width, height, 0, 0, 1, 32, image_size, image_offset
    )

    with open(ICO_PATH, 'wb') as f:
        f.write(ico_header + ico_dir + image_data)

    print(f"[OK] Ícone oficial gerado em: {ICO_PATH}")
    return ICO_PATH

def setup_desktop_shortcut():
    """Cria o atalho oficial ARPego.lnk na Área de Trabalho apontando para o ícone oficial."""
    create_ico_file()

    vbs_content = f'''Set oWS = WScript.CreateObject("WScript.Shell")
sUserDesktop = oWS.SpecialFolders("Desktop")

Sub CreateShortcutIn(sFolder)
    Dim oFSO, sLinkFile1, sLinkFile2, oLink1, oLink2
    Set oFSO = CreateObject("Scripting.FileSystemObject")
    If oFSO.FolderExists(sFolder) Then
        sLinkFile1 = sFolder & "\\ARPego.lnk"
        Set oLink1 = oWS.CreateShortcut(sLinkFile1)
        oLink1.TargetPath = "{BAT_PATH}"
        oLink1.WorkingDirectory = "{BASE_DIR}"
        oLink1.Description = "Assistente Pessoal - ARPego"
        oLink1.IconLocation = "{ICO_PATH},0"
        oLink1.WindowStyle = 7
        oLink1.Save

        sLinkFile2 = sFolder & "\\Assistente Pessoal - ARPego.lnk"
        Set oLink2 = oWS.CreateShortcut(sLinkFile2)
        oLink2.TargetPath = "{BAT_PATH}"
        oLink2.WorkingDirectory = "{BASE_DIR}"
        oLink2.Description = "Assistente Pessoal - ARPego"
        oLink2.IconLocation = "{ICO_PATH},0"
        oLink2.WindowStyle = 7
        oLink2.Save

        On Error Resume Next
        If oFSO.FileExists(sFolder & "\\ARPego - Painel Web.url") Then oFSO.DeleteFile(sFolder & "\\ARPego - Painel Web.url")
        If oFSO.FileExists(sFolder & "\\ARPego - Base Forte (SQL Server).bat") Then oFSO.DeleteFile(sFolder & "\\ARPego - Base Forte (SQL Server).bat")
        If oFSO.FileExists(sFolder & "\\ARPego - Sincronizar Agora.bat") Then oFSO.DeleteFile(sFolder & "\\ARPego - Sincronizar Agora.bat")
        If oFSO.FileExists(sFolder & "\\ARPego.url") Then oFSO.DeleteFile(sFolder & "\\ARPego.url")
        On Error GoTo 0
    End If
End Sub

CreateShortcutIn sUserDesktop
'''
    vbs_path = os.path.join(BASE_DIR, "criar_atalhos.vbs")
    with open(vbs_path, 'w', encoding='utf-8') as f:
        f.write(vbs_content)

    try:
        import subprocess
        subprocess.run(["wscript", vbs_path], check=False)
    except Exception:
        pass

    print(f"[OK] Script de atalho gerado e aplicado: {vbs_path}")

if __name__ == '__main__':
    setup_desktop_shortcut()
