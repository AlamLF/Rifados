# app.py

# =============================================================================
# 1. IMPORTACIONES
# =============================================================================
# Aquí traemos todas las "herramientas" que necesitamos para nuestro proyecto.
# - os: Para interactuar con el sistema operativo, específicamente para leer variables de entorno.
# - Flask: Es el corazón de nuestra aplicación web, el micro-framework.
# - render_template: La herramienta de Flask para dibujar plantillas HTML.
# - SQLAlchemy: Nuestro "traductor" entre código Python y la base de datos PostgreSQL.
# - datetime: Para manejar fechas y horas, que usaremos para la expiración de boletos.
# - urllib.parse: Para construir la URL de WhatsApp de forma segura
# =============================================================================
import os
from flask import Flask, render_template, request, redirect, url_for, flash, abort
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import urllib.parse

# =============================================================================
# 2. INICIALIZACIÓN Y CONFIGURACIÓN DE LA APLICACIÓN
# =============================================================================
# Creamos la aplicación y le damos un nombre.
app = Flask(__name__)


# Añadimos una SECRET_KEY para los mensajes flash ---
# Esta clave se usa para firmar criptográficamente los mensajes.
# ¡Es importante que sea un valor secreto y difícil de adivinar!
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'una-clave-secreta-muy-dificil-para-desarrollo')

# Leemos las nuevas variables de entorno ---
WHATSAPP_ADMIN = os.environ.get('WHATSAPP_ADMIN', '5560967913') 
ADMIN_SECRET_CODE = os.environ.get('ADMIN_SECRET_CODE', 'admin123')




# Leemos la URL de la base de datos desde una variable de entorno para mayor seguridad.
# Render (la plataforma donde desplegaremos) nos pedirá que configuremos esta variable.
# Si no la encuentra (porque estamos en nuestra computadora local), usamos una base de
# datos temporal de SQLite para facilitar el desarrollo.
DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    DATABASE_URL = "sqlite:///rifa_local.db"
    print("ADVERTENCIA: Variable de entorno DATABASE_URL no encontrada. Usando base de datos SQLite local.")

# Configuramos Flask para que sepa dónde está la base de datos y otras opciones.
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False # Recomendado para evitar sobrecarga.

# Inicializamos el objeto de base de datos, que nos permitirá interactuar con ella.
db = SQLAlchemy(app)

# =============================================================================
# ¡NUEVO! PROCESADOR DE CONTEXTO PARA INYECTAR EL AÑO ACTUAL
# =============================================================================
# Esta función se ejecutará para todas las peticiones y hará que la variable 'year'
# esté disponible en todas las plantillas Jinja2.

@app.context_processor
def inject_year():
    """ Inyecta el año actual en el contexto de la plantilla. """
    return {'year': datetime.utcnow().year}

# =============================================================================
# 3. MODELOS DE DATOS (LOS "PLANOS" DE NUESTRAS TABLAS)
# =============================================================================
# Estos modelos le dicen a SQLAlchemy cómo debe ser la estructura de nuestras
# tablas en la base de datos. Cada clase es una tabla, y cada atributo es una columna.

class Participante(db.Model):
    """Representa a una persona que compra uno o más boletos."""
    __tablename__ = 'participantes'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    telefono = db.Column(db.String(20), nullable=False)

    # La relación 'boletos' nos permite acceder a todos los boletos de un participante
    # de forma sencilla (ej: mi_participante.boletos).
    boletos = db.relationship('Boleto', backref='participante', lazy=True)

    def __repr__(self):
        return f'<Participante {self.nombre}>'

class Boleto(db.Model):
    """Representa un único boleto en la rifa."""
    __tablename__ = 'boletos'

    id = db.Column(db.Integer, primary_key=True)
    numero_boleto = db.Column(db.Integer, unique=True, nullable=False)
    estado = db.Column(db.String(20), nullable=False, default='disponible') # Estados: 'disponible', 'apartado', 'vendido'
    fecha_apartado = db.Column(db.DateTime, nullable=True)

    # Clave foránea que vincula este boleto con el participante que lo apartó.
    participante_id = db.Column(db.Integer, db.ForeignKey('participantes.id'), nullable=True)

    def __repr__(self):
        return f'<Boleto {self.numero_boleto} ({self.estado})>'

# =============================================================================
# 4. RUTAS DE LA APLICACIÓN (LAS "PÁGINAS" DE NUESTRO SITIO)
# =============================================================================
# Las rutas le dicen a Flask qué código ejecutar cuando un usuario visita una URL.

@app.route('/')
def index():
    """
    Página principal que muestra la cuadrícula de todos los boletos.
    """
    # 1. Obtenemos todos los boletos de la base de datos, ordenados por su número.
    todos_los_boletos = Boleto.query.order_by(Boleto.numero_boleto).all()

    # 2. Le pasamos los boletos a la plantilla 'index.html' para que los dibuje.
    return render_template('index.html', boletos=todos_los_boletos)

