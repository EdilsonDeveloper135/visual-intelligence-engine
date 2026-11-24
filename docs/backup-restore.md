# Respaldo y restauración

## Qué se guarda y dónde

| Dato | Volumen Docker | Incluido en `make backup` |
|---|---|---|
| Base de datos (observaciones, resultados, revisiones, chat, auditoría, configuración) | `vie_pgdata` | Sí (`db.dump`, formato `pg_dump -Fc`) |
| Originales inmutables y copias procesadas | `vie_files` | Sí (`files.tar.gz`) |
| Modelos de Ollama | `vie_ollama` | Solo con `make backup ARGS=--with-models` (se pueden volver a descargar) |
| Secretos (`.env`) | — | **No**: guárdelo aparte en un lugar seguro |

## Respaldar

Con el sistema en marcha:

```bash
make backup
```

Crea `data/backups/vie-AAAAMMDD-HHMMSS/` con `db.dump`, `files.tar.gz`, `manifest.json` y `SHA256SUMS`.

## Restaurar

```bash
make restore BACKUP=data/backups/vie-AAAAMMDD-HHMMSS
```

El script:

1. comprueba las sumas SHA-256 del respaldo;
2. pide escribir **RESTAURAR**;
3. hace un respaldo de seguridad del estado actual;
4. detiene frontend, api y worker;
5. reemplaza la base de datos (`pg_restore --clean`);
6. extrae los archivos sobre el volumen **sin borrar nada** (los archivos de observaciones que no existan en el respaldo quedan sin uso);
7. vuelve a iniciar los servicios.

## Recuperación completa en otro equipo

1. Copie el proyecto y su `.env`.
2. `make install` (con Internet) para construir imágenes y descargar modelos, o restaure `models.tar` si lo incluyó.
3. `make up`, luego `make restore BACKUP=…`.

## Verificación

`make test-persistence` comprueba que los datos sobreviven a `docker compose down` + `make up`. Los volúmenes solo se borran si alguien ejecuta explícitamente `docker compose down -v` o `docker volume rm`; ningún script del proyecto lo hace.
