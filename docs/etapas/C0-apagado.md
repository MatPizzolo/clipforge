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

Carpeta `~/archivo/clipforge-2026-11-19/` en la Mac del dueño (permisos 700), 2.1 GB, checksums en `SHA256SUMS` (48 archivos). **Es la única copia** (sección 4).

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
| Neon, proyecto `fragrant-violet-23654229` | intacto; sin la app no recibe conexiones y escala a cero | $0 en Free. **Confirmar el plan en Neon → Billing**; si es Launch, borrarlo antes o bajarlo a Free |
| Bot de Telegram | token vigente; el webhook apunta a la app detenida y no responde | $0 |
| Repo `MatPizzolo/clipforge` | activo; Dependabot sigue abriendo PRs semanales | $0 |
| Upload-Post, secretos de GitHub Actions | nunca existieron | $0 |

## 4. Pendiente para cuando se retome

Decisiones ya tomadas (2026-11-19), sin ejecutar:
1. **Segunda copia** de `~/archivo/clipforge-2026-11-19/` (disco externo o Google Drive, sin `neon.env`) **antes** de los borrados 3 y 4.
2. Credenciales: revocar la clave de Anthropic de ClipForge (solo si no la comparte otro proyecto); revocar el token del bot en BotFather (`/revoke`, o `/deletebot` para liberar el nombre); borrar las 2 apps OAuth de GitHub del panel; borrar el usuario del proxy Decodo (su contraseña se expuso en un chat) y el token de HF si existe.
3. **Neon: exportar y borrar.** El export está hecho (sección 2). Falta borrar el proyecto en la consola de Neon y después `neon.env`.
4. **`clipforge-models`: bajar `refs/x1` y borrar todo.** `refs/x1` está bajado; falta `uv run modal volume delete clipforge-models`.
5. A decidir: borrar también `clipforge-jobs` y el Dict (el archivo tiene lo que importa), archivar el repo (`gh repo archive MatPizzolo/clipforge`, reversible con `unarchive`; frena Dependabot) y, al final de todo, el secret `clipforge-secrets` y la app detenida.

## 5. Cómo volver atrás

- **App Modal:** `uv run modal deploy src/clipforge/app.py` desde `main` (`scripts/deploy.sh` necesita un `.env`, que ya no existe). Funciona mientras existan `clipforge-secrets`, Neon y el Volume `clipforge-jobs`. Después de más de 2 días detenida, `posting_daily` marca outage; restaurar con `clipforge status --restore` (runbook §2). Para eso la CLI necesita un `.env` nuevo con `API_URL` y `API_TOKEN`, y el valor de `API_TOKEN` solo está en el secret.
- **Panel:** `cd web && vercel deploy --prod`, cargando las variables de nuevo (runbook §5b).
- **Base, si ya se borró Neon:** proyecto nuevo y `pg_restore --no-owner -d "<url directa>" neon-clipforge.dump`.
