from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Configuração da URL de conexão do PostgreSQL
# Substitua os valores abaixo pelos dados do seu banco de dados local
SQLALCHEMY_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/projeto_bd"

# O Engine gerencia a conexão física com o banco de dados
engine = create_engine(SQLALCHEMY_DATABASE_URL)

# O SessionLocal será usado para instanciar sessões de banco de dados
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Função Dependency Injection (Injeção de Dependência)
# Ela abre uma sessão com o banco no início da requisição HTTP
# e garante que a conexão será fechada no final dela.
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
