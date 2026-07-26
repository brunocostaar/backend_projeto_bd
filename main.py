from fastapi import FastAPI

# Etapa 1: consultas em SQL puro
from routers.pessoa import router as pessoa_router
from routers.unidade import router as unidade_router
from routers.procedimento import router as procedimento_router
from routers.procedimento_realizado import router as procedimento_realizado_router
from routers.atendimento import router as atendimento_router
from routers.escala import router as escala_router

# Etapa 2: mesmas operações com ORM, sob /orm, mais as funcionalidades novas
from routers_orm.pessoa import router as orm_pessoa_router
from routers_orm.unidade import router as orm_unidade_router
from routers_orm.procedimento import router as orm_procedimento_router
from routers_orm.procedimento_realizado import router as orm_procedimento_realizado_router
from routers_orm.atendimento import router as orm_atendimento_router
from routers_orm.escala import router as orm_escala_router
from routers_orm.internacao import router as orm_internacao_router
from routers_orm.analiticas import router as orm_analiticas_router
from routers_orm.etapa2 import router as etapa2_router

app = FastAPI(
    title="Hospital API",
    description=(
        "API para gerenciamento hospitalar. As rotas na raiz são da Etapa 1 e "
        "usam SQL puro. As rotas sob /orm repetem as mesmas operações com o ORM "
        "do SQLAlchemy, e as sob /etapa2 expõem stored procedures, triggers, "
        "views e as consultas avançadas."
    ),
    version="2.0.0",
)

# Etapa 1
app.include_router(pessoa_router)
app.include_router(unidade_router)
app.include_router(procedimento_router)
app.include_router(procedimento_realizado_router)
app.include_router(atendimento_router)
app.include_router(escala_router)

# Etapa 2
app.include_router(orm_pessoa_router)
app.include_router(orm_unidade_router)
app.include_router(orm_procedimento_router)
app.include_router(orm_procedimento_realizado_router)
app.include_router(orm_atendimento_router)
app.include_router(orm_escala_router)
app.include_router(orm_internacao_router)
app.include_router(orm_analiticas_router)
app.include_router(etapa2_router)


@app.get("/")
def root():
    return {
        "message": "API Hospitalar rodando com sucesso! Acesse /docs para abrir a documentação interativa.",
        "etapa1": "SQL puro, rotas na raiz",
        "etapa2": "ORM em /orm, procedures, triggers e views em /etapa2",
    }
