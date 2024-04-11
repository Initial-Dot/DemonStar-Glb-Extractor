import os
import re
from PIL import Image
from io import BufferedReader

class sub_file_info:
    def __init__(self, idx:int, offset:int, len:int, name:str):
        self.idx = idx
        self.offset = offset
        self.len = len
        self.name = name
    
    
def readInt(f:BufferedReader):
    return int.from_bytes(bytes=f.read(4), byteorder='little', signed=True)


def readByte(f:BufferedReader):
    return int.from_bytes(f.read(1), 'little')


def readImage(f:BufferedReader, name:str):
    width = readInt(f)
    height = readInt(f)
    is_BMP = readInt(f)
    if width > 65535 or height > 65535 or width < 1 or height < 1:
        print('不是图像文件')
        return False
    if is_BMP == 1:
        readBmp(f, width, height)
        return False
    # 从这里开始读取glb自带的图像格式
    # 跳过一些无用数据 lines
    f.seek(4 * height, os.SEEK_CUR)
    # 先按宽高创建全透明的png对象
    png = Image.new('RGBA', (width, height))
    png.putalpha(0)
    while True:
        # posX:int, posY:int, count:int, colorArr:bytes[count]
        x = readInt(f)
        y = readInt(f)
        count = readInt(f)
        if x < 0 or x > width or y < 0 or y > height or count == -1:
            break
        for i in range(count):
            if x + i > width:
                print(x + i, '超出边界', width)
                continue
            pal = PAL[readByte(f)]
            png.putpixel((x + i, y), (pal.r, pal.g, pal.b, 255))
    print(name + '.png')
    png.save(name + '.png')
    return True


def readBmp(f:BufferedReader, width:int, height:int):
    print('读取bmp文件')


def convert_6bit_to_8bit(value):
    return (value << 2) | (value >> 4)


class RGBPAL:
    def __init__(self, r, g, b):
        self.r = convert_6bit_to_8bit(r)
        self.g = convert_6bit_to_8bit(g)
        self.b = convert_6bit_to_8bit(b)
        
        
PAL:list[RGBPAL] = []
def load_pal(f:BufferedReader):
    PAL.clear()
    for i in range(256):
        PAL.append(RGBPAL(readByte(f), readByte(f), readByte(f)))
    

if os.path.exists('palette'):
    with open('palette','rb') as pal_f:
        load_pal(pal_f)
        print('已载入默认色板')
        
if not os.path.exists('extracts'):
    os.mkdir('extracts')    
    
while 1:
    prompt = input()
    if not prompt:
        continue
    if not os.path.exists(prompt):
        print('file no found.')
        continue
    dirs = f'extracts/{prompt}_files'
    with open(prompt, 'rb') as f:
        if not os.path.exists(dirs):
            os.mkdir(dirs)
        header = f.read(8).decode()
        subfile_count = readInt(f)
        reserved_int = readInt(f)
        # print(header,subfile_count)   
        f_infos:list[sub_file_info] = []
        for i in range(subfile_count):
            file_offset = readInt(f)
            file_len = readInt(f)
            file_name = f.read(20).decode()
            f_infos.append(sub_file_info(i, file_offset, file_len, re.sub(r'[\x01\\/*?:"<>|\0]', "", file_name)))
        for info in f_infos:
            f.seek(info.offset)
            # print(info.name)
            if info.name == 'palette':
                load_pal(f)
            elif readImage(f, f'{dirs}/{info.idx}_{info.name}'):
                pass
            # fb = f.read(info.len)
            # with open(f'{dirs}/{info.name}.bin', 'wb') as extract_f:
            #     extract_f.write(fb)
            
            
