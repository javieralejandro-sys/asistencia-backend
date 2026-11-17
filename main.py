from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey, Boolean, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime, date, time, timedelta
from typing import Optional
import io
import os

from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class PuestoDB(Base):
    __tablename__ = "puestos"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, unique=True, nullable=False)
    pago_diario = Column(Float, nullable=False)
    pago_hora_extra = Column(Float, nullable=False)

class UsuarioDB(Base):
    __tablename__ = "usuarios"
    id = Column(Integer, primary_key=True, index=True)
    dui = Column(String, unique=True, index=True, nullable=False)
    nombre = Column(String, nullable=False)
    rol = Column(String, nullable=False)
    pin = Column(String, default="1234", nullable=False)
    cambiar_password = Column(Boolean, default=True)
    activo = Column(Boolean, default=True)
    puesto = Column(String, default="General", nullable=True)
    pago_diario = Column(Float, default=0.0)
    pago_hora_extra = Column(Float, default=0.0)
    fecha_ingreso = Column(String, nullable=True)
    fecha_baja = Column(String, nullable=True)

class AsistenciaDB(Base):
    __tablename__ = "asistencias"
    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"))
    supervisor_id = Column(Integer, ForeignKey("usuarios.id"))
    fecha = Column(String, nullable=False)
    proyecto = Column(String, default="Obra General", nullable=True)
    hora_entrada = Column(String, nullable=True)
    hora_salida = Column(String, nullable=True)
    horas_extras = Column(Float, default=0.0)
    ubicacion_2 = Column(String, nullable=True)
    hora_entrada_2 = Column(String, nullable=True)
    hora_salida_2 = Column(String, nullable=True)
    es_turno_partido = Column(Boolean, default=False)
    justificado = Column(Boolean, default=False)
    nota_justificacion = Column(String, nullable=True)

class AnticipoDB(Base):
    __tablename__ = "anticipos"
    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    autorizado_por_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    fecha = Column(String, nullable=False)
    monto = Column(Float, nullable=False)
    observacion = Column(String, nullable=True)

class AsuetoDB(Base):
    __tablename__ = "asuetos"
    id = Column(Integer, primary_key=True, index=True)
    fecha = Column(String, unique=True, nullable=False)
    motivo = Column(String, nullable=False)

Base.metadata.create_all(bind=engine)

def aplicar_migraciones_seguras():
    alteraciones = [
        "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS puesto VARCHAR DEFAULT 'General'",
        "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS fecha_ingreso VARCHAR",
        "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS fecha_baja VARCHAR",
        "ALTER TABLE asistencias ADD COLUMN IF NOT EXISTS proyecto VARCHAR DEFAULT 'Obra General'",
        "ALTER TABLE asistencias ADD COLUMN IF NOT EXISTS ubicacion_2 VARCHAR",
        "ALTER TABLE asistencias ADD COLUMN IF NOT EXISTS hora_entrada_2 VARCHAR",
        "ALTER TABLE asistencias ADD COLUMN IF NOT EXISTS hora_salida_2 VARCHAR",
        "ALTER TABLE asistencias ADD COLUMN IF NOT EXISTS es_turno_partido BOOLEAN DEFAULT FALSE",
        "ALTER TABLE asistencias ADD COLUMN IF NOT EXISTS justificado BOOLEAN DEFAULT FALSE",
        "ALTER TABLE asistencias ADD COLUMN IF NOT EXISTS nota_justificacion VARCHAR",
    ]
    with engine.begin() as conn:
        for sql in alteraciones:
            try:
                conn.execute(text(sql))
            except Exception:
                pass

aplicar_migraciones_seguras()

