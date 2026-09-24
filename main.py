# -*- coding: utf-8 -*-
"""
一键运行回测流水线（先检查数据是否符合 data_spec.py 的规则，再依次运行各步骤）。

    python main.py                  # 全部步骤（NEUTRAL=False 时跳过 neutralize）
    python main.py testing long_short   # 只运行指定步骤
"""
import os
import subprocess
import sys

from settings import NEUTRAL
from data_spec import DATA_DIR, STAGES, validate

SCRIPTS = {
    'neutralize': 'factor_neutralize.py',
    'ic':         'IC_tests.py',
    'testing':    'position2nav_testing.py',
    'long_short': 'long_short.py',
    'update':     'positions2nav_update.py',
    'stats':      'nav2stats.py',
}


def main(stages):
    unknown = [s for s in stages if s not in SCRIPTS]
    if unknown:
        sys.exit(f'unknown stage(s) {unknown}; choose from {STAGES}')

    problems = validate(stages)
    if problems:
        print(f'DATA_DIR = {DATA_DIR}\n数据不符合规则：')
        for p in problems:
            print('  - ' + p)
        sys.exit(1)

    here = os.path.dirname(os.path.abspath(__file__))
    for stage in stages:
        print(f'\n========== {stage}: {SCRIPTS[stage]} ==========', flush=True)
        subprocess.run([sys.executable, os.path.join(here, SCRIPTS[stage])], cwd=here, check=True)


if __name__ == '__main__':
    main(sys.argv[1:] or [s for s in STAGES if NEUTRAL or s != 'neutralize'])
