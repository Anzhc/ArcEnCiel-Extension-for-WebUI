# /a1111/extensions/Arcenciel/install.py
import launch

# We'll use 'requests' for Arcenciel API calls.
if not launch.is_installed("requests"):
    launch.run_pip("install requests", "requirements for Arcenciel extension")
