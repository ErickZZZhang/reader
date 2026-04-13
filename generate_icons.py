"""
生成 PWA 图标: icon-192.png 和 icon-512.png
无需任何第三方库，运行一次即可
"""
import struct, zlib

def create_icon(filename, size):
    bg      = (26,  26,  26)   # #1a1a1a
    page_r  = (200, 149, 108)  # #c8956c  right page
    page_l  = (220, 185, 155)  # lighter  left page
    spine_c = (139, 94,  60)   # #8b5e3c  spine
    line_c  = (50,  45,  40)   # text lines

    book_t = int(size * 0.18)
    book_b = int(size * 0.84)
    book_l = int(size * 0.10)
    book_r = int(size * 0.90)
    mid    = size // 2
    sw     = max(2, int(size * 0.022))   # spine half-width

    line_ys = [int(size * p) for p in (0.34, 0.42, 0.50, 0.58, 0.66)]
    lh      = max(2, int(size * 0.018))
    lpad    = int(size * 0.06)

    def is_line(x, y, x1, x2):
        for ly in line_ys:
            if ly <= y <= ly + lh and x1 + lpad <= x <= x2 - lpad:
                return True
        return False

    pixels = bytearray()
    for y in range(size):
        pixels += b'\x00'           # PNG filter byte (none)
        for x in range(size):
            if book_t <= y <= book_b:
                if book_l <= x < mid - sw:
                    c = line_c if is_line(x, y, book_l, mid - sw) else page_l
                elif mid - sw <= x <= mid + sw:
                    c = spine_c
                elif mid + sw < x <= book_r:
                    c = line_c if is_line(x, y, mid + sw, book_r) else page_r
                else:
                    c = bg
            else:
                c = bg
            pixels += bytes(c)

    def chunk(tag, data):
        return (struct.pack('>I', len(data)) + tag + data +
                struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff))

    ihdr = chunk(b'IHDR', struct.pack('>IIBBBBB', size, size, 8, 2, 0, 0, 0))
    idat = chunk(b'IDAT', zlib.compress(bytes(pixels), 9))
    iend = chunk(b'IEND', b'')

    with open(filename, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n' + ihdr + idat + iend)
    print(f'  ✓ {filename}')

print('生成图标中…')
create_icon('icon-192.png', 192)
create_icon('icon-512.png', 512)
print('完成！')
