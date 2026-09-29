# inemadlp

**🇧🇷 [Português](README.md) · 🇺🇸 [English](README.en.md) · 🇪🇸 [Español](README.es.md)**

Downloader personal de video y audio (FastAPI + yt-dlp) que funciona en tu VPS. Pegas el enlace desde el celular, la VPS descarga el archivo y te lo devuelve; el archivo se elimina solo después de 6 horas.

## 📖 Guía de uso

Guía completa (landing + paso a paso): **https://inematds.github.io/inemadlp/guia/es/**

---

## Índice

1. [Las tres claves de `.env`](#las-tres-claves-del-env)
2. [Antes de empezar](#antes-de-empezar)
3. [Paso a paso del deploy](#paso-a-paso-del-deploy)
4. [Acceso remoto y puertos](#acceso-remoto-y-puertos)
5. [Después de ponerlo en marcha: la primera descarga](#después-de-ponerlo-en-marcha-la-primera-descarga)
6. [Cookies](#cookies)
7. [Transcripción](#transcripción)
8. [Actualizar](#actualizar)
9. [Operación diaria](#operación-diaria)
10. [Cuando algo sale mal](#cuando-algo-sale-mal)

---

## Las tres claves de `.env`

`.env` tiene tres secretos con funciones **diferentes**. Conviene entenderlo antes de
generarlos, porque las consecuencias de que se filtre o se cambie cada uno no son iguales.

### `DLP_PASSWORD` — la contraseña que **tú** escribes

Es la única que usas manualmente. Es la que aparece en la pantalla de inicio de sesión. La escribes
una vez en el celular y nunca más, porque la sesión no vence.

- **Cambiarla:** edita la línea y ejecuta `docker compose restart app`. Las sesiones ya
  abiertas siguen siendo válidas (es intencional: cambiar la contraseña no cierra tu sesión).
- **Cuidado:** es lo único que hay entre internet y tu `cookies.txt`, que
  contiene la sesión de tu Google/YouTube/Instagram. No hay bloqueo por
  intentos fallidos, por diseño. Por eso **debe ser larga y aleatoria**,
  no una contraseña fácil de recordar.

### `DLP_SECRET_KEY` — la firma de la cookie de sesión

Nunca la escribes. Cuando ingresas la contraseña correctamente, el servidor devuelve una cookie
firmada con esta clave. En cada solicitud verifica la firma para saber
que él mismo emitió esa cookie y no alguien que la inventó.

- **Si se filtra:** cualquiera puede fabricar una cookie válida e ingresar **sin saber la
  contraseña**. Es tan grave como que se filtre la contraseña.
- **Si la cambias:** todos cierran sesión, incluso tú. Es precisamente el botón para
  "cerrar todas las sesiones"; úsalo si pierdes el celular.
- Es **independiente de la contraseña** y por eso cambiar la contraseña no cierra ninguna sesión.

### `DLP_UPLOAD_TOKEN` — la credencial del script

Sirve solo para `sync-cookies.sh`. Se ejecuta solo con cron, sin navegador ni
sesión, así que necesita demostrar quién es de otra manera: envía el token en el encabezado
`X-Upload-Token`.

Es una contraseña de máquina para **una sola ruta** (`POST /api/cookies`). No lista
jobs, no descarga archivos ni crea descargas.

- **Si se filtra:** el daño es limitado: pueden reemplazar tu `cookies.txt`, lo que
  interrumpiría tus descargas, pero no expone nada (la ruta solo recibe el
  archivo, nunca lo devuelve).
- **Si la cambias:** basta con actualizar la línea de cron.

**En resumen:** contraseña = tú ingresas · secret key = el servidor te reconoce después ·
upload token = el script ingresa solo por una puertita.

---

## Antes de empezar

Necesitas tener listas tres cosas:

| Qué | Por qué |
|---|---|
| Una **VPS Linux** con acceso `ssh` | ahí se ejecuta todo |
| **Docker + Compose** instalados | única dependencia; ffmpeg, yt-dlp y un runtime JS (Deno) vienen en la imagen |
| Un **subdominio** apuntado a la IP de la VPS | Caddy emite el certificado HTTPS automáticamente |

> YouTube empezó a exigir un runtime JavaScript para resolver sus desafíos
> antes de habilitar los formatos de video. Por eso la imagen ya incluye Deno y el
> soporte para EJS de yt-dlp, que se actualizan en cada inicio junto con el propio yt-dlp.

Instala Docker si todavía no lo tienes:

```bash
curl -fsSL https://get.docker.com | sh
```

El DNS debe estar configurado **antes** de ponerlo en marcha. En el panel de tu dominio, crea
un registro de tipo A:

```
Tipo   Nombre          Valor
A      dlp             203.0.113.10      ← la IP de tu VPS
```

Comprueba que se haya propagado (puede tardar unos minutos):

```bash
dig +short dlp.seudominio    # debe responder con la IP de la VPS
```

---

## Paso a paso del deploy

Todo lo siguiente se ejecuta **dentro de la VPS**, mediante `ssh`.

### Vía rápida: el instalador

Hace todo: genera los tres secretos, escribe `.env` con los permisos correctos, pone en marcha los
contenedores e imprime la contraseña al final:

```bash
ssh usuario@203.0.113.10

git clone https://github.com/inematds/inemadlp.git
cd inemadlp
./instalar.sh dlp.seudominio
```

Te avisa si el DNS todavía no apunta a la máquina, normaliza el dominio si lo pegas
por error con `https://` y, si ya existe un `.env`, pregunta antes de
modificarlo (ajusta solo el dominio, sin cambiar tu contraseña). Si vuelves a ejecutarlo después,
también detecta y corrige las líneas `DLP_DOMAIN` duplicadas.

Después, pasa a [Después de ponerlo en marcha](#después-de-ponerlo-en-marcha-la-primera-descarga).

### Vía manual

Si prefieres hacerlo a mano o entender cada parte:

### 1. Entrar a la VPS y clonar

```bash
ssh usuario@203.0.113.10

git clone https://github.com/inematds/inemadlp.git
cd inemadlp
```

### 2. Generar los tres secretos

Ejecuta los tres comandos y **guarda cada resultado**: lo pegarás en `.env` en el paso
siguiente:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(24))"   # → DLP_PASSWORD
python3 -c "import secrets; print(secrets.token_urlsafe(32))"   # → DLP_SECRET_KEY
python3 -c "import secrets; print(secrets.token_urlsafe(32))"   # → DLP_UPLOAD_TOKEN
```

La contraseña del primer comando es la que escribirás en el celular: guárdala en tu
administrador de contraseñas.

### 3. Completar `.env`

```bash
cp .env.example .env
nano .env          # o vim
```

Déjalo así, con los valores que acabas de generar:

```ini
DLP_PASSWORD=<salida del 1.er comando>
DLP_SECRET_KEY=<salida del 2.º comando>
DLP_UPLOAD_TOKEN=<salida del 3.er comando>
DLP_TTL_HOURS=6
DLP_DATA_DIR=/data
DLP_DOMAIN=dlp.seudominio
```

> **Edita la línea `DLP_DOMAIN` que ya existe**; no agregues otra con
> `echo ... >> .env`. Si hay dos líneas iguales, Docker usa la última y Caddy
> termina solicitando un certificado para el dominio equivocado. El síntoma es que el sitio no abre
> por un error de certificado, aunque todo lo demás parezca estar bien.

Protege el archivo: contiene los tres secretos en texto sin cifrar:

```bash
chmod 600 .env
```

### 4. Ponerlo en marcha

```bash
docker compose up --build -d
```

La primera compilación tarda unos minutos (descarga Python y ffmpeg). Puedes seguir el proceso:

```bash
docker compose logs -f
```

Debes ver `uvicorn running on http://0.0.0.0:8000` de la app y a Caddy
obteniendo el certificado. `Ctrl-C` sale de los registros sin detener nada.

### 5. Confirmar que está en línea

```bash
curl -I https://dlp.seudominio
```

Un `HTTP/2 200` significa que Caddy ya obtuvo el certificado y la app responde.
Si aparece un error de certificado, casi siempre se debe a que el DNS todavía no se propagó o a que el puerto
80 está cerrado; consulta la siguiente sección.

---

## Acceso remoto y puertos

**No tienes que configurar nada para acceder de forma remota, aparte del DNS.** El acceso es el propio
sitio: abre `https://dlp.seudominio` desde cualquier lugar, en el celular o en el
escritorio, e ingresa la contraseña. No hay VPN, túnel ni puertos
raros que tengas que recordar.

### Los puertos involucrados

| Puerto | Quién lo usa | ¿Debe estar abierto? |
|---|---|---|
| **443** | HTTPS: es por donde usas inemadlp | **sí** |
| **80** | Caddy, para emitir o renovar el certificado y redirigir al 443 | **sí** (sin este puerto no se emite el HTTPS) |
| **22** | Tu `ssh` para administrar la VPS | **sí** |
| 8000 | La app, **solo dentro** de la red de Docker | **no**, y no debe estarlo |

El puerto 8000 merece una nota: en `docker-compose.yml`, el servicio `app` usa
`expose`, no `ports`. Esto significa que solo se puede acceder a él **a través de** Caddy,
desde dentro de la red interna de Docker. No existe desde internet. Así
se garantiza que nadie llegue al servicio saltándose el HTTPS y la contraseña.

### Abrir el firewall

La mayoría de las VPS tiene **dos** firewalls: el del sistema y el del proveedor.

En el sistema (Ubuntu, con `ufw`):

```bash
sudo ufw allow OpenSSH      # no te bloquees el acceso
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status              # comprueba antes de cerrar la sesión ssh
```

En el panel del proveedor (security group de AWS, firewall de Oracle Cloud, DigitalOcean, Hetzner…), habilita los mismos puertos: **22, 80 y 443**. Este es el
paso que más se olvida: `ufw` queda bien configurado, el panel bloquea el tráfico y el certificado
nunca se emite.

### Hacer más segura la VPS (opcional, recomendado)

Como la máquina ahora está expuesta, conviene reforzar el `ssh`:

```bash
# usa una clave en vez de una contraseña y desactiva el inicio de sesión con contraseña
sudo nano /etc/ssh/sshd_config
#   PasswordAuthentication no
#   PermitRootLogin no
sudo systemctl restart ssh
```

---

## Después de ponerlo en marcha: la primera descarga

### 1. Instalarlo en el celular

Abre `https://dlp.seudominio` en el navegador del celular, escribe la contraseña y usa
**"Agregar a la pantalla de inicio"**. Aparecerá un ícono como si fuera una app. La sesión
no vence: no tendrás que volver a escribir la contraseña.

### 2. Enviar las cookies

Sin esto, es probable que YouTube rechace las descargas desde tu VPS, porque la
IP es de un centro de datos. En Edge o Chrome, con la sesión iniciada en
YouTube:

1. instala la extensión [**Get cookies.txt LOCALLY**](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc);
2. abre YouTube, haz clic en la extensión y exporta el `cookies.txt`;
3. en inemadlp, abre el panel **Cookies** y envía el archivo.

El panel mostrará la fecha del último envío.

### 3. Descargar

Pega la URL, elige **Video** (MP4, hasta 1080p) o **Audio** (M4A) y envíala. El
elemento aparecerá en la lista como "en cola", pasará a "descargando NN%" y terminará con el título
del video y un botón **Descargar**.

Recuerda: el archivo estará disponible durante **6 horas**. Después desaparecerá de la VPS y
tendrás que volver a ponerlo en cola. Si quieres más tiempo, cambia `DLP_TTL_HOURS` en
`.env` y reinicia.

---

## Cookies

### Por qué es necesario

YouTube (e Instagram, TikTok…) desconfía de las conexiones que vienen de centros de datos. Tu
VPS es un centro de datos. Sin cookies, la descarga falla con un mensaje como
*"Sign in to confirm you're not a bot"*.

Las cookies demuestran que hay una cuenta con sesión iniciada. Las obtienes de
**tu navegador**, donde ya tienes la sesión iniciada, y se las entregas a la VPS para que las use.

Las cookies **no son tu contraseña**. Son tu sesión ya iniciada. Aun así, quien
tenga el archivo puede entrar a tu cuenta; por eso solo permanece dentro de tu VPS,
protegido por la contraseña de inemadlp.

### Paso a paso (Windows, Edge o Chrome)

**1. Instalar la extensión**; solo una vez.

**Get cookies.txt LOCALLY** — enlace directo:
https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc

Es de código abierto y funciona sin conexión: lee las cookies del propio navegador y genera un
archivo, sin enviar nada a ninguna parte.

Funciona con Chrome y Edge. Edge la instala desde esa misma tienda
(la primera vez pide confirmación para permitir extensiones de otra tienda).

**2. Abrir el sitio y confirmar que iniciaste sesión**

Ve a `https://www.youtube.com` y comprueba si aparece tu foto de perfil en la esquina
superior derecha. Si no has iniciado sesión, hazlo. **Este paso es el que
importa**: la extensión solo copia lo que existe en ese momento.

**3. Exportar**

En la pestaña de YouTube, haz clic en el ícono de la extensión (quizás debas hacer clic en la
pieza de rompecabezas 🧩 para encontrarla) y elige **Export** (o *Export as*
→ `cookies.txt`).

Se descargará un archivo `cookies.txt` en tu carpeta de Descargas. Empieza con la línea
`# Netscape HTTP Cookie File`; inemadlp rechaza el archivo si esa línea no
está, precisamente porque yt-dlp también lo rechazaría.

inemadlp también acepta la exportación en **JSON** que ofrecen algunas versiones de esta y
otras extensiones. Si la página de exportación te permite elegir entre
`cookies.txt` y JSON, **prefiere `cookies.txt`**: es el formato que yt-dlp lee
de forma nativa, así que hay un paso de conversión menos y menos posibilidades de error. Si
el panel rechaza el archivo, el mensaje ahora explica el motivo (JSON malformado,
página HTML guardada por error, campos separados por espacios en vez de TAB,
archivo vacío, etc.) y qué hacer para corregirlo.

**4. Enviar a inemadlp**

1. abre `https://seu-dominio` (en la PC; es más fácil que en el celular);
2. inicia sesión con la contraseña, si te la pide;
3. abajo, haz clic en **Cookies** para abrir el panel;
4. haz clic en elegir archivo y selecciona el `cookies.txt` que acabas de descargar;
5. el panel responde con la cantidad de cookies recibidas y muestra la
   fecha del envío.

Listo. Ahora solo tienes que poner un enlace en la cola.

**5. Borrar el archivo descargado**

El archivo `cookies.txt` de tu carpeta de Descargas permite acceder a tu cuenta. Bórralo después de
enviarlo.

### Cuándo repetir estos pasos

Solo cuando falle una descarga. La interfaz muestra *"cookies expiradas; envía un
cookies.txt nuevo"* cuando reconoce el motivo, así que no tienes que adivinar.

En la práctica, las cookies de YouTube duran semanas, a veces meses. Las de Instagram y TikTok caducan mucho
más rápido. Repite los pasos 2 a 5 y vuelve a poner el enlace en cola: no hay
reintentos automáticos.

### Por qué no se puede automatizar en Windows

Edge y Chrome empezaron a cifrar las cookies con App-Bound Encryption a partir
de la versión 127: solo el propio proceso del navegador puede acceder a la clave. Ningún script
externo puede leer esas cookies, por más permisos que tenga. Por eso hay que exportarlas con la extensión.

### Atajo, solo si usas Firefox en Linux

Firefox guarda las cookies sin este cifrado, así que se pueden automatizar. En la
máquina Linux con Firefox y la sesión iniciada:

```bash
# obtén el token en la VPS:  grep DLP_UPLOAD_TOKEN .env
DLP_URL=https://seu-dominio DLP_UPLOAD_TOKEN=<token> ./sync-cookies.sh
```

Y, si quieres no volver a ver el error, puedes configurar un cron semanal:

```cron
0 9 * * 1 DLP_URL=https://seu-dominio DLP_UPLOAD_TOKEN=<token> /caminho/para/inemadlp/sync-cookies.sh
```

---

## Transcripción

Hay una tercera opción, además de Video y Audio: **Transcripción**, que usa
Whisper (`whisper-large-v3-turbo`) mediante la API de Groq. Hay dos formas de solicitarla:

- Directamente: pega el enlace y elige **Transcripción** en el formulario; el job descarga el
  audio y lo transcribe desde cero.
- A partir de un job listo: los jobs de video o audio con estado "listo" muestran
  un botón **Transcribir**, que reutiliza el archivo ya descargado en vez de buscar
  la fuente otra vez (solo vuelve a descargarlo si el archivo ya venció).

El texto aparece en la propia pantalla, en un bloque expandible con botón para copiar; está pensado
para celular, donde es molesto abrir un `.txt` descargado. También puedes descargar el `.txt`
con el botón de siempre.

**Limitación conocida por decisión de diseño: no se incluyen videos largos.**

La API de transcripción de Groq acepta archivos de hasta **25 MB**. El audio se
remuestrea a 16 kHz mono —el formato que Whisper usa internamente— y
se comprime en mp3 a 64 kbit/s (bitrate constante, así que el tamaño no depende
del contenido). Medición: ~481 KB por minuto, es decir, los 25 MB alcanzan para
aproximadamente **54 minutos de audio**.

Si supera ese límite, el job se **rechaza con un aviso** que indica la duración del audio y el límite,
sin consumir una llamada a la API. No hay división automática: sería posible cortar el
audio en partes y unir el texto, pero se dejó deliberadamente fuera para
mantenerlo simple. Por lo tanto, las clases largas y los podcasts no se transcriben
aquí; para eso, usa inemavox.

Requiere `GROQ_API_KEY` en `.env`. Si no está la clave, la opción no aparece en la interfaz.

Otros límites de Groq como referencia: 7.200 segundos de audio y 2.000
solicitudes por ventana de cuota. El modelo `whisper-large-v3-turbo` cuesta alrededor de
US$ 0,04 por hora de audio.

---

## Actualizar

En la VPS, basta con un comando:

```bash
cd inemadlp
./atualizar.sh
```

Trae el código nuevo, reconstruye la imagen, recrea los contenedores y comprueba que el
sitio vuelva a responder. Antes de todo eso, si hay ediciones locales sin
commit, **avisa y pregunta**; lo que se guarde va a `git stash`,
desde donde puedes recuperarlo con `git stash pop`. Nunca modifica `.env`: la contraseña, las claves,
las cookies y los archivos descargados permanecen donde están.

Si el historial local difiere del remoto, se detiene en vez de crear un merge
silencioso e indica cómo resolverlo.

Si lo prefieres, puedes hacerlo manualmente:

```bash
git pull
docker compose up -d --build
```

`--build` es obligatorio: sin eso, Docker reutiliza la imagen anterior y la
actualización no tiene ningún efecto.

Después de actualizar, la versión aparece discretamente en el pie de página de la interfaz
(`inemadlp vX.Y.Z`): basta con abrir el sitio y comprobar que coincida con la nueva versión
antes de considerar actualizada la VPS.

---

## Operación diaria

```bash
docker compose logs -f app     # ver qué está pasando
docker compose restart app     # reinicia y actualiza yt-dlp
docker compose down            # apaga (los datos de ./data se conservan)
docker compose up -d            # vuelve a encender
```

**Cambiar la contraseña:** edita `DLP_PASSWORD` en `.env` y ejecuta
`docker compose restart app`. Las sesiones abiertas siguen siendo válidas.

**Cerrar todas las sesiones** (celular perdido): cambia también
`DLP_SECRET_KEY` y reinicia. Entonces todos, incluyéndote, deberán iniciar sesión de nuevo.

**Actualizar el código:**

```bash
git pull && docker compose up --build -d
```

---

## Cuando algo sale mal

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| El sitio no abre; error de certificado | El DNS no se propagó o el puerto 80 está cerrado | `dig +short dlp.seudominio` y comprueba el firewall del proveedor |
| La descarga falla con "cookies expiradas" | Las cookies vencieron | expórtalas y envíalas de nuevo; después vuelve a poner el enlace en cola (no hay retry automático) |
| La descarga falla con "Requested format is not available" o la lista de formatos está vacía | YouTube requiere runtime JS (Deno/EJS) y la imagen está desactualizada | `docker compose pull && docker compose up -d --build`; en cada inicio se actualizan yt-dlp/deno automáticamente, pero quizá una imagen muy antigua aún no tenga soporte para EJS |
| La descarga falla con otro mensaje | La fuente no es compatible o la URL es incorrecta | el mensaje sin procesar de yt-dlp aparece en la lista |
| El archivo desapareció | Pasaron las 6 horas de TTL | vuelve a ponerlo en cola o aumenta `DLP_TTL_HOURS` |
| Un job queda atascado en "descargando" después de reiniciar | El contenedor se reinició en medio del proceso | cambia a "error" automáticamente al iniciar; vuelve a ponerlo en cola |
| El disco se está llenando | Poco probable (hay limpieza automática) | `du -sh data/downloads` y `docker compose logs app` |
