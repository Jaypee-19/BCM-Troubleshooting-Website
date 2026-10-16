# BCM-Troubleshooting-Website

BCM troubleshooting guide website for users.

## Run locally on Windows

Install Python 3.12 or newer, then double-click `run.bat` or run it from a
terminal in this repository:

```powershell
.\run.bat
```

The launcher creates a virtual environment if needed, installs the packages
listed in `BCM Troubleshooting Web\troubleshoot-main\requirements.txt`, applies
database migrations, and starts the Django development server. Open
<http://127.0.0.1:8000/> in your browser. Keep the terminal open while using
the site; press Ctrl+C there to stop the server.
