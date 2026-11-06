"""어느 폴더에서 실행해도 되는 테스트 실행기.

    python3 tests/run.py            # 전체
    python3 tests/run.py -k csv     # 이름에 csv 가 들어간 테스트만
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.argv[1:1] = ["discover", "-s", HERE, "-t", HERE]
unittest.main(module=None)
