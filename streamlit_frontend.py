"""Compatibility entrypoint for the FieldShift Streamlit dashboard."""
from pathlib import Path
import runpy

runpy.run_path(str(Path(__file__).resolve().parent / 'scripts' / 'streamlit_frontend.py'), run_name='__main__')
