# Restaurar SIMUTA v2 en Ubuntu

Archivos generados el 2026-06-18:

- `simutav2_full_20260618_153045.dump`: respaldo completo PostgreSQL, recomendado para restaurar la base desde cero.
- `simutav2_app_datos_20260618_153032.sql`: SQL solo con datos de usuarios, `core`, `academico` y `simulador`.
- `simutav2_datos_20260618_152942.json`: fixture Django portable de los mismos datos principales.

## Opcion recomendada: restaurar dump completo

```bash
createdb -U postgres simutav2
pg_restore -U postgres -d simutav2 --clean --if-exists --no-owner simutav2_full_20260618_153045.dump
```

## Opcion SQL solo datos

Usar sobre una base limpia donde ya corriste migraciones del proyecto:

```bash
python manage.py migrate
psql -U postgres -d simutav2 -f simutav2_app_datos_20260618_153032.sql
```

## Opcion fixture Django

Usar sobre una base limpia donde ya corriste migraciones del proyecto:

```bash
python manage.py migrate
python manage.py loaddata simutav2_datos_20260618_152942.json
```

Nota: para las opciones `sql` o `json`, el codigo en Ubuntu debe tener las migraciones hasta `simulador.0022`.
