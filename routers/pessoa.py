from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db
from schemas.pessoa import (
    PacienteCreate, PacienteRead,
    PreceptorCreate, PreceptorRead
)

router = APIRouter()

# ==============================================================================
# 🏥 SEÇÃO: PACIENTES (CRUD com Herança Física de 2 Níveis: Pessoa -> Paciente)
# ==============================================================================

@router.post("/pacientes/", response_model=PacienteRead, status_code=status.HTTP_201_CREATED)
def criar_paciente(paciente: PacienteCreate, db: Session = Depends(get_db)):
    """
    Cria um Paciente. Como Paciente herda de Pessoa no banco físico:
    1. Insere dados em 'pessoa' e captura o ID gerado.
    2. Insere dados em 'paciente' usando o mesmo ID.
    Tudo é feito dentro de uma transação (db.commit / db.rollback).
    """
    try:
        # Inserir dados na tabela PESSOA
        query_pessoa = text("""
            INSERT INTO pessoa (nome, CPF, data_nascimento, is_flamengo, telefone, endereco)
            VALUES (:nome, :cpf, :data_nascimento, :is_flamengo, :telefone, :endereco)
            RETURNING id_pessoa;
        """)
        
        result_pessoa = db.execute(query_pessoa, {
            "nome": paciente.nome,
            "cpf": paciente.CPF,
            "data_nascimento": paciente.data_nascimento,
            "is_flamengo": paciente.is_flamengo,
            "telefone": paciente.telefone,
            "endereco": paciente.endereco
        })
        
        # Pega o ID gerado pelo banco para a pessoa
        id_pessoa = result_pessoa.scalar()

        # 2. Inserir dados específicos na tabela PACIENTE
        query_paciente = text("""
            INSERT INTO paciente (id_pessoa, num_convenio, alergias, grupo_sanguineo)
            VALUES (:id_pessoa, :num_convenio, :alergias, :grupo_sanguineo);
        """)
        
        db.execute(query_paciente, {
            "id_pessoa": id_pessoa,
            "num_convenio": paciente.num_convenio,
            "alergias": paciente.alergias,
            "grupo_sanguineo": paciente.grupo_sanguineo
        })

        # Confirma as inserções no banco
        db.commit()

        # Retorna o paciente recém criado
        return {
            "id_pessoa": id_pessoa,
            "nome": paciente.nome,
            "CPF": paciente.CPF,
            "data_nascimento": paciente.data_nascimento,
            "is_flamengo": paciente.is_flamengo,
            "telefone": paciente.telefone,
            "endereco": paciente.endereco,
            "num_convenio": paciente.num_convenio,
            "alergias": paciente.alergias,
            "grupo_sanguineo": paciente.grupo_sanguineo
        }

    except Exception as e:
        db.rollback()  # Se qualquer um falhar, desfaz tudo
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erro ao cadastrar paciente. Detalhes: {str(e)}"
        )


@router.get("/pacientes/", response_model=list[PacienteRead])
def listar_pacientes(db: Session = Depends(get_db)):
    query = text("""
        SELECT pe.id_pessoa, pe.nome, pe.CPF, pe.data_nascimento, 
               pe.is_flamengo, pe.telefone, pe.endereco,
               pa.num_convenio, pa.alergias, pa.grupo_sanguineo
        FROM paciente pa
        INNER JOIN pessoa pe ON pa.id_pessoa = pe.id_pessoa;
    """)
    result = db.execute(query)
    
    # Converte os resultados para dicionários compatíveis com o PacienteRead
    return [dict(row._mapping) for row in result]


@router.get("/pacientes/{id_pessoa}", response_model=PacienteRead)
def buscar_paciente(id_pessoa: int, db: Session = Depends(get_db)):
    query = text("""
        SELECT pe.id_pessoa, pe.nome, pe.CPF, pe.data_nascimento, 
               pe.is_flamengo, pe.telefone, pe.endereco,
               pa.num_convenio, pa.alergias, pa.grupo_sanguineo
        FROM paciente pa
        INNER JOIN pessoa pe ON pa.id_pessoa = pe.id_pessoa
        WHERE pa.id_pessoa = :id_pessoa;
    """)
    result = db.execute(query, {"id_pessoa": id_pessoa}).first()
    
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Paciente não encontrado."
        )
        
    return dict(result._mapping)


@router.put("/pacientes/{id_pessoa}", response_model=PacienteRead)
def atualizar_paciente(id_pessoa: int, paciente: PacienteCreate, db: Session = Depends(get_db)):
    """
    Atualiza um Paciente. Atualiza a tabela 'pessoa' e depois 'paciente'.
    """
    # Verifica primeiro se o paciente existe
    verificacao = db.execute(text("SELECT 1 FROM paciente WHERE id_pessoa = :id"), {"id": id_pessoa}).first()
    if not verificacao:
        raise HTTPException(status_code=404, detail="Paciente não encontrado.")

    try:
        # 1. Atualiza dados na tabela PESSOA
        query_pessoa = text("""
            UPDATE pessoa 
            SET nome = :nome, CPF = :cpf, data_nascimento = :data_nascimento, 
                is_flamengo = :is_flamengo, telefone = :telefone, endereco = :endereco
            WHERE id_pessoa = :id_pessoa;
        """)
        db.execute(query_pessoa, {
            "id_pessoa": id_pessoa,
            "nome": paciente.nome,
            "cpf": paciente.CPF,
            "data_nascimento": paciente.data_nascimento,
            "is_flamengo": paciente.is_flamengo,
            "telefone": paciente.telefone,
            "endereco": paciente.endereco
        })

        # 2. Atualiza dados na tabela PACIENTE
        query_paciente = text("""
            UPDATE paciente 
            SET num_convenio = :num_convenio, alergias = :alergias, grupo_sanguineo = :grupo_sanguineo
            WHERE id_pessoa = :id_pessoa;
        """)
        db.execute(query_paciente, {
            "id_pessoa": id_pessoa,
            "num_convenio": paciente.num_convenio,
            "alergias": paciente.alergias,
            "grupo_sanguineo": paciente.grupo_sanguineo
        })

        db.commit()

        return {
            "id_pessoa": id_pessoa,
            "nome": paciente.nome,
            "CPF": paciente.CPF,
            "data_nascimento": paciente.data_nascimento,
            "is_flamengo": paciente.is_flamengo,
            "telefone": paciente.telefone,
            "endereco": paciente.endereco,
            "num_convenio": paciente.num_convenio,
            "alergias": paciente.alergias,
            "grupo_sanguineo": paciente.grupo_sanguineo
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erro ao atualizar paciente: {str(e)}"
        )


