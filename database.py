import psycopg2
import psycopg2.extras
import bcrypt
import os

def get_connection():
    # Soporta tanto .env local como st.secrets en Streamlit Cloud
    try:
        import streamlit as st
        db_url = st.secrets.get("DATABASE_URL") or os.getenv("DATABASE_URL")
    except Exception:
        from dotenv import load_dotenv
        load_dotenv()
        db_url = os.getenv("DATABASE_URL")

    if not db_url:
        raise ValueError("DATABASE_URL no configurada.")

    conn = psycopg2.connect(db_url)
    return conn

def run_query(sql, params=None):
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params or ())
        return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        raise e
    finally:
        conn.close()

def run_command(sql, params=None):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql, params or ())
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def hashear_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verificar_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except Exception:
        # Fallback para contraseñas en texto plano (datos de prueba)
        return password == hashed

def email_existe(email: str) -> bool:
    result = run_query("SELECT 1 FROM usuarios WHERE email=%s", (email,))
    return len(result) > 0
