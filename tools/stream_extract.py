# -*- coding: utf-8 -*-
r"""xdelta 로 «디코드하면서» 필요한 파일만 뽑아낸다 (709MB 를 디스크에 안 쓴다)

  python tools/stream_extract.py <원본.bin> <patch.xdelta> <xdelta.exe> <출력폴더> [파일…]

영문 패치본을 오라클로 쓰려는데 통째로 풀면 709MB 다. 표준출력으로 흘리면서
원하는 파일의 섹터 구간만 받아 적는다. MODE2/2352 이므로 섹터마다 +24 에서 2048 B.
"""
import os, re, subprocess, sys

RAW, OFF, USER = 2352, 24, 2048
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import discfs


def main():
    src, patch, xdelta, out = sys.argv[1:5]
    want = sys.argv[5:]
    _f, _vol, _rl, _rs, files = discfs.read_fs(src)
    # ⛔Git Bash 는 «/FONT.PXL» 같은 인수를 윈도 경로로 바꿔 버린다 — 파일 이름만 비교한다.
    base = {os.path.basename(w).upper() for w in want}
    todo = [(nm, lba, sz) for nm, lba, sz in files if not base or os.path.basename(nm).upper() in base]
    todo.sort(key=lambda t: t[1])
    os.makedirs(out, exist_ok=True)
    print('뽑을 파일 %d개 · %d B' % (len(todo), sum(t[2] for t in todo)))
    p = subprocess.Popen([xdelta, '-d', '-c', '-s', src, patch], stdout=subprocess.PIPE, bufsize=1 << 20)
    pos = 0                      # 스트림에서 읽은 바이트 수
    cur = 0                      # todo 색인
    outf = None
    left = 0
    sec = bytearray()
    end = max((lba + (sz + USER - 1) // USER) for _, lba, sz in todo) * RAW
    while cur < len(todo) and pos < end:
        want_lba = todo[cur][1]
        # 필요한 섹터까지 건너뛴다
        skip = want_lba * RAW - pos
        while skip > 0:
            b = p.stdout.read(min(skip, 1 << 22))
            if not b:
                raise SystemExit('⛔ 스트림이 일찍 끝났다 @%d' % pos)
            pos += len(b); skip -= len(b)
        nm, lba, sz = todo[cur]
        path = os.path.join(out, os.path.basename(nm))
        left = sz
        with open(path, 'wb') as f:
            while left > 0:
                sec = b''
                while len(sec) < RAW:
                    b = p.stdout.read(RAW - len(sec))
                    if not b:
                        raise SystemExit('⛔ 스트림이 일찍 끝났다 @%d' % pos)
                    sec += b
                pos += RAW
                n = min(USER, left)
                f.write(sec[OFF:OFF + n])
                left -= n
        print('  %-16s %d B' % (nm, sz))
        cur += 1
    p.stdout.close(); p.wait()
    print('끝 (스트림 %d B 소비)' % pos)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
