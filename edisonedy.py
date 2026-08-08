import os, sys, django
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()
import os

os.environ.setdefault(
    'DJANGO_SETTINGS_MODULE',
    'config.settings'
)
import os

import psycopg


DB_NAME = os.getenv('DB_NAME', 'simutav2')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', '')
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '5432')


print('=' * 60)
print('REINICIANDO BASE DE DATOS')
print('=' * 60)

print(f'Base de datos: {DB_NAME}')
print(f'Servidor: {DB_HOST}:{DB_PORT}')
print()


# Nos conectamos a "postgres", NO a simutav2,
# porque simutav2 será eliminada.
conexion = psycopg.connect(
    dbname='postgres',
    user=DB_USER,
    password=DB_PASSWORD,
    host=DB_HOST,
    port=DB_PORT,
    autocommit=True,
)


with conexion.cursor() as cursor:

    print('1. Cerrando conexiones existentes...')

    cursor.execute(
        """
        SELECT pg_terminate_backend(pid)
        FROM pg_stat_activity
        WHERE datname = %s
          AND pid <> pg_backend_pid();
        """,
        [DB_NAME],
    )

    print('   OK')

    print()
    print(f'2. Eliminando base {DB_NAME}...')

    cursor.execute(
        f'DROP DATABASE IF EXISTS "{DB_NAME}"'
    )

    print('   OK')

    print()
    print(f'3. Creando nuevamente {DB_NAME}...')

    cursor.execute(
        f'CREATE DATABASE "{DB_NAME}"'
    )

    print('   OK')


conexion.close()


print()
print('=' * 60)
print('BASE DE DATOS RECREADA CORRECTAMENTE')
print('=' * 60)
print()
print('Ahora ejecuta:')
print()
print(r'.\.venv\Scripts\python.exe manage.py migrate')
print()
print('Después:')
print()
print(r'.\.venv\Scripts\python.exe manage.py check')