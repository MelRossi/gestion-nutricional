import psycopg2
from dotenv import load_dotenv
import os

load_dotenv()

conn = psycopg2.connect(os.environ.get("DATABASE_URL"))
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM pacientes")
print("Pacientes en la base:", cur.fetchone()[0])
conn.close()
