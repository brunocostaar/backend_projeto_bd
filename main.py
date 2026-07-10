from fastapi import FastAPI
from routers.pessoa import router as pessoa_router
from routers.unidade import router as unidade_router
from routers.procedimento import router as procedimento_router
from routers.procedimento_realizado import router as procedimento_realizado_router
from routers.atendimento import router as atendimento_router
from routers.escala import router as escala_router

app = FastAPI(
    title="Hospital API",
    description="API para gerenciamento hospitalar construída usando FastAPI, Pydantic e SQL puro.",
    version="1.0.0"
)

# Registrando os endpoints
app.include_router(pessoa_router)
app.include_router(unidade_router)
app.include_router(procedimento_router)
app.include_router(procedimento_realizado_router)
app.include_router(atendimento_router)
app.include_router(escala_router)

@app.get("/")
def root():
    return {
        "message": "API Hospitalar rodando com sucesso! Acesse /docs para abrir a documentação interativa."
    }