app = FastAPI(
    title="API Asistencia y Nómina - FULL METAL",
    description="Sistema de asistencia, trazabilidad y nómina neta libre de impuestos"
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def inicializar_catalogos(db: Session):
    if db.query(PuestoDB).count() == 0:
        puestos_iniciales = [
            PuestoDB(nombre="ARGONERO", pago_diario=60.00, pago_hora_extra=8.00),
            PuestoDB(nombre="AYUDANTE 1", pago_diario=20.00, pago_hora_extra=3.50),
            PuestoDB(nombre="AYUDANTE 2", pago_diario=18.75, pago_hora_extra=3.50),
            PuestoDB(nombre="AYUDANTE 3", pago_diario=16.00, pago_hora_extra=3.50),
            PuestoDB(nombre="MECANICO 1", pago_diario=30.00, pago_hora_extra=5.00),
            PuestoDB(nombre="MECANICO 2", pago_diario=25.00, pago_hora_extra=5.00),
            PuestoDB(nombre="MECANICO 3", pago_diario=22.00, pago_hora_extra=4.00),
            PuestoDB(nombre="SOLDADOR 1", pago_diario=40.00, pago_hora_extra=6.00),
            PuestoDB(nombre="SOLDADOR 2", pago_diario=35.00, pago_hora_extra=5.00),
            PuestoDB(nombre="SOLDADOR 3", pago_diario=32.00, pago_hora_extra=5.00),
            PuestoDB(nombre="PINTOR", pago_diario=25.00, pago_hora_extra=5.00),
            PuestoDB(nombre="PINTOR2", pago_diario=20.00, pago_hora_extra=3.50),
            PuestoDB(nombre="BODEGUERO", pago_diario=20.00, pago_hora_extra=3.50),
            PuestoDB(nombre="AUXILIAR DE BODEGA", pago_diario=16.00, pago_hora_extra=3.50),
            PuestoDB(nombre="MOTORISTA", pago_diario=20.00, pago_hora_extra=3.50),
            PuestoDB(nombre="SUPERVISOR", pago_diario=66.67, pago_hora_extra=8.00),
        ]
        db.add_all(puestos_iniciales)

    if db.query(AsuetoDB).count() == 0:
        anio = date.today().year
        asuetos_sv = [
            AsuetoDB(fecha=f"{anio}-01-01", motivo="Año Nuevo (Art. 190 Código de Trabajo)"),
            AsuetoDB(fecha=f"{anio}-05-01", motivo="Día del Trabajo (Art. 190 Código de Trabajo)"),
            AsuetoDB(fecha=f"{anio}-05-10", motivo="Día de la Madre (Decreto Legislativo)"),
            AsuetoDB(fecha=f"{anio}-06-17", motivo="Día del Padre (Decreto Legislativo)"),
            AsuetoDB(fecha=f"{anio}-08-06", motivo="Fiestas Agostinas / Divino Salvador del Mundo"),
            AsuetoDB(fecha=f"{anio}-09-15", motivo="Día de la Independencia Patria"),
            AsuetoDB(fecha=f"{anio}-11-02", motivo="Día de los Difuntos (Art. 190 Código de Trabajo)"),
            AsuetoDB(fecha=f"{anio}-12-25", motivo="Navidad (Art. 190 Código de Trabajo)"),
        ]
        db.add_all(asuetos_sv)
    db.commit()

with SessionLocal() as db_init:
    inicializar_catalogos(db_init)

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
    puesto: Optional[str] = "General"
    pago_diario: Optional[float] = None
    pago_hora_extra: Optional[float] = None
    fecha_ingreso: Optional[str] = None
    fecha_baja: Optional[str] = None

class PuestoRequest(BaseModel):
    nombre: str
    pago_diario: float
    pago_hora_extra: float

class SupervisorMarcarRequest(BaseModel):
    empleado_dui: Optional[str] = None
    empleado_nombre: Optional[str] = None
    supervisor_id: int
    tipo: str
    proyecto: Optional[str] = "Obra General"
    fecha_manual: Optional[str] = None
    hora_manual: Optional[str] = None
    horas_extras_extra: float = 0.0
    ubicacion_2: Optional[str] = None
    hora_entrada_2: Optional[str] = None
    hora_salida_2: Optional[str] = None
    es_turno_partido: bool = False
    justificado: bool = False
    nota_justificacion: Optional[str] = None

class AnticipoRequest(BaseModel):
    usuario_id: int
    autorizado_por_id: int
    monto: float
    fecha: Optional[str] = None
    observacion: Optional[str] = None

class AsuetoRequest(BaseModel):
    fecha: str
    motivo: str

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

@app.get("/puestos")
def listar_puestos(db: Session = Depends(get_db)):
    return db.query(PuestoDB).all()

@app.post("/puestos/crear")
def crear_puesto(data: PuestoRequest, db: Session = Depends(get_db)):
    nuevo = PuestoDB(nombre=data.nombre, pago_diario=data.pago_diario, pago_hora_extra=data.pago_hora_extra)
    db.add(nuevo)
    db.commit()
    return {"status": "exito", "mensaje": f"Puesto '{data.nombre}' guardado."}

@app.get("/asuetos")
def listar_asuetos(db: Session = Depends(get_db)):
    return db.query(AsuetoDB).order_by(AsuetoDB.fecha.asc()).all()

@app.post("/asuetos/crear")
def agregar_asueto(data: AsuetoRequest, db: Session = Depends(get_db)):
    nuevo = AsuetoDB(fecha=data.fecha, motivo=data.motivo)
    db.add(nuevo)
    db.commit()
    return {"status": "exito", "mensaje": "Día de asueto registrado."}

@app.get("/usuarios/empleados")
def listar_empleados(solo_activos: bool = False, db: Session = Depends(get_db)):
    q = db.query(UsuarioDB).filter(UsuarioDB.rol == "empleado")
    if solo_activos:
        q = q.filter(UsuarioDB.activo == True)
    return q.order_by(UsuarioDB.nombre.asc()).all()

@app.post("/usuarios/crear")
def crear_usuario(data: CrearUsuarioRequest, db: Session = Depends(get_db)):
    existente = db.query(UsuarioDB).filter(UsuarioDB.dui == data.dui).first()
    if existente:
        raise HTTPException(status_code=400, detail="El DUI ya está registrado.")
    p_diario = data.pago_diario
    p_extra = data.pago_hora_extra
    if (p_diario is None or p_extra is None) and data.puesto:
        cat = db.query(PuestoDB).filter(PuestoDB.nombre == data.puesto).first()
        if cat:
            p_diario = p_diario if p_diario is not None else cat.pago_diario
            p_extra = p_extra if p_extra is not None else cat.pago_hora_extra

    nuevo = UsuarioDB(
        dui=data.dui,
        nombre=data.nombre,
        rol=data.rol,
        pin="1234",
        cambiar_password=True,
        activo=True,
        puesto=data.puesto or "General",
        pago_diario=p_diario or 0.0,
        pago_hora_extra=p_extra or 0.0,
        fecha_ingreso=data.fecha_ingreso or str(date.today()),
        fecha_baja=data.fecha_baja
    )
    db.add(nuevo)
    db.commit()
    return {"status": "exito", "mensaje": f"Usuario {data.nombre} creado con éxito."}

@app.put("/usuarios/estado/{usuario_id}")
def cambiar_estado_usuario(
    usuario_id: int,
    activo: bool,
    fecha_baja: Optional[str] = None,
    db: Session = Depends(get_db)
):
    user = db.query(UsuarioDB).filter(UsuarioDB.id == usuario_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    user.activo = activo
    if not activo:
        user.fecha_baja = fecha_baja or str(date.today())
    else:
        user.fecha_baja = None
    db.commit()
    estado_texto = "activado" if activo else f"dado de baja ({user.fecha_baja})"
    return {"status": "exito", "mensaje": f"El usuario ha sido {estado_texto} correctamente."}

@app.post("/asistencia/supervisor-marcar")
def supervisor_marcar_asistencia(data: SupervisorMarcarRequest, db: Session = Depends(get_db)):
    empleado = None
    if data.empleado_dui:
        empleado = db.query(UsuarioDB).filter(UsuarioDB.dui == data.empleado_dui, UsuarioDB.rol == 'empleado').first()
    elif data.empleado_nombre:
        empleado = db.query(UsuarioDB).filter(UsuarioDB.nombre == data.empleado_nombre, UsuarioDB.rol == 'empleado').first()

    if not empleado:
        raise HTTPException(status_code=404, detail="Empleado no encontrado.")

    fecha_registro = data.fecha_manual or str(date.today())
    hora_actual = data.hora_manual or datetime.now().strftime("%H:%M:%S")

    if data.tipo == 'entrada':
        existe = db.query(AsistenciaDB).filter(AsistenciaDB.usuario_id == empleado.id, AsistenciaDB.fecha == fecha_registro).first()
        if existe:
            raise HTTPException(status_code=400, detail="El empleado ya tiene registrada su entrada en esta fecha.")
        nueva = AsistenciaDB(
            usuario_id=empleado.id,
            supervisor_id=data.supervisor_id,
            fecha=fecha_registro,
            proyecto=data.proyecto or "Obra General",
            hora_entrada=hora_actual,
            horas_extras=data.horas_extras_extra,
            justificado=data.justificado,
            nota_justificacion=data.nota_justificacion
        )
        db.add(nueva)
        db.commit()
        return {"status": "exito", "mensaje": f"Entrada registrada para {empleado.nombre} el {fecha_registro}"}

    elif data.tipo == 'salida':
        registro = db.query(AsistenciaDB).filter(AsistenciaDB.usuario_id == empleado.id, AsistenciaDB.fecha == fecha_registro).first()
        if not registro:
            raise HTTPException(status_code=400, detail="No se encontró registro de entrada para esta fecha de este empleado.")
        registro.hora_salida = hora_actual
        if data.horas_extras_extra > 0:
            registro.horas_extras += data.horas_extras_extra
        if data.ubicacion_2:
            registro.ubicacion_2 = data.ubicacion_2
            registro.hora_entrada_2 = data.hora_entrada_2
            registro.hora_salida_2 = data.hora_salida_2
            registro.es_turno_partido = data.es_turno_partido
        if data.justificado:
            registro.justificado = True
            registro.nota_justificacion = data.nota_justificacion
        db.commit()
        return {"status": "exito", "mensaje": f"Salida registrada para {empleado.nombre} el {fecha_registro}."}

@app.post("/anticipos/registrar")
def registrar_anticipo(data: AnticipoRequest, db: Session = Depends(get_db)):
    autorizador = db.query(UsuarioDB).filter(UsuarioDB.id == data.autorizado_por_id).first()
    if not autorizador or autorizador.rol not in ["administrador", "supervisor", "contador"]:
        raise HTTPException(status_code=403, detail="Solo administrador, supervisor o contador pueden autorizar anticipos.")
    empleado = db.query(UsuarioDB).filter(UsuarioDB.id == data.usuario_id).first()
    if not empleado:
        raise HTTPException(status_code=404, detail="Empleado no encontrado.")
    nuevo_anticipo = AnticipoDB(
        usuario_id=empleado.id,
        autorizado_por_id=autorizador.id,
        fecha=data.fecha or str(date.today()),
        monto=data.monto,
        observacion=data.observacion
    )
    db.add(nuevo_anticipo)
    db.commit()
    return {
        "status": "exito",
        "mensaje": f"Anticipo de ${data.monto:.2f} registrado para {empleado.nombre}."
    }

@app.get("/asistencia/empleado/{usuario_id}")
def get_asistencia_empleado(usuario_id: int, db: Session = Depends(get_db)):
    asistencias = db.query(AsistenciaDB).filter(AsistenciaDB.usuario_id == usuario_id).all()
    historial = []
    total_dias = len(asistencias)
    total_horas_extras = sum([a.horas_extras for a in asistencias])
    for a in asistencias:
        historial.append({
            "fecha": a.fecha,
            "proyecto": a.proyecto,
            "hora_entrada": a.hora_entrada or "--",
            "hora_salida": a.hora_salida or "--",
            "ubicacion_2": a.ubicacion_2,
            "justificado": a.justificado,
            "horas_extras": a.horas_extras
        })
    return {
        "resumen": {
            "dias_asistidos": total_dias,
            "total_horas_extras": total_horas_extras
        },
        "historial": historial
    }

def _parse_hora(h_str: str) -> time:
    partes = [int(x) for x in h_str.split(":")]
    return time(partes[0], partes[1], partes[2] if len(partes) > 2 else 0)

def _horas_entre(h_ini: str, h_fin: str) -> float:
    t1, t2 = _parse_hora(h_ini), _parse_hora(h_fin)
    dt1 = datetime.combine(date.today(), t1)
    dt2 = datetime.combine(date.today(), t2)
    if dt2 <= dt1:
        dt2 += timedelta(days=1)
    return (dt2 - dt1).total_seconds() / 3600.0

def _horas_post_6pm(h_ini: str, h_fin: str) -> float:
    t1, t2 = _parse_hora(h_ini), _parse_hora(h_fin)
    dt1 = datetime.combine(date.today(), t1)
    dt2 = datetime.combine(date.today(), t2)
    if dt2 <= dt1:
        dt2 += timedelta(days=1)
    limite = datetime.combine(date.today(), time(18, 0))
    if dt2 <= limite:
        return 0.0
    return (dt2 - max(dt1, limite)).total_seconds() / 3600.0

def calcular_pago_dia(emp: UsuarioDB, fecha_str: str, reg: Optional[AsistenciaDB], asueto: Optional[AsuetoDB]):
    f_date = date.fromisoformat(fecha_str)
    tarifa_dia = emp.pago_diario
    tarifa_hora = tarifa_dia / 8.0
    tarifa_he = emp.pago_hora_extra
    es_domingo = (f_date.weekday() == 6)
    es_sabado = (f_date.weekday() == 5)

    if emp.fecha_baja and fecha_str > emp.fecha_baja:
        return {"estado": "INACTIVO", "pago": 0.0, "he_norm": 0.0, "he_noct": 0.0, "dom_h": 0.0}
    if emp.fecha_ingreso and fecha_str < emp.fecha_ingreso:
        return {"estado": "INACTIVO", "pago": 0.0, "he_norm": 0.0, "he_noct": 0.0, "dom_h": 0.0}

    if asueto and not es_domingo:
        if not reg or not reg.hora_entrada:
            return {"estado": "ASUETO", "pago": round(tarifa_dia, 2), "he_norm": 0.0, "he_noct": 0.0, "dom_h": 0.0}
        else:
            salida_ref = reg.hora_salida or "16:00:00"
            h_brutas = _horas_entre(reg.hora_entrada, salida_ref)
            if reg.hora_entrada_2 and reg.hora_salida_2:
                h_brutas += _horas_entre(reg.hora_entrada_2, reg.hora_salida_2)
            desc_comida = 2.0 if h_brutas >= 12.0 else (1.0 if h_brutas >= 5.5 else 0.0)
            h_ef = max(0.0, h_brutas - desc_comida)
            pago_total = tarifa_dia + (h_ef * tarifa_hora)
            return {"estado": "ASUETO_TRABAJADO", "pago": round(pago_total, 2), "he_norm": 0.0, "he_noct": 0.0, "dom_h": 0.0}

    if not reg or not reg.hora_entrada:
        return {"estado": "AUSENTE", "pago": 0.0, "he_norm": 0.0, "he_noct": 0.0, "dom_h": 0.0}

    salida_1 = reg.hora_salida or "16:00:00"
    h1 = _horas_entre(reg.hora_entrada, salida_1)
    noct1 = _horas_post_6pm(reg.hora_entrada, salida_1)

    h2, noct2 = 0.0, 0.0
    if reg.hora_entrada_2 and reg.hora_salida_2:
        h2 = _horas_entre(reg.hora_entrada_2, reg.hora_salida_2)
        noct2 = _horas_post_6pm(reg.hora_entrada_2, reg.hora_salida_2)

    h_brutas = h1 + h2
    h_noct_totales = noct1 + noct2

    if not reg.es_turno_partido:
        if h_brutas >= 12.0 and h_noct_totales >= 3.0:
            desc_comida = 2.0
        elif h_brutas >= 5.5:
            desc_comida = 1.0
        else:
            desc_comida = 0.0
    else:
        desc_comida = 1.0 if h1 >= 6.0 else 0.0

    h_efectivas = max(0.0, h_brutas - desc_comida)

    if es_domingo:
        tarifa_dom = tarifa_he * 2.0
        return {
            "estado": "DOMINGO",
            "pago": round(h_efectivas * tarifa_dom, 2),
            "he_norm": 0.0,
            "he_noct": 0.0,
            "dom_h": round(h_efectivas, 2)
        }

    if es_sabado:
        h_sabado_normal = min(h_efectivas, 4.0)
        h_sabado_extra = max(0.0, h_efectivas - 4.0) + (reg.horas_extras or 0.0)
        pago_sabado = (h_sabado_normal * (tarifa_dia / 4.0)) + (h_sabado_extra * tarifa_he)
        return {
            "estado": "SABADO",
            "pago": round(pago_sabado, 2),
            "he_norm": round(h_sabado_extra, 2),
            "he_noct": 0.0,
            "dom_h": 0.0
        }

    if h_efectivas < 8.0:
        if reg.justificado:
            return {"estado": "ORDINARIO", "pago": round(tarifa_dia, 2), "he_norm": 0.0, "he_noct": 0.0, "dom_h": 0.0}
        return {"estado": "ORDINARIO", "pago": round(h_efectivas * tarifa_hora, 2), "he_norm": 0.0, "he_noct": 0.0, "dom_h": 0.0}

    he_totales = (h_efectivas - 8.0) + (reg.horas_extras or 0.0)
    he_noct = min(he_totales, h_noct_totales)
    he_norm = max(0.0, he_totales - he_noct)

    pago_dia = tarifa_dia + (he_norm * tarifa_he) + (he_noct * tarifa_he * 1.15)
    return {
        "estado": "ORDINARIO",
        "pago": round(pago_dia, 2),
        "he_norm": round(he_norm, 2),
        "he_noct": round(he_noct, 2),
        "dom_h": 0.0
    }

@app.get("/reportes/nomina-pdf")
def generar_pdf_nomina(fecha_inicio: str, fecha_fin: str, db: Session = Depends(get_db)):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(letter), topMargin=25, bottomMargin=25)
    styles = getSampleStyleSheet()
    elementos = []

    empleados = db.query(UsuarioDB).filter(UsuarioDB.rol == "empleado").all()
    asuetos = {a.fecha: a for a in db.query(AsuetoDB).filter(AsuetoDB.fecha.between(fecha_inicio, fecha_fin)).all()}

    f_ini = date.fromisoformat(fecha_inicio)
    f_fin = date.fromisoformat(fecha_fin)
    dias_periodo = [str(f_ini + timedelta(days=i)) for i in range((f_fin - f_ini).days + 1)]

    filas_activos = [[
        "Empleado / DUI", "Puesto", "Días / Asuetos", "HE Norm.", "HE +15%", "Dom.",
        "Subtotal Dev.", "Anticipos", "LÍQUIDO NETO"
    ]]
    filas_inactivos = [["Empleado", "DUI", "Puesto", "Estado", "Fecha de Baja / Observación"]]

    total_neto_general = 0.0

    for emp in empleados:
        registros = {
            r.fecha: r for r in db.query(AsistenciaDB).filter(
                AsistenciaDB.usuario_id == emp.id,
                AsistenciaDB.fecha.between(fecha_inicio, fecha_fin)
            ).all()
        }
        anticipos_emp = db.query(AnticipoDB).filter(
            AnticipoDB.usuario_id == emp.id,
            AnticipoDB.fecha.between(fecha_inicio, fecha_fin)
        ).all()
        total_anticipos = sum(a.monto for a in anticipos_emp)

        subtotal_emp = 0.0
        dias_pagados = 0
        he_norm_total = 0.0
        he_noct_total = 0.0
        horas_domingo = 0.0
        dias_inactivos_corte = 0

        for d_str in dias_periodo:
            res = calcular_pago_dia(emp, d_str, registros.get(d_str), asuetos.get(d_str))
            if res["estado"] == "INACTIVO":
                dias_inactivos_corte += 1
            elif res["pago"] > 0:
                subtotal_emp += res["pago"]
                if res["estado"] == "DOMINGO":
                    horas_domingo += res["dom_h"]
                else:
                    dias_pagados += 1
                    he_norm_total += res["he_norm"]
                    he_noct_total += res["he_noct"]

        if subtotal_emp > 0 or total_anticipos > 0:
            liquido = subtotal_emp - total_anticipos
            total_neto_general += liquido
            etiqueta_dias = f"{dias_pagados} d"
            if dias_inactivos_corte > 0:
                etiqueta_dias += f" ({dias_inactivos_corte}d Inact.)"
            detalle_ant = f"-${total_anticipos:.2f}" if total_anticipos > 0 else "$0.00"

            filas_activos.append([
                f"{emp.nombre}\nDUI: {emp.dui}",
                emp.puesto or "General",
                etiqueta_dias,
                f"{he_norm_total:.1f}h",
                f"{he_noct_total:.1f}h",
                f"{horas_domingo:.1f}h",
                f"${subtotal_emp:.2f}",
                detalle_ant,
                f"${liquido:.2f}"
            ])
        else:
            motivo_baja = f"Baja registrada: {emp.fecha_baja}" if emp.fecha_baja else "Sin actividad en el periodo"
            filas_inactivos.append([emp.nombre, emp.dui, emp.puesto or "General", "INACTIVO", motivo_baja])

    elementos.append(Paragraph("<b>FULL METAL — REPORTE CONTABLE DE NÓMINA</b>", styles["Title"]))
    elementos.append(Paragraph(
        f"Periodo: {fecha_inicio} al {fecha_fin} | <i>Nota Contable: Salarios netos libres de retenciones.</i>",
        styles["Normal"]
    ))
    elementos.append(Spacer(1, 10))

    filas_activos.append(["", "", "", "", "", "", "", "TOTAL A PAGAR:", f"${total_neto_general:.2f}"])
    tabla_activos = Table(filas_activos, repeatRows=1)
    tabla_activos.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1B365D")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -2), 0.5, colors.grey),
        ("FONTNAME", (-2, -1), (-1, -1), "Helvetica-Bold"),
        ("BACKGROUND", (-2, -1), (-1, -1), colors.HexColor("#E8EEF5")),
    ]))
    elementos.append(tabla_activos)

    elementos.append(PageBreak())
    elementos.append(Paragraph("<b>FULL METAL — PADRÓN DE PERSONAL INACTIVO EN EL PERIODO</b>", styles["Title"]))
    elementos.append(Spacer(1, 10))
    if len(filas_inactivos) == 1:
        filas_inactivos.append(["Sin personal inactivo en este corte", "-", "-", "N/A", "-"])
    tabla_inact = Table(filas_inactivos, repeatRows=1)
    tabla_inact.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4A5568")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
    ]))
    elementos.append(tabla_inact)

    doc.build(elementos)
    return Response(
        content=buffer.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=nomina_full_metal_{fecha_inicio}_{fecha_fin}.pdf"}
    )

