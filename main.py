from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime, date

from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

# -----------------------------------------------------------------------------
import os

# Configuración de la base de datos conectada a la nube
DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# -----------------------------------------------------------------------------
# MODELOS / TABLAS
# -----------------------------------------------------------------------------
class UsuarioDB(Base):
    __tablename__ = "usuarios"
    id = Column(Integer, primary_key=True, index=True)
    dui = Column(String, unique=True, index=True, nullable=False) # DUI del trabajador
    nombre = Column(String, nullable=False)
    rol = Column(String, nullable=False) # 'administrador', 'supervisor' o 'empleado'
    pin = Column(String, default="1234", nullable=False)
    cambiar_password = Column(Boolean, default=True)
    activo = Column(Boolean, default=True) # Para pausar o dar de baja sin borrar
    pago_diario = Column(Float, default=0.0)      # Pago fijo por día
    pago_hora_extra = Column(Float, default=0.0)  # Pago fijo por hora extra

class AsistenciaDB(Base):
    __tablename__ = "asistencias"
    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id")) # Empleado que asistió
    supervisor_id = Column(Integer, ForeignKey("usuarios.id")) # Supervisor que marcó
    fecha = Column(String, nullable=False)
    hora_entrada = Column(String, nullable=True)
    hora_salida = Column(String, nullable=True)
    horas_extras = Column(Float, default=0.0)

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="API Asistencia - FULL METAL",
    description="Sistema de asistencia y control de costos para obra en campo"
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# -----------------------------------------------------------------------------
# ESQUEMAS PYDANTIC
# -----------------------------------------------------------------------------
class LoginRequest(BaseModel):
    dui: str
    pin: str

class UpdatePasswordRequest(BaseModel):
    dui: str
    nuevo_pin: str

class CrearUsuarioRequest(BaseModel):
    dui: str
    nombre: str
    rol: str
    pago_diario: float
    pago_hora_extra: float

class SupervisorMarcarRequest(BaseModel):
    empleado_dui: str
    supervisor_id: int
    tipo: str # 'entrada', 'salida'
    horas_extras_extra: float = 0.0

# -----------------------------------------------------------------------------
# AUTENTICACIÓN
# -----------------------------------------------------------------------------
@app.post("/auth/login")
def login_usuario(data: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(UsuarioDB).filter(UsuarioDB.dui == data.dui, UsuarioDB.activo == True).first()
    if not user or user.pin != data.pin:
        raise HTTPException(status_code=401, detail="DUI o contraseña incorrectos (o usuario inactivo)")
    
    return {
        "status": "exito",
        "usuario_id": user.id,
        "nombre": user.nombre,
        "rol": user.rol,
        "cambiar_password": user.cambiar_password
    }

@app.post("/auth/cambiar-password")
def cambiar_password(data: UpdatePasswordRequest, db: Session = Depends(get_db)):
    user = db.query(UsuarioDB).filter(UsuarioDB.dui == data.dui).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    user.pin = data.nuevo_pin
    user.cambiar_password = False
    db.commit()
    
    return {"status": "exito", "mensaje": "Contraseña actualizada correctamente"}

# -----------------------------------------------------------------------------
# GESTIÓN DE PERSONAL (SOLO ADMIN)
# -----------------------------------------------------------------------------
@app.post("/usuarios/crear")
def crear_usuario(data: CrearUsuarioRequest, db: Session = Depends(get_db)):
    existente = db.query(UsuarioDB).filter(UsuarioDB.dui == data.dui).first()
    if existente:
        raise HTTPException(status_code=400, detail="El DUI ya está registrado.")
    
    nuevo = UsuarioDB(
        dui=data.dui,
        nombre=data.nombre,
        rol=data.rol,
        pin="1234",
        cambiar_password=True,
        activo=True,
        pago_diario=data.pago_diario,
        pago_hora_extra=data.pago_hora_extra
    )
    db.add(nuevo)
    db.commit()
    return {"status": "exito", "mensaje": f"Usuario {data.nombre} creado con éxito."}

@app.put("/usuarios/estado/{usuario_id}")
def cambiar_estado_usuario(usuario_id: int, activo: bool, db: Session = Depends(get_db)):
    user = db.query(UsuarioDB).filter(UsuarioDB.id == usuario_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    user.activo = activo
    db.commit()
    estado_texto = "activado" if activo else "pausado/dado de baja"
    return {"status": "exito", "mensaje": f"El usuario ha sido {estado_texto} correctamente."}

# -----------------------------------------------------------------------------
# MARCACIÓN DE ASISTENCIA (POR EL SUPERVISOR / ADMIN)
# -----------------------------------------------------------------------------
@app.post("/asistencia/supervisor-marcar")
def supervisor_marcar_asistencia(data: SupervisorMarcarRequest, db: Session = Depends(get_db)):
    empleado = db.query(UsuarioDB).filter(UsuarioDB.dui == data.empleado_dui, UsuarioDB.rol == 'empleado').first()
    if not empleado:
        raise HTTPException(status_code=404, detail="Empleado no encontrado con ese DUI.")

    hoy = str(date.today())

    if data.tipo == 'entrada':
        existe = db.query(AsistenciaDB).filter(AsistenciaDB.usuario_id == empleado.id, AsistenciaDB.fecha == hoy).first()
        if existe:
            raise HTTPException(status_code=400, detail="El empleado ya tiene registrada su entrada hoy.")
        
        nueva = AsistenciaDB(
            usuario_id=empleado.id,
            supervisor_id=data.supervisor_id,
            fecha=hoy,
            hora_entrada=datetime.now().strftime("%H:%M:%S"),
            horas_extras=data.horas_extras_extra
        )
        db.add(nueva)
        db.commit()
        return {"status": "exito", "mensaje": f"Entrada registrada para {empleado.nombre}"}

    elif data.tipo == 'salida':
        registro = db.query(AsistenciaDB).filter(AsistenciaDB.usuario_id == empleado.id, AsistenciaDB.fecha == hoy).first()
        if not registro:
            raise HTTPException(status_code=400, detail="No se encontró registro de entrada para hoy de este empleado.")
        
        registro.hora_salida = datetime.now().strftime("%H:%M:%S")
        if data.horas_extras_extra > 0:
            registro.horas_extras += data.horas_extras_extra
            
        db.commit()
        return {"status": "exito", "mensaje": f"Salida registrada para {empleado.nombre}. Horas extra totales: {registro.horas_extras}h"}

# -----------------------------------------------------------------------------
# CONSULTA DE EMPLEADO (SOLO LECTURA)
# -----------------------------------------------------------------------------
@app.get("/asistencia/empleado/{usuario_id}")
def get_asistencia_empleado(usuario_id: int, db: Session = Depends(get_db)):
    asistencias = db.query(AsistenciaDB).filter(AsistenciaDB.usuario_id == usuario_id).all()
    
    historial = []
    total_dias = len(asistencias)
    total_horas_extras = sum([a.horas_extras for a in asistencias])

    for a in asistencias:
        historial.append({
            "fecha": a.fecha,
            "hora_entrada": a.hora_entrada or "--",
            "hora_salida": a.hora_salida or "--",
            "horas_extras": a.horas_extras
        })

    return {
        "resumen": {
            "dias_asistidos": total_dias,
            "total_horas_extras": total_horas_extras
        },
        "historial": historial
    }