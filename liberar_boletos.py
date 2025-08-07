# liberar_boletos.py

import os
from datetime import datetime, timedelta

# =============================================================================
# 1. IMPORTAR COMPONENTES CLAVE DE NUESTRA APP FLASK
# =============================================================================
# En lugar de redefinir los modelos de la base de datos o la configuración,
# importamos los objetos ya creados en nuestra aplicación principal.
# Esto es una excelente práctica para no repetir código (principio DRY).
from app import app, db, Boleto

# =============================================================================
# 2. CONFIGURACIÓN DEL SCRIPT
# =============================================================================
# Definimos cuánto tiempo puede estar un boleto apartado antes de ser liberado.
# Ponerlo como una constante aquí hace que sea fácil de cambiar en el futuro.
TIEMPO_LIMITE_MINUTOS = 120 # 2 horas

# =============================================================================
# 3. FUNCIÓN PRINCIPAL DE LIBERACIÓN
# =============================================================================
def liberar_boletos_expirados():
    """
    Busca y libera boletos cuyo tiempo de apartado ha expirado.
    """
    # Para que este script, que está fuera de Flask, pueda usar la configuración
    # de la base de datos (db) de la aplicación, necesitamos crear un "contexto de aplicación".
    # Es como decirle al script: "Actúa como si fueras la app de Flask por un momento
    # para poder usar sus herramientas".
    with app.app_context():
        print(f"Buscando boletos apartados por más de {TIEMPO_LIMITE_MINUTOS} minutos...")

        # 1. Calcular el momento límite en el pasado.
        #    Tomamos la hora actual (UTC, para ser consistentes) y le restamos
        #    el intervalo de tiempo que definimos.
        limite_de_tiempo = datetime.utcnow() - timedelta(minutes=TIEMPO_LIMITE_MINUTOS)

        # 2. Construir la consulta a la base de datos.
        #    Es como decirle a la base de datos: "Dame todos los boletos que
        #    cumplan ESTAS DOS condiciones a la vez:
        #      - Su estado debe ser 'apartado'.
        #      - Su fecha de apartado debe ser MÁS ANTIGUA que el momento límite."
        boletos_a_liberar = Boleto.query.filter(
            Boleto.estado == 'apartado',
            Boleto.fecha_apartado < limite_de_tiempo
        ).all()

        # 3. Procesar los boletos encontrados.
        cantidad_liberados = len(boletos_a_liberar)

        if cantidad_liberados > 0:
            print(f"Se encontraron {cantidad_liberados} boletos para liberar.")
            for boleto in boletos_a_liberar:
                print(f"  -> Liberando boleto #{boleto.numero_boleto} (apartado el {boleto.fecha_apartado.strftime('%Y-%m-%d %H:%M')})...")
                # Reseteamos sus valores al estado original
                boleto.estado = 'disponible'
                boleto.participante_id = None
                boleto.fecha_apartado = None
            
            # 4. Guardar todos los cambios en la base de datos.
            #    Hacemos un solo 'commit' al final, es más eficiente.
            db.session.commit()
            print(f"\n¡Proceso completado! Se liberaron exitosamente {cantidad_liberados} boletos.")
        else:
            print("No se encontraron boletos expirados. Todo en orden.")

# =============================================================================
# 4. PUNTO DE ENTRADA DEL SCRIPT
# =============================================================================
# Esta es la parte que permite que el script se ejecute desde la línea de comandos.
# Cuando Render (o tú) ejecute `python liberar_boletos.py`, se llamará a esta sección.
if __name__ == '__main__':
    print("=====================================================")
    print(f"INICIANDO SCRIPT DE LIBERACIÓN - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=====================================================")
    liberar_boletos_expirados()
    print("\nSCRIPT FINALIZADO.")
    print("=====================================================")