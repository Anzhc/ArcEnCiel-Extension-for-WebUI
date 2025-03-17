# install.py
import launch
from pathlib import Path

def install_req(check_name, install_name=None):
    if not install_name:
        install_name = check_name
    if not launch.is_installed(check_name):
        print(f"[ArcEnCiel] Installing {check_name} via pip...")
        launch.run_pip(f"install {install_name}", f"Installing {check_name}")

# Example: if you need requests, send2trash, etc.
install_req("requests")
install_req("send2trash")
install_req("beautifulsoup4", "beautifulsoup4==4.12.2")

print("[ArcEnCiel Extension] Finished install.py")
