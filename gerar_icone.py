import struct
import math
import os

def create_robot_ico(filepath):
    # Dimensao 48x48 para alta definicao na Area de Trabalho
    W, H = 48, 48
    pixels = [[(0, 0, 0, 0) for _ in range(W)] for _ in range(H)]

    def set_px(x, y, r, g, b, a=255):
        if 0 <= x < W and 0 <= y < H:
            pixels[y][x] = (b, g, r, a) # BGRA

    # 1. Fundo arredondado estilo App Icon (#090d16)
    radius = 10
    for y in range(H):
        for x in range(W):
            # Checa cantos arredondados
            dx = max(0, radius - 1 - x, x - (W - radius))
            dy = max(0, radius - 1 - y, y - (H - radius))
            if dx * dx + dy * dy <= radius * radius or (dx == 0 or dy == 0):
                # Gradiente sutil azul escuro / slate
                factor = y / H
                r = int(9 + factor * 5)
                g = int(13 + factor * 25)
                b = int(22 + factor * 60)
                set_px(x, y, r, g, b, 255)

    # 2. Borda sutil azul (#0284c7)
    for i in range(W):
        set_px(i, 2, 2, 132, 199, 180)
        set_px(i, H - 3, 2, 132, 199, 180)
    for j in range(H):
        set_px(2, j, 2, 132, 199, 180)
        set_px(W - 3, j, 2, 132, 199, 180)

    # 3. Antena (x=24, y=6..11) e esfera topo
    for y in range(6, 12):
        set_px(24, y, 56, 189, 248, 255)
        set_px(23, y, 56, 189, 248, 255)
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            if dx*dx + dy*dy <= 4:
                set_px(24 + dx, 5 + dy, 56, 189, 248, 255)

    # 4. Cabeca do Robo (circulo centro x=24, y=23, raio=12)
    head_cx, head_cy, head_r = 24, 23, 12
    for y in range(H):
        for x in range(W):
            d2 = (x - head_cx)**2 + (y - head_cy)**2
            if d2 <= head_r**2:
                if d2 >= (head_r - 2)**2: # Borda ciano #38bdf8
                    set_px(x, y, 56, 189, 248, 255)
                else: # Interior escuro #0f172a
                    set_px(x, y, 15, 23, 42, 255)

    # 5. Olhos ciano (#38bdf8)
    for eye_x in (19, 29):
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                if dx*dx + dy*dy <= 4:
                    set_px(eye_x + dx, 21 + dy, 56, 189, 248, 255)

    # 6. Sorriso ciano
    for dx in range(-4, 5):
        sy = 27 + int(abs(dx) * 0.35)
        set_px(head_cx + dx, sy, 56, 189, 248, 255)

    # 7. Orelhas / parafusos laterais (#0284c7)
    for ear_x in (10, 36):
        for y in range(21, 26):
            set_px(ear_x, y, 2, 132, 199, 255)
            set_px(ear_x + 1, y, 2, 132, 199, 255)

    # 8. Letras "ARP" na base (y=38..42)
    # Linha simples ciano
    for x in range(16, 32):
        set_px(x, 40, 56, 189, 248, 220)

    # Gerar estrutura binaria de arquivo .ICO
    # Bottom-up pixel rows
    pixel_data = bytearray()
    for y in reversed(range(H)):
        for x in range(W):
            b, g, r, a = pixels[y][x]
            pixel_data.extend(struct.pack('<BBBB', b, g, r, a))

    # Mask AND (1 bit por pixel, W * H / 8 bytes)
    row_bytes = (W + 31) // 32 * 4
    mask_data = bytearray(row_bytes * H)

    # BITMAPINFOHEADER (40 bytes)
    bih = struct.pack(
        '<IIIHHIIIIII',
        40,        # biSize
        W,         # biWidth
        H * 2,     # biHeight (duplo para XOR + AND mask)
        1,         # biPlanes
        32,        # biBitCount
        0,         # biCompression (BI_RGB)
        len(pixel_data), # biSizeImage
        0, 0, 0, 0
    )

    image_data = bih + pixel_data + mask_data

    # ICO Header (6 bytes)
    ico_header = struct.pack('<HHH', 0, 1, 1)

    # Directory Entry (16 bytes)
    ico_dir = struct.pack(
        '<BBBBHHII',
        W, H, 0, 0, 1, 32, len(image_data), 22 # Offset = 6 + 16
    )

    with open(filepath, 'wb') as f:
        f.write(ico_header + ico_dir + image_data)

if __name__ == '__main__':
    ico_path = os.path.join(os.path.dirname(__file__), 'icon.ico')
    create_robot_ico(ico_path)
    print(f"Icone gerado com sucesso: {ico_path}")
