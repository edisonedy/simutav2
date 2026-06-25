# Transferir datos locales a Ubuntu

Este paquete evita el problema de `pg_restore: unsupported version (1.16)` usando la fixture JSON de Django.

## Importante

La base de Ubuntu debe usar el mismo codigo/migraciones que esta maquina local. En esta maquina `simulador` llega hasta:

- `0020_eventosimulacion`
- `0021_accionsugeridasimulacion_costo_recursos_and_more`
- `0022_matrizevaluacioncaso_opcioncasosimulacion`

En Ubuntu no conviene seguir con la base actual si ya tiene migraciones faked o con otro `0020`. Lo mas limpio es recrear la base y cargar los datos.

## Archivos a copiar a Ubuntu

- `dumps/simutav2_datos_20260618_152942.json`
- `simulador/models.py`
- `simulador/migrations/0020_eventosimulacion.py`
- `simulador/migrations/0021_accionsugeridasimulacion_costo_recursos_and_more.py`
- `simulador/migrations/0022_matrizevaluacioncaso_opcioncasosimulacion.py`

Si Ubuntu tiene codigo viejo, primero copia/sube el proyecto actualizado completo.

## Comandos en Ubuntu

Desde `/home/django/simutav2`:

```bash
source .venv/bin/activate
systemctl stop simutav2

sudo -u postgres pg_dump -Fc simutav2 > /home/django/simutav2/backups/backup_antes_fixture_$(date +%F_%H%M).dump

sudo -u postgres psql -d postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='simutav2' AND pid <> pg_backend_pid();"
sudo -u postgres dropdb simutav2
sudo -u postgres createdb -O simutav2_user simutav2

python manage.py migrate
python manage.py loaddata dumps/simutav2_datos_20260618_152942.json
python manage.py collectstatic --noinput

systemctl start simutav2
systemctl status simutav2 --no-pager
```

## Verificar datos

```bash
python manage.py shell -c "from django.contrib.auth import get_user_model; from simulador.models import Simulacion, ConceptoEsperadoRonda; print('usuarios', get_user_model().objects.count()); print('simulaciones', Simulacion.objects.count()); print('conceptos', ConceptoEsperadoRonda.objects.count())"
```

Resultado esperado aproximado:

- usuarios: 8
- simulaciones: 87
- conceptos: 1036
