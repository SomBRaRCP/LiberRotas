"""Run with: PYTHONPATH=src python examples/demo_liberrotas.py"""

import json

from trq_bec.cli import run_demo

print(json.dumps(run_demo(), indent=2, ensure_ascii=False))

