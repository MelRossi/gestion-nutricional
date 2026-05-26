# 🥗 Sistema de Gestión Nutricional

Aplicación web desarrollada con Python, Streamlit y PostgreSQL para la gestión integral de pacientes, programas nutricionales, contratos, pagos, sesiones y seguimiento clínico.

El sistema fue diseñado para digitalizar y centralizar el flujo completo de trabajo de una consultoría nutricional: desde el registro de pacientes y la programación de consultas, hasta la generación automática de planes alimenticios en PDF y el seguimiento del progreso de cada usuario.

---

# ✨ Características principales

## 👥 Gestión de usuarios y roles

- Registro e inicio de sesión seguro.
- Sistema de autenticación con contraseñas hasheadas mediante bcrypt.
- Roles diferenciados:
  - Administrador
  - Nutricionista
  - Paciente
- Aprobación manual de nutricionistas por parte del administrador.

---

## 📋 Gestión de pacientes

- Alta y administración de pacientes.
- Ficha clínica completa.
- Historial nutricional.
- Visualización de contratos y sesiones.
- Seguimiento de evolución y progreso.

---

## 🗓️ Agenda y turnos

- Gestión de disponibilidad horaria.
- Reserva automática de sesiones.
- Reprogramación de turnos.
- Control de sesiones realizadas y pendientes.
- Bloqueo de horarios no laborales y feriados.

---

## 🧾 Programas y contratos

- Creación y administración de programas nutricionales.
- Contratos con fechas, sesiones y estados.
- Control de vencimientos.
- Gestión de reprogramaciones.

---

## 💳 Gestión de pagos

- Registro de pagos y cuotas.
- Control de estados:
  - Pendiente
  - Parcial
  - Pagado
  - Atrasado
- Historial de movimientos financieros.

---

## 🥦 Planes nutricionales inteligentes

- Creación de planes personalizados.
- Plantillas reutilizables.
- Generación automática de PDFs.
- Historial de versiones.
- Vista previa interactiva.
- Envío por email.

---

## 📈 Dashboard y métricas

- KPIs administrativos.
- Métricas de pacientes y contratos.
- Seguimiento de sesiones.
- Estado financiero general.

---

## 🎨 Interfaz moderna y responsive

- UI personalizada sobre Streamlit.
- Sidebar unificada.
- Componentes reutilizables.
- Sistema visual consistente.
- Experiencia optimizada para distintos roles.

---

# 🛠️ Tecnologías utilizadas

| Tecnología | Uso |
|---|---|
| Python | Backend principal |
| Streamlit | Frontend web |
| PostgreSQL | Base de datos |
| Pandas | Procesamiento de datos |
| ReportLab | Generación de PDFs |
| bcrypt | Seguridad y autenticación |
| Altair | Visualización de datos |

---

# 🧩 Arquitectura del proyecto

```bash
📦 gestion-nutricional
├── app.py
├── database.py
├── utils.py
├── components_ui.py
├── plan_utils.py
├── login.py
├── registro.py
├── portal.py
├── pages/
│   ├── 1_agenda.py
│   ├── 2_mis_pacientes.py
│   ├── 3_ficha_paciente.py
│   ├── 3b_cargar_plan.py
│   ├── 4_pagos.py
│   ├── 5_admin.py
│   ├── 5b_contratos.py
│   ├── 5c_disponibilidad.py
│   ├── 6_mi_progreso.py
│   └── 6c_elegir_sesion.py
└── styles.css
```

---

# 🔐 Funcionalidades destacadas

## Sistema multirol

Cada usuario accede únicamente a las funcionalidades correspondientes a su perfil.

---

## Gestión clínica integral

El sistema conecta:

- pacientes
- sesiones
- contratos
- pagos
- disponibilidad
- onboarding
- planes alimenticios

dentro de un único flujo centralizado.

---

## Generación automática de documentos

Los planes nutricionales se transforman automáticamente en documentos PDF listos para entregar o enviar por correo.

---

## Escalabilidad

La arquitectura modular permite agregar fácilmente:

- nuevas páginas
- métricas
- formularios
- dashboards
- automatizaciones
- integraciones externas

---

# 🧠 Aprendizajes y desafíos técnicos

Este proyecto implicó trabajar con:

- Arquitectura modular en Python.
- Manejo de estado en Streamlit.
- Diseño de bases de datos relacionales.
- Integración frontend/backend.
- Optimización de UX/UI.
- Generación dinámica de documentos.
- Control de permisos y sesiones.
- Lógica de negocio compleja.
- Validación y persistencia de datos.
- Gestión de workflows clínicos reales.
