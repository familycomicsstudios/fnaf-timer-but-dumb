#!/usr/bin/env python3
"""
Build script for FNaF Timer But Dumb
Generates a standalone EXE using PyInstaller
"""

import os
import subprocess
import sys

def build_exe():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    icon_path = os.path.join(script_dir, "fnaf-timer_256x256_32bit.ico")
    
    if not os.path.exists(icon_path):
        print(f"ERROR: Icon file not found at {icon_path}")
        sys.exit(1)
    
    # PyInstaller command - use venv python explicitly
    venv_python = os.path.join(script_dir, ".venv", "Scripts", "python.exe")
    if not os.path.exists(venv_python):
        venv_python = sys.executable
    
    cmd = [
        venv_python,
        "-m", "PyInstaller",
        "--onefile",                    # Single executable file
        "--windowed",                   # No console window
        f"--icon={icon_path}",          # Set icon
        "--add-data", "fnaf-timer_256x256_32bit.ico:.",  # Include icon in bundle
        "--name", "FNaF Timer But Dumb",  # Output executable name
        "--distpath", "dist",           # Output directory
        "--workpath", "build",          # Build directory
        "--specpath", ".",              # Spec file location
        "timer_app.py"
    ]
    
    print("Building EXE with PyInstaller...")
    print(f"Command: {' '.join(cmd)}")
    print()
    
    result = subprocess.run(cmd, cwd=script_dir)
    
    if result.returncode == 0:
        exe_path = os.path.join(script_dir, "dist", "FNaF Timer But Dumb.exe")
        print(f"\n✓ Build successful!")
        print(f"Executable: {exe_path}")
    else:
        print(f"\n✗ Build failed with return code {result.returncode}")
        sys.exit(1)

if __name__ == "__main__":
    build_exe()
