$connStr = "Server=localhost;Database=ASSISTPE;User Id=ASSISTPE;Password=ASSISTPE;TrustServerCertificate=True;"
try {
    Write-Host "Tentando conectar ao SQL Server local (ASSISTPE)..."
    $conn = New-Object System.Data.SqlClient.SqlConnection($connStr)
    $conn.Open()
    Write-Host "Conexao estabelecida com sucesso! Versao do servidor: $($conn.ServerVersion)"

    $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    $sqlFile = Join-Path $scriptDir "schema_assistpe.sql"
    $sqlContent = Get-Content -Path $sqlFile -Raw -Encoding UTF8
    
    $batches = $sqlContent -split "(?im)^\s*GO\s*$"

    foreach ($batch in $batches) {
        $trimmed = $batch.Trim()
        if ($trimmed.Length -gt 0) {
            $cmd = $conn.CreateCommand()
            $cmd.CommandText = $trimmed
            $cmd.ExecuteNonQuery() | Out-Null
        }
    }

    Write-Host "Tabelas e carga inicial criadas com sucesso na base ASSISTPE!"

    $cmdCheck = $conn.CreateCommand()
    $cmdCheck.CommandText = "SELECT COUNT(*) FROM dbo.TB_TAREFAS"
    $totalTarefas = $cmdCheck.ExecuteScalar()
    Write-Host "Total de tarefas registradas no banco: $totalTarefas"

    $conn.Close()
} catch {
    Write-Error "Erro ao conectar ou executar no SQL Server: $_"
}
