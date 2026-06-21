"""Host-side decrypt agent — wraps the Windows-only AlecaFrame DLL behind HTTP.

Runs as a system-tray app. Backend (in container) calls this over
host.docker.internal:8788 for on-demand refresh and to read the WFM JWT.
"""

__version__ = "0.1.0"
