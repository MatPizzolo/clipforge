# C0: apagado de ClipForge

Fecha: 2026-11-19. Decisión del dueño: ClipForge se para entero y queda como fuente de diseño y código para un estudio de contenido nuevo. Se ejecutó desde la Mac del dueño (la máquina WSL anterior se borró, con su `.env`, `videos/` y `~/clipforge-x4/`).

Prioridad acordada: que no quede nada corriendo ni publicando. Credenciales, segunda copia del archivo y borrado de datos quedan para cuando se retome el proyecto (sección 4).

## 1. Qué se apagó

| Cuándo (UTC) | Qué | Cómo | Verificación |
|---|---|---|---|
| ya estaba (desde 2026-10-05, ADR-54) | Publicación | Freno `/pause` en Telegram | Logs del `dispatcher` antes de apagar: `realtalk-clips-en: braked` en cada tick; nada se publicaba |
| 2026-11-19 04:28 | App Modal `clipforge` (API, webhook de Telegram, pasos del pipeline y los 3 crons: `sweeper` cada 10 min, `dispatcher` cada 5 min con las alertas, `posting_daily` 07:00 UTC) | `uv run modal app stop clipforge` (lo corrió el dueño) | `modal app list`: `stopped`, `stopped_at 2026-11-19 01:28:04-03:00`; `GET https://matpizzolo--clipforge-web.modal.run/jobs/x` → 404 (antes 401) |
| 2026-11-19 ~16:50 | Panel en Vercel, proyecto `clipforge-web` | `vercel project rm clipforge-web` (lo corrió el dueño) | `vercel project ls` ya no lo lista; `https://clipforge-web-brown.vercel.app/` → 404 |

No se bajó el plan Vercel Pro: la misma cuenta aloja otros proyectos (boxealas.com, ztoked.com, bahia-vision-web y más). Sus $20/mes son de esos proyectos.

Apps de los spikes (`clipforge-x1`, `-x2`, `-x2-dl`, `-x4`): ya no figuraban en `modal app list`; nada que apagar.

## 2. Qué quedó guardado y dónde

Carpeta `~/archivo/clipforge-2026-11-19/` en la Mac del dueño (permisos 700), 2.1 GB, checksums en `SHA256SUMS` (48 archivos). Segunda copia liviana en Google Drive desde el 2026-11-19 (sección 4).

| Archivo | Contenido | Verificación |
|---|---|---|
| `neon-clipforge.dump` (formato custom) y `neon-clipforge.sql` (plano) | Base Neon completa, proyecto `fragrant-violet-23654229`, migración `0003`: cuentas, fuentes y permisos, cola, jobs, costos, autopilot, hooks | 24 tablas; conteo de filas por tabla idéntico entre la base y el dump (accounts 1, sources 1, source_events 1, content_items 30, posts 90, post_events 30, sends 10, jobs 12, costs 430, assets 30, hook_patterns 6, …) |
| `accounts.csv`, `sources.csv`, `source_events.csv` | Registro de cuentas y permisos de fuentes, legibles sin Postgres | — |
| `volume-jobs/<job_id>/job.zip` (10) | Clips, captions, `post.md` y `metadata.json` de cada job. La cola entera (30 piezas, 24 abiertas; algunas ya publicadas a mano: 2 TikTok, 2 Instagram, 3 YouTube) es del job `20260930-b8193698-5ea5` | `unzip -t` ok en los 10; el de la cola tiene los 30 `video.mp4` |
| `volume-jobs/posting/snapshots/` | Los 28 snapshots diarios (cola del Dict y tablas de la base, hasta 2026-11-18) | 28 de 28 |
| `volume-jobs/uploads/` | Episodio fuente subido (Billy Garton Jr., 273.5 MiB) y otro corto | — |
| `volume-models/refs/x1/v2_en.wav`, `v2_es.wav` | Voz de referencia diseñada en X1 | — |
| `neon.env` (permisos 600) | El connection string directo de Neon, para el dump | **Secreto:** no copiar ni subir; borrarlo cuando se borre Neon |

Blueprints, registro de cuentas (`docs/studio/09`), ADRs, specs y nombres de secretos (`docs/ops/secrets.md`) ya estaban en git.

No se guardó (regenerable o perdido):
- `clipforge-jobs:/cache/`: transcripciones y salidas de etapas, se regeneran.
- Pesos de modelos (`x2/`, `hf/`, `whisper/`): públicos en Hugging Face, con revisiones fijadas en `docs/studio/spikes/`.
- El `.env`, `videos/` con su ledger `.clipforge.json` y `~/clipforge-x4/` se perdieron con la máquina WSL.

## 3. Qué sigue existiendo (sin correr)

