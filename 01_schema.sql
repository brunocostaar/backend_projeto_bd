-- Sistema de Gestão Hospitalar Dra. Yuska Maritan Brito
-- Etapa 1 - Schema (PostgreSQL)
--
-- Como executar:
--   psql -U postgres -f 01_schema.sql
-- O \c abaixo é um comando do psql: conecta no banco recém-criado
-- antes de criar as tabelas.

CREATE DATABASE hospital_universitario;
\c hospital_universitario

CREATE TABLE Pessoa(
    id_pessoa INTEGER GENERATED ALWAYS AS IDENTITY,
    CPF VARCHAR(11) UNIQUE NOT NULL,
    nome VARCHAR(100) NOT NULL,
    is_flamengo BOOLEAN DEFAULT FALSE,
    endereco VARCHAR(200),
    telefone VARCHAR(20),
    data_nascimento DATE NOT NULL,
    CONSTRAINT pk_pessoa PRIMARY KEY(id_pessoa)
);

CREATE TABLE Profissional(
    id_pessoa INTEGER PRIMARY KEY,
    CRM VARCHAR(30) UNIQUE NOT NULL,
    data_admissao DATE,
    especialidade VARCHAR(50) NOT NULL,
    CONSTRAINT ehPessoa FOREIGN KEY (id_pessoa)
        REFERENCES Pessoa(id_pessoa)
        ON DELETE CASCADE
        ON UPDATE CASCADE
);

CREATE TABLE Paciente(
    id_pessoa INTEGER PRIMARY KEY,
    numero_convenio VARCHAR(20) NOT NULL,
    grupo_sanguineo VARCHAR(3) NOT NULL,
    CONSTRAINT chk_grupo_sanguineo CHECK (grupo_sanguineo IN
        ('A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-')),
    CONSTRAINT ehPessoa FOREIGN KEY (id_pessoa)
        REFERENCES Pessoa(id_pessoa)
        ON DELETE CASCADE
        ON UPDATE CASCADE
);

-- Criada depois de Paciente, pois referencia Paciente
CREATE TABLE Alergia(
    alergia VARCHAR(30),
    id_pessoa INTEGER,
    PRIMARY KEY(alergia, id_pessoa),
    CONSTRAINT ehPaciente FOREIGN KEY (id_pessoa)
        REFERENCES Paciente(id_pessoa)
        ON DELETE CASCADE
        ON UPDATE CASCADE
);

CREATE TABLE Preceptor(
    id_profissional INTEGER PRIMARY KEY,
    titulacao VARCHAR(30) NOT NULL,
    CONSTRAINT ehProfissional FOREIGN KEY (id_profissional)
        REFERENCES Profissional(id_pessoa)
        ON DELETE CASCADE
        ON UPDATE CASCADE
);

CREATE TABLE Residente(
    id_profissional INTEGER PRIMARY KEY,
    ano_residencia CHAR(2) NOT NULL,
    CONSTRAINT chk_ano_residencia CHECK (ano_residencia IN ('R1', 'R2', 'R3')),
    CONSTRAINT ehProfissional FOREIGN KEY (id_profissional)
        REFERENCES Profissional(id_pessoa)
        ON DELETE CASCADE
        ON UPDATE CASCADE
);

CREATE TABLE Unidade(
    id_unidade INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nome VARCHAR(30) NOT NULL,
    tipo VARCHAR(30),
    capacidade_leitos INTEGER,
    CONSTRAINT chk_capacidade CHECK (capacidade_leitos >= 0)
);

CREATE TABLE Atendimento(
    id_atendimento INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    data_hora TIMESTAMP NOT NULL,
    duracao_minutos INTEGER,
    id_preceptor INTEGER NOT NULL,
    id_paciente INTEGER NOT NULL,
    id_residente INTEGER NOT NULL,
    CONSTRAINT chk_duracao CHECK (duracao_minutos > 0),
    CONSTRAINT temPreceptor FOREIGN KEY (id_preceptor)
        REFERENCES Preceptor(id_profissional)
        ON UPDATE CASCADE,
    CONSTRAINT temResidente FOREIGN KEY (id_residente)
        REFERENCES Residente(id_profissional)
        ON UPDATE CASCADE,
    CONSTRAINT temPaciente FOREIGN KEY (id_paciente)
        REFERENCES Paciente(id_pessoa)
        ON UPDATE CASCADE
);

CREATE TABLE Procedimento(
    id_procedimento INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    codigo INTEGER UNIQUE NOT NULL,
    nome VARCHAR(100) NOT NULL,
    tempo_medio_minutos INTEGER,
    nivel_risco VARCHAR(15),
    CONSTRAINT chk_nivel_risco CHECK (nivel_risco IN ('BAIXO', 'MEDIO', 'ALTO'))
);

CREATE TABLE Procedimento_Realizado(
    id_atendimento INTEGER NOT NULL,
    id_procedimento INTEGER NOT NULL,
    quantidade INTEGER NOT NULL DEFAULT 1,
    tempo_real_minutos INTEGER,
    observacao VARCHAR(1000),
    faturado BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY(id_atendimento, id_procedimento),
    CONSTRAINT chk_quantidade CHECK (quantidade > 0),
    CONSTRAINT chk_tempo_real CHECK (tempo_real_minutos > 0),
    CONSTRAINT temAtendimento FOREIGN KEY (id_atendimento)
        REFERENCES Atendimento(id_atendimento)
        ON DELETE CASCADE
        ON UPDATE CASCADE,
    CONSTRAINT temProcedimento FOREIGN KEY (id_procedimento)
        REFERENCES Procedimento(id_procedimento)
        ON UPDATE CASCADE
);

CREATE TABLE Escala(
    id_escala INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    dia_semana VARCHAR(15) NOT NULL,
    turno VARCHAR(15) NOT NULL,
    id_preceptor INTEGER NOT NULL,
    id_residente INTEGER NOT NULL,
    id_unidade INTEGER NOT NULL,
    CONSTRAINT chk_dia_semana CHECK (dia_semana IN
        ('segunda', 'terca', 'quarta', 'quinta', 'sexta', 'sabado', 'domingo')),
    CONSTRAINT chk_turno CHECK (turno IN ('manha', 'tarde', 'noite')),
    CONSTRAINT temPreceptor FOREIGN KEY (id_preceptor)
        REFERENCES Preceptor(id_profissional)
        ON DELETE CASCADE
        ON UPDATE CASCADE,
    CONSTRAINT temResidente FOREIGN KEY (id_residente)
        REFERENCES Residente(id_profissional)
        ON DELETE CASCADE
        ON UPDATE CASCADE,
    CONSTRAINT temUnidade FOREIGN KEY (id_unidade)
        REFERENCES Unidade(id_unidade)
        ON DELETE CASCADE
        ON UPDATE CASCADE,
    CONSTRAINT uq_escala UNIQUE(id_unidade, dia_semana, turno, id_residente)
);
