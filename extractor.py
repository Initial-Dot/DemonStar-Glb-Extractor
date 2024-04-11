import os
import re
import binascii
from io import BufferedReader

class sub_file_info:
    def __init__(self, idx:int, offset:int, len:int, name:str):
        self.idx = idx
        self.offset = offset
        self.len = len
        self.name = name
    
    
def readInt(f:BufferedReader):
    return int.from_bytes(f.read(4), 'little')


def readImage(f:BufferedReader):
    width = readInt(f)
    height = readInt(f)
    is_BMP = readInt(f)
    if width > 65535 or height > 65535 or width < 0 or height < 0:
        print('不是图像文件')
        return False
    if is_BMP == 1:
        readBmp(f, width, height)
        return False
    # 从这里开始读取glb自带的图像格式
    # 跳过一些无用数据 lines
    f.seek(4 * height, os.SEEK_CUR)
    while True:
        # posX:int, posY:int, count:int, colorArr:bytes[count]
        x = readInt(f)
        y = readInt(f)
        count = readInt(f)
        if x < 0 or x > width or y < 0 or y > height or count == -1:
            break
        colorBytes = binascii.hexlify(f.read(count)).decode()
        print(x,y,count, colorBytes)
    return True


def readBmp(f:BufferedReader, width:int, height:int):
    print('读取bmp文件')
    
    
while 1:
    prompt = input()
    if not prompt:
        continue
    if not os.path.exists(prompt):
        print('file no found.')
        continue
    dirs = prompt + '_extract'
    with open(prompt, 'rb') as f:
        if not os.path.exists(dirs):
            os.mkdir(dirs)
        header = f.read(8).decode()
        subfile_count = readInt(f)
        reserved_int = readInt(f)
        print(header,subfile_count)   
        f_infos:list[sub_file_info] = []
        for i in range(subfile_count):
            file_offset = readInt(f)
            file_len = readInt(f)
            file_name = f.read(20).decode()
            f_infos.append(sub_file_info(i, file_offset, file_len, re.sub(r'[\x01\\/*?:"<>|\0]', "", file_name)))
        for info in f_infos:
            f.seek(info.offset)
            print(info.name)
            if info.name == 'palette':
                continue
            if readImage(f):
                break
            # fb = f.read(info.len)
            # valid_name = re.sub(r'[\x01\\/*?:"<>|\0]', "", f'{info.idx}_{info.name}.bin')
            # print(valid_name)
            # with open(dirs + '\\' + valid_name, 'wb') as extract_f:
            #     extract_f.write(fb)
            
            