| Recurso | Estado | Costo esperado |
|---|---|---|
| App Modal `clipforge` | stopped (sin crons ni endpoints) | $0 |
| Volume `clipforge-models` (`x2/` ~227 GB, `hf/`, `whisper/`, `refs/`; `x4/` ya no estaba) | intacto | Modal incluye 1 TiB de Volumes y cobra $0.09/GiB-mes por encima (fuentes de terceros): debería dar $0. Confirmar en Modal → Usage |
| Volume `clipforge-jobs` (~2 GB de zips más `cache/`) | intacto | ídem |
| Dict `clipforge-job-state` | intacto; sus entradas vencen a los 7 días sin uso | $0 |
| Secret Modal `clipforge-secrets` | intacto; es la única copia de los valores y lo que permite redesplegar | $0 |
| Neon, proyecto `fragrant-violet-23654229` | intacto; sin la app no recibe conexiones y escala a cero | $0: plan Free (confirmado 2026-11-19, sección 4) |
| Bot de Telegram | token vigente; el webhook apunta a la app detenida y no responde | $0 |
| Repo `MatPizzolo/clipforge` | activo; Dependabot sigue abriendo PRs semanales | $0 |
| Upload-Post, secretos de GitHub Actions | nunca existieron | $0 |

## 4. Credenciales, segunda copia y borrados

### Hecho (2026-11-19, tarde)

| Cuándo (UTC) | Qué | Cómo | Verificación |
|---|---|---|---|
| ~17:05 | Credenciales guardadas en `clipforge-secrets` (Anthropic y proxy Decodo) | Prueba efímera con `modal run` (sin deploy) que monta el secret e imprime solo el código HTTP, nunca un valor | Anthropic `GET /v1/models` → **401**; proxy Decodo → **407**. Las dos ya no sirven |
| ~17:10 | Proxy Decodo (la contraseña se expuso en un chat) | El trial terminó y el dueño cerró la cuenta entera | Dashboard sin usuarios ni cuenta (lo miró el dueño); 407 de arriba. Los docs de `jarvis-idea` que nombran Decodo no tienen credenciales (grep por `usuario:clave@`: 0) |
| ~17:35 | Clave de Anthropic de ClipForge | El valor del secret ya da 401. La variable `ANTHROPIC_API_KEY` aparece en otros repos de code-dev (`clientes-estudio-abogacia`, `dilo-studio`, `shorts-*`, `old/…`), pero un grep de nombres no dice si comparten el valor; por eso se miró la consola | El dueño revisó console.anthropic.com → Settings → API Keys: no queda ninguna clave de ClipForge activa; 401 de arriba |
| ~17:15 | Plan de Neon | Lo miró el dueño en Neon → Billing | **Free**: $0 mientras exista |
| ~17:20 | **Segunda copia (liviana)** en Google Drive, carpeta `clipforge-copia-liviana` (subida por el dueño); copia local en `~/archivo/clipforge-copia-liviana/` (700) | 36 archivos, 407 MB, sin `neon.env`: dump y SQL de Neon, los 3 CSV, los 28 snapshots, `refs/x1` y el zip de la cola (`20260930-b8193698-5ea5`), con su propio `SHA256SUMS` | 36/36 OK contra el `SHA256SUMS` original, en el origen y en la copia local. En Drive: estructura completa y tamaños iguales a los locales (el conector no expone checksums); el dueño dio la subida por buena y decidió no bajarla para verificar los SHA256 en destino |

Fuera de la copia, a propósito: los otros 9 `job.zip` (re-cortes viejos) y el episodio fuente en `uploads/` (274 MB; se le puede volver a pedir al creador). Quedan solo en `~/archivo/clipforge-2026-11-19/`.

### Pendiente

Bloqueado hasta que exista `jarvis-idea/investigacion/C1-contenido.md` (el estudio v2 saca de acá lo que necesita). Cada borrado se muestra y espera el OK del dueño, uno por uno:
1. Neon: borrar el proyecto `fragrant-violet-23654229` en la consola y después `~/archivo/clipforge-2026-11-19/neon.env`.
2. C1 confirma que no necesita los 9 job.zip viejos ni el episodio fuente; si los necesita, se copian a Drive antes de borrar clipforge-jobs.
3. Volumes: `uv run modal volume delete clipforge-models` y `clipforge-jobs`.
4. Dict `clipforge-job-state` (`uv run modal dict delete`).
5. Token del bot de Telegram en BotFather (`/revoke`, o `/deletebot` para liberar el nombre) y las 2 apps OAuth de GitHub (Settings → Developer settings → OAuth Apps). Token de HF si existe.
6. Secret `clipforge-secrets` (`uv run modal secret delete`) y la app detenida (si la CLI de Modal no tiene cómo borrarla, queda stopped a $0).
7. Archivar el repo: `gh repo archive MatPizzolo/clipforge` (reversible con `unarchive`; frena Dependabot). Va último, porque después ya no se puede pushear este doc.

Con el paso 6 hecho, la sección 5 (volver atrás) deja de valer: solo queda restaurar desde el archivo.

## 5. Cómo volver atrás

- **App Modal:** `uv run modal deploy src/clipforge/app.py` desde `main` (`scripts/deploy.sh` necesita un `.env`, que ya no existe). Funciona mientras existan `clipforge-secrets`, Neon y el Volume `clipforge-jobs`. Después de más de 2 días detenida, `posting_daily` marca outage; restaurar con `clipforge status --restore` (runbook §2). Para eso la CLI necesita un `.env` nuevo con `API_URL` y `API_TOKEN`, y el valor de `API_TOKEN` solo está en el secret.
- **Panel:** `cd web && vercel deploy --prod`, cargando las variables de nuevo (runbook §5b).
- **Base, si ya se borró Neon:** proyecto nuevo y `pg_restore --no-owner -d "<url directa>" neon-clipforge.dump`.
