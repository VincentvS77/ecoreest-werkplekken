# Eco Reest — Aanwezigheid & Werkplekken
## Deployment op Azure App Service

### Vereisten
- Azure CLI geïnstalleerd (`az` commando beschikbaar)
- Bestaande Azure resource group (bijv. `ecoreest-rg`)

---

### Stap 1 — Maak een App Service aan (eenmalig)

```bash
# Inloggen
az login

# App Service Plan (gratis tier)
az appservice plan create \
  --name ecoreest-werkplekken-plan \
  --resource-group ecoreest-rg \
  --sku B1 \
  --is-linux

# Web App aanmaken (Python 3.12)
az webapp create \
  --name ecoreest-werkplekken \
  --resource-group ecoreest-rg \
  --plan ecoreest-werkplekken-plan \
  --runtime "PYTHON:3.12"
```

---

### Stap 2 — Database pad instellen

De SQLite database wordt opgeslagen op `/home/ecoreest.db` (persistente opslag op Azure).

```bash
az webapp config appsettings set \
  --name ecoreest-werkplekken \
  --resource-group ecoreest-rg \
  --settings DB_PATH="/home/ecoreest.db"
```

---

### Stap 3 — Startup command instellen

```bash
az webapp config set \
  --name ecoreest-werkplekken \
  --resource-group ecoreest-rg \
  --startup-file "gunicorn --bind=0.0.0.0:8000 --timeout 600 app:app"
```

---

### Stap 4 — Code uploaden

Vanuit de projectmap (waar app.py staat):

```bash
cd pad/naar/ecoreest-werkplekken

# Zip de bestanden
zip -r deploy.zip app.py requirements.txt startup.txt templates/

# Upload naar Azure
az webapp deploy \
  --name ecoreest-werkplekken \
  --resource-group ecoreest-rg \
  --src-path deploy.zip \
  --type zip
```

---

### Stap 5 — Controleer

```bash
# Logs bekijken
az webapp log tail \
  --name ecoreest-werkplekken \
  --resource-group ecoreest-rg

# Of open direct in browser:
az webapp browse --name ecoreest-werkplekken --resource-group ecoreest-rg
```

De app is bereikbaar op:
`https://ecoreest-werkplekken.azurewebsites.net`

---

### Updates deployen (na wijzigingen)

Herhaal stap 4 — zip en upload opnieuw.

```bash
zip -r deploy.zip app.py requirements.txt startup.txt templates/
az webapp deploy \
  --name ecoreest-werkplekken \
  --resource-group ecoreest-rg \
  --src-path deploy.zip \
  --type zip
```

---

### Lokaal testen

```bash
pip install flask gunicorn
python app.py
# Open http://localhost:8000
```
