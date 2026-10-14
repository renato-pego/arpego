-- =====================================================================
-- BANCO DE DADOS: ASSISTPE (SQL Server Local)
-- PROJETO: Assistente Pessoal (ARPego) - Base Forte Desktop
-- =====================================================================

USE ASSISTPE;
GO

-- 1. Tabela de Projetos
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'tb_projetos')
BEGIN
    CREATE TABLE tb_projetos (
        id INT IDENTITY(1,1) PRIMARY KEY,
        nome NVARCHAR(150) NOT NULL,
        sigla NVARCHAR(20),
        tipo NVARCHAR(50) DEFAULT 'Profissional'
    );
END
GO

-- 2. Tabela de Tarefas
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'tb_tarefas')
BEGIN
    CREATE TABLE tb_tarefas (
        id INT IDENTITY(1,1) PRIMARY KEY,
        codigo NVARCHAR(20) NOT NULL UNIQUE,
        id_projeto INT NULL,
        titulo NVARCHAR(255) NOT NULL,
        tipo NVARCHAR(50) DEFAULT 'Profissional',
        prioridade NVARCHAR(50) DEFAULT 'Média',
        status NVARCHAR(50) DEFAULT 'Não iniciada',
        observacoes NVARCHAR(MAX) NULL,
        data_conclusao NVARCHAR(50) NULL,
        recorrencia_dias INT DEFAULT 0,
        data_recorrencia NVARCHAR(50) NULL,
        sync_pendente BIT DEFAULT 0,
        ultima_atualizacao DATETIME DEFAULT GETDATE(),
        CONSTRAINT FK_tb_tarefas_projetos FOREIGN KEY (id_projeto) REFERENCES tb_projetos(id)
    );
END
GO

-- Adicionar colunas se tabela já existia sem elas
IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('tb_tarefas') AND name = 'sync_pendente')
BEGIN
    ALTER TABLE tb_tarefas ADD sync_pendente BIT DEFAULT 0;
END
GO

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('tb_tarefas') AND name = 'recorrencia_dias')
BEGIN
    ALTER TABLE tb_tarefas ADD recorrencia_dias INT DEFAULT 0;
END
GO

IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('tb_tarefas') AND name = 'data_recorrencia')
BEGIN
    ALTER TABLE tb_tarefas ADD data_recorrencia NVARCHAR(50) NULL;
END
GO

-- 3. Tabela de Histórico de Ações
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'tb_historico')
BEGIN
    CREATE TABLE tb_historico (
        id INT IDENTITY(1,1) PRIMARY KEY,
        codigo_tarefa NVARCHAR(20) NULL,
        descricao NVARCHAR(MAX) NOT NULL,
        data_hora DATETIME DEFAULT GETDATE()
    );
END
GO

-- 4. Tabela de Credenciais Criptografadas (Vault Zero-Knowledge)
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'tb_credenciais')
BEGIN
    CREATE TABLE tb_credenciais (
        id INT IDENTITY(1,1) PRIMARY KEY,
        categoria NVARCHAR(100) NOT NULL,
        titulo NVARCHAR(200) NOT NULL,
        usuario NVARCHAR(150) NULL,
        senha_cifrada NVARCHAR(MAX) NOT NULL,
        iv NVARCHAR(100) NOT NULL,
        salt NVARCHAR(100) NOT NULL,
        observacoes NVARCHAR(MAX) NULL,
        data_criacao DATETIME DEFAULT GETDATE()
    );
END
GO

-- 5. Tabela de Auditoria de Sincronização Local <-> Nuvem
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'tb_sync_log')
BEGIN
    CREATE TABLE tb_sync_log (
        id INT IDENTITY(1,1) PRIMARY KEY,
        data_hora DATETIME DEFAULT GETDATE(),
        direcao NVARCHAR(20) NOT NULL, -- 'PUSH', 'PULL', 'FULL'
        itens_enviados INT DEFAULT 0,
        itens_recebidos INT DEFAULT 0,
        status NVARCHAR(50) NOT NULL,  -- 'SUCESSO', 'ERRO'
        mensagem NVARCHAR(MAX) NULL
    );
END
GO

-- 6. Índices de Performance
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_tb_tarefas_codigo')
BEGIN
    CREATE INDEX IX_tb_tarefas_codigo ON tb_tarefas(codigo);
END
GO

IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_tb_tarefas_status')
BEGIN
    CREATE INDEX IX_tb_tarefas_status ON tb_tarefas(status);
END
GO

PRINT 'Esquema ASSISTPE criado/verificado com sucesso!';
GO
