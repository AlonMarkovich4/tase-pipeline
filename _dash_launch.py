"""Local preview launcher: load .env then run Streamlit."""
import os
import sys
import runpy

here = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(here, ".env")
if os.path.exists(env_path):
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

sys.argv = ["streamlit", "run", "dashboard.py",
            "--server.port=8501", "--server.headless=true",
            "--browser.gatherUsageStats=false"]
runpy.run_module("streamlit", run_name="__main__")
