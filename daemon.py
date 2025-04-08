import os
import sys
import time
import subprocess

def main():
    while True:
        print("Starting program")
        p = subprocess.Popen([sys.executable, 'main.py'])
        p.wait()
        print("Program exited")
        time.sleep(5)

def activate_venv(venv_name):
      if os.name == 'nt':  # Windows
          activate_script = os.path.join(venv_name, "Scripts", "activate")
      else:  # macOS and Linux
          activate_script = os.path.join(venv_name, "bin", "activate")
      
      try:
          subprocess.check_call(activate_script, shell=True)
          print(f"Virtual environment '{venv_name}' activated.")
      except subprocess.CalledProcessError as e:
          print(f"Error activating virtual environment: {e}")

if __name__ == "__main__":
    venv_name = "venv"
    activate_venv(venv_name)
    main()