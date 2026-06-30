# Aviso de restaurantes nuevos en Valencia

Detecta restaurantes nuevos en Google (Valencia) y te avisa por email, sin
necesidad de tener ningún servidor propio encendido — todo corre gratis en
GitHub Actions.

## 1. Crea una API key de Google
1. Ve a https://console.cloud.google.com/
2. Crea un proyecto (o usa uno existente).
3. Activa la **Places API**.
4. Crea una API key en "Credenciales" y restríngela a la Places API.
5. Activa la facturación (Google da $200 gratis al mes; con una consulta
   diaria no llegarás a gastar nada).

## 2. Prepara tu email para enviar avisos
Si usas Gmail:
1. Activa la verificación en 2 pasos en tu cuenta.
2. Crea una "contraseña de aplicación" en
   https://myaccount.google.com/apppasswords
3. Usa esa contraseña (no la de tu cuenta normal) como `EMAIL_PASSWORD`.

Datos para Gmail: `SMTP_SERVER=smtp.gmail.com`, `SMTP_PORT=587`.

## 3. Sube estos archivos a un repositorio de GitHub
- `check_new_restaurants.py`
- `requirements.txt`
- `check_new_restaurants_workflow.yml` → muévelo a la ruta `.github/workflows/check_new_restaurants_workflow.yml` dentro del repo (GitHub solo detecta workflows en esa carpeta).

El repositorio puede ser privado.

## 4. Configura los "Secrets" del repositorio
En GitHub: Settings → Secrets and variables → Actions → New repository secret.
Crea estos seis secrets:
- `GOOGLE_API_KEY`
- `EMAIL_FROM`
- `EMAIL_PASSWORD`
- `EMAIL_TO`
- `SMTP_SERVER`
- `SMTP_PORT`

## 5. Listo
El workflow se ejecutará solo cada día a las 08:00 UTC. También puedes
lanzarlo a mano desde la pestaña "Actions" del repo ("Run workflow") para
probarlo al momento.

La primera ejecución no envía ningún email (solo guarda el estado inicial,
`state.json`, dentro del propio repo). A partir de la segunda ejecución,
cualquier restaurante nuevo que aparezca te llegará por correo.

## Limitación a tener en cuenta
El script busca por una **cuadrícula de 9 zonas** repartidas por Valencia
(en vez de una sola búsqueda) para evitar el límite de 60 resultados de
Google y cubrir mejor toda la ciudad. Puedes ajustar `GRID_POINTS` en
`check_new_restaurants.py` para añadir más puntos (más cobertura, más coste)
o quitarlos (menos coste).

Con 9 zonas y ejecución diaria, el consumo de la API se mantiene cómodamente
dentro del crédito gratuito mensual de Google ($200). Si en el futuro
añades más tipos de local (bares, cafeterías, etc.) o más puntos, el coste
sube proporcionalmente — en ese caso conviene pasar a ejecución semanal en
vez de diaria (solo hay que cambiar el cron en el workflow).

El email agrupa los restaurantes nuevos por zona de la cuadrícula, no por
código postal exacto (eso requeriría llamadas adicionales a la API de
Geocoding, con coste extra). Si en algún momento quieres precisión de
código postal real, puedo añadirlo.
