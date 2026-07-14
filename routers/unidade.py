from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db
from schemas.unidade import UnidadeCreate, UnidadeRead

router = APIRouter(prefix="/unidades", tags=["Unidades"])

@router.post("/", response_model=UnidadeRead, status_code=status.HTTP_201_CREATED)
def criar_unidade(unidade: UnidadeCreate, db: Session = Depends(get_db)):
    try:
        query = text("""
            INSERT INTO unidade (nome, tipo, capacidade_leitos)
            VALUES (:nome, :tipo, :capacidade_leitos)
            RETURNING id_unidade;
        """)
        
        result = db.execute(query, {
            "nome": unidade.nome,
            "tipo": unidade.tipo,
            "capacidade_leitos": unidade.capacidade_leitos
        })
        
        # Pega o ID gerado pelo banco
        id_unidade = result.scalar()
        db.commit()

        return {
            "id_unidade": id_unidade,
            "nome": unidade.nome,
            "tipo": unidade.tipo,
            "capacidade_leitos": unidade.capacidade_leitos
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erro ao criar unidade: {str(e)}"
        )


@router.get("/", response_model=list[UnidadeRead])
def listar_unidades(
    nome: str | None = None,
    tipo: str | None = None,
    db: Session = Depends(get_db),
):
    """
    Lista as unidades. Aceita filtros opcionais: nome e tipo (busca parcial).
    """
    sql = "SELECT id_unidade, nome, tipo, capacidade_leitos FROM unidade"
    condicoes, params = [], {}
    if nome:
        condicoes.append("nome ILIKE :nome")
        params["nome"] = f"%{nome}%"
    if tipo:
        condicoes.append("tipo ILIKE :tipo")
        params["tipo"] = f"%{tipo}%"
    if condicoes:
        sql += " WHERE " + " AND ".join(condicoes)
    sql += " ORDER BY nome;"

    result = db.execute(text(sql), params)

    # Converte os resultados para dicionários compatíveis com UnidadeRead
    return [dict(row._mapping) for row in result]


@router.get("/{id_unidade}", response_model=UnidadeRead)
def buscar_unidade(id_unidade: int, db: Session = Depends(get_db)):
    query = text("""
        SELECT id_unidade, nome, tipo, capacidade_leitos 
        FROM unidade 
        WHERE id_unidade = :id_unidade;
    """)
    result = db.execute(query, {"id_unidade": id_unidade}).first()
    
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unidade não encontrada."
        )
        
    return dict(result._mapping)


@router.put("/{id_unidade}", response_model=UnidadeRead)
def atualizar_unidade(id_unidade: int, unidade: UnidadeCreate, db: Session = Depends(get_db)):
    # Verifica se a unidade existe antes de tentar atualizar
    verificacao = db.execute(
        text("SELECT 1 FROM unidade WHERE id_unidade = :id;"), 
        {"id": id_unidade}
    ).first()
    
    if not verificacao:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unidade não encontrada."
        )

    try:
        query = text("""
            UPDATE unidade 
            SET nome = :nome, tipo = :tipo, capacidade_leitos = :capacidade_leitos
            WHERE id_unidade = :id_unidade;
        """)
        
        db.execute(query, {
            "id_unidade": id_unidade,
            "nome": unidade.nome,
            "tipo": unidade.tipo,
            "capacidade_leitos": unidade.capacidade_leitos
        })
        
        db.commit()

        return {
            "id_unidade": id_unidade,
            "nome": unidade.nome,
            "tipo": unidade.tipo,
            "capacidade_leitos": unidade.capacidade_leitos
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erro ao atualizar unidade: {str(e)}"
        )


@router.delete("/{id_unidade}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_unidade(id_unidade: int, db: Session = Depends(get_db)):
    verificacao = db.execute(
        text("SELECT 1 FROM unidade WHERE id_unidade = :id;"), 
        {"id": id_unidade}
    ).first()
    
    if not verificacao:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unidade não encontrada."
        )

    try:
        query = text("DELETE FROM unidade WHERE id_unidade = :id_unidade;")
        db.execute(query, {"id_unidade": id_unidade})
        db.commit()
        return None
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erro ao deletar unidade: {str(e)}"
        )