@app.get("/reportes/constancia-ubicacion-pdf")
def generar_pdf_ubicacion(
    fecha_inicio: str,
    fecha_fin: str,
    usuario_id: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=30, bottomMargin=30)
    styles = getSampleStyleSheet()
    elementos = []

    query_emp = db.query(UsuarioDB).filter(UsuarioDB.rol == "empleado")
    if usuario_id:
        query_emp = query_emp.filter(UsuarioDB.id == usuario_id)
    empleados = query_emp.all()

    elementos.append(Paragraph("<b>FULL METAL — CONSTANCIA DE UBICACIÓN Y ASISTENCIA LABORAL</b>", styles["Title"]))
    elementos.append(Paragraph(
        f"Periodo Consultado: {fecha_inicio} al {fecha_fin} | Documento oficial.",
        styles["Normal"]
    ))
    elementos.append(Spacer(1, 12))

    for emp in empleados:
        elementos.append(Paragraph(
            f"<b>Trabajador:</b> {emp.nombre} | <b>DUI:</b> {emp.dui} | <b>Cargo:</b> {emp.puesto or 'General'}",
            styles["Heading4"]
        ))
        registros = db.query(AsistenciaDB).filter(
            AsistenciaDB.usuario_id == emp.id,
            AsistenciaDB.fecha.between(fecha_inicio, fecha_fin)
        ).order_by(AsistenciaDB.fecha.asc()).all()

        filas = [["Fecha", "Horario Bloque 1", "Ubicación Principal", "Bloque 2 / Traslado", "Validado Por"]]
        if not registros:
            filas.append(["-", "Sin registros en el rango seleccionado", "-", "-", "-"])
        else:
            for r in registros:
                sup = db.query(UsuarioDB).filter(UsuarioDB.id == r.supervisor_id).first()
                sup_nombre = sup.nombre if sup else f"ID {r.supervisor_id}"
                b1 = f"{r.hora_entrada or '--'} - {r.hora_salida or '--'}"
                b2 = "-"
                if r.ubicacion_2:
                    b2 = f"{r.ubicacion_2} ({r.hora_entrada_2 or '--'} - {r.hora_salida_2 or '--'})"
                if r.justificado:
                    b2 += f" [Justificado: {r.nota_justificacion or 'Sí'}]"
                filas.append([r.fecha, b1, r.proyecto or "Obra General", b2, sup_nombre])

        tabla = Table(filas, repeatRows=1, colWidths=[65, 95, 130, 165, 85])
        tabla.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1B365D")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        elementos.append(tabla)
        elementos.append(Spacer(1, 14))

    doc.build(elementos)
    return Response(
        content=buffer.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=constancia_ubicacion_{fecha_inicio}_{fecha_fin}.pdf"}
    )
