# Live deployment

This public repository's `main` branch is watched by the existing Bot-Hosting server every 15 seconds. Push or merge to main to deploy. Other branches are not deployed.

The active hosting entry is `.hosting/github_autodeploy.py`, installed from `deploy/github_autodeploy.py`. It maintains its own checkout and does not rely on the hosting dashboard's Git source selector. Runtime files and public assets are copied from main; tokens, environment settings and databases stay in place.

Python syntax is validated before switching. The server backs up its SQLite database and previous source, restarts a single web/bot instance, and checks health. Failed startup restores the previous source; database backups remain available. At most five recent bridge backups are retained. A rejected commit is retried after a new commit is pushed.

Deployment status is stored privately at `.hosting/deployed.json`; logs include `GitHub auto-deploy ready: main <commit>`. Hosting restart still starts the watcher. This mechanism does not renew the free hosting plan.

Changes to the deployment bridge itself require updating the installed `.hosting/github_autodeploy.py`; the application auto-update does not overwrite its own supervisor.