@app.route('/apartar/<int:numero_boleto>', methods=['GET', 'POST'])
def apartar(numero_boleto):
    """
    Página para que un usuario aparte un boleto.
    - GET: Muestra el formulario si el boleto está disponible.
    - POST: Procesa los datos del formulario, actualiza el boleto y crea el participante.
    """
    boleto = Boleto.query.filter_by(numero_boleto=numero_boleto).first_or_404()

    if request.method == 'POST':
        # --- LÓGICA PARA PROCESAR EL FORMULARIO (POST) ---
        if boleto.estado != 'disponible':
            flash('¡Lo sentimos! Alguien más apartó este boleto mientras llenabas el formulario.', 'danger')
            return redirect(url_for('index'))

        nombre = request.form.get('nombre')
        email = request.form.get('email')
        telefono = request.form.get('telefono')

        # Buscar si el participante ya existe por su email
        participante = Participante.query.filter_by(email=email).first()
        if not participante:
            # Si no existe, creamos uno nuevo
            participante = Participante(nombre=nombre, email=email, telefono=telefono)
            db.session.add(participante)
            # Hacemos un 'flush' para que el nuevo participante obtenga un ID
            # antes de asignarlo al boleto.
            db.session.flush()

        # Actualizamos los datos del boleto
        boleto.estado = 'apartado'
        boleto.participante_id = participante.id
        boleto.fecha_apartado = datetime.utcnow()

        # Guardamos todos los cambios en la base de datos
        db.session.commit()

        # Creamos el mensaje para WhatsApp
        mensaje = f"¡Hola! Quiero confirmar que he apartado el boleto número *{boleto.numero_boleto}* de la rifa. Mis datos son:\nNombre: {nombre}\nEmail: {email}"
        mensaje_codificado = urllib.parse.quote(mensaje)

        # Redirigimos a la URL de WhatsApp
        url_whatsapp = f"https://wa.me/{WHATSAPP_ADMIN}?text={mensaje_codificado}"
        return redirect(url_whatsapp)

    # --- LÓGICA PARA MOSTRAR LA PÁGINA (GET) ---
    if boleto.estado != 'disponible':
        flash(f'El boleto {numero_boleto} ya no está disponible.', 'warning')
        return redirect(url_for('index'))

    return render_template('apartar.html', boleto=boleto)

# =============================================================================
# 5. SCRIPT DE INICIALIZACIÓN
# =============================================================================
# Este bloque se ejecuta una vez al iniciar la aplicación. Es perfecto para
# crear las tablas en la base de datos si no existen y para llenarla con
# datos iniciales para las pruebas.

with app.app_context():
    # Se asegura de que todas las tablas definidas en los modelos existan.
    db.create_all()

    # Si no hay boletos en la base de datos...
    if Boleto.query.count() == 0:
        print("Base de datos vacía. Creando 100 boletos iniciales...")
        # ...creamos 100 boletos, del 0 al 99.
        for i in range(0, 100):
            nuevo_boleto = Boleto(numero_boleto=i, estado='disponible')
            db.session.add(nuevo_boleto)
        
        # Guardamos todos los nuevos boletos en la base de datos.
        db.session.commit()
        print("¡100 boletos creados exitosamente!")
        
        
@app.route('/admin/<codigo_secreto>')
def admin(codigo_secreto):
    """
    Panel de administrador para ver boletos apartados y confirmar pagos.
    Protegido por un código secreto.
    """
    if codigo_secreto != ADMIN_SECRET_CODE:
        abort(403) # Error 403: Forbidden (Acceso Prohibido)

    # Obtenemos los boletos que necesitan acción (los apartados)
    boletos_apartados = Boleto.query.filter_by(estado='apartado').order_by(Boleto.fecha_apartado).all()
    
    return render_template('admin.html', boletos=boletos_apartados, codigo_secreto=codigo_secreto)

@app.route('/confirmar/<int:boleto_id>/<codigo_secreto>')
def confirmar(boleto_id, codigo_secreto):
    """
    Confirma el pago de un boleto, cambiando su estado a 'vendido'.
    """
    if codigo_secreto != ADMIN_SECRET_CODE:
        abort(403)

    boleto = Boleto.query.get_or_404(boleto_id)
    boleto.estado = 'vendido'
    db.session.commit()
    
    flash(f'¡El pago del boleto {boleto.numero_boleto} ha sido confirmado!', 'success')
    return redirect(url_for('admin', codigo_secreto=codigo_secreto))

# =============================================================================
# 6. PUNTO DE ENTRADA PARA EJECUTAR LA APLICACIÓN
# =============================================================================
# Esta es la sección que inicia el servidor web de desarrollo.
# Solo se ejecuta cuando corremos el archivo directamente con 'python app.py'.
# 'debug=True' activa el modo de depuración, que reinicia el servidor
# automáticamente con cada cambio y muestra errores detallados. Es muy útil.

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)), debug=True)