@router.delete("/pacientes/{id_pessoa}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_paciente(id_pessoa: int, db: Session = Depends(get_db)):
    """
    Remove um Paciente.
    No banco, é preciso remover primeiro da tabela filha (paciente) e depois da tabela pai (pessoa).
    """
    verificacao = db.execute(text("SELECT 1 FROM paciente WHERE id_pessoa = :id"), {"id": id_pessoa}).first()
    if not verificacao:
        raise HTTPException(status_code=404, detail="Paciente não encontrado.")

    try:
        # 1. Deletar da tabela filha PACIENTE
        db.execute(text("DELETE FROM paciente WHERE id_pessoa = :id_pessoa;"), {"id_pessoa": id_pessoa})
        
        # 2. Deletar da tabela pai PESSOA
        db.execute(text("DELETE FROM pessoa WHERE id_pessoa = :id_pessoa;"), {"id_pessoa": id_pessoa})

        db.commit()
        return None

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erro ao deletar paciente: {str(e)}"
        )


# ==============================================================================
# 🩺 SEÇÃO: PRECEPTORES (Herança de 3 Níveis: Pessoa -> Profissional -> Preceptor)
# ==============================================================================

@router.post("/preceptores/", response_model=PreceptorRead, status_code=status.HTTP_201_CREATED)
def criar_preceptor(preceptor: PreceptorCreate, db: Session = Depends(get_db)):
    """
    Exemplo de herança com 3 tabelas no banco de dados físico.
    Insere em PESSOA -> pega ID -> insere em PROFISSIONAL -> insere em PRECEPTOR.
    """
    try:
        # 1. Inserir em PESSOA
        query_pessoa = text("""
            INSERT INTO pessoa (nome, CPF, data_nascimento, is_flamengo, telefone, endereco)
            VALUES (:nome, :cpf, :data_nascimento, :is_flamengo, :telefone, :endereco)
            RETURNING id_pessoa;
        """)
        id_pessoa = db.execute(query_pessoa, {
            "nome": preceptor.nome,
            "cpf": preceptor.CPF,
            "data_nascimento": preceptor.data_nascimento,
            "is_flamengo": preceptor.is_flamengo,
            "telefone": preceptor.telefone,
            "endereco": preceptor.endereco
        }).scalar()

        # 2. Inserir em PROFISSIONAL usando o id_pessoa
        query_profissional = text("""
            INSERT INTO profissional (id_pessoa, CRM, data_admissao, especialidade)
            VALUES (:id_pessoa, :crm, :data_admissao, :especialidade);
        """)
        db.execute(query_profissional, {
            "id_pessoa": id_pessoa,
            "crm": preceptor.CRM,
            "data_admissao": preceptor.data_admissao,
            "especialidade": preceptor.especialidade
        })

        # 3. Inserir em PRECEPTOR usando o mesmo id_pessoa
        query_preceptor = text("""
            INSERT INTO preceptor (id_profissional, titulacao)
            VALUES (:id_pessoa, :titulacao);
        """)
        db.execute(query_preceptor, {
            "id_pessoa": id_pessoa,
            "titulacao": preceptor.titulacao
        })

        db.commit()

        # Retorna o objeto completo mesclando as três tabelas
        return {
            "id_pessoa": id_pessoa,
            "nome": preceptor.nome,
            "CPF": preceptor.CPF,
            "data_nascimento": preceptor.data_nascimento,
            "is_flamengo": preceptor.is_flamengo,
            "telefone": preceptor.telefone,
            "endereco": preceptor.endereco,
            "CRM": preceptor.CRM,
            "data_admissao": preceptor.data_admissao,
            "especialidade": preceptor.especialidade,
            "titulacao": preceptor.titulacao
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erro ao cadastrar preceptor: {str(e)}"
        )


@router.get("/preceptores/", response_model=list[PreceptorRead])
def listar_preceptores(db: Session = Depends(get_db)):
    """
    Retorna todos os Preceptores fazendo JOIN entre as 3 tabelas.
    """
    query = text("""
        SELECT pe.id_pessoa, pe.nome, pe.CPF, pe.data_nascimento, 
               pe.is_flamengo, pe.telefone, pe.endereco,
               pr.CRM, pr.data_admissao, pr.especialidade,
               pt.titulacao
        FROM preceptor pt
        INNER JOIN profissional pr ON pt.id_profissional = pr.id_pessoa
        INNER JOIN pessoa pe ON pr.id_pessoa = pe.id_pessoa;
    """)
    result = db.execute(query)
    return [dict(row._mapping) for row in result]
