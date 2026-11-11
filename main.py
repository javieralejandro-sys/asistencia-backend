from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime, date
import io

from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

import os

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class UsuarioDB(Base):
    __tablename__ = "usuarios"
    id = Column(Integer, primary_key=True, index=True)
    dui = Column(String, unique=True, index=True, nullable=False) 
    nombre = Column(String, nullable=False)
    rol = Column(String, nullable=False) 
    pin = Column(String, default="1234", nullable=False)
    cambiar_password = Column(Boolean, default=True)
    activo = Column(Boolean, default=True) 
    pago_diario = Column(Float, default=0.0)      
    pago_hora_extra = Column(Float, default=0.0)  

class AsistenciaDB(Base):
    __tablename__ = "asistencias"
    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id")) 
    supervisor_id = Column(Integer, ForeignKey("usuarios.id")) 
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
    tipo: str 
    horas_extras_extra: float = 0.0
    fecha_manual: str = None      
    hora_manual: str = None       

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

@app.post("/asistencia/supervisor-marcar")
def supervisor_marcar_asistencia(data: SupervisorMarcarRequest, db: Session = Depends(get_db)):
    empleado = db.query(UsuarioDB).filter(UsuarioDB.dui == data.empleado_dui, UsuarioDB.activo == True).first()
    if not empleado:
        raise HTTPException(status_code=404, detail="Usuario no encontrado o inactivo con ese DUI.")

    hoy = data.fecha_manual if data.fecha_manual else str(date.today())
    hora_actual = data.hora_manual if data.hora_manual else datetime.now().strftime("%H:%M:%S")

    if data.tipo == 'entrada':
        existe = db.query(AsistenciaDB).filter(AsistenciaDB.usuario_id == empleado.id, AsistenciaDB.fecha == hoy).first()
        if existe:
            raise HTTPException(status_code=400, detail=f"El empleado ya tiene registrada su entrada para el día {hoy}.")
        nueva = AsistenciaDB(
            usuario_id=empleado.id,
            supervisor_id=data.supervisor_id,
            fecha=hoy,
            hora_entrada=hora_actual,
            horas_extras=data.horas_extras_extra
        )
        db.add(nueva)
        db.commit()
        return {"status": "exito", "mensaje": f"Entrada registrada ({hoy} {hora_actual}) para {empleado.nombre}"}

    elif data.tipo == 'salida':
        registro = db.query(AsistenciaDB).filter(AsistenciaDB.usuario_id == empleado.id, AsistenciaDB.fecha == hoy).first()
        if not registro:
            raise HTTPException(status_code=400, detail=f"No se encontró registro de entrada el {hoy} para este empleado.")
        registro.hora_salida = hora_actual
        if data.horas_extras_extra > 0:
            registro.horas_extras += data.horas_extras_extra
        db.commit()
        return {"status": "exito", "mensaje": f"Salida registrada ({hora_actual}) para {empleado.nombre}. Horas extra: {registro.horas_extras}h"}

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

@app.get("/reporte/pdf")
def generar_reporte_pdf(usuario_id: int = Query(None), db: Session = Depends(get_db)):
    query = db.query(UsuarioDB).filter(UsuarioDB.activo == True)
    if usuario_id:
        query = query.filter(UsuarioDB.id == usuario_id)
    usuarios = query.all()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elementos = []

    styles = getSampleStyleSheet()
    elementos.append(Paragraph("<b>FULL METAL - Reporte de Nómina y Asistencia</b>", styles['Title']))
    elementos.append(Paragraph(f"Generado el: {date.today()}", styles['Normal']))
    elementos.append(Spacer(1, 15))

    data_tabla = [["Colaborador", "Días", "P. Diario", "Subtotal Días", "Hrs Ext", "P. H.Ext", "Subtotal Ext", "Total a Pagar"]]
    total_general_nomina = 0.0

    for u in usuarios:
        asistencias = db.query(AsistenciaDB).filter(AsistenciaDB.usuario_id == u.id).all()
        dias_asistidos = len(asistencias)
        if dias_asistidos == 0 and usuario_id is None:
            continue

        total_horas_extras = sum([a.horas_extras for a in asistencias])
        subtotal_dias = dias_asistidos * u.pago_diario
        subtotal_extras = total_horas_extras * u.pago_hora_extra
        total_empleado = subtotal_dias + subtotal_extras
        total_general_nomina += total_empleado

        data_tabla.append([
            str(u.nombre),
            str(dias_asistidos),
            f"${u.pago_diario:.2f}",
            f"${subtotal_dias:.2f}",
            f"{total_horas_extras}h",
            f"${u.pago_hora_extra:.2f}",
            f"${subtotal_extras:.2f}",
            f"${total_empleado:.2f}"
        ])

    t = Table(data_tabla)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.bluegray),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('BOTTOMPADDING', (0,0), (-1,0), 6),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
    ]))

    elementos.append(t)
    elementos.append(Spacer(1, 15))
    elementos.append(Paragraph(f"<b>Total General de Nómina en Obra: ${total_general_nomina:.2f}</b>", styles['Heading2']))

    doc.build(elementos)
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type='application/pdf',
        headers={"Content-Disposition": "attachment; filename=reporte_nomina_full_metal.pdf"}
    )

@app.get("/")
def home():
    return {"estado": "activo", "mensaje": "API de Asistencia y Nómina funcionando correctamente"}
