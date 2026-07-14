from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db
from schemas.procedimento import ProcedimentoCreate, ProcedimentoRead

router = APIRouter(tags=["Procedimentos"])

# ==============================================================================
# 📋 SEÇÃO: PROCEDIMENTOS (CRUD Básico)
# ==============================================================================

@router.post("/procedimentos/", response_model=ProcedimentoRead, status_code=status.HTTP_201_CREATED)
def criar_procedimento(procedimento: ProcedimentoCreate, db: Session = Depends(get_db)):
    """
    Cadastra um novo procedimento no sistema usando SQL Puro.
    """
    try:
        query = text("""
            INSERT INTO procedimento (codigo, nome, tempo_medio_minutos, nivel_risco)
            VALUES (:codigo, :nome, :tempo_medio_minutos, :nivel_risco)
            RETURNING id_procedimento;
        """)
        result = db.execute(query, {
            "codigo": procedimento.codigo,
            "nome": procedimento.nome,
            "tempo_medio_minutos": procedimento.tempo_medio_minutos,
            "nivel_risco": procedimento.nivel_risco
        })
        id_procedimento = result.scalar()
        db.commit()

        return {
            "id_procedimento": id_procedimento,
            "codigo": procedimento.codigo,
            "nome": procedimento.nome,
            "tempo_medio_minutos": procedimento.tempo_medio_minutos,
            "nivel_risco": procedimento.nivel_risco
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erro ao cadastrar procedimento: {str(e)}"
        )


@router.get("/procedimentos/", response_model=list[ProcedimentoRead])
def listar_procedimentos(
    nome: str | None = None,
    nivel_risco: str | None = None,
    codigo: int | None = None,
    db: Session = Depends(get_db),
):
    """
    Retorna os procedimentos cadastrados usando SQL Puro.
    Aceita filtros opcionais: nome (busca parcial), nivel_risco e codigo (exatos).
    """
    sql = "SELECT id_procedimento, codigo, nome, tempo_medio_minutos, nivel_risco FROM procedimento"
    condicoes, params = [], {}
    if nome:
        condicoes.append("nome ILIKE :nome")
        params["nome"] = f"%{nome}%"
    if nivel_risco:
        condicoes.append("nivel_risco = :nivel_risco")
        params["nivel_risco"] = nivel_risco
    if codigo is not None:
        condicoes.append("codigo = :codigo")
        params["codigo"] = codigo
    if condicoes:
        sql += " WHERE " + " AND ".join(condicoes)
    sql += " ORDER BY nome;"

    result = db.execute(text(sql), params)
    return [dict(row._mapping) for row in result]


@router.get("/procedimentos/{id_procedimento}", response_model=ProcedimentoRead)
def buscar_procedimento(id_procedimento: int, db: Session = Depends(get_db)):
    """
    Busca um procedimento específico por ID usando SQL Puro.
    """
    query = text("""
        SELECT id_procedimento, codigo, nome, tempo_medio_minutos, nivel_risco 
        FROM procedimento 
        WHERE id_procedimento = :id_procedimento;
    """)
    result = db.execute(query, {"id_procedimento": id_procedimento}).first()
    
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Procedimento não encontrado."
        )
    return dict(result._mapping)


@router.put("/procedimentos/{id_procedimento}", response_model=ProcedimentoRead)
def atualizar_procedimento(id_procedimento: int, procedimento: ProcedimentoCreate, db: Session = Depends(get_db)):
    """
    Atualiza um procedimento por ID usando SQL Puro.
    """
    verificacao = db.execute(
        text("SELECT 1 FROM procedimento WHERE id_procedimento = :id;"), 
        {"id": id_procedimento}
    ).first()
    
    if not verificacao:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Procedimento não encontrado."
        )

    try:
        query = text("""
            UPDATE procedimento 
            SET codigo = :codigo, nome = :nome, 
                tempo_medio_minutos = :tempo_medio_minutos, nivel_risco = :nivel_risco
            WHERE id_procedimento = :id_procedimento;
        """)
        db.execute(query, {
            "id_procedimento": id_procedimento,
            "codigo": procedimento.codigo,
            "nome": procedimento.nome,
            "tempo_medio_minutos": procedimento.tempo_medio_minutos,
            "nivel_risco": procedimento.nivel_risco
        })
        db.commit()

        return {
            "id_procedimento": id_procedimento,
            "codigo": procedimento.codigo,
            "nome": procedimento.nome,
            "tempo_medio_minutos": procedimento.tempo_medio_minutos,
            "nivel_risco": procedimento.nivel_risco
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erro ao atualizar procedimento: {str(e)}"
        )


@router.delete("/procedimentos/{id_procedimento}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_procedimento(id_procedimento: int, db: Session = Depends(get_db)):
    """
    Remove um procedimento por ID usando SQL Puro.
    """
    verificacao = db.execute(
        text("SELECT 1 FROM procedimento WHERE id_procedimento = :id;"), 
        {"id": id_procedimento}
    ).first()
    
    if not verificacao:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Procedimento não encontrado."
        )

    try:
        query = text("DELETE FROM procedimento WHERE id_procedimento = :id_procedimento;")
        db.execute(query, {"id_procedimento": id_procedimento})
        db.commit()
        return None
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erro ao deletar procedimento: {str(e)}"
        )
